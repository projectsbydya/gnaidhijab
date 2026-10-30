from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app, Response
from sqlalchemy.orm import selectinload
from models import db
from models.order import Order, OrderItem
from models.product import Product
from models.product_variant import ProductVariant
from models.payment import Payment
from models.order_status_log import annotate_last_log
from routes.utils import login_required

orders_bp = Blueprint("orders", __name__)


def _restore_order_stock(order):
    """
    Restore product/variant stock for all items in a cancelled order.

    Callers must acquire a row lock on the order and verify that
    order.status is still 'pending' before calling this function. This
    prevents concurrent cancellation/expiry requests from restoring stock
    more than once.
    """
    for item in order.items:
        qty = item.quantity
        if item.variant_id:
            variant = ProductVariant.query.get(item.variant_id)
            if variant:
                variant.stock += qty
        else:
            product = Product.query.get(item.product_id)
            if product:
                product.stock += qty


def _auto_cancel_if_expired(order):
    """
    Cancel a pending order whose payment has expired, restoring stock.
    Returns True if the order was cancelled, False if no action was taken.
    Safe to call on any order — non-pending or non-expired orders are skipped.

    The order row is locked before reading status to prevent concurrent
    expiry/cancellation requests from restoring stock more than once.
    """
    from models.order_status_log import annotate_last_log

    # Re-fetch with a row lock so the status check is authoritative.
    # Eager load items and payment to avoid N+1 when restoring stock.
    locked_order = (
        Order.query
        .options(
            selectinload(Order.items).selectinload(OrderItem.product),
            selectinload(Order.items).selectinload(OrderItem.variant),
            selectinload(Order.payment),
        )
        .with_for_update()
        .get(order.id)
    )
    if locked_order is None or locked_order.status != "pending":
        return False

    # Continue with the locked instance for the rest of the operation.
    order = locked_order

    payment = order.payment
    now = datetime.utcnow()
    payment_expired = (
        payment is None
        or payment.status == "expired"
        or (order.payment_deadline is not None and now > order.payment_deadline)
    )
    if not payment_expired:
        return False

    _restore_order_stock(order)
    order.status = "cancelled"
    order.cancellation_reason = "expired_payment"
    if payment and payment.status != "expired":
        payment.status = "expired"
    annotate_last_log(order, changed_by="system", note="system_cancelled")
    db.session.commit()
    return True



def _get_user_order(order_id):
    return (
        Order.query
        .filter_by(id=order_id, user_id=session["user_id"])
        .options(
            selectinload(Order.items).selectinload(OrderItem.product),
            selectinload(Order.items).selectinload(OrderItem.variant),
            selectinload(Order.payment),
        )
        .first()
    )


def _format_timedelta(delta):
    if not delta or delta.total_seconds() <= 0:
        return "00:00"
    hours = int(delta.total_seconds() // 3600)
    minutes = int((delta.total_seconds() % 3600) // 60)
    return f"{hours} jam {minutes} menit"


@orders_bp.route("/orders")
@login_required
def order_history():
    orders = (
        Order.query
        .filter_by(user_id=session["user_id"])
        .order_by(Order.created_at.desc())
        .options(selectinload(Order.payment))
        .all()
    )
    for order in orders:
        if _auto_cancel_if_expired(order):
            pass  # session already committed inside helper
    return render_template("order_history.html", orders=orders)


@orders_bp.route("/orders/<int:order_id>")
@login_required
def order_detail(order_id):
    order = _get_user_order(order_id)
    if not order:
        return redirect(url_for("shop.index"))

    if not order.payment:
        payment = Payment(order_id=order.id, payment_method=None, status="unpaid")
        db.session.add(payment)
        db.session.flush()  # Flush to DB but don't commit yet

        # Re-check after flush — another request might have created it
        db.session.refresh(order)
        if order.payment and order.payment.id != payment.id:
            # Another request won the race, rollback our duplicate
            db.session.rollback()
        else:
            db.session.commit()

        order = _get_user_order(order_id)

    _auto_cancel_if_expired(order)
    db.session.refresh(order)

    now = datetime.utcnow()
    payment = order.payment
    time_left = None
    if order.status == "pending" and order.payment_deadline:
        time_left = _format_timedelta(order.payment_deadline - now)

    return render_template(
        "order_detail.html",
        order=order,
        time_left=time_left,
    )


@orders_bp.route("/orders/<int:order_id>/invoice")
@login_required
def order_invoice(order_id):
    user_id = session["user_id"]
    user_role = session.get("user_role", "user")

    order_query = Order.query.options(
        selectinload(Order.items).selectinload(OrderItem.product),
        selectinload(Order.items).selectinload(OrderItem.variant),
        selectinload(Order.payment),
    )

    if user_role in ("admin", "staff"):
        order = order_query.get_or_404(order_id)
    else:
        order = order_query.filter_by(id=order_id, user_id=user_id).first()
        if not order:
            flash("Invoice tidak ditemukan.", "danger")
            return redirect(url_for("orders.order_history"))

    try:
        import pdfkit
    except ImportError:
        flash("PDF generation tidak tersedia. Hubungi administrator.", "danger")
        return redirect(url_for("orders.order_detail", order_id=order_id))

    payment = order.payment
    status_map = {
        "paid": ("Paid", "paid"),
        "unpaid": ("Unpaid", "unpaid"),
        "pending_payment": ("Pending Payment", "unpaid"),
        "expired": ("Expired", "expired"),
    }
    raw_status = payment.status if payment else "unpaid"
    payment_status, badge_class = status_map.get(raw_status, (raw_status.capitalize(), "unpaid"))

    if order.status == "shipped":
        badge_class = "shipped"

    subtotal = sum(item.price * item.quantity for item in order.items)

    html_string = render_template(
        "invoice.html",
        order=order,
        payment=payment,
        payment_status=payment_status,
        badge_class=badge_class,
        subtotal=subtotal,
        store_name=current_app.config["STORE_NAME"],
        store_location=current_app.config.get("STORE_LOCATION", ""),
        generated_at=datetime.utcnow().strftime("%d %B %Y, %H:%M UTC"),
    )

    pdf_bytes = pdfkit.from_string(html_string, False, options={'enable-local-file-access': '', 'quiet': ''})

    filename = f"invoice-{order.id}.pdf"
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )



@orders_bp.route("/orders/<int:order_id>/cancel", methods=["POST"])
@login_required
def cancel_order(order_id):
    """
    Manual cancellation by the customer before payment is completed.
    Only pending orders can be cancelled. Stock is restored exactly once.
    """
    # Lock the order row so concurrent cancellation/expiry requests cannot
    # observe status == 'pending' simultaneously and restore stock twice.
    order = (
        Order.query
        .filter_by(id=order_id, user_id=session["user_id"])
        .with_for_update()
        .first()
    )
    if not order:
        flash("Order tidak ditemukan.", "danger")
        return redirect(url_for("orders.order_history"))

    if order.status != "pending":
        flash("Order ini tidak dapat dibatalkan.", "warning")
        return redirect(url_for("orders.order_detail", order_id=order.id))

    _restore_order_stock(order)
    order.status = "cancelled"
    order.cancellation_reason = "user_cancelled"
    if order.payment and order.payment.status != "expired":
        order.payment.status = "expired"
    annotate_last_log(order, changed_by="user", note="user_cancelled")
    db.session.commit()

    flash("Pesanan berhasil dibatalkan.", "success")
    return redirect(url_for("orders.order_detail", order_id=order.id))


@orders_bp.route("/orders/<int:order_id>/select-payment", methods=["POST"])
@login_required
def select_payment(order_id):
    # Lock order so it cannot be cancelled/expired while payment method is selected.
    order = (
        Order.query
        .filter_by(id=order_id, user_id=session["user_id"])
        .with_for_update()
        .first()
    )
    if not order or not order.is_pending:
        flash("Order tidak dapat diproses untuk pemilihan metode pembayaran.", "danger")
        return redirect(url_for("orders.order_detail", order_id=order_id))

    method = request.form.get("payment_method", "").strip()
    if method not in ["bank_transfer", "qris", "ewallet"]:
        flash("Metode pembayaran tidak valid.", "danger")
        return redirect(url_for("orders.order_detail", order_id=order.id))

    payment = order.payment or Payment(order_id=order.id, payment_method=method, status="unpaid")
    payment.payment_method = method
    payment.status = "pending_payment"
    payment.transaction_id = None
    order.payment_deadline = datetime.utcnow() + timedelta(hours=24)
    db.session.add(payment)
    db.session.commit()

    flash("Metode pembayaran berhasil disimpan. Ikuti instruksi pembayaran selanjutnya.", "success")
    return redirect(url_for("orders.order_detail", order_id=order.id))


