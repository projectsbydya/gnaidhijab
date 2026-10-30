import hashlib
import re
from datetime import datetime
from flask import Blueprint, jsonify, render_template, request, redirect, url_for, flash, session, current_app
from sqlalchemy import select
from models import db
from models.order import Order, OrderItem
from models.product import Product
from models.product_variant import ProductVariant
from models.user import User
from models.payment import Payment
from models.shipping_discount import ShippingDiscount
from services.biteship_service import BiteshipService
from services.email_service import send_order_created_email
from models.order_status_log import annotate_last_log
from services.cart_service import clear_db_cart
from services.discount_service import calculate_product_or_variant_discount
from services.shipping_discount_service import calculate_best_shipping_discount

_POSTAL_RE = re.compile(r'^\d{5}$')
_ADDRESS_MIN = 10
_ADDRESS_MAX = 500


def _cart_signature_from_session():
    cart = session.get("cart", {})
    parts = [f"{k}:{qty}" for k, qty in cart.items()]
    payload = "|".join(sorted(parts))
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _allowed_couriers():
    return {
        c.strip().lower()
        for c in current_app.config["BITESHIP_COURIERS"].split(",")
        if c.strip()
    }

checkout_bp = Blueprint("checkout", __name__)


def _get_cart_items():
    """
    Read cart from session and return (items, subtotal).
    Delegates to the canonical cart helper so key parsing is in one place.
    Items include: product, variant (or None), quantity, unit_price,
                   unit_weight, subtotal.
    """
    # Import moved inside function to avoid circular import with routes.cart
    import importlib
    cart_module = importlib.import_module('routes.cart')
    items, subtotal = cart_module._get_cart_items()
    # Strip invalid items — checkout only works with valid lines
    valid = [i for i in items if not i.get("invalid")]
    subtotal = sum(i["subtotal"] for i in valid)
    return valid, subtotal


def _get_pending_order_items(user_id):
    pending_order = (
        Order.query
        .filter(Order.user_id == user_id)
        .filter(Order.status == "pending")
        .order_by(Order.created_at.desc())
        .first()
    )
    if not pending_order:
        return []

    items = []
    for item in pending_order.items:
        if not item.product:
            continue
        variant = item.variant  # may be None for legacy orders
        unit_weight = (
            variant.effective_weight if variant else (item.product.weight or 0)
        )
        items.append({
            "product": item.product,
            "variant": variant,
            "quantity": item.quantity,
            "unit_price": item.price,
            "unit_weight": unit_weight,
            "subtotal": item.price * item.quantity,
        })
    return items


def _get_shipping_items(user_id):
    items, subtotal = _get_cart_items()
    if items:
        return items
    return _get_pending_order_items(user_id)


def _checkout_maintenance_guard():
    """Return a redirect response when checkout is disabled, else None."""
    if current_app.config.get("MAINTENANCE_MODE"):
        msg = current_app.config.get("CHECKOUT_DISABLED_MESSAGE", "Checkout sedang tidak tersedia.")
        if request.is_json or request.accept_mimetypes.best == "application/json":
            return jsonify({"error": msg}), 503
        flash(msg, "warning")
        return redirect(url_for("cart.cart"))
    return None


def _render_checkout_page():
    guard = _checkout_maintenance_guard()
    if guard:
        return guard

    if not session.get("user_id"):
        flash("Silakan login terlebih dahulu.", "warning")
        return redirect(url_for("auth.login"))

    items, subtotal = _get_cart_items()
    if not items:
        flash("Keranjang kosong. Tambahkan produk terlebih dahulu.", "warning")
        return redirect(url_for("shop.index"))

    user = User.query.get_or_404(session["user_id"])

    # Decrypt address for display
    from utils.crypto import AddressCrypto
    secret_key = current_app.config["SECRET_KEY"]
    address_crypto = AddressCrypto(secret_key)

    try:
        decrypted_address = address_crypto.decrypt(user.encrypted_address) if user.encrypted_address else user.address
    except Exception:
        decrypted_address = user.address

    try:
        decrypted_postal = address_crypto.decrypt(user.encrypted_postal_code) if user.encrypted_postal_code else None
    except Exception:
        decrypted_postal = None

    # Extract postal code from address if not stored separately
    if not decrypted_postal and decrypted_address:
        match = re.search(r'\b\d{5}\b', decrypted_address)
        if match:
            decrypted_postal = match.group(0)

    total_discount = sum(
        i.get("discount_savings", 0) * i["quantity"]
        for i in items
        if i.get("discount_applied")
    )

    return render_template(
        "checkout.html",
        items=items,
        subtotal=subtotal,
        total_discount=total_discount,
        user=user,
        decrypted_address=decrypted_address,
        decrypted_postal=decrypted_postal,
    )


@checkout_bp.route("/api/shipping-cost", methods=["POST"])
def shipping_cost_api():
    if not request.is_json:
        return jsonify({"error": "Content-Type harus application/json."}), 415
    if not session.get("user_id"):
        return jsonify({"error": "Silakan login terlebih dahulu."}), 401

    data = request.get_json(silent=True) or {}
    destination_postal = (data.get("destination_postal") or "").strip()

    if not destination_postal:
        return jsonify({"error": "destination_postal (kode pos tujuan) wajib diisi."}), 400

    items = _get_shipping_items(session["user_id"])
    if not items:
        current_app.logger.warning("Shipping cost request gagal: keranjang kosong untuk user_id=%s", session["user_id"])
        return jsonify({"error": "Keranjang kosong atau tidak ada pesanan pending."}), 400

    if not any((item.get("unit_weight") or 0) > 0 for item in items):
        current_app.logger.warning("Shipping cost request gagal: semua produk tidak memiliki berat untuk user_id=%s", session["user_id"])
        return jsonify({"error": "Berat produk tidak boleh nol. Pastikan setiap produk memiliki berat."}), 400

    origin_postal = current_app.config["BITESHIP_ORIGIN_POSTAL"]

    try:
        svc = BiteshipService()
        results = svc.get_rates(origin_postal, destination_postal, items)

        # Attach estimated shipping discount to each option for checkout display.
        # The final snapshot is still calculated and stored on order creation.
        subtotal = sum(i.get("subtotal", 0) for i in items)
        shipping_discounts = ShippingDiscount.query.all()
        for option in results:
            original_cost = int(option.get("price", 0))
            discount_result = calculate_best_shipping_discount(
                original_cost, subtotal, shipping_discounts
            )
            option["original_price"] = original_cost
            option["discount_amount"] = discount_result.savings
            option["final_price"] = discount_result.final_shipping_cost

        return jsonify({
            "origin_postal": origin_postal,
            "destination_postal": destination_postal,
            "options": results,
        }), 200
    except Exception as exc:
        current_app.logger.exception("Gagal mengambil ongkir Biteship: %s", exc)
        return jsonify({"error": "Gagal mengambil ongkir. Silakan coba lagi."}), 500


def _validate_checkout_data(data):
    errors = []
    allowed = _allowed_couriers()
    shipping_address = (data.get("shipping_address") or "").strip()
    courier = (data.get("courier") or "").strip().lower()
    service = (data.get("service") or "").strip()
    destination_postal = (data.get("destination_postal") or "").strip()

    if not shipping_address:
        errors.append("shipping_address wajib diisi.")
    elif len(shipping_address) < _ADDRESS_MIN:
        errors.append(f"shipping_address terlalu pendek (minimal {_ADDRESS_MIN} karakter).")
    elif len(shipping_address) > _ADDRESS_MAX:
        errors.append(f"shipping_address terlalu panjang (maksimal {_ADDRESS_MAX} karakter).")
    if not courier:
        errors.append("courier wajib diisi.")
    elif courier not in allowed:
        errors.append(f"courier tidak valid. Pilihan: {', '.join(sorted(allowed))}.")
    if not service:
        errors.append("service wajib diisi.")
    if not destination_postal:
        errors.append("destination_postal wajib diisi.")
    elif not _POSTAL_RE.match(destination_postal):
        errors.append("destination_postal harus 5 digit angka.")

    return errors


def _create_order_api(data):
    errors = _validate_checkout_data(data)
    if errors:
        return jsonify({"errors": errors}), 400

    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Silakan login terlebih dahulu."}), 401

    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User tidak ditemukan."}), 404

    shipping_address = data["shipping_address"].strip()
    courier = data["courier"].strip().lower()
    service = data["service"].strip()
    destination_postal = (data.get("destination_postal") or "").strip()

    ignored = [f for f in ("items", "user_id", "price", "shipping_cost", "total_price") if f in data]
    if ignored:
        current_app.logger.warning("[Checkout] Client sent ignored fields %s.", ignored)

    existing_order = Order.query.filter_by(user_id=user.id, status="pending").first()
    if existing_order:
        from routes.order import _auto_cancel_if_expired
        cancelled = _auto_cancel_if_expired(existing_order)
        if not cancelled:
            return jsonify({"error": "Masih ada checkout yang belum selesai."}), 409

    cart_items, _ = _get_cart_items()
    if not cart_items:
        return jsonify({"error": "Keranjang kosong."}), 400

    cart_sig = None
    try:
        cart_sig = _cart_signature_from_session()
        subtotal = 0
        order_items = []

        for cart_item in cart_items:
            product_id = cart_item["product"].id
            cart_variant = cart_item.get("variant")  # ProductVariant or None
            qty = int(cart_item["quantity"])

            if qty <= 0 or qty > 100:
                db.session.rollback()
                return jsonify({"error": "Quantity tidak valid."}), 400

            # ── Lock the product row ──────────────────────────────────────
            product = (
                db.session.execute(
                    select(Product)
                    .where(Product.id == product_id)
                    .with_for_update()
                )
                .scalar_one_or_none()
            )
            if not product:
                db.session.rollback()
                return jsonify({"error": f"Produk ID {product_id} tidak ditemukan."}), 404

            # Expire cached state so the next attribute access re-reads the
            # freshly-locked row from the database (prevents identity-map staleness).
            db.session.expire(product)

            if not product.is_active:
                db.session.rollback()
                return jsonify({"error": f"Produk '{product.name}' tidak lagi tersedia."}), 400

            if cart_variant is not None:
                # ── Variant path: lock and deduct the specific variant ────
                variant = (
                    db.session.execute(
                        select(ProductVariant)
                        .where(
                            ProductVariant.id == cart_variant.id,
                            ProductVariant.product_id == product_id,
                        )
                        .with_for_update()
                    )
                    .scalar_one_or_none()
                )
                if not variant or not variant.is_active:
                    db.session.rollback()
                    return jsonify({
                        "error": f"Varian '{cart_variant.display_name}' dari '{product.name}' "
                                 "tidak lagi tersedia."
                    }), 400

                # Expire to get fresh stock from the locked row.
                db.session.expire(variant)

                if variant.stock < qty:
                    db.session.rollback()
                    return jsonify({
                        "error": f"Stok varian '{variant.display_name}' dari '{product.name}' "
                                 f"tidak cukup (tersisa {variant.stock})."
                    }), 400

                variant.stock -= qty
                if variant.stock < 0:
                    db.session.rollback()
                    return jsonify({
                        "error": f"Stok varian '{variant.display_name}' dari '{product.name}' "
                                 "habis. Silakan perbarui keranjang Anda."
                    }), 400

                _disc = calculate_product_or_variant_discount(product, variant=variant)
                unit_price = _disc.final_price
                unit_weight = variant.effective_weight
                variant_id = variant.id
            else:
                # ── No-variant path ───────────────────────────────────────
                if product.stock < qty:
                    db.session.rollback()
                    return jsonify({
                        "error": f"Stok '{product.name}' tidak cukup (tersisa {product.stock})."
                    }), 400

                product.stock -= qty
                if product.stock < 0:
                    db.session.rollback()
                    return jsonify({
                        "error": f"Stok '{product.name}' habis. Silakan perbarui keranjang Anda."
                    }), 400

                _disc = calculate_product_or_variant_discount(product, variant=None)
                unit_price = _disc.final_price
                unit_weight = product.weight or 0
                variant_id = None

            subtotal += qty * unit_price
            order_items.append({
                "product_id": product_id,
                "variant_id": variant_id,
                "quantity": qty,
                "price": unit_price,
                "original_price": _disc.original_price,
                "discount_amount": _disc.savings,
                "unit_weight": unit_weight,
                "_product_obj": product,
            })

        # ── Verify shipping cost server-side ─────────────────────────────
        origin_postal = current_app.config["BITESHIP_ORIGIN_POSTAL"]
        # Build items list with variant-aware weight for Biteship
        checkout_items = [
            {
                "product": oi["_product_obj"],
                "quantity": oi["quantity"],
                "unit_weight": oi["unit_weight"],
            }
            for oi in order_items
        ]
        try:
            svc = BiteshipService()
            rates = svc.get_rates(origin_postal, destination_postal, checkout_items)
            matched = next(
                (
                    r for r in rates
                    if r["service"].lower() == service.lower()
                    and r["courier_code"].lower() == courier.lower()
                ),
                None,
            )
            if matched is None:
                db.session.rollback()
                return jsonify({
                    "error": "Layanan ongkir yang dipilih tidak valid atau tidak tersedia untuk rute ini."
                }), 400
            verified_shipping_cost = int(matched["price"])
        except Exception as exc:
            current_app.logger.exception("Gagal verifikasi ongkir saat checkout: %s", exc)
            db.session.rollback()
            return jsonify({"error": "Gagal memverifikasi ongkir. Silakan coba lagi."}), 500

        # ── Apply shipping discount ───────────────────────────────────────
        shipping_discounts = ShippingDiscount.query.all()
        shipping_discount_result = calculate_best_shipping_discount(
            verified_shipping_cost, subtotal, shipping_discounts
        )
        original_shipping_cost = verified_shipping_cost
        shipping_discount_amount = shipping_discount_result.savings
        final_shipping_cost = shipping_discount_result.final_shipping_cost

        # ── Final cart consistency check ──────────────────────────────────
        if _cart_signature_from_session() != cart_sig:
            db.session.rollback()
            return jsonify({"error": "Keranjang berubah selama checkout. Silakan ulangi."}), 409

        total_price = subtotal + final_shipping_cost

        # ── Idempotency guard ─────────────────────────────────────────────
        duplicate = Order.query.filter_by(
            user_id=user.id,
            total_price=total_price,
            courier=courier,
            service=service,
            status="pending",
        ).first()
        if duplicate:
            db.session.rollback()
            return jsonify({
                "error": "Order sudah pernah dibuat.",
                "order_id": duplicate.id,
                "order_url": url_for("orders.order_detail", order_id=duplicate.id),
            }), 409

        # ── Persist order ─────────────────────────────────────────────────
        order = Order(
            user_id=user.id,
            total_price=total_price,
            status="pending",
            shipping_address=shipping_address,
            courier=courier,
            service=service,
            shipping_cost=final_shipping_cost,
            original_shipping_cost=original_shipping_cost,
            shipping_discount_amount=shipping_discount_amount,
            destination_postal=destination_postal or None,
        )
        db.session.add(order)
        db.session.flush()
        # Annotate the 'pending' log created by the event listener on Order creation.
        annotate_last_log(order, changed_by="system", note="Order created")

        for item in order_items:
            db.session.add(
                OrderItem(
                    order_id=order.id,
                    product_id=item["product_id"],
                    variant_id=item["variant_id"],
                    quantity=item["quantity"],
                    price=item["price"],
                    original_price=item["original_price"],
                    discount_amount=item["discount_amount"],
                )
            )

        db.session.add(Payment(
            order_id=order.id,
            payment_method=None,
            status="unpaid",
        ))

        db.session.commit()

        # Clear cart AFTER successful commit
        session["cart"] = {}
        clear_db_cart(session.get("user_id"))

        send_order_created_email(order, user)

        return jsonify({
            "message": "Checkout berhasil",
            "order_id": order.id,
            "order_url": url_for("orders.order_detail", order_id=order.id),
            "total_price": total_price,
            "shipping_cost": final_shipping_cost,
            "original_shipping_cost": original_shipping_cost,
            "shipping_discount_amount": shipping_discount_amount,
        }), 201
    except Exception as exc:
        current_app.logger.exception("Gagal membuat checkout API: %s", exc)
        db.session.rollback()
        return jsonify({"error": "Checkout gagal. Coba lagi."}), 500


@checkout_bp.route("/api/couriers", methods=["GET"])
def couriers_api():
    couriers = [
        {"value": c.strip().lower(), "label": c.strip().upper()}
        for c in current_app.config["BITESHIP_COURIERS"].split(",")
        if c.strip()
    ]
    return jsonify({"couriers": couriers}), 200


@checkout_bp.route("/checkout", methods=["GET"])
def checkout():
    return _render_checkout_page()


@checkout_bp.route("/api/checkout", methods=["POST"])
def checkout_api():
    guard = _checkout_maintenance_guard()
    if guard:
        return guard

    if not request.is_json:
        return jsonify({"error": "Content-Type harus application/json."}), 415
    
    data = request.get_json(silent=True) or {}
    return _create_order_api(data)
