from datetime import datetime
from . import db


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(50), nullable=True)
    address = db.Column(db.Text, nullable=True)  # Legacy plain text (deprecated)
    encrypted_address = db.Column(db.Text, nullable=True)  # Encrypted full address
    encrypted_postal_code = db.Column(db.String(255), nullable=True)  # Encrypted postal code
    role = db.Column(db.String(20), nullable=False, default="user")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    orders = db.relationship("Order", back_populates="user", lazy=True)
    cart = db.relationship("Cart", back_populates="user", uselist=False, lazy=True, cascade="all, delete-orphan")

    def is_admin(self):
        return self.role == "admin"

    def get_decrypted_address(self, secret_key):
        """Get decrypted address using the application's secret key."""
        if not self.encrypted_address:
            return self.address  # Fallback to legacy plain text
        from utils.crypto import AddressCrypto
        crypto = AddressCrypto(secret_key)
        return crypto.decrypt(self.encrypted_address)

    def get_decrypted_postal_code(self, secret_key):
        """Get decrypted postal code using the application's secret key."""
        if not self.encrypted_postal_code:
            return None
        from utils.crypto import AddressCrypto
        crypto = AddressCrypto(secret_key)
        return crypto.decrypt(self.encrypted_postal_code)

    def set_encrypted_address(self, plain_address, secret_key, postal_code=None):
        """Encrypt and set the address and optionally postal code."""
        from utils.crypto import AddressCrypto
        crypto = AddressCrypto(secret_key)
        if plain_address:
            self.encrypted_address = crypto.encrypt(plain_address)
        else:
            self.encrypted_address = None
        if postal_code:
            self.encrypted_postal_code = crypto.encrypt(postal_code)
        else:
            self.encrypted_postal_code = None
