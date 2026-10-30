from flask import Blueprint, render_template, request, redirect, url_for, current_app, Response
import sqlalchemy as sa
from extensions import limiter
from models.product import Product
from models.product_slug_history import ProductSlugHistory
from models.video import Video
from models.cta_setting import CTASetting

shop_bp = Blueprint("shop", __name__)


def _product_meta(product, request) -> dict:
    """Build SEO meta dict for a product page."""
    base_url = request.host_url.rstrip("/")
    canonical = (
        f"{base_url}{url_for('shop.product_detail_slug', slug=product.slug)}"
        if product.slug
        else f"{base_url}{url_for('shop.product_detail', product_id=product.id)}"
    )
    description = (product.description or "").strip()
    if len(description) > 160:
        description = description[:157] + "…"
    og_image = ""
    if product.primary_image:
        og_image = f"{base_url}{url_for('static', filename=product.primary_image)}"
    price_formatted = f"Rp {product.price:,}"
    return {
        "title": f"{product.name} — {current_app.config['STORE_NAME']}",
        "description": description or f"Buy {product.name} at {current_app.config['STORE_NAME']}. {price_formatted}.",
        "canonical": canonical,
        "og_image": og_image,
        "og_type": "product",
        "price_formatted": price_formatted,
        "availability": "InStock" if product.effective_stock > 0 else "OutOfStock",
    }


@shop_bp.route("/")
def index():
    """Home page - displays hero CTA, video, featured products"""
    featured_products = Product.query.filter_by(is_active=True).order_by(Product.created_at.desc()).limit(6).all()
    video = Video.query.filter_by(is_active=True).order_by(Video.created_at.desc()).first()
    cta = CTASetting.get_active()
    return render_template("index.html", featured_products=featured_products, video=video, cta=cta)


@shop_bp.route("/products")
def products():
    """Products page - displays all active products"""
    products = Product.query.filter_by(is_active=True).order_by(Product.created_at.desc()).all()
    return render_template("products.html", products=products)


@shop_bp.route("/search")
@limiter.limit("30 per minute")
def search():
    query = request.args.get("query", "").strip()
    products = []
    if query:
        # Safe parameterized wildcard search using SQL-level concatenation
        # Prevents SQL injection by using bound parameters
        products = Product.query.filter(
            Product.name.ilike(sa.func.concat('%', query, '%')) |
            Product.description.ilike(sa.func.concat('%', query, '%'))
        ).filter_by(is_active=True).order_by(Product.created_at.desc()).all()
    return render_template("search_results.html", products=products, query=query)


@shop_bp.route("/product/<int:product_id>")
def product_detail(product_id):
    """Legacy numeric URL — always 301 to slug if available."""
    product = Product.query.get_or_404(product_id)
    if product.slug:
        return redirect(url_for("shop.product_detail_slug", slug=product.slug), code=301)
    related_products = (
        Product.query.filter_by(is_active=True)
        .filter(Product.id != product_id)
        .order_by(Product.created_at.desc())
        .limit(4)
        .all()
    )
    meta = _product_meta(product, request)
    return render_template(
        "product_detail.html",
        product=product,
        related_products=related_products,
        meta=meta,
    )


@shop_bp.route("/products/<slug>")
def product_detail_slug(slug):
    """Canonical SEO-friendly product URL.

    Lookup order:
      1. Active product with this exact slug  → serve normally.
      2. Slug exists in product_slug_history  → 301 to current canonical slug.
      3. Neither found                        → 404.
    """
    product = Product.query.filter_by(slug=slug, is_active=True).first()
    if product is None:
        # Check slug history for a 301 redirect target
        history = ProductSlugHistory.query.filter_by(slug=slug).first()
        if history:
            current = Product.query.filter_by(
                id=history.product_id, is_active=True
            ).first()
            if current and current.slug:
                return redirect(
                    url_for("shop.product_detail_slug", slug=current.slug),
                    code=301,
                )
        from flask import abort
        abort(404)

    related_products = (
        Product.query.filter_by(is_active=True)
        .filter(Product.id != product.id)
        .order_by(Product.created_at.desc())
        .limit(4)
        .all()
    )
    meta = _product_meta(product, request)
    return render_template(
        "product_detail.html",
        product=product,
        related_products=related_products,
        meta=meta,
    )


@shop_bp.route("/robots.txt")
def robots_txt():
    """Serve robots.txt — allow public pages, block private/admin routes."""
    base_url = request.host_url.rstrip("/")
    lines = [
        "User-agent: *",
        "",
        "# ── Public pages (explicitly allowed) ────────────────────────",
        "Allow: /$",
        "Allow: /products",
        "Allow: /products/",
        "Allow: /search",
        "Allow: /terms",
        "Allow: /privacy",
        "Allow: /refund",
        "Allow: /shipping-policy",
        "",
        "# ── Admin panel ───────────────────────────────────────────────",
        "Disallow: /admin/",
        "",
        "# ── Internal API ──────────────────────────────────────────────",
        "Disallow: /api/",
        "",
        "# ── Auth routes ───────────────────────────────────────────────",
        "Disallow: /login",
        "Disallow: /register",
        "Disallow: /logout",
        "Disallow: /profile",
        "Disallow: /request-reset-password",
        "Disallow: /verify-otp",
        "Disallow: /reset-password",
        "",
        "# ── Checkout & transactional routes ───────────────────────────",
        "Disallow: /cart",
        "Disallow: /checkout",
        "Disallow: /payment",
        "Disallow: /orders",
        "",
        f"Sitemap: {base_url}/sitemap.xml",
    ]
    return Response("\n".join(lines), mimetype="text/plain")


@shop_bp.route("/sitemap.xml")
def sitemap_xml():
    """Dynamic XML sitemap with canonical URLs and lastmod timestamps."""
    from datetime import datetime, timezone

    base_url = request.host_url.rstrip("/")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # ── Helper ───────────────────────────────────────────────────────────────
    def _url(loc, priority, changefreq, lastmod=None):
        return {
            "loc": loc,
            "priority": priority,
            "changefreq": changefreq,
            "lastmod": lastmod or now,
        }

    # ── Static pages ─────────────────────────────────────────────────────────
    urls = [
        _url(f"{base_url}/",        "1.0", "weekly"),
        _url(f"{base_url}/products","0.9", "daily"),
    ]

    # ── Product pages — canonical slug URL, lastmod from created_at ──────────
    products = (
        Product.query
        .filter_by(is_active=True)
        .order_by(Product.created_at.desc())
        .all()
    )
    for p in products:
        loc = (
            f"{base_url}{url_for('shop.product_detail_slug', slug=p.slug)}"
            if p.slug
            else f"{base_url}{url_for('shop.product_detail', product_id=p.id)}"
        )
        lastmod = p.created_at.strftime("%Y-%m-%d") if p.created_at else now
        urls.append(_url(loc, "0.8", "weekly", lastmod))

    # ── Policy pages ─────────────────────────────────────────────────────────
    for path in ("/terms", "/privacy", "/refund", "/shipping-policy"):
        urls.append(_url(f"{base_url}{path}", "0.4", "monthly"))

    # ── Render XML ───────────────────────────────────────────────────────────
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for u in urls:
        lines.append(
            f'  <url>'
            f'<loc>{u["loc"]}</loc>'
            f'<lastmod>{u["lastmod"]}</lastmod>'
            f'<changefreq>{u["changefreq"]}</changefreq>'
            f'<priority>{u["priority"]}</priority>'
            f'</url>'
        )
    lines.append("</urlset>")

    return Response("\n".join(lines), mimetype="application/xml")


@shop_bp.route("/terms")
def terms():
    return render_template("policies/terms.html")


@shop_bp.route("/privacy")
def privacy():
    return render_template("policies/privacy.html")


@shop_bp.route("/refund")
def refund():
    return render_template("policies/refund.html")


@shop_bp.route("/shipping-policy")
def shipping_policy():
    return render_template("policies/shipping_policy.html")
