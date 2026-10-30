from . import db


class ProductImage(db.Model):
    __tablename__ = "product_images"

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    image_path = db.Column(db.String(255), nullable=False)
    alt_text = db.Column(db.String(200), nullable=True)
    sort_order = db.Column(db.Integer, nullable=False, default=0)

    product = db.relationship("Product", back_populates="images")
