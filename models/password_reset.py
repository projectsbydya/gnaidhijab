from datetime import datetime
from . import db


OTP_MAX_ATTEMPTS = 5


class PasswordReset(db.Model):
    __tablename__ = "password_resets"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), nullable=False, index=True)
    otp = db.Column(db.String(6), nullable=False)
    reset_token = db.Column(db.String(64), nullable=True, unique=True)
    expires_at = db.Column(db.DateTime, nullable=False)
    used = db.Column(db.Boolean, default=False, nullable=False)
    failed_attempts = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def is_expired(self):
        return datetime.utcnow() > self.expires_at

    def is_locked(self):
        return self.failed_attempts >= OTP_MAX_ATTEMPTS
