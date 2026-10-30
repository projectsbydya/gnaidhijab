from datetime import datetime
from . import db


class ShippingDiscount(db.Model):
    __tablename__ = "shipping_discounts"
    __table_args__ = (
        db.Index(
            "ix_shipping_discounts_active_dates",
            "is_active",
            "starts_at",
            "ends_at",
        ),
        db.CheckConstraint(
            "value >= 0", name="ck_shipping_discounts_value_non_negative"
        ),
        db.CheckConstraint(
            "discount_type IN ('fixed', 'percentage')",
            name="ck_shipping_discounts_type_allowed",
        ),
        db.CheckConstraint(
            "(discount_type != 'percentage') OR (value BETWEEN 0 AND 100)",
            name="ck_shipping_discounts_percentage_range",
        ),
        db.CheckConstraint(
            "minimum_order_amount >= 0",
            name="ck_shipping_discounts_min_order_non_negative",
        ),
        db.CheckConstraint(
            "(maximum_discount_amount IS NULL) OR (maximum_discount_amount >= 0)",
            name="ck_shipping_discounts_max_discount_non_negative",
        ),
        db.CheckConstraint(
            "(maximum_discount_amount IS NULL) OR (discount_type != 'fixed') OR (maximum_discount_amount >= value)",
            name="ck_shipping_discounts_fixed_max_ge_value",
        ),
        db.CheckConstraint(
            "(ends_at IS NULL) OR (starts_at IS NULL) OR (ends_at >= starts_at)",
            name="ck_shipping_discounts_dates",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=True)
    discount_type = db.Column(db.String(20), nullable=False)
    value = db.Column(db.Integer, nullable=False, default=0)
    minimum_order_amount = db.Column(db.Integer, nullable=False, default=0)
    maximum_discount_amount = db.Column(db.Integer, nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=True)
    starts_at = db.Column(db.DateTime, nullable=True)
    ends_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def is_currently_active(self, now=None):
        """Return True if the discount is active and within its valid period."""
        if now is None:
            now = datetime.utcnow()
        if not self.is_active:
            return False
        if self.starts_at is not None and now < self.starts_at:
            return False
        if self.ends_at is not None and now > self.ends_at:
            return False
        return True
