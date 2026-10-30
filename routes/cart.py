import time
from flask import Blueprint, session, redirect, url_for, request, flash, render_template
from models.product import Product
from models.product_variant import ProductVariant
from routes.utils import login_required
from services.cart_service import save_session_cart_to_db
from services.discount_service import calculate_product_or_variant_discount

cart_bp = Blueprint("cart", __name__)

_MAX_CART_QTY = 100          # Max quantity per distinct line
_MAX_CART_TOTAL_ITEMS = 20   # Max distinct lines in cart

# ---------------------------------------------------------------------------
# Cart key helpers
# ---------------------------------------------------------------------------
# Cart keys are stored as "pid:vid" where vid=0 means no-variant product.
# Legacy plain-integer keys ("123") are treated as stale and dropped silently.

def _make_cart_key(product_id: int, variant_id: int) -> str:
    return f"{product_id}:{variant_id}"


def _parse_cart_key(key: str):
    """Return (product_id, variant_id) int tuple, or None if key is invalid/legacy."""
    try:
        parts = str(key).split(":")
        if len(parts) != 2:
            return None
        return int(parts[0]), int(parts[1])
    except (ValueError, TypeError):
        return None


def _resolve_line(pid: int, vid: int, product=None, variant=None):
    """
    Load product (and optionally variant), validate both are active.
    Returns (product, variant_or_None, avail_stock, unit_price, unit_weight)
    or raises ValueError with a user-facing message on any invalid state.

    Callers may pass pre-loaded product/variant objects to avoid N+1 queries.
    """
    if product is None:
        product = Product.query.get(pid)
    if not product:
        raise ValueError(f"Produk ID {pid} tidak ditemukan.")
    if not product.is_active:
        raise ValueError(f"Produk '{product.name}' tidak lagi tersedia.")

    if vid == 0:
        # No-variant path - only check if any active variants exist
        requires_variant = any(v.is_active for v in product.variants)
        if requires_variant:
            raise ValueError(
                f"Produk '{product.name}' memiliki varian. Pilih varian terlebih dahulu."
            )
        discount_result = calculate_product_or_variant_discount(product, variant=None)
        return product, None, product.stock, discount_result.final_price, product.weight, discount_result

    # Variant path
    if variant is None:
        variant = ProductVariant.query.get(vid)
    if not variant or variant.product_id != pid:
        raise ValueError(f"Varian ID {vid} tidak ditemukan untuk produk ini.")
    if not variant.is_active:
        raise ValueError(
            f"Varian '{variant.display_name}' dari '{product.name}' tidak aktif."
        )
    discount_result = calculate_product_or_variant_discount(product, variant=variant)
    return product, variant, variant.stock, discount_result.final_price, variant.effective_weight, discount_result


# ---------------------------------------------------------------------------
# Internal read helpers (used by both cart routes and checkout)
# ---------------------------------------------------------------------------

def _get_cart_items():
    """
    Returns (items_list, total_int).
    Each item dict:
        cart_key, product, variant (or None), quantity, unit_price,
        unit_weight, subtotal, invalid (bool), invalid_reason (str)
    Invalid items are returned so the template can display them, but they
    are stripped from the cart and excluded from the total.

    Products and variants are loaded in bulk to avoid N+1 queries.
    """
    cart = session.get("cart", {})
    items = []
    total = 0
    stale_keys = []
    dirty = False

    # Parse all keys first and collect product/variant ids for bulk loading.
    parsed_entries = []
    product_ids = set()
    variant_ids = set()
    for cart_key, quantity in list(cart.items()):
        parsed = _parse_cart_key(cart_key)
        if parsed is None:
            stale_keys.append(cart_key)
            continue

        pid, vid = parsed
        try:
            qty = int(quantity)
        except (ValueError, TypeError):
            stale_keys.append(cart_key)
            continue

        if qty < 1:
            stale_keys.append(cart_key)
            continue

        parsed_entries.append((cart_key, pid, vid, qty))
        product_ids.add(pid)
        if vid:
            variant_ids.add(vid)

    # Bulk load all referenced products and variants in two queries.
    products = {
        p.id: p
        for p in Product.query.filter(Product.id.in_(product_ids)).all()
    } if product_ids else {}
    variants = {
        v.id: v
        for v in ProductVariant.query.filter(ProductVariant.id.in_(variant_ids)).all()
    } if variant_ids else {}

    for cart_key, pid, vid, qty in parsed_entries:
        if qty > _MAX_CART_QTY:
            qty = _MAX_CART_QTY
            cart[cart_key] = qty
            dirty = True

        try:
            product, variant, avail, unit_price, unit_weight, discount_result = _resolve_line(
                pid, vid, product=products.get(pid), variant=variants.get(vid)
            )
        except ValueError as exc:
            items.append({
                "cart_key": cart_key,
                "product": products.get(pid),
                "variant": None,
                "quantity": qty,
                "unit_price": 0,
                "unit_weight": 0,
                "subtotal": 0,
                "invalid": True,
                "invalid_reason": str(exc),
            })
            stale_keys.append(cart_key)
            continue

        subtotal = unit_price * qty
        total += subtotal
        items.append({
            "cart_key": cart_key,
            "product": product,
            "variant": variant,
            "quantity": qty,
            "unit_price": unit_price,
            "original_price": discount_result.original_price,
            "discount_applied": discount_result.is_applied,
            "discount_savings": discount_result.savings,
            "unit_weight": unit_weight,
            "subtotal": subtotal,
            "invalid": False,
        })

    if stale_keys:
        for k in stale_keys:
            cart.pop(k, None)
        dirty = True

    if dirty:
        session["cart"] = cart

    return items, total


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@cart_bp.route("/cart")
def view_cart():
    items, total = _get_cart_items()
    invalid_count = sum(1 for i in items if i.get("invalid"))
    if invalid_count:
        flash(
            f"{invalid_count} item di keranjang tidak lagi tersedia dan telah dihapus.",
            "warning",
        )
    # One-time payload for TikTok AddToCart event (consumed here)
    ttq_add = session.pop("ttq_add_to_cart", None)
    return render_template("cart.html", items=items, total=total, ttq_add=ttq_add)


@cart_bp.route("/cart/add/<int:product_id>", methods=["POST"])
@login_required
def add_to_cart(product_id):
    # Resolve variant_id from form (0 means no variant)
    try:
        variant_id = int(request.form.get("variant_id") or 0)
    except (ValueError, TypeError):
        variant_id = 0

    # Validate product/variant before touching the cart
    try:
        product, variant, avail, unit_price, _weight, _discount = _resolve_line(product_id, variant_id)
    except ValueError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("shop.product_detail", product_id=product_id))

    try:
        quantity = int(request.form.get("quantity", 1))
    except (ValueError, TypeError):
        quantity = 1
    if quantity < 1:
        quantity = 1

    cart = session.get("cart", {})
    cart_key = _make_cart_key(product_id, variant_id)

    # Global limit: max distinct lines
    if cart_key not in cart and len(cart) >= _MAX_CART_TOTAL_ITEMS:
        flash(
            f"Keranjang penuh (maksimal {_MAX_CART_TOTAL_ITEMS} item). "
            "Hapus item lain untuk menambahkan.",
            "danger",
        )
        return redirect(url_for("shop.product_detail", product_id=product_id))

    current_qty = cart.get(cart_key, 0)
    new_qty = current_qty + quantity

    label = f"'{product.name}'" + (f" ({variant.display_name})" if variant else "")

    if avail <= 0:
        flash(f"Stok {label} habis.", "danger")
        return redirect(url_for("shop.product_detail", product_id=product_id))

    if new_qty > avail:
        flash(
            f"Stok {label} tidak cukup. "
            f"Tersedia: {avail}, sudah di keranjang: {current_qty}.",
            "danger",
        )
        return redirect(url_for("shop.product_detail", product_id=product_id))

    if new_qty > _MAX_CART_QTY:
        flash(f"Maksimal {_MAX_CART_QTY} item per produk.", "danger")
        return redirect(url_for("shop.product_detail", product_id=product_id))

    cart[cart_key] = new_qty
    session["cart"] = cart
    save_session_cart_to_db(session.get("user_id"))

    # One-time payload for TikTok AddToCart event (consumed in cart view)
    session["ttq_add_to_cart"] = {
        "product_id": product_id,
        "variant_id": variant_id,
        "quantity": quantity,
        "unit_price": unit_price,  # already discounted
        "product_name": product.name,
        "variant_name": variant.display_name if variant else None,
        "ts": int(time.time() * 1000),
    }

    flash(f"{label} berhasil ditambahkan ke keranjang.", "success")
    return redirect(url_for("cart.view_cart"))


@cart_bp.route("/cart/update", methods=["POST"])
@login_required
def update_cart():
    cart = session.get("cart", {}).copy()
    warnings = []

    if len(cart) > _MAX_CART_TOTAL_ITEMS:
        flash(
            f"Keranjang melebihi batas maksimal {_MAX_CART_TOTAL_ITEMS} item. "
            "Silakan hapus beberapa item.",
            "danger",
        )
        return redirect(url_for("cart.view_cart"))

    for field, quantity in request.form.items():
        if not field.startswith("qty_"):
            continue
        # field format: qty_<cart_key> where cart_key uses '-' instead of ':' in HTML
        # We encode ':' as '-' in form field names to keep HTML valid (handled in template)
        raw_key = field[4:]  # strip "qty_"
        cart_key = raw_key.replace("-", ":")  # restore ':' separator

        parsed = _parse_cart_key(cart_key)
        if parsed is None:
            cart.pop(cart_key, None)
            continue

        pid, vid = parsed

        try:
            qty = int(quantity)
        except (ValueError, TypeError):
            qty = 0

        if qty < 1:
            cart.pop(cart_key, None)
            continue

        try:
            product, variant, avail, _price, _w, _disc = _resolve_line(pid, vid)
        except ValueError:
            cart.pop(cart_key, None)
            continue

        label = f"'{product.name}'" + (f" ({variant.display_name})" if variant else "")

        if avail <= 0:
            cart.pop(cart_key, None)
            warnings.append(f"{label} dihapus karena stok habis.")
            continue

        effective_max = min(avail, _MAX_CART_QTY)
        if qty > effective_max:
            cart[cart_key] = effective_max
            warnings.append(
                f"{label}: quantity disesuaikan ke {effective_max} (stok tersedia)."
            )
            continue

        cart[cart_key] = qty

    session["cart"] = cart
    session.modified = True
    save_session_cart_to_db(session.get("user_id"))

    for w in warnings:
        flash(w, "warning")
    flash("Keranjang berhasil diperbarui.", "success")
    return redirect(url_for("cart.view_cart"))


@cart_bp.route("/cart/remove", methods=["POST"])
@login_required
def remove_from_cart():
    cart_key = request.form.get("cart_key", "")
    cart = session.get("cart", {})
    cart.pop(cart_key, None)
    session["cart"] = cart
    save_session_cart_to_db(session.get("user_id"))
    flash("Item dihapus dari keranjang.", "success")
    return redirect(url_for("cart.view_cart"))
