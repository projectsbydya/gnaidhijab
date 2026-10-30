from flask_sqlalchemy import SQLAlchemy

# central SQLAlchemy object

db = SQLAlchemy()

from .user import User
from .product import Product
from .product_image import ProductImage
from .product_variant import ProductVariant
from .variant_image import VariantImage
from .order import Order, OrderItem
from .order_status_log import OrderStatusLog
from .payment import Payment
from .cart import Cart, CartItem
from .product_slug_history import ProductSlugHistory
from .password_reset import PasswordReset
from .video import Video
from .cta_setting import CTASetting
from .footer_setting import FooterSetting
from .audit_log import AuditLog, log_admin_action
from .product_discount import ProductDiscount
from .shipping_discount import ShippingDiscount
