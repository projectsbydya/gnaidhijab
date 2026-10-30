"""Centralized backend validation for product data.

This module is intentionally decoupled from UI, templates, and routes. It can be
reused by the admin panel, API endpoints, or any other backend process.
"""

from typing import Any, Optional
from urllib.parse import urlparse


_MAX_URL_LENGTH = 1000
_ALLOWED_SCHEMES = {"http", "https"}


class ProductValidationError(ValueError):
    """Raised when product data fails validation."""

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


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def validate_url(
    value: Any,
    *,
    max_length: int = _MAX_URL_LENGTH,
    allowed_schemes: Optional[set[str]] = None,
) -> Optional[str]:
    """Validate a single URL string.

    Args:
        value: The URL value to validate.
        max_length: Maximum allowed URL length.
        allowed_schemes: Set of permitted URL schemes. Defaults to http/https.

    Returns:
        An error message string if invalid, otherwise None.
    """
    if _is_blank(value):
        return None

    text = str(value).strip()
    if len(text) > max_length:
        return f"URL maksimal {max_length} karakter."

    try:
        parsed = urlparse(text)
    except ValueError:
        return "Format URL tidak valid."

    schemes = allowed_schemes or _ALLOWED_SCHEMES
    if parsed.scheme not in schemes:
        return "URL harus menggunakan scheme http atau https."
    if not parsed.netloc:
        return "URL harus memiliki domain."

    return None


def validate_product_urls(data: dict[str, Any]) -> dict[str, list[str]]:
    """Validate product marketplace URLs.

    Args:
        data: Dictionary containing product URL fields (e.g. from a form or API
            payload). Recognized keys: shopee_url, shopee_affiliate_url.

    Returns:
        Dictionary mapping field names to lists of error messages. An empty
        dictionary means the data is valid.
    """
    errors: dict[str, list[str]] = {}

    for field in ("shopee_url", "shopee_affiliate_url"):
        value = data.get(field)
        if not _is_blank(value):
            err = validate_url(value)
            if err:
                _add_error(errors, field, err)

    return errors


def validate_product_urls_or_raise(data: dict[str, Any]) -> None:
    """Validate product URL data and raise ProductValidationError if invalid."""
    errors = validate_product_urls(data)
    if errors:
        raise ProductValidationError(errors)
