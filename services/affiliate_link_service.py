"""Internal-only service for managing product affiliate links.

This module provides the only supported code path for reading or writing
`Product.shopee_affiliate_url`. It is intentionally decoupled from admin routes
and templates so that the affiliate URL is never exposed or modified through
the admin UI/API.

All admin-facing product flows should ignore this field entirely.
"""

from typing import Optional

from models import db
from models.product import Product
from services.product_validator import validate_url


class AffiliateLinkError(ValueError):
    """Raised when affiliate link data fails validation or lookup."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def _resolve_product(product: Product | int) -> Product:
    if isinstance(product, Product):
        return product
    product_obj = Product.query.get(product)
    if product_obj is None:
        raise AffiliateLinkError("Produk tidak ditemukan.")
    return product_obj


def get_shopee_affiliate_url(product: Product | int) -> Optional[str]:
    """Return the internal Shopee affiliate URL for a product, or None.

    Args:
        product: Product instance or product ID.

    Returns:
        The stored affiliate URL, or None if not set.

    Raises:
        AffiliateLinkError: If the product cannot be found.
    """
    return _resolve_product(product).shopee_affiliate_url


def set_shopee_affiliate_url(
    product: Product | int,
    url: Optional[str],
    *,
    updated_by: Optional[str] = None,
) -> None:
    """Set or clear a product's internal Shopee affiliate URL.

    This function performs URL validation and should be the only internal path
    that mutates `Product.shopee_affiliate_url`.

    Args:
        product: Product instance or product ID.
        url: Affiliate URL, or None/empty string to clear the value.
        updated_by: Optional identifier of the caller for audit/logging.

    Raises:
        AffiliateLinkError: If validation fails or the product cannot be found.
    """
    product_obj = _resolve_product(product)

    if not url or not str(url).strip():
        product_obj.shopee_affiliate_url = None
        return

    error = validate_url(url)
    if error:
        raise AffiliateLinkError(error)

    product_obj.shopee_affiliate_url = str(url).strip()
    db.session.add(product_obj)
