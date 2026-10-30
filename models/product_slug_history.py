from datetime import datetime
from . import db


class ProductSlugHistory(db.Model):
    """Immutable log of every slug a product has ever used.

    Used to issue 301 redirects from old slugs to the current canonical URL,
    preserving inbound links and search engine equity after product renames.
    """

    __tablename__ = "product_slug_history"
    __table_args__ = (
        db.Index("ix_psh_slug", "slug", unique=True),
        db.Index("ix_psh_product_id", "product_id"),
    )

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(
        db.Integer,
        db.ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
    )
    slug = db.Column(db.String(220), nullable=False, unique=True)
    replaced_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    product = db.relationship("Product", back_populates="slug_history")

    def __repr__(self):
        return f"<ProductSlugHistory product={self.product_id} slug={self.slug!r}>"
