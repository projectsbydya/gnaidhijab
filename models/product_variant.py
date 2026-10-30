from . import db


class ProductVariant(db.Model):
    __tablename__ = "product_variants"
    __table_args__ = (
        db.Index("ix_product_variants_product_id", "product_id"),
        db.UniqueConstraint("product_id", "sku", name="uq_variant_product_sku"),
    )

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    color = db.Column(db.String(100), nullable=True)
    color_image_path = db.Column(db.String(255), nullable=True)  # Swatch image for color
    size = db.Column(db.String(100), nullable=True)
    sku = db.Column(db.String(100), nullable=True)
    stock = db.Column(db.Integer, nullable=False, default=0)
    price = db.Column(db.Integer, nullable=True)    # overrides product.price when set
    weight = db.Column(db.Float, nullable=True)     # overrides product.weight when set
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    product = db.relationship("Product", back_populates="variants")
    images = db.relationship(
        "VariantImage", back_populates="variant", lazy=True,
        cascade="all, delete-orphan", order_by="VariantImage.sort_order",
    )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @property
    def effective_price(self):
        """Variant price if set, else fall back to product base price."""
        return self.price if self.price is not None else self.product.price

    @property
    def effective_weight(self):
        """Variant weight if set, else fall back to product base weight."""
        return self.weight if self.weight is not None else self.product.weight

    @property
    def effective_size(self):
        """Variant size if set, else fall back to product base sizes."""
        return self.size if self.size is not None else self.product.sizes

    @property
    def display_name(self):
        parts = [p for p in (self.color, self.effective_size) if p]
        return " / ".join(parts) if parts else (self.sku or f"Variant {self.id}")
