import re
import unicodedata
from datetime import datetime
from . import db


def _slugify(text: str) -> str:
    """Convert a string to a URL-safe ASCII slug."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-{2,}", "-", text)
    return text


class Product(db.Model):
    __tablename__ = "products"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(220), nullable=True, unique=True)
    price = db.Column(db.Integer, nullable=False)
    stock = db.Column(db.Integer, nullable=False, default=0)
    weight = db.Column(db.Float, nullable=False, default=0)  # Berat produk dalam gram
    sizes = db.Column(db.String(200), nullable=True)  # Default sizes for variants (e.g., "S,M,L,XL")
    description = db.Column(db.Text, nullable=True)
    image = db.Column(db.String(255), nullable=True)  # legacy; use ProductImage for new uploads
    is_active = db.Column(db.Boolean, default=True, nullable=True)

    # Sales count - incremented when order status becomes "completed"
    sold_count = db.Column(db.Integer, default=0, nullable=False)

    # Dynamic accordion content (admin-editable, replaces hardcoded text)
    materials_care = db.Column(db.Text, nullable=True)
    shipping_returns = db.Column(db.Text, nullable=True)
    size_guide = db.Column(db.Text, nullable=True)

    # Marketplace links
    shopee_url = db.Column(db.String(1000), nullable=True)
    # Internal-only: must never be exposed or editable through the admin UI/API.
    # Use services.affiliate_link_service for read/write access.
    shopee_affiliate_url = db.Column(db.String(1000), nullable=True)

    @property
    def shopee_link(self) -> str | None:
        """Return the effective Shopee storefront URL.

        Prefers the internal affiliate URL when set, otherwise falls back to the
        admin-managed Shopee URL. Returns None when neither is configured.
        """
        return self.shopee_affiliate_url or self.shopee_url

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    order_items = db.relationship("OrderItem", back_populates="product", lazy=True)
    images = db.relationship(
        "ProductImage", back_populates="product", lazy=True,
        cascade="all, delete-orphan", order_by="ProductImage.sort_order",
    )
    variants = db.relationship(
        "ProductVariant", back_populates="product", lazy=True,
        cascade="all, delete-orphan",
    )
    slug_history = db.relationship(
        "ProductSlugHistory", back_populates="product", lazy=True,
        cascade="all, delete-orphan",
    )
    discount = db.relationship(
        "ProductDiscount", back_populates="product", lazy=True,
        cascade="all, delete-orphan", uselist=False,
    )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @property
    def primary_image(self):
        """Return the first ProductImage path, falling back to the legacy image field."""
        if self.images:
            return self.images[0].image_path
        return self.image

    @property
    def effective_stock(self):
        """Total available stock: sum of variant stocks when variants exist, else product.stock."""
        if self.variants:
            return sum(v.stock for v in self.variants if v.is_active)
        return self.stock

    def generate_slug(self, preserve_old: bool = True):
        """Generate a unique slug from the product name.

        If the product already has a slug and the new slug would differ,
        the old slug is archived in ProductSlugHistory so inbound links
        keep working via 301 redirect.

        Args:
            preserve_old: When True (default), archive the current slug
                          before replacing it.  Pass False only when
                          backfilling brand-new products that have no
                          existing inbound equity.
        """
        from .product_slug_history import ProductSlugHistory

        base = _slugify(self.name)
        if not base:
            return

        candidate = base
        n = 1
        while True:
            # A candidate is free if no *other* product owns it AND
            # it is not reserved in the slug history of any other product.
            product_clash = (
                Product.query.filter(
                    Product.slug == candidate,
                    Product.id != self.id,
                ).first()
                if self.id
                else Product.query.filter_by(slug=candidate).first()
            )
            history_clash = ProductSlugHistory.query.filter(
                ProductSlugHistory.slug == candidate,
                ProductSlugHistory.product_id != (self.id or 0),
            ).first()
            if not product_clash and not history_clash:
                break
            candidate = f"{base}-{n}"
            n += 1

        if candidate == self.slug:
            return

        # Archive the old slug before replacing it
        if preserve_old and self.slug and self.id:
            already_archived = ProductSlugHistory.query.filter_by(
                slug=self.slug
            ).first()
            if not already_archived:
                self.slug_history.append(
                    ProductSlugHistory(product_id=self.id, slug=self.slug)
                )

        self.slug = candidate
