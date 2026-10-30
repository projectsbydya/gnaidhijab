"""
Reusable transactional email service.

All emails are sent as multipart/alternative (plain-text + HTML).
Call send_transactional_email() from any route — it logs and swallows
SMTP errors so a mail failure never breaks a user-facing request.
"""
import smtplib
import logging
import base64
from pathlib import Path
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from flask import current_app, render_template

logger = logging.getLogger(__name__)


def _mask(email: str) -> str:
    if not email or "@" not in email:
        return "***"
    local, domain = email.split("@", 1)
    return local[:2] + "***@" + domain


def _get_logo_data_uri(logo_filename: str) -> str | None:
    """Read logo file and return base64 data URI for email embedding."""
    if not logo_filename:
        return None
    try:
        base_dir = Path(current_app.root_path)
        logo_path = base_dir / "static" / logo_filename
        if not logo_path.exists():
            logger.warning("[Email] Logo file not found: %s", logo_path)
            return None

        ext = logo_path.suffix.lower()
        mime_type = "image/jpeg" if ext in (".jpg", ".jpeg") else "image/png" if ext == ".png" else "image/gif" if ext == ".gif" else "image/webp" if ext == ".webp" else "image/jpeg"

        with open(logo_path, "rb") as f:
            encoded = base64.b64encode(f.read()).decode("utf-8")
        return f"data:{mime_type};base64,{encoded}"
    except Exception as exc:
        logger.warning("[Email] Failed to encode logo: %s", exc)
        return None


def send_transactional_email(recipient: str, subject: str, template: str, **ctx) -> bool:
    """
    Render `templates/emails/<template>.html`, send as HTML + plain-text fallback.

    Returns True on success, False on failure (error is logged, never raised).
    `ctx` kwargs are passed as Jinja2 template variables.
    """
    cfg = current_app.config
    mail_user = cfg.get("MAIL_USER")
    mail_password = cfg.get("MAIL_PASSWORD")
    mail_server = cfg.get("MAIL_SERVER", "smtp.gmail.com")
    mail_port = int(cfg.get("MAIL_PORT", 587))
    store_name = cfg.get("STORE_NAME", "G.N.A.ID")

    if not mail_user or not mail_password:
        logger.error("[Email] SMTP credentials not configured — skipping email to %s", _mask(recipient))
        return False

    ctx.setdefault("store_name", store_name)
    store_url = cfg.get("STORE_URL", "https://gnaidhijab.shop")
    logo_filename = cfg.get("LOGO_FILENAME", "images/logo.jpg")
    ctx.setdefault("store_url", store_url)
    # Use base64 embedded logo for better email client compatibility
    ctx.setdefault("logo_url", _get_logo_data_uri(logo_filename))

    try:
        html_body = render_template(f"emails/{template}.html", **ctx)
    except Exception as exc:
        logger.error("[Email] Failed to render template emails/%s.html: %s", template, exc)
        return False

    msg = MIMEMultipart("alternative")
    msg["From"] = f"{store_name} <{mail_user}>"
    msg["To"] = recipient
    msg["Subject"] = subject

    plain_body = f"{subject}\n\nPlease view this email in an HTML-capable client.\n\n— {store_name}"
    msg.attach(MIMEText(plain_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        logger.info("[Email] Sending '%s' to %s", subject, _mask(recipient))
        with smtplib.SMTP(mail_server, mail_port, timeout=15) as server:
            server.starttls()
            server.login(mail_user, mail_password)
            server.send_message(msg)
        logger.info("[Email] Sent successfully to %s", _mask(recipient))
        return True
    except Exception as exc:
        logger.error("[Email] Failed to send to %s: %s", _mask(recipient), exc)
        return False


# ── Convenience wrappers ─────────────────────────────────────────────────────

def send_welcome_email(user) -> bool:
    store_name = current_app.config.get("STORE_NAME", "G.N.A.ID")
    return send_transactional_email(
        recipient=user.email,
        subject=f"Welcome to {store_name}!",
        template="welcome",
        user=user,
    )


def send_order_created_email(order, user) -> bool:
    store_name = current_app.config.get("STORE_NAME", "G.N.A.ID")
    subtotal = order.total_price - order.shipping_cost
    return send_transactional_email(
        recipient=user.email,
        subject=f"Order #{order.id} Confirmed — {store_name}",
        template="order_created",
        order=order,
        user=user,
        subtotal=subtotal,
    )


def send_payment_success_email(order, user) -> bool:
    store_name = current_app.config.get("STORE_NAME", "G.N.A.ID")
    subtotal = order.total_price - order.shipping_cost
    return send_transactional_email(
        recipient=user.email,
        subject=f"Payment Received for Order #{order.id} — {store_name}",
        template="payment_success",
        order=order,
        user=user,
        subtotal=subtotal,
        payment=order.payment,
    )


def send_shipment_email(order, user) -> bool:
    store_name = current_app.config.get("STORE_NAME", "G.N.A.ID")
    return send_transactional_email(
        recipient=user.email,
        subject=f"Your Order #{order.id} Has Been Shipped — {store_name}",
        template="shipment_sent",
        order=order,
        user=user,
    )


def send_otp_email(email: str, user_name: str, otp: str) -> bool:
    store_name = current_app.config.get("STORE_NAME", "G.N.A.ID")
    return send_transactional_email(
        recipient=email,
        subject=f"Reset Password {store_name} — OTP Code",
        template="otp_reset",
        user_name=user_name,
        otp=otp,
    )
