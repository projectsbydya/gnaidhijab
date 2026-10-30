"""Centralized shipping discount calculation service.

This module is intentionally decoupled from checkout, Biteship, admin, and
templates. It only knows how to determine whether a shipping discount is
applicable and how to calculate its effect on a shipping cost.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable, Optional

from models.shipping_discount import ShippingDiscount


@dataclass(frozen=True)
class ShippingDiscountResult:
    """Immutable result of a shipping discount calculation."""

    original_shipping_cost: int
    final_shipping_cost: int
    savings: int
    is_active: bool
    is_applied: bool
    discount_id: Optional[int] = None
    discount_name: Optional[str] = None
    discount_type: Optional[str] = None
    discount_value: Optional[int] = None
    minimum_order_amount: Optional[int] = None
    maximum_discount_amount: Optional[int] = None


# ── Internal helpers ─────────────────────────────────────────────────────────


def _to_naive_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Convert a timezone-aware datetime to naive UTC; leave naive as-is."""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _is_discount_active(
    discount: Optional[ShippingDiscount],
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


def _meets_minimum_order(discount: ShippingDiscount, subtotal: int) -> bool:
    """Return True if the subtotal meets the discount's minimum order amount."""
    minimum = discount.minimum_order_amount
    if minimum is None:
        return True
    return int(subtotal) >= int(minimum)


def _calculate_savings(shipping_cost: int, discount: ShippingDiscount) -> int:
    """Calculate the raw savings amount without active/period/order checks."""
    value = discount.value if discount.value is not None else 0
    cost = int(shipping_cost)

    if discount.discount_type == "percentage":
        savings = int(
            (Decimal(cost) * Decimal(value) / Decimal(100))
            .to_integral_value(rounding=ROUND_HALF_UP)
        )
    elif discount.discount_type == "fixed":
        savings = int(value)
    else:
        savings = 0

    maximum = discount.maximum_discount_amount
    if maximum is not None:
        savings = min(savings, int(maximum))

    return min(savings, cost)


# ── Public API ───────────────────────────────────────────────────────────────


def calculate_shipping_discount(
    shipping_cost: int,
    subtotal: int,
    discount: Optional[ShippingDiscount] = None,
    reference_time: Optional[datetime] = None,
) -> ShippingDiscountResult:
    """Calculate shipping discount for a given shipping cost and order subtotal.

    Args:
        shipping_cost: Original shipping cost in smallest currency unit.
        subtotal: Order subtotal used for minimum_order_amount check.
        discount: Optional ``ShippingDiscount`` to apply.
        reference_time: Optional datetime used for period checks. May be
            timezone-aware or naive (assumed UTC). Useful in tests.

    Returns:
        ``ShippingDiscountResult`` with final cost, savings, and promo metadata.
    """
    original_cost = int(shipping_cost) if shipping_cost is not None else 0
    if original_cost < 0:
        raise ValueError("shipping_cost cannot be negative")

    order_subtotal = int(subtotal) if subtotal is not None else 0
    if order_subtotal < 0:
        raise ValueError("subtotal cannot be negative")

    if not _is_discount_active(discount, reference_time):
        return ShippingDiscountResult(
            original_shipping_cost=original_cost,
            final_shipping_cost=original_cost,
            savings=0,
            is_active=False,
            is_applied=False,
        )

    if not _meets_minimum_order(discount, order_subtotal):
        return ShippingDiscountResult(
            original_shipping_cost=original_cost,
            final_shipping_cost=original_cost,
            savings=0,
            is_active=True,
            is_applied=False,
            discount_id=discount.id,
            discount_name=discount.name,
            discount_type=discount.discount_type,
            discount_value=discount.value,
            minimum_order_amount=discount.minimum_order_amount,
            maximum_discount_amount=discount.maximum_discount_amount,
        )

    savings = _calculate_savings(original_cost, discount)
    final_cost = max(0, original_cost - savings)

    return ShippingDiscountResult(
        original_shipping_cost=original_cost,
        final_shipping_cost=final_cost,
        savings=savings,
        is_active=True,
        is_applied=True,
        discount_id=discount.id,
        discount_name=discount.name,
        discount_type=discount.discount_type,
        discount_value=discount.value,
        minimum_order_amount=discount.minimum_order_amount,
        maximum_discount_amount=discount.maximum_discount_amount,
    )


def calculate_best_shipping_discount(
    shipping_cost: int,
    subtotal: int,
    discounts: Optional[Iterable[ShippingDiscount]] = None,
    reference_time: Optional[datetime] = None,
) -> ShippingDiscountResult:
    """Pick and apply the active, valid shipping discount with the greatest savings.

    Args:
        shipping_cost: Original shipping cost in smallest currency unit.
        subtotal: Order subtotal used for minimum_order_amount checks.
        discounts: Iterable of ``ShippingDiscount`` candidates.
        reference_time: Optional datetime used for period checks. May be
            timezone-aware or naive (assumed UTC). Useful in tests.

    Returns:
        ``ShippingDiscountResult`` for the winning promo, or a no-discount
        result when no active/valid discount is available.
    """
    original_cost = int(shipping_cost) if shipping_cost is not None else 0
    if original_cost < 0:
        raise ValueError("shipping_cost cannot be negative")

    order_subtotal = int(subtotal) if subtotal is not None else 0
    if order_subtotal < 0:
        raise ValueError("subtotal cannot be negative")

    if not discounts:
        return ShippingDiscountResult(
            original_shipping_cost=original_cost,
            final_shipping_cost=original_cost,
            savings=0,
            is_active=False,
            is_applied=False,
        )

    candidates = [
        calculate_shipping_discount(
            original_cost, order_subtotal, discount, reference_time
        )
        for discount in discounts
        if discount is not None
    ]
    applied = [c for c in candidates if c.is_applied]

    if not applied:
        return ShippingDiscountResult(
            original_shipping_cost=original_cost,
            final_shipping_cost=original_cost,
            savings=0,
            is_active=False,
            is_applied=False,
        )

    return max(applied, key=lambda r: r.savings)


# ── Admin form validation helpers ───────────────────────────────────────────


_DATETIME_FORMATS = (
    "%Y-%m-%dT%H:%M",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
)


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def _parse_bool(value: Any) -> Optional[bool]:
    """Parse a boolean value. Returns None for unrecognised input.

    ``None`` is treated as ``False`` (inactive) because an unset active flag
    should never accidentally enable a discount.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return bool(value)
    if value is None:
        return False
    text = str(value).strip().lower()
    if text in {"true", "1", "on", "yes"}:
        return True
    if text in {"false", "0", "off", "no", ""}:
        return False
    return None


def _parse_datetime(value: Any) -> tuple[Optional[datetime], Optional[str]]:
    """Parse a datetime value. Returns (datetime, None) or (None, error)."""
    if value is None or (isinstance(value, str) and value.strip() == ""):
        return None, None
    text = str(value).strip()
    for fmt in _DATETIME_FORMATS:
        try:
            return datetime.strptime(text, fmt), None
        except ValueError:
            continue
    return None, "Format tanggal tidak valid."


def _add_error(errors: dict[str, list[str]], field: str, message: str) -> None:
    errors.setdefault(field, []).append(message)


def validate_shipping_discount_form(data: dict[str, Any]) -> dict[str, list[str]]:
    """Validate shipping discount form data and return a mapping of errors.

    Validated fields: name, discount_type, value, minimum_order_amount,
    maximum_discount_amount, starts_at, ends_at.
    """
    errors: dict[str, list[str]] = {}

    discount_type = data.get("discount_type")
    if _is_blank(discount_type):
        _add_error(errors, "discount_type", "Tipe diskon wajib dipilih.")
    else:
        discount_type = str(discount_type).strip().lower()
        if discount_type not in {"fixed", "percentage"}:
            _add_error(errors, "discount_type", "Tipe diskon harus 'fixed' atau 'percentage'.")

    value = data.get("value")
    value_int = None
    if _is_blank(value):
        _add_error(errors, "value", "Nilai diskon wajib diisi.")
    else:
        try:
            value_int = int(value)
        except (ValueError, TypeError):
            _add_error(errors, "value", "Nilai diskon harus berupa angka bulat.")
        else:
            if value_int < 0:
                _add_error(errors, "value", "Nilai diskon tidak boleh negatif.")
            elif discount_type == "percentage" and value_int > 100:
                _add_error(errors, "value", "Diskon persentase tidak boleh lebih dari 100%.")

    minimum_order_amount = data.get("minimum_order_amount")
    if _is_blank(minimum_order_amount):
        minimum_order_amount = 0
    else:
        try:
            minimum_order_amount = int(minimum_order_amount)
        except (ValueError, TypeError):
            _add_error(errors, "minimum_order_amount", "Minimum order harus berupa angka bulat.")
            minimum_order_amount = 0
    if isinstance(minimum_order_amount, int) and minimum_order_amount < 0:
        _add_error(errors, "minimum_order_amount", "Minimum order tidak boleh negatif.")

    maximum_discount_amount = data.get("maximum_discount_amount")
    maximum_discount_amount_int = None
    if not _is_blank(maximum_discount_amount):
        try:
            maximum_discount_amount_int = int(maximum_discount_amount)
        except (ValueError, TypeError):
            _add_error(errors, "maximum_discount_amount", "Maksimal diskon harus berupa angka bulat.")
        else:
            if maximum_discount_amount_int < 0:
                _add_error(errors, "maximum_discount_amount", "Maksimal diskon tidak boleh negatif.")
            elif discount_type == "fixed" and value_int is not None and maximum_discount_amount_int < value_int:
                _add_error(
                    errors,
                    "maximum_discount_amount",
                    "Maksimal diskon untuk tipe fixed tidak boleh lebih kecil dari nilai diskon.",
                )

    name = data.get("name")
    if not _is_blank(name) and len(str(name).strip()) > 100:
        _add_error(errors, "name", "Nama diskon maksimal 100 karakter.")

    starts_at, err = _parse_datetime(data.get("starts_at"))
    if err:
        _add_error(errors, "starts_at", err)

    ends_at, err = _parse_datetime(data.get("ends_at"))
    if err:
        _add_error(errors, "ends_at", err)

    if starts_at is not None and ends_at is not None and ends_at < starts_at:
        _add_error(errors, "ends_at", "Tanggal berakhir tidak boleh lebih awal dari tanggal mulai.")

    is_active = data.get("is_active")
    if is_active is not None and _parse_bool(is_active) is None:
        _add_error(errors, "is_active", "Status aktif harus berupa boolean.")

    return errors
