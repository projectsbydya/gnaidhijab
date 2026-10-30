from . import db


class VariantImage(db.Model):
    __tablename__ = "variant_images"

    id = db.Column(db.Integer, primary_key=True)
    variant_id = db.Column(db.Integer, db.ForeignKey("product_variants.id"), nullable=False)
    image_path = db.Column(db.String(255), nullable=False)
    alt_text = db.Column(db.String(200), nullable=True)
    sort_order = db.Column(db.Integer, nullable=False, default=0)

    variant = db.relationship("ProductVariant", back_populates="images")
