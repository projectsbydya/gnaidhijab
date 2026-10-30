import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / '.env')

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY")
    if not SECRET_KEY:
        raise ValueError("SECRET_KEY tidak ditemukan di environment!")

    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL")
    if not SQLALCHEMY_DATABASE_URI:
        raise ValueError("DATABASE_URL wajib di-set di environment!")

    MAINTENANCE_MODE = os.getenv("MAINTENANCE_MODE", "false").lower() == "true"

    CHECKOUT_DISABLED_MESSAGE = os.getenv(
        "CHECKOUT_DISABLED_MESSAGE",
        "Checkout sedang tidak tersedia sementara kami melakukan pemeliharaan. "
        "Silakan kunjungi kembali sebentar lagi.",
    )
    CHECKOUT_DISABLED_BUTTON_TEXT = os.getenv(
        "CHECKOUT_DISABLED_BUTTON_TEXT",
        "Checkout Tidak Tersedia",
    )
    
    MAIL_SERVER = os.getenv("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT = int(os.getenv("MAIL_PORT", "587"))
    MAIL_USER = os.getenv("MAIL_USER")
    if not MAIL_USER:
        raise ValueError("MAIL_USER tidak ditemukan di environment!")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")
    if not MAIL_PASSWORD:
        raise ValueError("MAIL_PASSWORD tidak ditemukan di environment!")

    WHATSAPP_NUMBER = os.getenv("WHATSAPP_NUMBER")
    if not WHATSAPP_NUMBER:
        raise ValueError("WHATSAPP_NUMBER tidak ditemukan di environment!")
    WHATSAPP_TOOLTIP = os.getenv("WHATSAPP_TOOLTIP", "")  # optional

    STORE_NAME = os.getenv("STORE_NAME")
    if not STORE_NAME:
        raise ValueError("STORE_NAME tidak ditemukan di environment!")
    BRAND_NAME = os.getenv("BRAND_NAME") or STORE_NAME
    LOGO_FILENAME = os.getenv("LOGO_FILENAME", "")  # optional — leave empty to show text
    STORE_URL = os.getenv("STORE_URL", "https://gnaidhijab.shop")
    # Social media URLs (optional — leave empty to hide)
    SOCIAL_INSTAGRAM = os.getenv("SOCIAL_INSTAGRAM", "")
    SOCIAL_TIKTOK = os.getenv("SOCIAL_TIKTOK", "")
    SOCIAL_FACEBOOK = os.getenv("SOCIAL_FACEBOOK", "")
    SOCIAL_SHOPEE = os.getenv("SOCIAL_SHOPEE", "")

    # TikTok Pixel (optional — leave empty to disable)
    TIKTOK_PIXEL_ID = os.getenv("TIKTOK_PIXEL_ID", "")

    STORE_LOCATION = os.getenv("STORE_LOCATION")
    if not STORE_LOCATION:
        raise ValueError("STORE_LOCATION tidak ditemukan di environment!")
    XENDIT_SECRET_KEY = os.getenv("XENDIT_SECRET_KEY")
    if not XENDIT_SECRET_KEY:
        raise ValueError("XENDIT_SECRET_KEY tidak ditemukan di environment!")
    XENDIT_BASE_URL = os.getenv("XENDIT_BASE_URL", "https://api.xendit.co/v2/invoices")
    XENDIT_CALLBACK_TOKEN = os.getenv("XENDIT_CALLBACK_TOKEN")
    if not XENDIT_CALLBACK_TOKEN:
        raise ValueError("XENDIT_CALLBACK_TOKEN tidak ditemukan di environment!")

    BITESHIP_API_KEY = os.getenv("BITESHIP_API_KEY")
    if not BITESHIP_API_KEY:
        raise ValueError("BITESHIP_API_KEY tidak ditemukan di environment!")
    BITESHIP_WEBHOOK_TOKEN = os.getenv("BITESHIP_WEBHOOK_TOKEN")
    BITESHIP_BASE_URL = os.getenv("BITESHIP_BASE_URL", "https://api.biteship.com/v1")
    BITESHIP_ORIGIN_POSTAL = os.getenv("BITESHIP_ORIGIN_POSTAL")
    if not BITESHIP_ORIGIN_POSTAL:
        raise ValueError("BITESHIP_ORIGIN_POSTAL tidak ditemukan di environment!")
    BITESHIP_ORIGIN_ADDRESS = os.getenv("BITESHIP_ORIGIN_ADDRESS")
    if not BITESHIP_ORIGIN_ADDRESS:
        raise ValueError("BITESHIP_ORIGIN_ADDRESS tidak ditemukan di environment!")
    BITESHIP_COURIERS = os.getenv("BITESHIP_COURIERS")
    if not BITESHIP_COURIERS:
        raise ValueError("BITESHIP_COURIERS tidak ditemukan di environment!")

    # Upload limits (bytes)
    MAX_IMAGE_BYTES = int(os.getenv("MAX_IMAGE_BYTES", str(20 * 1024 * 1024)))  # Default 20 MB
    MAX_VIDEO_BYTES = int(os.getenv("MAX_VIDEO_BYTES", str(50 * 1024 * 1024)))  # Default 50 MB

    RATELIMIT_STORAGE_URI = os.getenv("RATELIMIT_STORAGE_URI", "memory://")
    SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true"
    REMEMBER_COOKIE_HTTPONLY = True

    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = 3600

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_recycle": 280,
        "pool_pre_ping": True,
    }

    PRODUCT_UPLOAD_FOLDER = os.getenv(
        "PRODUCT_UPLOAD_FOLDER",
        str(BASE_DIR / "static" / "uploads" / "products"),
    )
    VIDEO_UPLOAD_FOLDER = os.getenv(
        "VIDEO_UPLOAD_FOLDER",
        str(BASE_DIR / "static" / "videos"),
    )
    CTA_UPLOAD_FOLDER = os.getenv(
        "CTA_UPLOAD_FOLDER",
        str(BASE_DIR / "static" / "images" / "cta"),
    )
    ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
    ALLOWED_VIDEO_EXTENSIONS = {"mp4"}
    MAX_CONTENT_LENGTH = 52 * 1024 * 1024  # 52MB ceiling (50MB video + overhead)
