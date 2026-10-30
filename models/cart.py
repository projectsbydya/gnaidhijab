from datetime import datetime
from . import db


class Cart(db.Model):
    """One persistent cart per registered user."""

    __tablename__ = "carts"
    __table_args__ = (
        db.Index("ix_carts_user_id", "user_id", unique=True),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    user = db.relationship("User", back_populates="cart")
    items = db.relationship(
        "CartItem",
        back_populates="cart",
        cascade="all, delete-orphan",
        lazy=True,
    )

    def __repr__(self):
        return f"<Cart user_id={self.user_id} items={len(self.items)}>"


class CartItem(db.Model):
    """One line in a persistent cart: (cart, product, optional variant)."""

    __tablename__ = "cart_items"
    __table_args__ = (
        db.UniqueConstraint(
            "cart_id", "product_id", "variant_id",
            name="uq_cart_product_variant",
        ),
        db.Index("ix_cart_items_cart_id", "cart_id"),
    )

    id = db.Column(db.Integer, primary_key=True)
    cart_id = db.Column(
        db.Integer,
        db.ForeignKey("carts.id", ondelete="CASCADE"),
        nullable=False,
    )
    product_id = db.Column(
        db.Integer,
        db.ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
    )
    # NULL means no variant (stored as NULL, not 0, to satisfy the unique constraint)
    variant_id = db.Column(
        db.Integer,
        db.ForeignKey("product_variants.id", ondelete="CASCADE"),
        nullable=True,
    )
    quantity = db.Column(db.Integer, nullable=False, default=1)

    cart = db.relationship("Cart", back_populates="items")
    product = db.relationship("Product")
    variant = db.relationship("ProductVariant")

    def __repr__(self):
        return (
            f"<CartItem cart={self.cart_id} "
            f"product={self.product_id} variant={self.variant_id} "
            f"qty={self.quantity}>"
        )
