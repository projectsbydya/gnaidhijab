from datetime import datetime
from . import db


class OrderStatusLog(db.Model):
    """Immutable audit record for every Order.status transition."""

    __tablename__ = "order_status_logs"
    __table_args__ = (
        db.Index("ix_order_status_logs_order_id", "order_id"),
        db.Index("ix_order_status_logs_created_at", "created_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(
        db.Integer,
        db.ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    old_status = db.Column(db.String(50), nullable=True)
    new_status = db.Column(db.String(50), nullable=False)
    changed_by = db.Column(db.String(100), nullable=True)
    note = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    order = db.relationship(
        "Order",
        back_populates="status_logs",
    )

    def __repr__(self):
        return (
            f"<OrderStatusLog order={self.order_id} "
            f"{self.old_status!r} → {self.new_status!r} "
            f"by={self.changed_by}>"
        )


def annotate_last_log(order, changed_by: str, note: str | None = None) -> None:
    """
    Set changed_by (and optionally note) on the most-recently appended
    OrderStatusLog for the given order.

    Call this immediately after setting order.status so the log row
    created by the SQLAlchemy event listener gets properly attributed.
    If the relationship list is empty for any reason the call is a no-op.
    """
    if not order.status_logs:
        return
    # status_logs is ordered desc by created_at but newly appended items
    # without a created_at are at the END of the in-memory list before flush.
    # Find the first entry that has no changed_by yet.
    for log in reversed(order.status_logs):
        if log.changed_by is None:
            log.changed_by = changed_by
            if note is not None:
                log.note = note
            return
