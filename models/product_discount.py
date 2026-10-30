from datetime import datetime
from . import db


class ProductDiscount(db.Model):
    __tablename__ = "product_discounts"
    __table_args__ = (
        db.UniqueConstraint("product_id", name="uq_product_discounts_product_id"),
        db.Index(
            "ix_product_discounts_active_dates", "is_active", "starts_at", "ends_at"
        ),
        db.CheckConstraint(
            "value >= 0", name="ck_product_discounts_value_non_negative"
        ),
        db.CheckConstraint(
            "discount_type IN ('percentage', 'fixed')",
            name="ck_product_discounts_type_allowed",
        ),
        db.CheckConstraint(
            "(discount_type != 'percentage') OR (value BETWEEN 0 AND 100)",
            name="ck_product_discounts_percentage_range",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(
        db.Integer,
        db.ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
    )
    name = db.Column(db.String(100), nullable=True)
    discount_type = db.Column(db.String(20), nullable=False)
    value = db.Column(db.Integer, nullable=False, default=0)
    is_active = db.Column(db.Boolean, default=True, nullable=True)
    starts_at = db.Column(db.DateTime, nullable=True)
    ends_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    product = db.relationship("Product", back_populates="discount")
