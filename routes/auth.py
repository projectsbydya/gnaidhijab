from datetime import datetime, timedelta
import bcrypt
import secrets

from flask import Blueprint, current_app, jsonify, render_template, request, redirect, url_for, flash, session
from werkzeug.security import check_password_hash
from extensions import limiter
from models import db
from services.email_service import send_welcome_email, send_otp_email
from services.cart_service import merge_guest_cart_into_db, load_db_cart_into_session
from models.password_reset import PasswordReset, OTP_MAX_ATTEMPTS
from models.user import User
from routes.utils import login_required

auth_bp = Blueprint("auth", __name__)


def _mask_email(email: str) -> str:
    if not email or "@" not in email:
        return "***"
    local, domain = email.split("@", 1)
    return local[:2] + "***@" + domain


def hash_password(password: str) -> str:
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(password: str, stored_hash: str) -> bool:
    if stored_hash.startswith("$2b$") or stored_hash.startswith("$2a$"):
        return bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8"))
    return check_password_hash(stored_hash, password)


def generate_otp() -> str:
    return "".join(str(secrets.randbelow(10)) for _ in range(6))


def get_input(key: str) -> str:
    if request.is_json:
        data = request.get_json(silent=True) or {}
        return (data.get(key) or "").strip()
    return (request.form.get(key) or "").strip()


@auth_bp.route("/register", methods=["GET", "POST"])
@limiter.limit("3 per hour", methods=["POST"])
def register():
    if session.get("user_id"):
        return redirect(url_for("shop.index"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        password_confirmation = request.form.get("password_confirmation", "")
        phone = request.form.get("phone", "").strip()
        
        # Get all address fields from form
        street_address = request.form.get("street_address", "").strip()
        village = request.form.get("village", "").strip()
        subdistrict = request.form.get("subdistrict", "").strip()
        city = request.form.get("city", "").strip()
        province = request.form.get("province", "").strip()
        postal_code = request.form.get("postal_code", "").strip()
        
        # Build complete address string: Street, Village, Subdistrict, City, Province, Postal Code
        address_parts = []
        if street_address:
            address_parts.append(street_address)
        if village:
            address_parts.append(village)
        if subdistrict:
            address_parts.append(subdistrict)
        if city:
            address_parts.append(city)
        if province:
            address_parts.append(province)
        if postal_code:
            address_parts.append(postal_code)
        
        final_address = ", ".join(address_parts) if address_parts else None

        if not name or not email or not password or not password_confirmation:
            flash("Semua kolom wajib diisi.", "danger")
        elif password != password_confirmation:
            flash("Password dan konfirmasi password tidak sama.", "danger")
        else:
            existing_user = User.query.filter_by(email=email).first()
            if existing_user:
                flash("Email sudah terdaftar.", "danger")
            else:
                # Get secret key for address encryption
                from utils.crypto import AddressCrypto
                secret_key = current_app.config["SECRET_KEY"]
                
                user = User(
                    name=name,
                    email=email,
                    password=hash_password(password),
                    phone=phone or None,
                    address=final_address,  # Keep plain text for backward compatibility
                    role="user",
                )
                # Encrypt and set address and postal code
                user.set_encrypted_address(final_address, secret_key, postal_code)
                
                db.session.add(user)
                db.session.commit()
                send_welcome_email(user)
                flash("Registrasi berhasil. Silakan login.", "success")
                return redirect(url_for("auth.login"))

    return render_template("auth/register.html")


@auth_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    user = User.query.get_or_404(session["user_id"])
    if request.method == "POST":
        user.name = request.form.get("name", user.name).strip()
        user.phone = request.form.get("phone", user.phone).strip() or None
        
        # Get all address fields from form
        street_address = request.form.get("street_address", "").strip()
        village = request.form.get("village", "").strip()
        subdistrict = request.form.get("subdistrict", "").strip()
        city = request.form.get("city", "").strip()
        province = request.form.get("province", "").strip()
        postal_code = request.form.get("postal_code", "").strip()
        
        # Build complete address string: Street, Village, Subdistrict, City, Province, Postal Code
        address_parts = []
        if street_address:
            address_parts.append(street_address)
        if village:
            address_parts.append(village)
        if subdistrict:
            address_parts.append(subdistrict)
        if city:
            address_parts.append(city)
        if province:
            address_parts.append(province)
        if postal_code:
            address_parts.append(postal_code)
        
        final_address = ", ".join(address_parts) if address_parts else None
        
        user.address = final_address  # Keep plain text for backward compatibility
        
        # Encrypt the address and postal code for security
        if final_address:
            from utils.crypto import AddressCrypto
            secret_key = current_app.config["SECRET_KEY"]
            user.set_encrypted_address(final_address, secret_key, postal_code)
        else:
            user.encrypted_address = None
            user.encrypted_postal_code = None
        
        db.session.commit()
        session["user_name"] = user.name
        flash("Profil berhasil diperbarui.", "success")
        return redirect(url_for("auth.profile"))

    # Decrypt address for display
    from utils.crypto import AddressCrypto
    secret_key = current_app.config["SECRET_KEY"]
    address_crypto = AddressCrypto(secret_key)
    decrypted_address = address_crypto.decrypt(user.encrypted_address) if user.encrypted_address else user.address
    
    return render_template("auth/profile.html", user=user, decrypted_address=decrypted_address)


@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per 15 minutes", methods=["POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("shop.index"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()
        if user and verify_password(password, user.password):
            session["user_id"] = user.id
            session["user_name"] = user.name
            session["user_role"] = user.role
            # Merge any items the guest added before login, then restore full DB cart.
            merge_guest_cart_into_db(user.id)
            load_db_cart_into_session(user.id)
            flash("Login berhasil.", "success")
            if user.role in ("admin", "staff"):
                return redirect(url_for("admin.dashboard"))
            return redirect(url_for("shop.index"))
        flash("Email atau password salah.", "danger")

    return render_template("auth/login.html")


@auth_bp.route("/request-reset-password", methods=["GET", "POST"])
@limiter.limit("5 per hour", methods=["POST"])
def request_reset_password():
    if request.method == "GET":
        return render_template("auth/forgot_password.html")

    email = get_input("email").lower()
    if not email:
        error = "Email harus diisi untuk meminta OTP."
        if request.is_json:
            return jsonify({"error": error}), 400
        flash(error, "danger")
        return redirect(url_for("auth.request_reset_password"))

    user = User.query.filter_by(email=email).first()
    if not user:
        if request.is_json:
            return jsonify({"error": "Email tidak terdaftar."}), 404
        flash("Email tidak terdaftar.", "danger")
        return redirect(url_for("auth.request_reset_password"))

    window_start = datetime.utcnow() - timedelta(minutes=1)
    recent_count = PasswordReset.query.filter(
        PasswordReset.email == email,
        PasswordReset.created_at >= window_start,
    ).count()
    if recent_count >= 3:
        error = "Batas pengiriman OTP tercapai. Silakan coba lagi setelah 1 menit."
        if request.is_json:
            return jsonify({"error": error}), 429
        flash(error, "warning")
        return redirect(url_for("auth.request_reset_password"))

    # Invalidate all previous unused OTPs for this email
    PasswordReset.query.filter_by(email=email, used=False).update({"used": True})
    db.session.commit()

    otp = generate_otp()
    expires_at = datetime.utcnow() + timedelta(minutes=5)
    reset_entry = PasswordReset(
        email=email,
        otp=otp,
        expires_at=expires_at,
        used=False,
    )
    db.session.add(reset_entry)
    db.session.commit()

    sent = send_otp_email(email, user.name, otp)
    if not sent:
        if request.is_json:
            return jsonify({"error": "Gagal mengirim email. Periksa konfigurasi SMTP."}), 500
        flash("Gagal mengirim email OTP. Periksa konfigurasi SMTP.", "danger")
        return redirect(url_for("auth.request_reset_password"))

    message = "OTP telah dikirim ke email Anda."
    if request.is_json:
        return jsonify({"message": message, "expires_in": 300}), 200
    flash(message, "success")
    return redirect(url_for("auth.verify_otp", email=email))


@auth_bp.route("/verify-otp", methods=["GET", "POST"])
@limiter.limit("5 per hour", methods=["POST"])
def verify_otp():
    email = request.args.get("email", "")
    if request.method == "GET":
        return render_template("auth/verify_otp.html", email=email)

    email = get_input("email").lower()
    otp = get_input("otp")

    if not email or not otp:
        error = "Email dan OTP harus diisi."
        if request.is_json:
            return jsonify({"error": error}), 400
        flash(error, "danger")
        return redirect(url_for("auth.verify_otp", email=email))

    reset_entry = PasswordReset.query.filter_by(email=email, used=False).order_by(PasswordReset.created_at.desc()).first()

    if not reset_entry or reset_entry.is_expired():
        error = "OTP tidak valid atau sudah kedaluwarsa."
        if request.is_json:
            return jsonify({"error": error}), 400
        flash(error, "danger")
        return redirect(url_for("auth.verify_otp", email=email))

    if reset_entry.is_locked():
        error = "Terlalu banyak percobaan OTP salah. Silakan minta OTP baru."
        if request.is_json:
            return jsonify({"error": error}), 429
        flash(error, "danger")
        return redirect(url_for("auth.verify_otp", email=email))

    if reset_entry.otp != otp:
        reset_entry.failed_attempts += 1
        db.session.commit()
        if reset_entry.is_locked():
            error = "Terlalu banyak percobaan OTP salah. Silakan minta OTP baru."
            if request.is_json:
                return jsonify({"error": error}), 429
        else:
            remaining = OTP_MAX_ATTEMPTS - reset_entry.failed_attempts
            error = f"OTP tidak valid atau sudah kedaluwarsa. Sisa percobaan: {remaining}."
            if request.is_json:
                return jsonify({"error": error}), 400
        flash(error, "danger")
        return redirect(url_for("auth.verify_otp", email=email))

    session["password_reset_email"] = email
    session["password_reset_entry_id"] = reset_entry.id
    flash("OTP valid. Silakan isi password baru.", "success")
    return redirect(url_for("auth.reset_password"))


@auth_bp.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    verified_email = session.get("password_reset_email")
    reset_entry_id = session.get("password_reset_entry_id")
    if not verified_email or not reset_entry_id:
        flash("Silakan verifikasi OTP terlebih dahulu.", "warning")
        return redirect(url_for("auth.verify_otp"))

    if request.method == "GET":
        return render_template("auth/reset_password.html", email=verified_email)

    new_password = get_input("new_password")
    confirm_password = get_input("confirm_password")

    if not new_password or not confirm_password:
        error = "Semua kolom password harus diisi."
        if request.is_json:
            return jsonify({"error": error}), 400
        flash(error, "danger")
        return redirect(url_for("auth.reset_password"))

    if new_password != confirm_password:
        error = "Password baru dan konfirmasi tidak cocok."
        if request.is_json:
            return jsonify({"error": error}), 400
        flash(error, "danger")
        return redirect(url_for("auth.reset_password"))

    reset_entry = PasswordReset.query.get(reset_entry_id)
    if not reset_entry or reset_entry.used or reset_entry.is_expired() or reset_entry.email != verified_email:
        error = "OTP sudah tidak valid. Silakan ulangi proses reset password."
        if request.is_json:
            return jsonify({"error": error}), 400
        flash(error, "danger")
        session.pop("password_reset_email", None)
        session.pop("password_reset_entry_id", None)
        return redirect(url_for("auth.request_reset_password"))

    user = User.query.filter_by(email=verified_email).first()
    if not user:
        error = "Email tidak ditemukan."
        if request.is_json:
            return jsonify({"error": error}), 404
        flash(error, "danger")
        return redirect(url_for("auth.request_reset_password"))

    user.password = hash_password(new_password)
    reset_entry.used = True
    db.session.commit()
    session.pop("password_reset_email", None)
    session.pop("password_reset_entry_id", None)

    message = "Password berhasil diubah. Silakan login dengan password baru Anda."
    if request.is_json:
        return jsonify({"message": message}), 200
    flash(message, "success")
    return redirect(url_for("auth.login"))


@auth_bp.route("/logout")
def logout():
    session.clear()
    flash("Anda berhasil logout.", "success")
    return redirect(url_for("shop.index"))
