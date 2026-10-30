from datetime import datetime
from . import db

class CTASetting(db.Model):
    __tablename__ = "cta_settings"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False, default="Define Your Style")
    description = db.Column(db.Text, nullable=True, default="Discover modern modest fashion designed for the contemporary woman")
    button_text = db.Column(db.String(100), nullable=False, default="Shop Collection")
    button_link = db.Column(db.String(255), nullable=False, default="/products")
    background_image = db.Column(db.String(255), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<CTASetting {self.title}>"

    @classmethod
    def get_active(cls):
        """Get the active CTA setting, or None if not found"""
        return cls.query.filter_by(is_active=True).first()
