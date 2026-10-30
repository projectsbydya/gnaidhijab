import imghdr
import uuid
from datetime import datetime, timezone, timedelta
from werkzeug.security import check_password_hash
from werkzeug.utils import secure_filename
import bcrypt
import os
from urllib.parse import quote_plus
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app
from sqlalchemy.orm import selectinload
from models import db
from models.user import User
from models.product import Product
from models.product_image import ProductImage
from models.product_variant import ProductVariant
from models.product_discount import ProductDiscount
from models.shipping_discount import ShippingDiscount
from services.discount_validator import validate_product_discount
from services.product_validator import validate_product_urls
from services.shipping_discount_service import validate_shipping_discount_form
from models.video import Video
from models.order import Order, OrderItem
from models.cta_setting import CTASetting
from models.footer_setting import FooterSetting
from models.order_status_log import annotate_last_log
from routes.utils import admin_required, staff_or_admin_required
from extensions import limiter
from routes.order import _auto_cancel_if_expired
from utils.crypto import sanitize_html
from models import log_admin_action

admin_bp = Blueprint("admin", __name__)

def verify_password(password: str, stored_hash: str) -> bool:
    if stored_hash.startswith("$2b$") or stored_hash.startswith("$2a$"):
        return bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8"))
    return check_password_hash(stored_hash, password)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _generate_variant_sku(product_slug: str, color: str | None, size: str | None, index: int) -> str:
    """Generate unique SKU from product slug, color, size, and index."""
    parts = [product_slug]
    if color:
        parts.append(color.lower().replace(" ", "-"))
    if size:
        parts.append(size.lower().replace(" ", "-").replace("x", "x"))
    # Always add index to ensure uniqueness
    parts.append(str(index + 1))
    sku = "-".join(parts)
    return sku[:100]  # Limit to 100 chars


def _get_total_variants(*field_lists) -> int:
    """Calculate total variant rows from multiple field lists."""
    return max((len(lst) for lst in field_lists if lst), default=0)


_MIME_IMAGE_ALLOWED = {"png", "jpeg", "jpg", "webp"}
_MIME_VIDEO_ALLOWED = {"mp4"}  # only MP4 accepted


def _safe_ext(filename: str) -> str:
    """Return lowercased extension without leading dot, or empty string."""
    if "." not in filename:
        return ""
    return filename.rsplit(".", 1)[1].lower()


def _validate_image_mime(file) -> bool:
    """Peek at file header bytes to confirm it is a real image."""
    header = file.read(512)
    file.seek(0)
    detected = imghdr.what(None, h=header)
    return detected in _MIME_IMAGE_ALLOWED


def _validate_video_mime(file) -> bool:
    """Peek at file header bytes to confirm it is a real MP4."""
    header = file.read(8192)
    file.seek(0)
    # MP4 magic: bytes 4-7 must be 'ftyp', 'moov', or 'mdat'
    mp4_markers = [b"ftyp", b"moov", b"mdat"]
    return any(len(header) >= 8 and header[4:8] == m for m in mp4_markers)


def _uuid_filename(original_filename: str) -> str:
    """Return a UUID-based filename preserving the original extension."""
    ext = _safe_ext(secure_filename(original_filename))
    return f"{uuid.uuid4().hex}.{ext}" if ext else uuid.uuid4().hex


_ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}


def allowed_image(filename: str) -> bool:
    return _safe_ext(filename) in _ALLOWED_IMAGE_EXTENSIONS


_MAX_IMAGE_BYTES = 5 * 1024 * 1024
_MAX_VIDEO_BYTES = 50 * 1024 * 1024


_ALLOWED_VIDEO_EXTENSIONS = {"mp4"}


def allowed_video(filename: str) -> bool:
    return _safe_ext(filename) in _ALLOWED_VIDEO_EXTENSIONS


def save_video_file(file):
    if not file or not file.filename:
        return None
    original = secure_filename(file.filename)
    if not allowed_video(original):
        flash("Format video tidak didukung. Hanya file MP4 yang diizinkan.", "danger")
        return None
    if not _validate_video_mime(file):
        current_app.logger.warning("[Upload] MIME type tidak valid untuk video: %s", original)
        flash("File bukan video MP4 yang valid.", "danger")
        return None
    file.seek(0, 2)
    size = file.tell()
    file.seek(0)
    if size > _MAX_VIDEO_BYTES:
        flash("Ukuran video melebihi batas 50 MB.", "danger")
        return None
    upload_folder = current_app.config["VIDEO_UPLOAD_FOLDER"]
    os.makedirs(upload_folder, exist_ok=True)
    filename = _uuid_filename(original)
    file_path = os.path.join(upload_folder, filename)
    file.save(file_path)
    return os.path.relpath(file_path, os.path.join(current_app.root_path, "static")).replace("\\", "/")


def save_cta_image(file):
    """Save CTA background image, return relative path or None on error."""
    if not file or not file.filename:
        return None
    original = secure_filename(file.filename)
    if not allowed_image(original):
        flash("Format gambar tidak didukung. Gunakan PNG, JPG, JPEG, atau WEBP.", "danger")
        return None
    if not _validate_image_mime(file):
        current_app.logger.warning("[Upload] MIME type tidak valid untuk CTA image: %s", original)
        flash("File bukan gambar yang valid.", "danger")
        return None
    file.seek(0, 2)
    size = file.tell()
    file.seek(0)
    if size > _MAX_IMAGE_BYTES:
        flash("Ukuran gambar melebihi batas 5 MB.", "danger")
        return None
    upload_folder = current_app.config["CTA_UPLOAD_FOLDER"]
    os.makedirs(upload_folder, exist_ok=True)
    filename = _uuid_filename(original)
    file_path = os.path.join(upload_folder, filename)
    file.save(file_path)
    return os.path.relpath(file_path, os.path.join(current_app.root_path, "static")).replace("\\", "/")


def _save_variant_color_image(file) -> str | None:
    """Validate and save a variant color swatch image; return relative static path or None."""
    if not file or not file.filename:
        return None
    if not allowed_image(file.filename):
        flash("Format gambar warna tidak didukung. Gunakan PNG, JPG, JPEG, atau WEBP.", "danger")
        return None
    if not _validate_image_mime(file):
        flash("File gambar warna tidak valid.", "danger")
        return None
    file.seek(0, 2)
    size = file.tell()
    file.seek(0)
    if size > _MAX_IMAGE_BYTES:
        flash("Ukuran gambar warna melebihi batas 5 MB.", "danger")
        return None
    upload_folder = current_app.config["PRODUCT_UPLOAD_FOLDER"]
    os.makedirs(upload_folder, exist_ok=True)
    filename = _uuid_filename(file.filename)
    file_path = os.path.join(upload_folder, filename)
    file.save(file_path)
    return os.path.relpath(file_path, os.path.join(current_app.root_path, "static")).replace("\\", "/")


_WIB = timezone(timedelta(hours=7))


def _parse_discount_datetime(raw: str) -> datetime | None:
    """Parse datetime-local form value (WIB/UTC+7) and return naive UTC datetime."""
    if not raw:
        return None
    try:
        local_dt = datetime.strptime(raw, "%Y-%m-%dT%H:%M").replace(tzinfo=_WIB)
        return local_dt.astimezone(timezone.utc).replace(tzinfo=None)
    except ValueError:
        return None


def _save_product_discount(product) -> bool:
    """Validate then create, update, or delete ProductDiscount from submitted form.

    Returns True if the operation succeeded (or was skipped cleanly), False if
    validation failed. Validation errors are flashed to the admin.

    A discount is considered configured only when its value is greater than 0.
    When value <= 0 any existing discount is removed without validation.
    """
    discount_name = request.form.get("discount_name", "").strip() or None
    discount_type = request.form.get("discount_type", "fixed")
    discount_is_active = request.form.get("discount_is_active") == "on"
    raw_value = request.form.get("discount_value", "").strip()
    raw_starts = request.form.get("discount_starts_at", "")
    raw_ends = request.form.get("discount_ends_at", "")

    try:
        discount_value = int(float(raw_value or 0))
    except (ValueError, TypeError):
        discount_value = 0

    existing = product.discount

    # No discount configured: delete existing if any, skip validation
    if discount_value <= 0:
        if existing:
            db.session.delete(existing)
        return True

    # Validate before any DB write
    errors = validate_product_discount(
        {
            "discount_type": discount_type,
            "value": discount_value,
            "is_active": discount_is_active,
            "name": discount_name,
            "starts_at": raw_starts,
            "ends_at": raw_ends,
            "product_id": product.id,
        },
        require_product=False,
        exclude_discount_id=existing.id if existing else None,
    )

    if errors:
        for messages in errors.values():
            for msg in messages:
                flash(msg, "danger")
        return False

    starts_at = _parse_discount_datetime(raw_starts)
    ends_at = _parse_discount_datetime(raw_ends)

    if existing:
        existing.name = discount_name
        existing.discount_type = discount_type
        existing.value = discount_value
        existing.is_active = discount_is_active
        existing.starts_at = starts_at
        existing.ends_at = ends_at
    else:
        db.session.add(
            ProductDiscount(
                product_id=product.id,
                name=discount_name,
                discount_type=discount_type,
                value=discount_value,
                is_active=discount_is_active,
                starts_at=starts_at,
                ends_at=ends_at,
            )
        )

    return True


@admin_bp.route("/admin/login", methods=["GET", "POST"])
@limiter.limit("5 per 15 minutes", methods=["POST"])
def admin_login():
    if session.get("user_id") and session.get("user_role") in ("admin", "staff"):
        return redirect(url_for("admin.dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        account = User.query.filter(User.email == email, User.role.in_(["admin", "staff"])) .first()
        if account and verify_password(password, account.password):
            session["user_id"] = account.id
            session["user_name"] = account.name
            session["user_role"] = account.role
            
            # Audit log: admin login
            log_admin_action(
                user_id=account.id,
                user_email=account.email,
                action="LOGIN",
                entity_type="session",
                details=f"Role: {account.role}",
                request=request,
            )
            db.session.commit()
            
            flash("Login berhasil.", "success")
            return redirect(url_for("admin.dashboard"))
        flash("Email atau password tidak valid.", "danger")

    return render_template("admin/login.html")


@admin_bp.route("/admin/password-change", methods=["GET", "POST"])
@staff_or_admin_required
def password_change():
    user = User.query.get_or_404(session["user_id"])
    pending = session.get("pending_password_change")
    whatsapp_number = current_app.config["WHATSAPP_NUMBER"]
    wa_message = (
        f"Halo, saya ingin konfirmasi ganti password untuk akun {user.email}. "
        f"Peran: {user.role}. "
        "Mohon proses konfirmasi ganti password."
    )
    whatsapp_url = f"https://wa.me/{whatsapp_number}?text={quote_plus(wa_message)}"

    if request.method == "POST":
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not current_password or not new_password or not confirm_password:
            flash("Semua kolom password harus diisi.", "danger")
        elif not verify_password(current_password, user.password):
            flash("Password lama salah.", "danger")
        elif new_password != confirm_password:
            flash("Password baru dan konfirmasi tidak cocok.", "danger")
        else:
            session["pending_password_change"] = {
                "user_id": user.id,
                "new_password_hash": hash_password(new_password),
            }
            return render_template(
                "admin/password_change_confirm.html",
                whatsapp_url=whatsapp_url,
                whatsapp_number=whatsapp_number,
            )

    return render_template(
        "admin/password_change.html",
        whatsapp_url=whatsapp_url,
        whatsapp_number=whatsapp_number,
        pending=pending,
    )


@admin_bp.route("/admin/password-change/confirm", methods=["POST"])
@staff_or_admin_required
def password_change_confirm():
    pending = session.get("pending_password_change")
    if not pending or pending.get("user_id") != session.get("user_id"):
        flash("Tidak ada permintaan ganti password yang aktif.", "warning")
        return redirect(url_for("admin.password_change"))

    user = User.query.get_or_404(session["user_id"])
    user.password = pending["new_password_hash"]
    db.session.commit()
    session.pop("pending_password_change", None)
    flash("Password berhasil diubah setelah konfirmasi WhatsApp.", "success")
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/admin/dashboard")
@staff_or_admin_required
def dashboard():
    products = Product.query.order_by(Product.created_at.desc()).all()
    orders = Order.query.order_by(Order.created_at.desc()).limit(10).all()
    return render_template("admin/dashboard.html", products=products, orders=orders)


@admin_bp.route("/admin/products")
@staff_or_admin_required
def product_list():
    from sqlalchemy import func

    # Get all products with their total variant stock (sum of active variants)
    products = Product.query.order_by(Product.created_at.desc()).all()

    # Calculate total stock from active variants for each product
    variant_stock_totals = (
        db.session.query(
            ProductVariant.product_id,
            func.sum(ProductVariant.stock).label("total_stock")
        )
        .filter(ProductVariant.is_active == True)
        .group_by(ProductVariant.product_id)
        .all()
    )

    # Create lookup dict: product_id -> total_variant_stock
    stock_lookup = {p_id: int(total or 0) for p_id, total in variant_stock_totals}

    # Attach calculated stock to each product object (for template use)
    for product in products:
        product.total_variant_stock = stock_lookup.get(product.id, 0)

    return render_template("admin/product_list.html", products=products)


def _save_product_image(file) -> str | None:
    """Validate and save a product image file; return relative static path or None."""
    if not file or not file.filename:
        return None
    if not allowed_image(file.filename):
        flash("Format gambar tidak didukung. Gunakan PNG, JPG, JPEG, atau WEBP.", "danger")
        return None
    if not _validate_image_mime(file):
        flash("File bukan gambar yang valid. Pastikan file tidak diubah ekstensinya.", "danger")
        return None
    file.seek(0, 2)
    size = file.tell()
    file.seek(0)
    if size > _MAX_IMAGE_BYTES:
        flash("Ukuran gambar melebihi batas 5 MB.", "danger")
        return None
    upload_folder = current_app.config["PRODUCT_UPLOAD_FOLDER"]
    os.makedirs(upload_folder, exist_ok=True)
    filename = _uuid_filename(file.filename)
    file_path = os.path.join(upload_folder, filename)
    file.save(file_path)
    return os.path.relpath(file_path, os.path.join(current_app.root_path, "static")).replace("\\", "/")


@admin_bp.route("/admin/products/new", methods=["GET", "POST"])
@staff_or_admin_required
def product_create():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        price = int(request.form.get("price", 0))
        stock = int(request.form.get("stock", 0))
        weight = request.form.get("weight", "").strip()
        sizes = request.form.get("sizes", "").strip() or None
        description = request.form.get("description", "").strip()
        is_active = request.form.get("is_active") == "on"
        shopee_url = request.form.get("shopee_url", "").strip() or None

        # shopee_affiliate_url is internal-only: never read or persist it from
        # the admin form. Log a warning as defense-in-depth.
        if "shopee_affiliate_url" in request.form:
            current_app.logger.warning(
                "[Admin] shopee_affiliate_url submitted in create-product form; ignored"
            )

        # Dynamic accordion content (sanitized HTML)
        materials_care = sanitize_html(request.form.get("materials_care", ""))
        shipping_returns = sanitize_html(request.form.get("shipping_returns", ""))
        size_guide = sanitize_html(request.form.get("size_guide", ""))

        try:
            weight_val = float(weight) if weight else 0
        except ValueError:
            weight_val = 0

        url_errors = validate_product_urls({"shopee_url": shopee_url})
        if url_errors:
            for messages in url_errors.values():
                for msg in messages:
                    flash(msg, "danger")

        if url_errors or not name or price <= 0 or stock < 0 or weight_val <= 0:
            flash("Lengkapi data produk dengan benar. Berat harus lebih dari 0 gram.", "danger")
        else:
            product = Product(
                name=name,
                price=price,
                stock=stock,
                weight=weight_val,
                sizes=sizes,
                description=description,
                is_active=is_active,
                materials_care=materials_care,
                shipping_returns=shipping_returns,
                size_guide=size_guide,
                shopee_url=shopee_url,
            )
            db.session.add(product)
            db.session.flush()  # get product.id before slug generation
            product.generate_slug()

            # ── Multiple product images ──────────────────────────────────────
            uploaded_files = request.files.getlist("images")

            for idx, file in enumerate(uploaded_files):
                path = _save_product_image(file)
                if path:
                    db.session.add(ProductImage(
                        product_id=product.id,
                        image_path=path,
                        sort_order=idx,
                    ))

            # ── Variants (JSON-like repeating form fields) ───────────────────
            # Simplified: color, image, sku, stock, active only
            # price, size, weight always inherit from product base (stored null in DB)
            v_colors  = request.form.getlist("variant_color")
            v_skus    = request.form.getlist("variant_sku")
            v_stocks  = request.form.getlist("variant_stock")
            v_active  = request.form.getlist("variant_active")

            # Color image files (uploaded via file input)
            color_image_files = request.files.getlist("variant_color_image")

            # Calculate total variants safely (Color is required)
            total_variants = _get_total_variants(v_colors, v_skus, v_stocks, v_active)

            # Collect variants and their color images to associate after flush
            variant_color_images = []  # List of (variant_index, image_file)

            for i in range(total_variants):
                color = (v_colors[i] if i < len(v_colors) else "").strip() or None

                # Get or generate SKU (auto-generate with color + index)
                sku_input = (v_skus[i] if i < len(v_skus) else "").strip()
                if sku_input:
                    sku = sku_input
                else:
                    sku = _generate_variant_sku(product.slug, color, None, i)

                try:
                    v_stock = int(v_stocks[i]) if i < len(v_stocks) else 0
                except (ValueError, TypeError):
                    v_stock = 0

                is_active_v = (v_active[i] == "on") if i < len(v_active) else True

                # Create variant with null overrides - inherits from product via effective_* properties
                new_variant = ProductVariant(
                    product_id=product.id,
                    color=color,
                    size=None,      # Inherits from product.sizes
                    sku=sku,
                    stock=v_stock,
                    price=None,     # Inherits from product.price
                    weight=None,    # Inherits from product.weight
                    is_active=is_active_v,
                )
                db.session.add(new_variant)

                # Track color image for this variant (to save after flush gets ID)
                if i < len(color_image_files) and color_image_files[i] and color_image_files[i].filename:
                    variant_color_images.append((new_variant, color_image_files[i]))

            db.session.flush()  # Get IDs for new variants

            # Save color images and associate with variants
            for variant, img_file in variant_color_images:
                img_path = _save_variant_color_image(img_file)
                if img_path:
                    variant.color_image_path = img_path

            # ── Product discount (one-to-one) ──────────────────────────────
            if not _save_product_discount(product):
                db.session.rollback()
                return render_template("admin/product_form.html", product=None)

            db.session.commit()
            
            # Audit log: product created
            user = User.query.get(session.get("user_id"))
            log_admin_action(
                user_id=user.id,
                user_email=user.email,
                action="CREATE",
                entity_type="product",
                entity_id=product.id,
                entity_name=product.name,
                details=f"Created product with {total_variants} variants",
                request=request,
            )
            db.session.commit()
            
            flash("Produk berhasil ditambahkan.", "success")
            return redirect(url_for("admin.product_list"))

    return render_template("admin/product_form.html", product=None)


@admin_bp.route("/admin/products/<int:product_id>/edit", methods=["GET", "POST"])
@staff_or_admin_required
def product_edit(product_id):
    product = Product.query.get_or_404(product_id)
    if request.method == "POST":
        shopee_url = request.form.get("shopee_url", "").strip() or None

        # shopee_affiliate_url is internal-only: never read or persist it from
        # the admin form. Log a warning as defense-in-depth.
        if "shopee_affiliate_url" in request.form:
            current_app.logger.warning(
                "[Admin] shopee_affiliate_url submitted in edit-product form; ignored (product_id=%s)",
                product_id,
            )

        url_errors = validate_product_urls({"shopee_url": shopee_url})
        if url_errors:
            for messages in url_errors.values():
                for msg in messages:
                    flash(msg, "danger")
            return redirect(url_for("admin.product_edit", product_id=product_id))
        product.shopee_url = shopee_url

        old_name = product.name
        product.name = request.form.get("name", product.name).strip()
        product.price = int(request.form.get("price", product.price))
        product.stock = int(request.form.get("stock", product.stock))
        weight = request.form.get("weight", "").strip()
        product.sizes = request.form.get("sizes", "").strip() or None
        try:
            weight_val = float(weight) if weight else 0
        except ValueError:
            weight_val = 0
        if weight_val <= 0:
            flash("Berat produk harus lebih dari 0 gram.", "danger")
            return redirect(url_for("admin.product_edit", product_id=product_id))
        product.weight = weight_val
        product.description = request.form.get("description", product.description).strip()
        product.is_active = request.form.get("is_active") == "on"

        # Update dynamic accordion content (sanitized HTML)
        product.materials_care = sanitize_html(request.form.get("materials_care", ""))
        product.shipping_returns = sanitize_html(request.form.get("shipping_returns", ""))
        product.size_guide = sanitize_html(request.form.get("size_guide", ""))

        # Regenerate slug if name changed or slug is missing
        if product.name != old_name or not product.slug:
            product.generate_slug()

        # ── Add new images ───────────────────────────────────────────────────
        uploaded_files = request.files.getlist("images")

        next_order = max((img.sort_order for img in product.images), default=-1) + 1
        for idx, file in enumerate(uploaded_files):
            path = _save_product_image(file)
            if path:
                db.session.add(ProductImage(
                    product_id=product.id,
                    image_path=path,
                    sort_order=next_order + idx,
                ))

        # ── Delete images by ID ──────────────────────────────────────────────
        delete_image_ids = request.form.getlist("delete_image_id")
        for img_id in delete_image_ids:
            img = ProductImage.query.get(int(img_id))
            if img and img.product_id == product.id:
                db.session.delete(img)

        # ── Variants: update existing, add new, delete removed ───────────────
        # Simplified: color, image, sku, stock, active only
        # Existing variants preserve their override values (no data loss)
        # New variants inherit from product base via effective_* properties
        v_ids     = request.form.getlist("variant_id")
        v_colors  = request.form.getlist("variant_color")
        v_skus    = request.form.getlist("variant_sku")
        v_stocks  = request.form.getlist("variant_stock")
        v_active  = request.form.getlist("variant_active")

        # Color image files and deletion flags
        color_image_files = request.files.getlist("variant_color_image")
        delete_color_images = request.form.getlist("delete_variant_color_image")

        # Calculate total variants safely (Color is required)
        submitted_ids = set()   # will hold int IDs of ALL kept variants
        new_variants = []       # track new ORM objects until flush assigns IDs
        total_variants = _get_total_variants(v_ids, v_colors, v_skus, v_stocks, v_active)

        # Track color images for new variants (to save after flush)
        new_variant_color_images = []  # List of (variant_object, image_file)

        for i in range(total_variants):
            color = (v_colors[i] if i < len(v_colors) else "").strip() or None

            try:
                v_stock = int(v_stocks[i]) if i < len(v_stocks) else 0
            except (ValueError, TypeError):
                v_stock = 0

            is_active_v = (v_active[i] == "on") if i < len(v_active) else True

            # Get or generate SKU
            sku_input = (v_skus[i] if i < len(v_skus) else "").strip()
            if sku_input:
                sku = sku_input
            else:
                sku = _generate_variant_sku(product.slug, color, None, i)

            vid_raw = v_ids[i] if i < len(v_ids) else ""
            if vid_raw and vid_raw.isdigit():
                # Update existing variant - preserve override fields (price, size, weight)
                variant = ProductVariant.query.get(int(vid_raw))
                if variant and variant.product_id == product.id:
                    variant.color   = color
                    variant.sku     = sku
                    variant.stock   = v_stock
                    variant.is_active = is_active_v
                    # Note: price, size, weight are NOT modified - preserved from DB
                    submitted_ids.add(variant.id)

                    # Handle color image deletion for existing variant
                    if str(variant.id) in delete_color_images:
                        variant.color_image_path = None

                    # Handle new color image upload for existing variant
                    if i < len(color_image_files) and color_image_files[i] and color_image_files[i].filename:
                        img_path = _save_variant_color_image(color_image_files[i])
                        if img_path:
                            variant.color_image_path = img_path
            else:
                # Create new variant - inherits from product via effective_* properties
                new_v = ProductVariant(
                    product_id=product.id,
                    color=color,
                    size=None,      # Inherits from product.sizes
                    sku=sku,
                    stock=v_stock,
                    price=None,     # Inherits from product.price
                    weight=None,    # Inherits from product.weight
                    is_active=is_active_v,
                )
                db.session.add(new_v)
                new_variants.append(new_v)

                # Track color image for new variant (save after flush)
                if i < len(color_image_files) and color_image_files[i] and color_image_files[i].filename:
                    new_variant_color_images.append((new_v, color_image_files[i]))

        # Flush to assign IDs to new variants
        db.session.flush()

        # Save color images for new variants
        for variant, img_file in new_variant_color_images:
            img_path = _save_variant_color_image(img_file)
            if img_path:
                variant.color_image_path = img_path

        # Register new variant IDs so cleanup won't delete them
        for nv in new_variants:
            submitted_ids.add(nv.id)

        # Remove only variants whose ID is NOT in submitted_ids
        for variant in list(product.variants):
            if variant.id not in submitted_ids:
                db.session.delete(variant)

        # ── Product discount (one-to-one) ──────────────────────────────────
        if not _save_product_discount(product):
            db.session.rollback()
            return render_template("admin/product_form.html", product=product)

        db.session.commit()
        
        # Audit log: product updated
        user = User.query.get(session.get("user_id"))
        log_admin_action(
            user_id=user.id,
            user_email=user.email,
            action="UPDATE",
            entity_type="product",
            entity_id=product.id,
            entity_name=product.name,
            details=f"Updated product with {len(submitted_ids)} variants",
            request=request,
        )
        db.session.commit()
        
        flash("Produk berhasil diperbarui.", "success")
        return redirect(url_for("admin.product_list"))

    return render_template("admin/product_form.html", product=product)


@admin_bp.route("/admin/products/<int:product_id>/delete", methods=["POST"])
@staff_or_admin_required
def product_delete(product_id):
    product = Product.query.get_or_404(product_id)

    # Check if product has any order items
    product_name = product.name
    product_id = product.id
    
    if product.order_items:
        # If product has orders, deactivate instead of delete
        product.is_active = False
        db.session.commit()
        
        # Audit log: product deactivated
        user = User.query.get(session.get("user_id"))
        log_admin_action(
            user_id=user.id,
            user_email=user.email,
            action="UPDATE",
            entity_type="product",
            entity_id=product_id,
            entity_name=product_name,
            details="Deactivated product (has existing orders)",
            request=request,
        )
        db.session.commit()
        
        flash("Produk dinonaktifkan karena sudah ada dalam pesanan. Produk tidak akan ditampilkan di toko.", "warning")
    else:
        # If no orders, safe to delete
        db.session.delete(product)
        db.session.commit()
        
        # Audit log: product deleted
        user = User.query.get(session.get("user_id"))
        log_admin_action(
            user_id=user.id,
            user_email=user.email,
            action="DELETE",
            entity_type="product",
            entity_id=product_id,
            entity_name=product_name,
            details="Permanently deleted product",
            request=request,
        )
        db.session.commit()
        
        flash("Produk berhasil dihapus.", "success")

    return redirect(url_for("admin.product_list"))


@admin_bp.route("/admin/orders")
@admin_required
def order_list():
    orders = (
        Order.query
        .order_by(Order.created_at.desc())
        .options(
            selectinload(Order.user),
            selectinload(Order.payment),
        )
        .all()
    )
    return render_template("admin/order_list.html", orders=orders)


@admin_bp.route("/admin/orders/<int:order_id>")
@admin_required
def order_detail(order_id):
    order = Order.query.options(
        selectinload(Order.items).selectinload(OrderItem.product),
        selectinload(Order.items).selectinload(OrderItem.variant),
        selectinload(Order.payment),
        selectinload(Order.user),
    ).get_or_404(order_id)
    # Keep admin view consistent with customer view: expired pending orders
    # are cancelled and stock restored before rendering.
    _auto_cancel_if_expired(order)
    db.session.refresh(order)
    return render_template("admin/order_detail.html", order=order)



@admin_bp.route("/admin/orders/<int:order_id>/ship", methods=["POST"])
@admin_required
def ship_order(order_id):
    # Lock order to prevent concurrent webhook/payment handler from also
    # creating shipment for the same paid order.
    order = Order.query.with_for_update().get_or_404(order_id)
    if order.status != "paid":
        flash("Pesanan harus berstatus paid sebelum dapat dikirim.", "warning")
        return redirect(url_for("admin.order_detail", order_id=order.id))

    resi_number = request.form.get("resi_number", "").strip()
    if not resi_number:
        flash("Masukkan nomor resi terlebih dahulu.", "danger")
    else:
        order.resi_number = resi_number
        order.status = "shipped"
        admin_user = User.query.get(session.get("user_id"))
        changed_by = admin_user.email if admin_user else "admin"
        annotate_last_log(order, changed_by=changed_by, note=f"Shipped manually. Resi: {resi_number}")
        db.session.commit()
        flash("Nomor resi berhasil disimpan.", "success")
    return redirect(url_for("admin.order_detail", order_id=order.id))


@admin_bp.route("/admin/videos")
@admin_required
def video_list():
    videos = Video.query.order_by(Video.created_at.desc()).all()
    return render_template("admin/video_list.html", videos=videos)


@admin_bp.route("/admin/videos/new", methods=["GET", "POST"])
@admin_required
def video_create():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        is_active = request.form.get("is_active") == "on"
        video_file = None

        if 'video_file' in request.files:
            file = request.files['video_file']
            if file and file.filename:
                video_file = save_video_file(file)

        if not title or not video_file:
            flash("Judul dan file video wajib diisi. Pastikan file MP4 di bawah 50 MB.", "danger")
        else:
            video = Video(
                title=title,
                description=description,
                video_file=video_file,
                is_active=is_active,
            )
            db.session.add(video)
            db.session.commit()
            flash("Video berhasil ditambahkan.", "success")
            return redirect(url_for("admin.video_list"))

    return render_template("admin/video_form.html", video=None)


@admin_bp.route("/admin/videos/<int:video_id>/edit", methods=["GET", "POST"])
@admin_required
def video_edit(video_id):
    video = Video.query.get_or_404(video_id)
    if request.method == "POST":
        video.title = request.form.get("title", video.title).strip()
        video.description = request.form.get("description", video.description).strip()
        video.is_active = request.form.get("is_active") == "on"

        if 'video_file' in request.files:
            file = request.files['video_file']
            if file and file.filename:
                new_video_file = save_video_file(file)
                if new_video_file:
                    video.video_file = new_video_file

        db.session.commit()
        flash("Video berhasil diperbarui.", "success")
        return redirect(url_for("admin.video_list"))

    return render_template("admin/video_form.html", video=video)


@admin_bp.route("/admin/videos/<int:video_id>/delete", methods=["POST"])
@admin_required
def video_delete(video_id):
    video = Video.query.get_or_404(video_id)
    db.session.delete(video)
    db.session.commit()
    flash("Video berhasil dihapus.", "success")
    return redirect(url_for("admin.video_list"))


@admin_bp.route("/admin/cta")
@admin_required
def cta_list():
    cta_settings = CTASetting.query.order_by(CTASetting.created_at.desc()).all()
    return render_template("admin/cta_list.html", cta_settings=cta_settings)


@admin_bp.route("/admin/cta/new", methods=["GET", "POST"])
@admin_required
def cta_create():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        button_text = request.form.get("button_text", "").strip()
        button_link = request.form.get("button_link", "").strip()
        is_active = request.form.get("is_active") == "on"
        background_image = None

        # Handle image upload
        if 'background_image' in request.files:
            file = request.files['background_image']
            if file and file.filename:
                background_image = save_cta_image(file)

        if not title or not button_text:
            flash("Judul dan teks tombol wajib diisi.", "danger")
        else:
            # Deactivate other CTAs if this one is active
            if is_active:
                CTASetting.query.update({"is_active": False})

            cta = CTASetting(
                title=title,
                description=description,
                button_text=button_text,
                button_link=button_link or "/products",
                background_image=background_image,
                is_active=is_active,
            )
            db.session.add(cta)
            db.session.commit()
            flash("CTA berhasil ditambahkan.", "success")
            return redirect(url_for("admin.cta_list"))

    return render_template("admin/cta_form.html", cta=None)


@admin_bp.route("/admin/cta/<int:cta_id>/edit", methods=["GET", "POST"])
@admin_required
def cta_edit(cta_id):
    cta = CTASetting.query.get_or_404(cta_id)
    if request.method == "POST":
        cta.title = request.form.get("title", cta.title).strip()
        cta.description = request.form.get("description", cta.description).strip()
        cta.button_text = request.form.get("button_text", cta.button_text).strip()
        cta.button_link = request.form.get("button_link", cta.button_link).strip() or "/products"
        is_active = request.form.get("is_active") == "on"

        # Handle image upload
        if 'background_image' in request.files:
            file = request.files['background_image']
            if file and file.filename:
                saved_path = save_cta_image(file)
                if saved_path:
                    cta.background_image = saved_path

        # Handle activation - only one CTA should be active
        if is_active and not cta.is_active:
            CTASetting.query.filter(CTASetting.id != cta.id).update({"is_active": False})

        cta.is_active = is_active
        cta.updated_at = datetime.utcnow()
        db.session.commit()
        flash("CTA berhasil diperbarui.", "success")
        return redirect(url_for("admin.cta_list"))

    return render_template("admin/cta_form.html", cta=cta)


@admin_bp.route("/admin/cta/<int:cta_id>/delete", methods=["POST"])
@admin_required
def cta_delete(cta_id):
    cta = CTASetting.query.get_or_404(cta_id)
    db.session.delete(cta)
    db.session.commit()
    flash("CTA berhasil dihapus.", "success")
    return redirect(url_for("admin.cta_list"))


@admin_bp.route("/admin/footer", methods=["GET", "POST"])
@admin_required
def footer_edit():
    setting = FooterSetting.get()
    if request.method == "POST":
        setting.about_text = request.form.get("about_text", "").strip() or None
        setting.operating_hours = request.form.get("operating_hours", "").strip() or None
        setting.copyright_text = request.form.get("copyright_text", "").strip() or None
        setting.updated_at = datetime.utcnow()
        db.session.commit()
        flash("Footer berhasil diperbarui.", "success")
        return redirect(url_for("admin.footer_edit"))
    return render_template("admin/footer_form.html", setting=setting)


# ── Shipping Discount Admin ─────────────────────────────────────────────────


def _parse_shipping_discount_form():
    """Return a dict of cleaned form data for ShippingDiscount."""
    return {
        "name": request.form.get("name", "").strip() or None,
        "discount_type": request.form.get("discount_type", "").strip().lower() or None,
        "value": request.form.get("value", "").strip() or None,
        "minimum_order_amount": request.form.get("minimum_order_amount", "").strip() or None,
        "maximum_discount_amount": request.form.get("maximum_discount_amount", "").strip() or None,
        "starts_at": request.form.get("starts_at", "").strip() or None,
        "ends_at": request.form.get("ends_at", "").strip() or None,
        "is_active": request.form.get("is_active", "").strip() or None,
    }


@admin_bp.route("/admin/shipping-discounts")
@admin_required
def shipping_discount_list():
    discounts = ShippingDiscount.query.order_by(ShippingDiscount.created_at.desc()).all()
    return render_template("admin/shipping_discount_list.html", discounts=discounts)


@admin_bp.route("/admin/shipping-discounts/new", methods=["GET", "POST"])
@admin_required
def shipping_discount_create():
    if request.method == "POST":
        data = _parse_shipping_discount_form()
        errors = validate_shipping_discount_form(data)
        is_active = bool(data.get("is_active"))

        if errors:
            for field, messages in errors.items():
                for message in messages:
                    flash(f"{field}: {message}", "danger")
            return render_template("admin/shipping_discount_form.html", discount=None, form_data=data, is_active=is_active)

        discount = ShippingDiscount(
            name=data["name"],
            discount_type=data["discount_type"],
            value=int(data["value"]),
            minimum_order_amount=int(data["minimum_order_amount"] or 0),
            maximum_discount_amount=int(data["maximum_discount_amount"]) if data["maximum_discount_amount"] else None,
            is_active=is_active,
            starts_at=data["starts_at"],
            ends_at=data["ends_at"],
        )
        db.session.add(discount)
        db.session.commit()
        log_admin_action(
            session.get("user_id"),
            session.get("user_email", ""),
            "CREATE",
            "shipping_discount",
            entity_id=discount.id,
            entity_name=discount.name,
            request=request,
        )
        flash("Diskon ongkir berhasil ditambahkan.", "success")
        return redirect(url_for("admin.shipping_discount_list"))

    return render_template("admin/shipping_discount_form.html", discount=None)


@admin_bp.route("/admin/shipping-discounts/<int:discount_id>/edit", methods=["GET", "POST"])
@admin_required
def shipping_discount_edit(discount_id):
    discount = ShippingDiscount.query.get_or_404(discount_id)
    if request.method == "POST":
        data = _parse_shipping_discount_form()
        errors = validate_shipping_discount_form(data)
        is_active = bool(data.get("is_active"))

        if errors:
            for field, messages in errors.items():
                for message in messages:
                    flash(f"{field}: {message}", "danger")
            return render_template("admin/shipping_discount_form.html", discount=discount, form_data=data, is_active=is_active)

        discount.name = data["name"]
        discount.discount_type = data["discount_type"]
        discount.value = int(data["value"])
        discount.minimum_order_amount = int(data["minimum_order_amount"] or 0)
        discount.maximum_discount_amount = int(data["maximum_discount_amount"]) if data["maximum_discount_amount"] else None
        discount.is_active = is_active
        discount.starts_at = data["starts_at"]
        discount.ends_at = data["ends_at"]
        discount.updated_at = datetime.utcnow()
        db.session.commit()
        log_admin_action(
            session.get("user_id"),
            session.get("user_email", ""),
            "UPDATE",
            "shipping_discount",
            entity_id=discount.id,
            entity_name=discount.name,
            request=request,
        )
        flash("Diskon ongkir berhasil diperbarui.", "success")
        return redirect(url_for("admin.shipping_discount_list"))

    return render_template("admin/shipping_discount_form.html", discount=discount)


@admin_bp.route("/admin/shipping-discounts/<int:discount_id>/delete", methods=["POST"])
@admin_required
def shipping_discount_delete(discount_id):
    discount = ShippingDiscount.query.get_or_404(discount_id)
    db.session.delete(discount)
    db.session.commit()
    log_admin_action(
        session.get("user_id"),
        session.get("user_email", ""),
        "DELETE",
        "shipping_discount",
        entity_id=discount_id,
        entity_name=discount.name,
        request=request,
    )
    flash("Diskon ongkir berhasil dihapus.", "success")
    return redirect(url_for("admin.shipping_discount_list"))


@admin_bp.route("/admin/shipping-discounts/<int:discount_id>/toggle", methods=["POST"])
@admin_required
def shipping_discount_toggle(discount_id):
    discount = ShippingDiscount.query.get_or_404(discount_id)
    discount.is_active = not discount.is_active
    discount.updated_at = datetime.utcnow()
    db.session.commit()
    status = "diaktifkan" if discount.is_active else "dinonaktifkan"
    log_admin_action(
        session.get("user_id"),
        session.get("user_email", ""),
        "UPDATE",
        "shipping_discount",
        entity_id=discount.id,
        entity_name=discount.name,
        details=f"is_active={discount.is_active}",
        request=request,
    )
    flash(f"Diskon ongkir berhasil {status}.", "success")
    return redirect(url_for("admin.shipping_discount_list"))
