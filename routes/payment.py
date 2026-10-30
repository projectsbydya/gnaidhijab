from datetime import datetime
from flask import Blueprint, current_app, jsonify, request, session
from models import db
from models.order import Order
from models.payment import Payment
from routes.utils import login_required
from services.biteship_service import BiteshipService
from services.xendit_service import DuplicateInvoiceError, XenditService
from extensions import csrf
from services.email_service import send_payment_success_email, send_shipment_email
from models.order_status_log import annotate_last_log

payment_bp = Blueprint("payment", __name__)


@payment_bp.route("/payment-status/<int:order_id>", methods=["GET"])
@login_required
def payment_status(order_id):
    order = Order.query.get(order_id)
    if not order:
        return jsonify({"error": "Order tidak ditemukan."}), 404

    user_id = session.get("user_id")
    user_role = session.get("user_role")
    if order.user_id != user_id and user_role != "admin":
        return jsonify({"error": "Akses ditolak. Hanya pemilik order atau admin yang bisa melihat."}), 403

    payment = order.payment
    if not payment:
        return jsonify({"error": "Data pembayaran tidak ditemukan."}), 404

    # Note: order.total_price already includes shipping_cost from checkout
    return jsonify({
        "order_id": order.id,
        "payment_status": payment.status,
        "payment_method": payment.payment_method,
        "transaction_id": payment.transaction_id,
        "paid_at": payment.paid_at.isoformat() if payment.paid_at else None,
        "subtotal": order.total_price - order.shipping_cost,
        "shipping_cost": order.shipping_cost,
        "total_price": order.total_price,
    }), 200


@payment_bp.route("/api/create-payment/<int:order_id>", methods=["POST"])
@login_required
def api_create_xendit_payment(order_id):
    if current_app.config.get("MAINTENANCE_MODE"):
        msg = current_app.config.get("CHECKOUT_DISABLED_MESSAGE", "Checkout sedang tidak tersedia.")
        return jsonify({"error": msg}), 503

    order = Order.query.get(order_id)
    if not order:
        return jsonify({"error": "Order tidak ditemukan."}), 404

    user_id = session.get("user_id")
    user_role = session.get("user_role")
    if order.user_id != user_id and user_role != "admin":
        return jsonify({"error": "Akses ditolak."}), 403

    payment = order.payment
    if not payment:
        return jsonify({"error": "Data pembayaran tidak ditemukan."}), 404
    if payment.status != "pending_payment":
        return jsonify({"error": "Order tidak siap untuk membuat invoice Xendit."}), 400
    if payment.payment_method not in ("qris", "ewallet", "bank_transfer"):
        return jsonify({
            "error": "Metode pembayaran tidak valid. Gunakan bank_transfer, qris, atau ewallet."
        }), 400

    try:
        xendit = XenditService()

        if payment.transaction_id:
            # Invoice already created — return existing one to avoid DUPLICATE_EXTERNAL_ID
            try:
                invoice = xendit.get_invoice(payment.transaction_id)
            except Exception as exc:
                current_app.logger.exception("Gagal mengambil invoice Xendit yang ada: %s", exc)
                return jsonify({"error": "Gagal mengambil invoice yang sudah ada."}), 500
        else:
            try:
                invoice = xendit.create_invoice(order)
            except DuplicateInvoiceError:
                current_app.logger.warning(
                    "Duplicate invoice untuk order %s — transaction_id hilang di DB, fetch ulang.",
                    order_id,
                )
                return jsonify({"error": "Invoice sudah ada. Refresh halaman dan coba lagi."}), 409

        payment.transaction_id = invoice["invoice_id"]
        payment.invoice_url = invoice["invoice_url"]
        if invoice.get("external_id"):
            payment.external_id = invoice["external_id"]
        db.session.commit()
        return jsonify({"invoice_url": invoice["invoice_url"]}), 200
    except Exception as exc:
        current_app.logger.exception("Gagal membuat invoice Xendit untuk order %s: %s", order_id, exc)
        return jsonify({"error": str(exc)}), 500


@csrf.exempt
@payment_bp.route("/xendit/webhook", methods=["POST"])
def xendit_webhook():
    if not request.is_json:
        return jsonify({"error": "Content-Type harus application/json."}), 415

    xendit_token = request.headers.get("x-callback-token")
    expected_token = current_app.config.get("XENDIT_CALLBACK_TOKEN")
    if not xendit_token or xendit_token != expected_token:
        current_app.logger.warning("[Xendit Webhook] Token tidak valid atau tidak ada.")
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json(silent=True) or {}

    external_id = data.get("external_id")
    status = (data.get("status") or "").upper()

    if not external_id or not status:
        return jsonify({"error": "external_id dan status wajib diisi."}), 400

    payment = Payment.query.filter_by(external_id=external_id).with_for_update().first()
    if not payment:
        current_app.logger.warning("[Xendit Webhook] Payment dengan external_id %s tidak ditemukan.", external_id)
        return jsonify({"error": "Payment tidak ditemukan."}), 404

    order = Order.query.with_for_update().get(payment.order_id)
    if not order:
        current_app.logger.warning("[Xendit Webhook] Order untuk external_id %s tidak ditemukan.", external_id)
        return jsonify({"error": "Order tidak ditemukan."}), 404

    current_app.logger.info("[Xendit Webhook] Processing order_id: %s status: %s", order.id, status)

    amount = data.get("amount")
    # order.total_price already includes shipping_cost from checkout
    expected_amount = int(order.total_price)
    if amount is not None and int(amount) != expected_amount:
        current_app.logger.warning("[Xendit Webhook] Amount mismatch for order %s.", order.id)
        return jsonify({"error": "Amount mismatch"}), 400

    if payment.status == "paid":
        current_app.logger.info("[Xendit Webhook] Order %s already paid — skip.", order.id)
        return jsonify({"message": "Already processed"}), 200

    if status == "PAID":
        payment.status = "paid"
        payment.paid_at = datetime.utcnow()
        order.status = "paid"
        annotate_last_log(order, changed_by="xendit_webhook", note="Payment confirmed by Xendit")
        db.session.commit()
        current_app.logger.info("[Xendit Webhook] Order %s marked as paid.", order.id)

        send_payment_success_email(order, order.user)

        try:
            biteship = BiteshipService()
            shipment = biteship.create_shipment(order)
            order.resi_number = shipment["resi_number"]
            order.shipment_id = shipment["shipment_id"]
            order.status = "shipped"
            annotate_last_log(order, changed_by="biteship_system", note="Shipment created")
            db.session.commit()
            current_app.logger.info(
                "[Biteship] Shipment created for order %s: resi=%s id=%s",
                order.id, order.resi_number, order.shipment_id,
            )
            send_shipment_email(order, order.user)
        except Exception as ship_exc:
            current_app.logger.exception(
                "[Biteship] Gagal membuat shipment untuk order %s: %s",
                order.id, ship_exc,
            )
    elif status == "EXPIRED":
        payment.status = "expired"
        db.session.commit()
        current_app.logger.info("[Xendit Webhook] Order %s invoice expired.", order.id)
    elif status == "PENDING":
        current_app.logger.info("[Xendit Webhook] Order %s still pending — no action.", order.id)
    else:
        current_app.logger.warning(
            "[Xendit Webhook] Unknown status '%s' for order %s.",
            status,
            order.id
        )
        return jsonify({"error": f"Status Xendit tidak didukung: {status}"}), 400

    return jsonify({"message": "Webhook Xendit diproses."}), 200

@csrf.exempt
@payment_bp.route("/api/webhook/biteship", methods=["POST"])
def biteship_webhook():
    if not request.is_json:
        return jsonify({"error": "Content-Type harus application/json."}), 415

    body = request.get_json(silent=True) or {}

    # Biteship sends a verification POST without token headers during webhook
    # registration. These pings have no 'event' field in the body.
    # Respond 200 immediately so installation succeeds.
    if not body.get("event"):
        current_app.logger.info("[Biteship Webhook] Verification ping diterima.")
        return jsonify({"success": True}), 200

    # Runtime events always carry an 'event' field — enforce token verification.
    expected_token = current_app.config.get("BITESHIP_WEBHOOK_TOKEN")
    if expected_token:
        incoming_token = request.headers.get("x-biteship-token")
        if not incoming_token or incoming_token != expected_token:
            current_app.logger.warning("[Biteship Webhook] Token tidak valid atau tidak ada.")
            return jsonify({"error": "Unauthorized"}), 401
    else:
        current_app.logger.warning(
            "[Biteship Webhook] BITESHIP_WEBHOOK_TOKEN tidak dikonfigurasi — webhook tidak diverifikasi."
        )

    return jsonify({"success": True}), 200


@payment_bp.route("/tracking/<int:order_id>", methods=["GET"])
@login_required
def tracking(order_id):
    order = Order.query.get(order_id)
    if not order:
        return jsonify({"error": "Order tidak ditemukan."}), 404

    user_id = session.get("user_id")
    user_role = session.get("user_role")
    if order.user_id != user_id and user_role != "admin":
        return jsonify({"error": "Akses ditolak."}), 403

    if not order.resi_number:
        return jsonify({"error": "Resi belum tersedia untuk order ini."}), 404

    try:
        biteship = BiteshipService()
        result = biteship.track_shipment(order.resi_number, order.courier)
        return jsonify(result), 200
    except Exception as exc:
        current_app.logger.exception("[Biteship] Gagal tracking order %s: %s", order_id, exc)
        return jsonify({"error": "Gagal mengambil info tracking. Silakan coba lagi."}), 500
