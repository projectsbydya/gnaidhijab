from datetime import datetime
from . import db

class Payment(db.Model):
    __tablename__ = "payments"
    __table_args__ = (
        db.Index("ix_payments_external_id", "external_id", unique=True),
        db.Index("ix_payments_transaction_id", "transaction_id"),
    )

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False)
    payment_method = db.Column(db.String(100), nullable=True)
    payment_proof = db.Column(db.String(255), nullable=True)
    status = db.Column(
        db.Enum(
            "unpaid",
            "pending_payment",
            "paid",
            "expired",
            name="payment_status",
        ),
        nullable=False,
        default="unpaid",
    )
    paid_at = db.Column(db.DateTime, nullable=True)
    transaction_id = db.Column(db.String(255), nullable=True)
    invoice_url = db.Column(db.Text, nullable=True)
    external_id = db.Column(db.String(100), nullable=True)

    order = db.relationship("Order", back_populates="payment")
