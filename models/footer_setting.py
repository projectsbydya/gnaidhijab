from datetime import datetime
from . import db


class FooterSetting(db.Model):
    __tablename__ = "footer_settings"

    id = db.Column(db.Integer, primary_key=True)

    # Kolom "Tentang Kami"
    about_text = db.Column(db.Text, nullable=True)

    # Informasi operasional
    operating_hours = db.Column(db.String(255), nullable=True, default="Senin - Sabtu (08.00 - 17.00)")

    # Copyright text (optional override; default pakai STORE_NAME dari config)
    copyright_text = db.Column(db.String(255), nullable=True)

    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @classmethod
    def get(cls):
        """Get footer setting (singleton). Creates default row if not exists."""
        setting = cls.query.first()
        if not setting:
            setting = cls()
            db.session.add(setting)
            db.session.commit()
        return setting
