import os
from datetime import datetime, timezone, timedelta
import bcrypt
import click
from flask import Flask, request, flash, redirect, render_template, url_for
from flask.cli import AppGroup
from flask_wtf.csrf import CSRFError
from extensions import csrf, limiter
from sqlalchemy import text
from werkzeug.exceptions import RequestEntityTooLarge
from config import Config
from models import db
from models.user import User
from models.product import Product
from models.footer_setting import FooterSetting
from routes.auth import auth_bp
from routes.shop import shop_bp
from routes.cart import cart_bp
from routes.checkout import checkout_bp
from routes.payment import payment_bp
from routes.order import orders_bp
from routes.admin import admin_bp
from routes.regions import regions_bp
from flask_migrate import Migrate, upgrade as upgrade_db, migrate as flask_migrate
from monitoring import init_monitoring
from services.affiliate_link_service import AffiliateLinkError, set_shopee_affiliate_url
from services.discount_service import calculate_product_discount


migrate = Migrate()
affiliate_cli = AppGroup("affiliate")


@affiliate_cli.command("set")
@click.argument("product_name")
@click.argument("affiliate_url")
def set_affiliate_link(product_name, affiliate_url):
    matches = Product.query.filter(Product.name == product_name).order_by(Product.id).all()
    if not matches:
        raise click.ClickException(f'Product with exact name "{product_name}" was not found.')
    if len(matches) > 1:
        products = "\n".join(
            f"  ID {product.id}: {product.name} (slug: {product.slug or '-'})"
            for product in matches
        )
        raise click.ClickException(
            f'Multiple products have the exact name "{product_name}"; no product was updated:\n{products}'
        )

    try:
        set_shopee_affiliate_url(matches[0], affiliate_url, updated_by="affiliate CLI")
        db.session.commit()
    except AffiliateLinkError as error:
        db.session.rollback()
        raise click.ClickException(error.message) from error

    click.echo(f'Affiliate URL updated for product "{matches[0].name}" (ID {matches[0].id}).')


def create_app():
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.from_object(Config)

    @app.before_request
    def maintenance_mode():
        if not app.config.get("MAINTENANCE_MODE"):
            return

        # Block only checkout / payment-initiation endpoints.
        # All storefront, cart, auth, admin, and static routes remain accessible.
        _CHECKOUT_PREFIXES = ("/checkout", "/api/checkout", "/api/shipping-cost", "/api/create-payment")
        if request.path.startswith(_CHECKOUT_PREFIXES):
            msg = app.config.get("CHECKOUT_DISABLED_MESSAGE", "Checkout sedang tidak tersedia.")
            # JSON callers (fetch / XHR)
            if request.accept_mimetypes.best == "application/json" or request.is_json:
                from flask import jsonify
                return jsonify({"error": msg}), 503
            flash(msg, "warning")
            return redirect(url_for("cart.view_cart"))

    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    limiter.init_app(app)

    app.register_blueprint(auth_bp)
    app.register_blueprint(shop_bp)
    app.register_blueprint(cart_bp)
    app.register_blueprint(checkout_bp)
    app.register_blueprint(payment_bp)
    app.register_blueprint(orders_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(regions_bp)

    _WIB = timezone(timedelta(hours=7))

    @app.template_filter("utc_to_wib")
    def utc_to_wib(dt):
        """Format a naive UTC datetime as a WIB datetime-local string (YYYY-MM-DDTHH:MM)."""
        if dt is None:
            return ""
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(_WIB).strftime("%Y-%m-%dT%H:%M")

    _css_path = os.path.join(app.static_folder, "css", "style.css")

    @app.context_processor
    def inject_globals():
        try:
            footer = FooterSetting.get()
        except Exception:
            footer = None
        try:
            css_v = int(os.path.getmtime(_css_path))
        except OSError:
            css_v = 1
        return {
            "year": datetime.utcnow().year,
            "config": app.config,
            "footer": footer,
            "calculate_product_discount": calculate_product_discount,
            "css_version": css_v,
        }

    _CDN = "https://cdn.jsdelivr.net"
    _GFONTS = "https://fonts.googleapis.com"
    _GSTATIC = "https://fonts.gstatic.com"
    _CLOUDFLARE = "https://static.cloudflareinsights.com"
    _TIKTOK = "https://analytics.tiktok.com"

    @app.after_request
    def set_security_headers(response):
        csp_parts = [
            "default-src 'self'",
            f"script-src 'self' 'unsafe-inline' {_CDN} {_CLOUDFLARE} {_TIKTOK}",
            f"style-src 'self' 'unsafe-inline' {_CDN} {_GFONTS}",
            f"font-src 'self' {_CDN} {_GSTATIC}",
            f"img-src 'self' data: https:",
            f"connect-src 'self' {_CDN} {_TIKTOK}",
            "frame-ancestors 'none'",
            "base-uri 'self'",
            "form-action 'self'",
        ]
        response.headers["Content-Security-Policy"] = "; ".join(csp_parts)
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "geolocation=(), microphone=(), camera=()"
        )
        if app.config.get("SESSION_COOKIE_SECURE"):
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        return response

    @app.template_filter('regex_search')
    def regex_search_filter(text, pattern):
        """Extract text matching regex pattern."""
        if not text:
            return ''
        import re
        match = re.search(pattern, text)
        return match.group(0) if match else ''

    @app.template_filter('censor')
    def censor_filter(text):
        """Censor text by masking middle characters with asterisks."""
        if not text:
            return ''
        text = str(text)
        if len(text) <= 2:
            return text
        if len(text) <= 4:
            return text[0] + '*' * (len(text) - 1)
        # Show first 2 and last 2 chars, mask the middle
        return text[:2] + '*' * (len(text) - 4) + text[-2:]

    from flask_limiter.errors import RateLimitExceeded

    @app.errorhandler(RateLimitExceeded)
    def handle_rate_limit(error):
        retry = getattr(error, "description", "Too many requests. Please wait and try again.")
        if request.accept_mimetypes.best == "application/json" or request.is_json:
            from flask import jsonify
            return jsonify({"error": str(retry)}), 429
        flash("Too many attempts. Please wait a moment and try again.", "danger")
        return redirect(request.referrer or "/"), 429

    @app.errorhandler(CSRFError)
    def handle_csrf_error(error):
        if request.accept_mimetypes.best == "application/json" or request.is_json:
            from flask import jsonify
            return jsonify({"error": "CSRF token missing or invalid. Please refresh and try again."}), 400
        flash("Your session expired or the request was invalid. Please try again.", "danger")
        return redirect(request.referrer or "/"), 400

    @app.errorhandler(RequestEntityTooLarge)
    def handle_request_entity_too_large(error):
        flash("File terlalu besar. Maksimal ukuran gambar 5 MB dan video 50 MB.", "danger")
        return redirect(request.url)

    app.cli.add_command(affiliate_cli)

    @app.cli.command("seed_admin")
    def seed_admin():
        """Seed admin & staff user from env"""
        _seed_data()
        print("Admin & staff created.")

    @app.cli.command("backfill_slugs")
    def backfill_slugs():
        """Generate slugs for every product that is currently missing one."""
        missing = Product.query.filter(
            (Product.slug == None) | (Product.slug == "")
        ).all()
        if not missing:
            print("All products already have slugs.")
            return
        updated = 0
        for product in missing:
            product.generate_slug(preserve_old=False)
            updated += 1
            print(f"  [{product.id}] {product.name!r} → {product.slug!r}")
        db.session.commit()
        print(f"Done. {updated} slug(s) generated.")

    @app.cli.command("db_migrate")
    def db_migrate_command():
        """Generate a new database migration from model changes."""
        flask_migrate(message="Auto generated migration")

    @app.cli.command("db_upgrade")
    def db_upgrade_command():
        """Apply database migrations to upgrade the schema."""
        upgrade_db()

    init_monitoring(app)

    return app

def _seed_data():
    admin_email = os.getenv("ADMIN_EMAIL")
    admin_password = os.getenv("ADMIN_PASSWORD")

    if not admin_email or not admin_password:
        raise ValueError("ADMIN_EMAIL dan ADMIN_PASSWORD belum diset di environment!")

    admin = User.query.filter_by(email=admin_email).first()
    if not admin:
        print("Creating admin user...")
        admin = User(
            name="Admin",
            email=admin_email,
            password=bcrypt.hashpw(admin_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8"),
            role="admin",
        )
        db.session.add(admin)
    else:
        print("Admin already exists, skip.")

    db.session.commit()