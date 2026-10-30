"""Encryption and security utilities."""
import hashlib
import bleach
from cryptography.fernet import Fernet
import base64


# Allowed HTML tags for rich text fields (product descriptions, care guides)
ALLOWED_HTML_TAGS = ['p', 'br', 'strong', 'em', 'b', 'i', 'ul', 'ol', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6']
ALLOWED_HTML_ATTRS = {
    '*': ['class'],
    'a': ['href', 'title'],
    'img': ['src', 'alt', 'width', 'height'],
}
ALLOWED_PROTOCOLS = ['http', 'https', 'mailto', 'tel']


def sanitize_html(html_content: str | None) -> str | None:
    """Sanitize HTML content for safe rendering with |safe filter.
    
    Removes dangerous tags like script, style, iframe while keeping
    basic formatting tags (p, strong, em, lists, etc.).
    
    Returns None if input is None or empty after stripping.
    """
    if not html_content:
        return None
    
    # Strip tags not in allowed list
    cleaned = bleach.clean(
        html_content,
        tags=ALLOWED_HTML_TAGS,
        attributes=ALLOWED_HTML_ATTRS,
        protocols=ALLOWED_PROTOCOLS,
        strip=True,
    )
    
    # Return None if result is empty or just whitespace
    return cleaned.strip() if cleaned.strip() else None


def get_fernet_key(secret_key):
    """Generate a Fernet key from Flask SECRET_KEY."""
    # Fernet requires 32 bytes base64-encoded key
    key = hashlib.sha256(secret_key.encode()).digest()
    return base64.urlsafe_b64encode(key)


class AddressCrypto:
    """Encrypt/decrypt user addresses."""
    
    def __init__(self, secret_key):
        self.fernet = Fernet(get_fernet_key(secret_key))
    
    def encrypt(self, address):
        """Encrypt an address string."""
        if not address:
            return None
        return self.fernet.encrypt(address.encode()).decode()
    
    def decrypt(self, encrypted_address):
        """Decrypt an encrypted address string."""
        if not encrypted_address:
            return None
        try:
            return self.fernet.decrypt(encrypted_address.encode()).decode()
        except Exception:
            return None
