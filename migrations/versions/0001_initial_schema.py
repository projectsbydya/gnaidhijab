"""Initial schema — full squash of all previous migrations.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-05-11 00:00:00.000000

Represents the complete database schema as of the squash date.
Reproducible from an empty database.

Tables created (creation order respects FK dependencies):
  1.  users
  2.  products
  3.  product_images
  4.  product_variants
  5.  variant_images
  6.  banners
  7.  videos
  8.  cta_settings
  9.  password_resets
  10. orders
  11. order_items
  12. order_status_logs
  13. payments
  14. carts
  15. cart_items

Upgrade on an existing database:
  If the database is already fully migrated, stamp it at this revision:
      flask db stamp 0001_initial_schema
  Then run normally:
      flask db upgrade
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector
from sqlalchemy.dialects import mysql


revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _table_exists(name: str) -> bool:
    return name in Inspector.from_engine(op.get_bind()).get_table_names()


def _index_exists(table: str, index: str) -> bool:
    insp = Inspector.from_engine(op.get_bind())
    return index in [i["name"] for i in insp.get_indexes(table)]


def _column_exists(table: str, column: str) -> bool:
    insp = Inspector.from_engine(op.get_bind())
    return column in [c["name"] for c in insp.get_columns(table)]


# ── upgrade ───────────────────────────────────────────────────────────────────

def upgrade():

    # ── 1. users ─────────────────────────────────────────────────────────────
    if not _table_exists("users"):
        op.create_table(
            "users",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("name", sa.String(150), nullable=False),
            sa.Column("email", sa.String(150), nullable=False, unique=True),
            sa.Column("password", sa.String(255), nullable=False),
            sa.Column("phone", sa.String(50), nullable=True),
            sa.Column("address", sa.Text, nullable=True),
            sa.Column("encrypted_address", sa.Text, nullable=True),
            sa.Column("encrypted_postal_code", sa.String(255), nullable=True),
            sa.Column("role", sa.String(20), nullable=False, server_default="user"),
            sa.Column("created_at", sa.DateTime, server_default=sa.text("NOW()")),
        )
    else:
        for col, col_type in [
            ("encrypted_address", sa.Text()),
            ("encrypted_postal_code", sa.String(255)),
        ]:
            if not _column_exists("users", col):
                op.add_column("users", sa.Column(col, col_type, nullable=True))

    # ── 2. products ──────────────────────────────────────────────────────────
    if not _table_exists("products"):
        op.create_table(
            "products",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("slug", sa.String(220), nullable=True, unique=True),
            sa.Column("price", sa.Integer, nullable=False),
            sa.Column("stock", sa.Integer, nullable=False, server_default="0"),
            sa.Column("weight", sa.Float, nullable=False, server_default="0"),
            sa.Column("description", sa.Text, nullable=True),
            sa.Column("image", sa.String(255), nullable=True),
            sa.Column("is_active", sa.Boolean, server_default=sa.text("1")),
            sa.Column("created_at", sa.DateTime, server_default=sa.text("NOW()")),
        )
    else:
        for col, col_type in [
            ("slug", sa.String(220)),
            ("weight", sa.Float()),
        ]:
            if not _column_exists("products", col):
                op.add_column("products", sa.Column(col, col_type, nullable=True))

    # ── 3. product_images ────────────────────────────────────────────────────
    if not _table_exists("product_images"):
        op.create_table(
            "product_images",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("product_id", sa.Integer, sa.ForeignKey("products.id"), nullable=False),
            sa.Column("image_path", sa.String(255), nullable=False),
            sa.Column("alt_text", sa.String(200), nullable=True),
            sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        )

    # ── 4. product_variants ──────────────────────────────────────────────────
    if not _table_exists("product_variants"):
        op.create_table(
            "product_variants",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("product_id", sa.Integer, sa.ForeignKey("products.id"), nullable=False),
            sa.Column("color", sa.String(100), nullable=True),
            sa.Column("size", sa.String(100), nullable=True),
            sa.Column("sku", sa.String(100), nullable=True),
            sa.Column("stock", sa.Integer, nullable=False, server_default="0"),
            sa.Column("price", sa.Integer, nullable=True),
            sa.Column("weight", sa.Float, nullable=True),
            sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("1")),
            sa.UniqueConstraint("product_id", "sku", name="uq_variant_product_sku"),
        )
        if not _index_exists("product_variants", "ix_product_variants_product_id"):
            op.create_index("ix_product_variants_product_id", "product_variants", ["product_id"])

    # ── 5. variant_images ────────────────────────────────────────────────────
    if not _table_exists("variant_images"):
        op.create_table(
            "variant_images",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("variant_id", sa.Integer, sa.ForeignKey("product_variants.id"), nullable=False),
            sa.Column("image_path", sa.String(255), nullable=False),
            sa.Column("alt_text", sa.String(200), nullable=True),
            sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        )

    # ── 6. banners ───────────────────────────────────────────────────────────
    if not _table_exists("banners"):
        op.create_table(
            "banners",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("description", sa.Text, nullable=True),
            sa.Column("image", sa.String(255), nullable=False),
            sa.Column("link", sa.String(255), nullable=True),
            sa.Column("sort_order", sa.Integer, server_default="0"),
            sa.Column("is_active", sa.Boolean, server_default=sa.text("1")),
            sa.Column("created_at", sa.DateTime, server_default=sa.text("NOW()")),
            sa.Column("updated_at", sa.DateTime, server_default=sa.text("NOW()"),
                      onupdate=sa.text("NOW()")),
        )

    # ── 7. videos ────────────────────────────────────────────────────────────
    if not _table_exists("videos"):
        op.create_table(
            "videos",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("description", sa.Text, nullable=True),
            sa.Column("video_file", sa.String(255), nullable=False),
            sa.Column("is_active", sa.Boolean, server_default=sa.text("1")),
            sa.Column("created_at", sa.DateTime, server_default=sa.text("NOW()")),
            sa.Column("updated_at", sa.DateTime, server_default=sa.text("NOW()"),
                      onupdate=sa.text("NOW()")),
        )

    # ── 8. cta_settings ──────────────────────────────────────────────────────
    if not _table_exists("cta_settings"):
        op.create_table(
            "cta_settings",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("title", sa.String(200), nullable=False,
                      server_default="Define Your Style"),
            sa.Column("description", sa.Text, nullable=True),
            sa.Column("button_text", sa.String(100), nullable=False,
                      server_default="Shop Collection"),
            sa.Column("button_link", sa.String(255), nullable=False,
                      server_default="/products"),
            sa.Column("background_image", sa.String(255), nullable=True),
            sa.Column("is_active", sa.Boolean, server_default=sa.text("1")),
            sa.Column("created_at", sa.DateTime, server_default=sa.text("NOW()")),
            sa.Column("updated_at", sa.DateTime, server_default=sa.text("NOW()"),
                      onupdate=sa.text("NOW()")),
        )

    # ── 9. password_resets ───────────────────────────────────────────────────
    if not _table_exists("password_resets"):
        op.create_table(
            "password_resets",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("email", sa.String(150), nullable=False),
            sa.Column("otp", sa.String(6), nullable=False),
            sa.Column("reset_token", sa.String(64), nullable=True, unique=True),
            sa.Column("expires_at", sa.DateTime, nullable=False),
            sa.Column("used", sa.Boolean, nullable=False, server_default=sa.text("0")),
            sa.Column("created_at", sa.DateTime, nullable=False,
                      server_default=sa.text("NOW()")),
        )
        op.create_index("ix_password_resets_email", "password_resets", ["email"])

    # ── 10. orders ───────────────────────────────────────────────────────────
    if not _table_exists("orders"):
        op.create_table(
            "orders",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
            sa.Column("total_price", sa.Integer, nullable=False),
            sa.Column(
                "status",
                sa.Enum("pending", "paid", "shipped", "completed", name="order_status"),
                nullable=False,
                server_default="pending",
            ),
            sa.Column("shipping_address", sa.Text, nullable=False),
            sa.Column("courier", sa.String(50), nullable=False),
            sa.Column("service", sa.String(50), nullable=False),
            sa.Column("shipping_cost", sa.Integer, nullable=False),
            sa.Column("payment_deadline", sa.DateTime, nullable=True),
            sa.Column("resi_number", sa.String(100), nullable=True),
            sa.Column("destination_postal", sa.String(10), nullable=True),
            sa.Column("shipment_id", sa.String(100), nullable=True),
            sa.Column("created_at", sa.DateTime, server_default=sa.text("NOW()")),
        )
        op.create_index("ix_orders_user_id", "orders", ["user_id"])
    else:
        for col, col_type in [
            ("destination_postal", sa.String(10)),
            ("shipment_id", sa.String(100)),
        ]:
            if not _column_exists("orders", col):
                op.add_column("orders", sa.Column(col, col_type, nullable=True))

    # ── 11. order_items ──────────────────────────────────────────────────────
    if not _table_exists("order_items"):
        op.create_table(
            "order_items",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("order_id", sa.Integer, sa.ForeignKey("orders.id"), nullable=False),
            sa.Column("product_id", sa.Integer, sa.ForeignKey("products.id"), nullable=False),
            sa.Column(
                "variant_id",
                sa.Integer,
                sa.ForeignKey("product_variants.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("quantity", sa.Integer, nullable=False),
            sa.Column("price", sa.Integer, nullable=False),
        )
        op.create_index("ix_order_items_variant_id", "order_items", ["variant_id"])
    else:
        if not _column_exists("order_items", "variant_id"):
            op.add_column(
                "order_items",
                sa.Column(
                    "variant_id",
                    sa.Integer,
                    sa.ForeignKey("product_variants.id", ondelete="SET NULL"),
                    nullable=True,
                ),
            )
            if not _index_exists("order_items", "ix_order_items_variant_id"):
                op.create_index("ix_order_items_variant_id", "order_items", ["variant_id"])

    # ── 12. order_status_logs ────────────────────────────────────────────────
    if not _table_exists("order_status_logs"):
        op.create_table(
            "order_status_logs",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column(
                "order_id",
                sa.Integer,
                sa.ForeignKey("orders.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("old_status", sa.String(50), nullable=True),
            sa.Column("new_status", sa.String(50), nullable=False),
            sa.Column("changed_by", sa.String(100), nullable=True),
            sa.Column("note", sa.Text, nullable=True),
            sa.Column("created_at", sa.DateTime, nullable=False,
                      server_default=sa.text("NOW()")),
        )
        op.create_index("ix_order_status_logs_order_id", "order_status_logs", ["order_id"])
        op.create_index("ix_order_status_logs_created_at", "order_status_logs", ["created_at"])

    # ── 13. payments ─────────────────────────────────────────────────────────
    if not _table_exists("payments"):
        op.create_table(
            "payments",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("order_id", sa.Integer, sa.ForeignKey("orders.id"), nullable=False),
            sa.Column("payment_method", sa.String(100), nullable=True),
            sa.Column("payment_proof", sa.String(255), nullable=True),
            sa.Column(
                "status",
                sa.Enum(
                    "unpaid", "pending_payment", "paid", "expired",
                    name="payment_status",
                ),
                nullable=False,
                server_default="unpaid",
            ),
            sa.Column("paid_at", sa.DateTime, nullable=True),
            sa.Column("transaction_id", sa.String(255), nullable=True),
            sa.Column("invoice_url", sa.Text, nullable=True),
            sa.Column("external_id", sa.String(100), nullable=True),
        )
        op.create_index("ix_payments_external_id", "payments", ["external_id"], unique=True)
        op.create_index("ix_payments_transaction_id", "payments", ["transaction_id"])

    # ── 14. carts ────────────────────────────────────────────────────────────
    if not _table_exists("carts"):
        op.create_table(
            "carts",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column(
                "user_id",
                sa.Integer,
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
                unique=True,
            ),
            sa.Column("updated_at", sa.DateTime, nullable=False,
                      server_default=sa.text("NOW()")),
        )
        op.create_index("ix_carts_user_id", "carts", ["user_id"], unique=True)

    # ── 15. cart_items ───────────────────────────────────────────────────────
    if not _table_exists("cart_items"):
        op.create_table(
            "cart_items",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column(
                "cart_id",
                sa.Integer,
                sa.ForeignKey("carts.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "product_id",
                sa.Integer,
                sa.ForeignKey("products.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "variant_id",
                sa.Integer,
                sa.ForeignKey("product_variants.id", ondelete="CASCADE"),
                nullable=True,
            ),
            sa.Column("quantity", sa.Integer, nullable=False, server_default="1"),
            sa.UniqueConstraint(
                "cart_id", "product_id", "variant_id",
                name="uq_cart_product_variant",
            ),
        )
        op.create_index("ix_cart_items_cart_id", "cart_items", ["cart_id"])


# ── downgrade ─────────────────────────────────────────────────────────────────

def downgrade():
    # Drop in reverse FK order
    for table in [
        "cart_items",
        "carts",
        "payments",
        "order_status_logs",
        "order_items",
        "orders",
        "password_resets",
        "cta_settings",
        "videos",
        "banners",
        "variant_images",
        "product_variants",
        "product_images",
        "products",
        "users",
    ]:
        if _table_exists(table):
            op.drop_table(table)

    # Drop named Enums (MySQL does not require explicit drop but safe to call)
    try:
        sa.Enum(name="order_status").drop(op.get_bind(), checkfirst=True)
        sa.Enum(name="payment_status").drop(op.get_bind(), checkfirst=True)
    except Exception:
        pass
