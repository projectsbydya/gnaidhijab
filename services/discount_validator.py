"""Centralized backend validation for product discount data.

This module is intentionally decoupled from UI, templates, and routes. It can be
reused by the admin panel, API endpoints, or any other backend process.
"""

from datetime import datetime, timezone
from typing import Any, Optional

from models.product import Product
from models.product_discount import ProductDiscount


_ALLOWED_TYPES = {"percentage", "fixed"}
_MAX_NAME_LENGTH = 100
_DATETIME_FORMATS = [
    "%Y-%m-%dT%H:%M",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
]


class DiscountValidationError(ValueError):
    """Raised when discount data fails validation."""

    def __init__(self, errors: dict[str, list[str]]):
        self.errors = errors
        super().__init__(self._format_errors(errors))

    @staticmethod
    def _format_errors(errors: dict[str, list[str]]) -> str:
        return "; ".join(
            f"{field}: {', '.join(messages)}"
            for field, messages in errors.items()
        )


def _add_error(errors: dict[str, list[str]], field: str, message: str) -> None:
    errors.setdefault(field, []).append(message)


def _to_naive_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Convert a timezone-aware datetime to naive UTC; leave naive as-is."""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _parse_bool(value: Any) -> Optional[bool]:
    """Parse a boolean value. Returns None for unrecognised input."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return bool(value)
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"true", "1", "on", "yes"}:
        return True
    if text in {"false", "0", "off", "no", ""}:
        return False
    return None


def _parse_datetime(value: Any) -> tuple[Optional[datetime], Optional[str]]:
    """Parse a datetime value. Returns (datetime, None) or (None, error_message)."""
    if value is None or (isinstance(value, str) and value.strip() == ""):
        return None, None
    if isinstance(value, datetime):
        return _to_naive_utc(value), None
    text = str(value).strip()
    for fmt in _DATETIME_FORMATS:
        try:
            return datetime.strptime(text, fmt), None
        except ValueError:
            continue
    return None, "Format tanggal tidak valid."


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def validate_product_discount(
    data: dict[str, Any],
    *,
    require_product: bool = True,
    exclude_discount_id: Optional[int] = None,
) -> dict[str, list[str]]:
    """Validate product discount data.

    Args:
        data: Dictionary of discount fields (e.g. from a form or API payload).
        require_product: Whether to validate and require a product_id.
        exclude_discount_id: Discount ID to ignore when checking for duplicate
            product discounts (useful for updates).

    Returns:
        Dictionary mapping field names to lists of error messages. An empty
        dictionary means the data is valid.
    """
    errors: dict[str, list[str]] = {}

    # ── discount_type ─────────────────────────────────────────────────────────
    discount_type = data.get("discount_type")
    if _is_blank(discount_type):
        _add_error(errors, "discount_type", "Tipe diskon wajib diisi.")
    else:
        discount_type = str(discount_type).strip().lower()
        if discount_type not in _ALLOWED_TYPES:
            _add_error(errors, "discount_type", "Tipe diskon harus 'percentage' atau 'fixed'.")

    # ── value ─────────────────────────────────────────────────────────────────
    value = data.get("value")
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
            if discount_type == "percentage" and value_int > 100:
                _add_error(errors, "value", "Diskon persentase tidak boleh lebih dari 100%.")

    # ── is_active ─────────────────────────────────────────────────────────────
    is_active = data.get("is_active")
    if is_active is not None:
        parsed = _parse_bool(is_active)
        if parsed is None:
            _add_error(errors, "is_active", "Status aktif harus berupa boolean.")

    # ── name ───────────────────────────────────────────────────────────────────
    name = data.get("name")
    if not _is_blank(name) and len(str(name).strip()) > _MAX_NAME_LENGTH:
        _add_error(errors, "name", f"Nama diskon maksimal {_MAX_NAME_LENGTH} karakter.")

    # ── period ───────────────────────────────────────────────────────────────
    starts_at, err = _parse_datetime(data.get("starts_at"))
    if err:
        _add_error(errors, "starts_at", err)

    ends_at, err = _parse_datetime(data.get("ends_at"))
    if err:
        _add_error(errors, "ends_at", err)

    if starts_at is not None and ends_at is not None and ends_at < starts_at:
        _add_error(errors, "ends_at", "Tanggal berakhir tidak boleh lebih awal dari tanggal mulai.")

    # ── product_id ─────────────────────────────────────────────────────────────
    product_id = data.get("product_id")
    if require_product:
        if _is_blank(product_id):
            _add_error(errors, "product_id", "Produk wajib dipilih.")
        else:
            try:
                product_id_int = int(product_id)
            except (ValueError, TypeError):
                _add_error(errors, "product_id", "ID produk harus berupa angka.")
            else:
                if product_id_int <= 0:
                    _add_error(errors, "product_id", "ID produk tidak valid.")
                elif Product.query.get(product_id_int) is None:
                    _add_error(errors, "product_id", "Produk tidak ditemukan.")
                else:
                    existing = ProductDiscount.query.filter_by(
                        product_id=product_id_int
                    ).first()
                    if existing and (
                        exclude_discount_id is None or existing.id != exclude_discount_id
                    ):
                        _add_error(
                            errors,
                            "product_id",
                            "Produk ini sudah memiliki konfigurasi diskon.",
                        )

    return errors


def validate_product_discount_or_raise(
    data: dict[str, Any],
    *,
    require_product: bool = True,
    exclude_discount_id: Optional[int] = None,
) -> None:
    """Validate discount data and raise DiscountValidationError if invalid."""
    errors = validate_product_discount(
        data,
        require_product=require_product,
        exclude_discount_id=exclude_discount_id,
    )
    if errors:
        raise DiscountValidationError(errors)
