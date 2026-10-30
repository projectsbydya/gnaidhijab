from datetime import datetime
from sqlalchemy import event
from . import db


class Order(db.Model):
    __tablename__ = "orders"
    __table_args__ = (
        db.Index("ix_orders_user_id", "user_id"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    total_price = db.Column(db.Integer, nullable=False)
    status = db.Column(
        db.Enum("pending", "paid", "shipped", "completed", "cancelled", name="order_status"),
        nullable=False,
        default="pending",
    )
    shipping_address = db.Column(db.Text, nullable=False)
    courier = db.Column(db.String(50), nullable=False)
    service = db.Column(db.String(50), nullable=False)
    shipping_cost = db.Column(db.Integer, nullable=False)
    original_shipping_cost = db.Column(db.Integer, nullable=False, default=0)
    shipping_discount_amount = db.Column(db.Integer, nullable=False, default=0)
    payment_deadline = db.Column(db.DateTime, nullable=True)
    cancellation_reason = db.Column(db.String(50), nullable=True)
    resi_number = db.Column(db.String(100), nullable=True)
    destination_postal = db.Column(db.String(10), nullable=True)
    shipment_id = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", back_populates="orders")
    items = db.relationship("OrderItem", back_populates="order", lazy=True, cascade="all, delete-orphan")
    payment = db.relationship("Payment", back_populates="order", uselist=False, lazy=True, cascade="all, delete-orphan")
    status_logs = db.relationship(
        "OrderStatusLog",
        back_populates="order",
        lazy=True,
        cascade="all, delete-orphan",
        order_by="OrderStatusLog.created_at.desc()",
    )

    @property
    def normalized_status(self):
        return self.status

    @property
    def is_pending(self):
        return self.status == "pending"


@event.listens_for(Order.status, "set")
def _log_order_status_change(target, new_value, old_value, initiator):
    """
    Fires after Order.status is assigned a new value.
    Skips the log when:
      - old_value is the SQLAlchemy NEVER_SET sentinel (column not yet initialised)
      - new_value equals the current persisted value (no real change)
    The actual log row is appended via the relationship so it is committed
    in the same transaction as the status update.
    """
    from sqlalchemy.orm.attributes import NO_VALUE, NEVER_SET
    from .order_status_log import OrderStatusLog

    # Normalise sentinels to None
    old_str = None if old_value in (NO_VALUE, NEVER_SET) else old_value

    # Skip no-op assignments (e.g. order.status = order.status)
    if old_str == new_value:
        return

    log = OrderStatusLog(
        old_status=old_str,
        new_status=new_value,
        # changed_by / note are set by callers via helpers in order_status_log
    )
    target.status_logs.append(log)


@event.listens_for(Order.status, "set")
def _update_product_sold_count(target, new_value, old_value, initiator):
    """
    Increment product sold_count when order status becomes 'completed'.
    Decrement if status moves away from 'completed' to non-completed.
    """
    from sqlalchemy.orm.attributes import NO_VALUE, NEVER_SET

    old_str = None if old_value in (NO_VALUE, NEVER_SET) else old_value
    if old_str == new_value:
        return

    # Only process on actual database commit (not on transient objects)
    if new_value == "completed" and old_str != "completed":
        # Order completed - add to sold_count
        for item in target.items:
            if item.product:
                item.product.sold_count = (item.product.sold_count or 0) + item.quantity
    elif old_str == "completed" and new_value != "completed":
        # Order un-completed (e.g., refunded, cancelled after completion) - subtract from sold_count
        for item in target.items:
            if item.product:
                item.product.sold_count = max(0, (item.product.sold_count or 0) - item.quantity)


class OrderItem(db.Model):
    __tablename__ = "order_items"
    __table_args__ = (
        db.Index("ix_order_items_variant_id", "variant_id"),
    )

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    variant_id = db.Column(
        db.Integer,
        db.ForeignKey("product_variants.id", ondelete="SET NULL"),
        nullable=True,
    )
    quantity = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Integer, nullable=False)
    original_price = db.Column(db.Integer, nullable=True, default=0)
    discount_amount = db.Column(db.Integer, nullable=True, default=0)

    order = db.relationship("Order", back_populates="items")
    product = db.relationship("Product", back_populates="order_items")
    variant = db.relationship("ProductVariant", foreign_keys=[variant_id], lazy="joined")
