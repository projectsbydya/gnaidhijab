"""Centralized product discount calculation service.

This module is intentionally decoupled from cart, checkout, admin, and templates.
It only knows how to determine whether a discount is active and how to calculate
its effect on a product price.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from models.product_discount import ProductDiscount


@dataclass(frozen=True)
class DiscountResult:
    """Immutable result of a discount calculation."""

    original_price: int
    final_price: int
    savings: int
    is_active: bool
    discount_id: Optional[int] = None
    discount_name: Optional[str] = None
    discount_type: Optional[str] = None
    discount_value: Optional[int] = None
    is_applied: bool = False


# ── Internal helpers ─────────────────────────────────────────────────────────


def _to_naive_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Convert a timezone-aware datetime to naive UTC; leave naive as-is."""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _is_discount_active(
    discount: Optional[ProductDiscount],
    reference_time: Optional[datetime] = None,
) -> bool:
    """Return True if the discount exists, is active, and inside its period.

    ``is_active`` is treated as inactive when it is ``None`` or ``False``
    to avoid accidentally applying discounts with an unset active flag.
    """
    if discount is None or not discount.is_active:
        return False

    now = _to_naive_utc(reference_time) or _to_naive_utc(datetime.now(timezone.utc))
    starts_at = _to_naive_utc(discount.starts_at)
    ends_at = _to_naive_utc(discount.ends_at)

    if starts_at is not None and now < starts_at:
        return False
    if ends_at is not None and now > ends_at:
        return False

    return True


def _calculate_savings(price: int, discount: ProductDiscount) -> int:
    """Calculate the raw savings amount without active/period checks."""
    value = discount.value if discount.value is not None else 0

    if discount.discount_type == "percentage":
        return int(
            (Decimal(price) * Decimal(value) / Decimal(100))
            .to_integral_value(rounding=ROUND_HALF_UP)
        )
    if discount.discount_type == "fixed":
        return min(value, price)
    return 0


# ── Public API ───────────────────────────────────────────────────────────────


def calculate_discount(
    price: int,
    discount: Optional[ProductDiscount] = None,
    reference_time: Optional[datetime] = None,
) -> DiscountResult:
    """Calculate discount for a given price.

    Args:
        price: Original product price in smallest currency unit.
        discount: Optional ``ProductDiscount`` to apply.
        reference_time: Optional datetime used for period checks. May be
            timezone-aware or naive (assumed UTC). Useful in tests.

    Returns:
        ``DiscountResult`` with final price, savings, and active status.
    """
    if price is None:
        price = 0
    original_price = int(price)
    if original_price < 0:
        raise ValueError("price cannot be negative")

    if not _is_discount_active(discount, reference_time):
        return DiscountResult(
            original_price=original_price,
            final_price=original_price,
            savings=0,
            is_active=False,
            is_applied=False,
        )

    savings = min(_calculate_savings(original_price, discount), original_price)
    final_price = original_price - savings

    return DiscountResult(
        original_price=original_price,
        final_price=final_price,
        savings=savings,
        is_active=True,
        discount_id=discount.id,
        discount_name=discount.name,
        discount_type=discount.discount_type,
        discount_value=discount.value,
        is_applied=True,
    )


def resolve_unit_price(product, variant=None) -> int:
    """Return the current unit price for a product/variant line.

    If ``variant`` is provided and has an explicit price, that price is used.
    Otherwise the price falls back to the product base price.
    """
    if variant is not None:
        variant_price = getattr(variant, "price", None)
        if variant_price is not None:
            return int(variant_price)
    return int(getattr(product, "price", 0) or 0)


def calculate_product_or_variant_discount(
    product,
    variant=None,
    reference_time: Optional[datetime] = None,
) -> DiscountResult:
    """Calculate discount for a product or a specific variant.

    Discounts are attached to the product, but the base price is resolved from
    the variant override when available.
    """
    price = resolve_unit_price(product, variant)
    discount = getattr(product, "discount", None)
    return calculate_discount(price, discount, reference_time)


def calculate_product_discount(
    product,
    reference_time: Optional[datetime] = None,
) -> DiscountResult:
    """Calculate discount for a ``Product`` instance using ``product.price``.

    Falls back to no discount if the product has no ``discount`` relation.
    """
    return calculate_product_or_variant_discount(product, variant=None, reference_time=reference_time)
