import logging
import uuid
from requests.auth import HTTPBasicAuth
import requests
from flask import current_app

logger = logging.getLogger(__name__)


class XenditService:
    PAYMENT_METHOD_MAP = {
        "qris": ["QRIS"],
        "ewallet": ["OVO", "DANA", "LINKAJA", "SHOPEEPAY"],
        "bank_transfer": ["BCA"],
    }

    def __init__(self):
        self.api_key = current_app.config["XENDIT_SECRET_KEY"]
        self.base_url = current_app.config["XENDIT_BASE_URL"]
        self.store_name = current_app.config["STORE_NAME"]

    def create_invoice(self, order):
        payment_method = getattr(order.payment, "payment_method", None)
        if payment_method not in self.PAYMENT_METHOD_MAP:
            raise ValueError(
                f"Payment method tidak didukung: {payment_method!r}. "
                "Gunakan 'bank_transfer', 'qris', atau 'ewallet'."
            )

        external_id = f"order-{order.id}-{uuid.uuid4().hex}"
        # order.total_price already includes shipping_cost from checkout
        amount = int(order.total_price)
        payer_email = getattr(order.user, "email", None)
        if not payer_email:
            raise ValueError("User email tidak ditemukan untuk invoice Xendit.")

        payload = {
            "external_id": external_id,
            "amount": amount,
            "payer_email": payer_email,
            "description": f"Pembayaran Order #{order.id} - {self.store_name}",
            "should_send_email": False,
            "should_send_sms": False,
            "payment_methods": self.PAYMENT_METHOD_MAP[payment_method],
        }

        logger.info("[Xendit] Creating invoice for order %s", order.id)

        response = requests.post(
            self.base_url,
            auth=HTTPBasicAuth(self.api_key, ""),
            json=payload,
            timeout=15,
        )

        logger.info("[Xendit] Response %s for order %s", response.status_code, order.id)

        try:
            data = response.json()
        except ValueError:
            raise RuntimeError("Respons Xendit tidak valid: bukan JSON")

        if response.status_code == 422:
            error_code = data.get("error_code", "")
            if error_code == "DUPLICATE_EXTERNAL_ID":
                raise DuplicateInvoiceError(external_id)

        if not response.ok:
            error_code = data.get("error_code", "")
            message = data.get("message") or data.get("error") or "Unknown error"
            raise RuntimeError(
                f"Gagal membuat invoice Xendit [{error_code}]: {message}"
            )

        invoice_url = data.get("invoice_url")
        invoice_id = data.get("id")
        if not invoice_url or not invoice_id:
            raise RuntimeError("Respons Xendit tidak berisi invoice_url atau id")

        return {
            "invoice_url": invoice_url,
            "invoice_id": invoice_id,
            "external_id": external_id,
        }

    def get_invoice(self, invoice_id: str) -> dict:
        url = f"{self.base_url}/{invoice_id}"
        logger.info("[Xendit] Fetching existing invoice %s", invoice_id)
        response = requests.get(
            url,
            auth=HTTPBasicAuth(self.api_key, ""),
            timeout=15,
        )
        logger.info("[Xendit] Get invoice %s response %s", invoice_id, response.status_code)
        try:
            data = response.json()
        except ValueError:
            raise RuntimeError("Respons Xendit tidak valid: bukan JSON")

        if not response.ok:
            message = data.get("message") or data.get("error") or "Unknown error"
            raise RuntimeError(f"Gagal mengambil invoice Xendit: {message}")

        return {
            "invoice_url": data.get("invoice_url"),
            "invoice_id": data.get("id"),
        }


class DuplicateInvoiceError(Exception):
    def __init__(self, external_id: str):
        self.external_id = external_id
        super().__init__(f"Duplicate invoice for {external_id}")
