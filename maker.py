#!/usr/bin/env python3
"""
maker.py — Ultimate AppStore + IG Services + Support Chat + GitHub Storage
"""

import secrets
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
FILES: dict[str, str] = {}

# ---------------------------------------------------------------
FILES["requirements.txt"] = r"""Flask==3.0.3
Flask-SQLAlchemy==3.1.1
python-dotenv==1.0.1
Pillow==10.4.0
qrcode==7.4.2
pytesseract==0.3.10
gunicorn==21.2.0
requests==2.31.0
psycopg2-binary==2.9.9
"""

FILES["render.yaml"] = r"""services:
  - type: web
    name: viraj-store
    runtime: docker
    envVars:
      - key: SECRET_KEY
        generateValue: true
      - key: UPI_ID
        value: 9579059838@fam
      - key: UPI_NAME
        value: Viraj
      - key: SITE_NAME
        value: Viraj Store
      - key: GITHUB_TOKEN
        sync: false
      - key: GITHUB_REPO
        value: bodare207-ai/shop
      - key: DATABASE_URL
        sync: false
"""

FILES["Dockerfile"] = r"""FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

EXPOSE 8000
CMD ["gunicorn", "run:app", "--bind", "0.0.0.0:8000"]
"""

FILES["config.py"] = r"""import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

DATA_DIR = os.environ.get("DATA_DIR", str(BASE_DIR))
DATABASE_URL = os.environ.get("DATABASE_URL")

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-key-change-me")
    
    # Use PostgreSQL if DATABASE_URL is set (for Render persistence), else SQLite
    if DATABASE_URL:
        SQLALCHEMY_DATABASE_URI = DATABASE_URL.replace("postgres://", "postgresql://")
    else:
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{os.path.join(DATA_DIR, 'instance', 'store.db')}"
        
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    SESSION_COOKIE_SECURE   = os.environ.get("HTTPS", "false").lower() == "true"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 24 * 7

    MAX_CONTENT_LENGTH = 100 * 1024 * 1024 # 100 MB for big APKs

    UPI_ID      = os.environ.get("UPI_ID", "9579059838@fam")
    UPI_NAME    = os.environ.get("UPI_NAME", "Viraj")
    SITE_NAME   = os.environ.get("SITE_NAME", "Viraj Store")
    
    EXPECTED_NAMES = ["shivrudra", "viraj", "santosh", "bodare"]
    EXPECTED_UPI = "9579059838"

    DOWNLOAD_EXPIRY_DAYS = 30
    DOWNLOAD_MAX_COUNT   = 50

    GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
    GITHUB_REPO = os.environ.get("GITHUB_REPO", "")
"""

FILES["run.py"] = r"""from app import create_app

app = create_app()

if __name__ == "__main__":
    print("\n  ✅  Store:        http://localhost:5000")
    print("  ✅  Admin panel:  http://localhost:5000/admin\n")
    app.run(host="127.0.0.1", port=5000, debug=True)
"""

FILES["app/__init__.py"] = r"""import os
import qrcode
from pathlib import Path
from flask import Flask, render_template
from .extensions import db
from .utils import csrf_token, require_csrf

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("DATA_DIR", BASE_DIR))

def create_app():
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object("config.Config")

    dirs = [
        DATA_DIR / "instance", 
        DATA_DIR / "uploads", 
        DATA_DIR / "files", 
        BASE_DIR / "app" / "static" / "products"
    ]
    for d in dirs:
        os.makedirs(d, exist_ok=True)

    app.config["UPLOAD_FOLDER"] = str(DATA_DIR / "uploads")
    app.config["FILES_FOLDER"]  = str(DATA_DIR / "files")
    app.config["PRODUCTS_IMG_FOLDER"] = str(BASE_DIR / "app" / "static" / "products")

    db.init_app(app)

    from .store import bp as store_bp
    from .admin import bp as admin_bp
    from .auth import bp as auth_bp
    
    app.register_blueprint(store_bp)
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(auth_bp, url_prefix="/auth")

    app.jinja_env.globals["csrf_token"] = csrf_token
    app.jinja_env.globals["SITE_NAME"]  = app.config["SITE_NAME"]
    app.jinja_env.filters["from_json"] = lambda x: __import__("json").loads(x) if x else []

    @app.before_request
    def _before():
        require_csrf()

    @app.after_request
    def _headers(resp):
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "same-origin"
        return resp

    @app.errorhandler(404)
    def _404(e):
        return render_template("errors/error.html", code=404, msg="Page not found."), 404

    @app.errorhandler(413)
    def _413(e):
        return render_template("errors/error.html", code=413, msg="File too large."), 413

    @app.errorhandler(400)
    def _400(e):
        return render_template("errors/error.html", code=400, msg=str(e.description)), 400

    with app.app_context():
        db.create_all()
        _bootstrap()
        _generate_qr(app)
        _generate_default_image(app)

    return app

def _bootstrap():
    from .models import Product
    if Product.query.count() == 0:
        p1 = Product(name="Premium Android App", slug="premium-android-app", category="App",
                description="The ultimate tool for your phone.", price=149, download_url="https://example.com/app.apk", images='["default.jpg"]')
        p2 = Product(name="Instagram Followers (1000)", slug="ig-followers", category="IG",
                description="High quality IG followers.", price=0.50, is_ig_service=True, download_url="N/A", images='["default.jpg"]')
        db.session.add(p1)
        db.session.add(p2)
        db.session.commit()

def _generate_qr(app):
    qr_path = BASE_DIR / "app" / "static" / "qr.png"
    upi_id = app.config["UPI_ID"]
    upi_name = app.config["UPI_NAME"]
    upi_link = f"upi://pay?pa={upi_id}&pn={upi_name}&cu=INR"
    
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=4)
    qr.add_data(upi_link)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    img.save(qr_path)

def _generate_default_image(app):
    from PIL import Image, ImageDraw
    default_path = Path(app.config["PRODUCTS_IMG_FOLDER"]) / "default.jpg"
    if not default_path.exists():
        img = Image.new('RGB', (400, 300), color=(22, 29, 46))
        d = ImageDraw.Draw(img)
        d.text((150, 140), "No Image", fill=(147, 162, 186))
        img.save(default_path, "JPEG")
"""

FILES["app/extensions.py"] = r"""from flask_sqlalchemy import SQLAlchemy
db = SQLAlchemy()
"""

FILES["app/models.py"] = r"""import secrets
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from .extensions import db

class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(190), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, pw): self.password_hash = generate_password_hash(pw)
    def check_password(self, pw): return check_password_hash(self.password_hash, pw)

class Admin(db.Model):
    __tablename__ = "admins"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, pw): self.password_hash = generate_password_hash(pw)
    def check_password(self, pw): return check_password_hash(self.password_hash, pw)

class Product(db.Model):
    __tablename__ = "products"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(220), unique=True, nullable=False)
    category = db.Column(db.String(50), default="App") # App, Game, IG
    description = db.Column(db.Text, default="")
    price = db.Column(db.Numeric(10, 2), nullable=False)
    is_ig_service = db.Column(db.Boolean, default=False) # If True, user inputs quantity
    
    images = db.Column(db.Text, default='["default.jpg"]') 
    file_path = db.Column(db.String(255))
    download_url = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Order(db.Model):
    __tablename__ = "orders"
    id = db.Column(db.Integer, primary_key=True)
    order_code = db.Column(db.String(32), unique=True, nullable=False)
    public_token = db.Column(db.String(64), unique=True, nullable=False)
    
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    user = db.relationship("User")
    
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    product = db.relationship("Product")
    
    quantity = db.Column(db.Integer, default=1)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    status = db.Column(db.String(20), default="pending", nullable=False, index=True)
    screenshot_path = db.Column(db.String(255))
    ocr_text = db.Column(db.Text)
    admin_note = db.Column(db.String(500))
    
    download_token = db.Column(db.String(64), unique=True, index=True)
    download_expires_at = db.Column(db.DateTime)
    download_count = db.Column(db.Integer, default=0)
    approved_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    def generate_download(self, days=30):
        self.download_token = secrets.token_urlsafe(32)
        self.download_expires_at = datetime.utcnow() + timedelta(days=days)

class SupportMessage(db.Model):
    __tablename__ = "support_messages"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    user = db.relationship("User")
    is_admin = db.Column(db.Boolean, default=False)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
"""

FILES["app/utils.py"] = r"""import re, secrets, platform, base64, requests
from datetime import datetime
from functools import wraps
from flask import session, request, abort, redirect, url_for, current_app
from .extensions import db

try:
    import pytesseract
    from PIL import Image
    if platform.system() == 'Windows':
        pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
    HAS_OCR = True
except ImportError:
    HAS_OCR = False

def slugify(s):
    s = re.sub(r"[^\w\s-]", "", s.lower()).strip()
    return re.sub(r"[-\s]+", "-", s)

def csrf_token():
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]

def require_csrf():
    if request.method in ("POST", "PUT", "DELETE", "PATCH"):
        if not request.form.get("csrf") or request.form.get("csrf") != session.get("csrf"):
            abort(400, "Form expired — go back and reload.")

def user_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if "user_id" not in session:
            return redirect(url_for("auth.login", next=request.path))
        return fn(*a, **kw)
    return wrapper

def admin_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if "admin_id" not in session:
            return redirect(url_for("admin.login", next=request.path))
        return fn(*a, **kw)
    return wrapper

def current_user():
    from .models import User
    if "user_id" in session:
        return db.session.get(User, session["user_id"])
    return None

def client_ip():
    return request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip()

_rate_store = {}
def rate_limit(key, limit, window_seconds):
    now = datetime.utcnow().timestamp()
    entry = [t for t in _rate_store.get(key, []) if t > now - window_seconds]
    if len(entry) >= limit:
        _rate_store[key] = entry
        return False
    entry.append(now)
    _rate_store[key] = entry
    return True

def upload_to_github(filepath, filename):
    # Uploads file to GitHub repo via API so files don't delete on Render Free Tier
    token = current_app.config["GITHUB_TOKEN"]
    repo = current_app.config["GITHUB_REPO"]
    if not token or not repo:
        return False
        
    with open(filepath, "rb") as f:
        content = base64.b64encode(f.read()).decode("utf-8")
        
    url = f"https://api.github.com/repos/{repo}/contents/uploads/{filename}"
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}
    
    # Check if exists to get SHA
    res = requests.get(url, headers=headers)
    data = {"message": f"Upload {filename}", "content": content}
    if res.status_code == 200:
        data["sha"] = res.json()["sha"]
        
    res = requests.put(url, headers=headers, json=data)
    return res.status_code in (200, 201)

def verify_screenshot(filepath, expected_amount):
    if not HAS_OCR:
        return False, "OCR not installed."

    try:
        img = Image.open(filepath)
        img = img.convert('L') 
        raw_text = pytesseract.image_to_string(img).lower()
        clean_text = raw_text.replace(",", "").replace(" ", "")
        
        upi_match = current_app.config["EXPECTED_UPI"] in clean_text
        name_match = any(name in clean_text for name in current_app.config["EXPECTED_NAMES"])
        
        amt_str = f"{float(expected_amount):.2f}".rstrip('0').rstrip('.')
        amt_match = amt_str in clean_text or f"{float(expected_amount):.2f}" in clean_text
        
        if (upi_match or name_match) and amt_match:
            return True, raw_text
        return False, raw_text
    except Exception as e:
        return False, str(e)
"""

FILES["app/auth.py"] = r"""import re
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from .extensions import db
from .models import User

bp = Blueprint("auth", __name__)
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

@bp.route("/register", methods=["GET", "POST"])
def register():
    if session.get("user_id"): return redirect(url_for("store.home"))
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not name or not EMAIL_RE.match(email) or len(password) < 6:
            flash("Valid name, email, and password (6+ chars) are required.", "err")
        elif User.query.filter_by(email=email).first():
            flash("Email already registered. Please login.", "err")
        else:
            u = User(name=name, email=email)
            u.set_password(password)
            db.session.add(u)
            db.session.commit()
            session["user_id"] = u.id
            session["user_name"] = u.name
            flash("Account created! You are now logged in.", "ok")
            return redirect(request.args.get("next") or url_for("store.home"))
    return render_template("auth/register.html")

@bp.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"): return redirect(url_for("store.home"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        u = User.query.filter_by(email=email).first()
        if u and u.check_password(password):
            session["user_id"] = u.id
            session["user_name"] = u.name
            flash("Welcome back!", "ok")
            return redirect(request.args.get("next") or url_for("store.home"))
        flash("Invalid email or password.", "err")
    return render_template("auth/login.html")

@bp.route("/logout")
def logout():
    session.pop("user_id", None)
    session.pop("user_name", None)
    flash("Logged out successfully.", "ok")
    return redirect(url_for("store.home"))
"""

FILES["app/store.py"] = r"""import os, secrets, json
from datetime import datetime
from urllib.parse import quote
from flask import (Blueprint, render_template, request, redirect,
                   url_for, abort, current_app, send_from_directory, flash)
from .extensions import db
from .models import Product, Order, SupportMessage
from .utils import rate_limit, client_ip, current_user, user_required, verify_screenshot

bp = Blueprint("store", __name__)
ALLOWED_IMAGE = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}

@bp.route("/")
def home():
    category = request.args.get("cat", "All")
    if category in ("App", "Game", "IG"):
        products = Product.query.filter_by(is_active=True, category=category).all()
    else:
        products = Product.query.filter_by(is_active=True).all()
    return render_template("store/home.html", products=products, current_cat=category)

@bp.route("/p/<slug>")
def product(slug):
    p = Product.query.filter_by(slug=slug, is_active=True).first_or_404()
    already_bought = False
    u = current_user()
    if u and not p.is_ig_service:
        if Order.query.filter_by(user_id=u.id, product_id=p.id, status="approved").first():
            already_bought = True
            
    imgs = json.loads(p.images) if p.images else ["default.jpg"]
    return render_template("store/product.html", product=p, already_bought=already_bought, imgs=imgs)

@bp.route("/checkout", methods=["POST"])
@user_required
def checkout():
    u = current_user()
    p = Product.query.filter_by(id=request.form.get("product_id", type=int), is_active=True).first()
    if not p: abort(404)
    
    qty = int(request.form.get("quantity", 1)) if p.is_ig_service else 1
    total_amount = float(p.price) * qty

    o = Order(order_code="ORD-" + secrets.token_hex(4).upper(),
              public_token=secrets.token_urlsafe(24),
              user_id=u.id, product_id=p.id, amount=total_amount, quantity=qty)
    db.session.add(o)
    db.session.commit()
    return redirect(url_for("store.order_view", token=o.public_token))

@bp.route("/o/<token>", methods=["GET", "POST"])
@user_required
def order_view(token):
    o = Order.query.filter_by(public_token=token).first_or_404()
    err = ""
    if request.method == "POST":
        if o.status == "approved":
            err = "This order is already approved."
        else:
            f = request.files.get("screenshot")
            if not f or not f.filename:
                err = "Please choose your payment screenshot."
            else:
                ext = ALLOWED_IMAGE.get(f.mimetype)
                if not ext:
                    err = "Only JPG, PNG or WEBP allowed."
                else:
                    from PIL import Image
                    try:
                        img = Image.open(f); img.verify(); f.seek(0)
                    except Exception:
                        err = "Invalid image."
                    else:
                        fname = f"{o.id}_{secrets.token_hex(8)}.{ext}"
                        filepath = os.path.join(current_app.config["UPLOAD_FOLDER"], fname)
                        f.save(filepath)
                        
                        is_verified, ocr_text = verify_screenshot(filepath, o.amount)
                        o.screenshot_path = fname
                        o.ocr_text = ocr_text
                        
                        if is_verified:
                            o.status = "approved"
                            o.approved_at = datetime.utcnow()
                            o.generate_download(current_app.config["DOWNLOAD_EXPIRY_DAYS"])
                            db.session.commit()
                            flash("Payment verified automatically! Download unlocked.", "ok")
                            return redirect(url_for("store.my_downloads"))
                        else:
                            o.status = "pending"
                            db.session.commit()
                            return redirect(url_for("store.order_view", token=token) + "?uploaded=1")

    upi = ("upi://pay?pa={pa}&pn={pn}&am={am}&cu=INR&tn={tn}").format(
        pa=quote(current_app.config["UPI_ID"]),
        pn=quote(current_app.config["UPI_NAME"]),
        am=f"{float(o.amount):.2f}",
        tn=quote(o.order_code),
    )
    return render_template("store/order.html", order=o, upi=upi, err=err)

@bp.route("/my-downloads")
@user_required
def my_downloads():
    u = current_user()
    orders = Order.query.filter_by(user_id=u.id, status="approved").order_by(Order.approved_at.desc()).all()
    return render_template("store/my_downloads.html", orders=orders)

@bp.route("/d/<token>")
def download_page(token):
    o = Order.query.filter_by(download_token=token).first_or_404()
    if o.status != "approved": abort(403)
    if not o.download_expires_at or datetime.utcnow() > o.download_expires_at:
        abort(400, "This download link has expired.")
    o.download_count += 1
    db.session.commit()
    p = o.product
    if p.file_path:
        return send_from_directory(current_app.config["FILES_FOLDER"], p.file_path, as_attachment=True)
    if p.download_url:
        return render_template("store/download.html", order=o, url=p.download_url)
    abort(404)

@bp.route("/uploads/<path:name>")
def upload_file(name):
    return send_from_directory(current_app.config["UPLOAD_FOLDER"], name)

@bp.route("/uploads/products/<path:name>")
def product_image(name):
    return send_from_directory(current_app.config["PRODUCTS_IMG_FOLDER"], name)

# --- SUPPORT CHAT ---
@bp.route("/support", methods=["GET", "POST"])
@user_required
def support():
    u = current_user()
    if request.method == "POST":
        msg = request.form.get("message", "").strip()
        if msg:
            db.session.add(SupportMessage(user_id=u.id, message=msg, is_admin=False))
            db.session.commit()
            return redirect(url_for("store.support"))
            
    messages = SupportMessage.query.filter_by(user_id=u.id).order_by(SupportMessage.created_at.asc()).all()
    return render_template("store/support.html", messages=messages)
"""

FILES["app/admin.py"] = r"""import os, secrets, json
from datetime import datetime
from flask import (Blueprint, render_template, request, redirect,
                   url_for, session, abort, flash, current_app)
from sqlalchemy import func
from .extensions import db
from .models import Admin, Product, Order, User, SupportMessage
from .utils import admin_required, slugify, upload_to_github

bp = Blueprint("admin", __name__)
ALLOWED_PRODUCT_EXT = {".apk", ".zip", ".pdf", ".exe", ".dmg", ".mp4", ".rar", ".7z"}
ALLOWED_IMG_EXT = {".jpg", ".jpeg", ".png", ".webp"}

@bp.route("/")
def index():
    return redirect(url_for("admin.dashboard")) if "admin_id" in session else redirect(url_for("admin.login"))

@bp.route("/login", methods=["GET", "POST"])
def login():
    if Admin.query.count() == 0: return redirect(url_for("admin.setup"))
    if "admin_id" in session: return redirect(url_for("admin.dashboard"))
    err = ""
    if request.method == "POST":
        a = Admin.query.filter_by(username=(request.form.get("username") or "").strip()).first()
        if a and a.check_password(request.form.get("password", "")):
            session.clear()
            session["admin_id"] = a.id
            session["admin_name"] = a.username
            return redirect(url_for("admin.dashboard"))
        err = "Wrong username or password."
    return render_template("admin/login.html", err=err)

@bp.route("/setup", methods=["GET", "POST"])
def setup():
    if Admin.query.count() > 0: return redirect(url_for("admin.login"))
    err = ""
    if request.method == "POST":
        u = (request.form.get("username") or "").strip()
        p = request.form.get("password") or ""
        if len(u) < 3 or len(p) < 10:
            err = "Username 3+ chars, password 10+ chars."
        else:
            a = Admin(username=u); a.set_password(p)
            db.session.add(a); db.session.commit()
            session["admin_id"] = a.id
            session["admin_name"] = u
            return redirect(url_for("admin.dashboard"))
    return render_template("admin/setup.html", err=err)

@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("store.home"))

@bp.route("/dashboard")
@admin_required
def dashboard():
    stats = {
        "pending":  Order.query.filter_by(status="pending").count(),
        "approved": Order.query.filter_by(status="approved").count(),
        "revenue":  float(db.session.query(func.coalesce(func.sum(Order.amount), 0)).filter_by(status="approved").scalar() or 0),
    }
    pending = Order.query.filter_by(status="pending").order_by(Order.created_at.desc()).limit(20).all()
    return render_template("admin/dashboard.html", stats=stats, pending=pending)

@bp.route("/orders")
@admin_required
def orders():
    f = request.args.get("f", "pending")
    query = Order.query
    if f in ("pending", "approved", "rejected"): query = query.filter_by(status=f)
    orders = query.order_by(Order.created_at.desc()).all()
    return render_template("admin/orders.html", orders=orders, f=f)

@bp.route("/orders/<int:oid>/verify", methods=["POST"])
@admin_required
def verify(oid):
    o = db.session.get(Order, oid) or abort(404)
    do   = request.form.get("do")
    note = (request.form.get("note") or "").strip() or None
    if do == "approved":
        o.status = "approved"
        o.admin_note = note
        o.approved_at = datetime.utcnow()
        if not o.download_token:
            o.generate_download(current_app.config["DOWNLOAD_EXPIRY_DAYS"])
        db.session.commit()
        flash(f"Order {o.order_code} Approved.", "ok")
    elif do == "rejected":
        o.status = "rejected"
        o.admin_note = note
        db.session.commit()
        flash(f"Order {o.order_code} Rejected.", "err")
    return redirect(url_for("admin.orders", f=request.form.get("f", "pending")))

@bp.route("/products", methods=["GET", "POST"])
@admin_required
def products():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "add":
            name = (request.form.get("name") or "").strip()
            price = float(request.form.get("price", 0) or 0)
            category = request.form.get("category", "App")
            is_ig = request.form.get("is_ig_service") == "on"

            if not name or price <= 0:
                flash("Name and price are required.", "err")
            else:
                slug = slugify(name) or "product"
                p = Product(name=name, slug=slug, category=category, is_ig_service=is_ig,
                            description=(request.form.get("description") or "").strip(),
                            price=price,
                            download_url=(request.form.get("download_url") or "").strip() or None)
                
                # Upload File to GitHub (so it doesn't delete on Render)
                f = request.files.get("file")
                if f and f.filename:
                    ext = os.path.splitext(f.filename)[1].lower()
                    if ext in ALLOWED_PRODUCT_EXT:
                        fname = f"{slug}-{secrets.token_hex(4)}{ext}"
                        temp_path = os.path.join(current_app.config["FILES_FOLDER"], fname)
                        f.save(temp_path)
                        
                        # Try pushing to GitHub
                        success = upload_to_github(temp_path, fname)
                        if success:
                            p.download_url = f"https://raw.githubusercontent.com/{current_app.config['GITHUB_REPO']}/main/uploads/{fname}"
                        else:
                            p.file_path = fname
                            flash("File saved locally (GitHub upload failed).", "err")

                uploaded_images = request.files.getlist("images")
                saved_images = []
                for img in uploaded_images:
                    if img and img.filename:
                        ext = os.path.splitext(img.filename)[1].lower()
                        if ext in ALLOWED_IMG_EXT and len(saved_images) < 4:
                            iname = f"img-{slug}-{secrets.token_hex(4)}{ext}"
                            img.save(os.path.join(current_app.config["PRODUCTS_IMG_FOLDER"], iname))
                            saved_images.append(iname)
                
                if not saved_images: saved_images = ["default.jpg"]
                p.images = json.dumps(saved_images)
                
                db.session.add(p); db.session.commit()
                flash("Product added successfully.", "ok")

        elif action == "delete":
            p = db.session.get(Product, request.form.get("id", type=int))
            if p:
                db.session.delete(p); db.session.commit()
                flash("Product deleted.", "ok")
        return redirect(url_for("admin.products"))

    products = Product.query.all()
    for p in products:
        p.img_list = json.loads(p.images) if p.images else []
        if not p.img_list: p.img_list = ["default.jpg"]
    return render_template("admin/products.html", products=products)

# --- ADMIN SUPPORT CHAT ---
@bp.route("/support")
@admin_required
def support_list():
    # Get distinct users who have messages
    users = User.query.join(SupportMessage).group_by(User.id).all()
    return render_template("admin/support_list.html", users=users)

@bp.route("/support/<int:uid>", methods=["GET", "POST"])
@admin_required
def support_chat(uid):
    u = db.session.get(User, uid) or abort(404)
    if request.method == "POST":
        msg = request.form.get("message", "").strip()
        if msg:
            db.session.add(SupportMessage(user_id=u.id, message=msg, is_admin=True))
            db.session.commit()
            return redirect(url_for("admin.support_chat", uid=uid))
            
    messages = SupportMessage.query.filter_by(user_id=u.id).order_by(SupportMessage.created_at.asc()).all()
    return render_template("admin/support_chat.html", messages=messages, target_user=u)
"""

FILES["app/templates/base.html"] = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{% block title %}{{ SITE_NAME }}{% endblock %}</title>
<link rel="stylesheet" href="{{ url_for('static', filename='css/style.css') }}">
</head>
<body>
<header class="topbar">
  <a class="brand" href="{{ url_for('store.home') }}">{{ SITE_NAME }}</a>
  <nav>
    <a href="{{ url_for('store.home') }}">Store</a>
    {% if session.get('user_id') %}
      <a href="{{ url_for('store.my_downloads') }}" style="color:#4ade80; font-weight:bold;">My Downloads</a>
      <a href="{{ url_for('store.support') }}">Support</a>
      <span style="color:#93a2ba; margin:0 10px;">|</span>
      <span style="color:#fff;">Hi, {{ session.get('user_name').split()[0] }}</span>
      <a href="{{ url_for('auth.logout') }}">Logout</a>
    {% else %}
      <a href="{{ url_for('auth.login') }}">Login</a>
      <a href="{{ url_for('auth.register') }}">Register</a>
    {% endif %}
  </nav>
</header>

{% with msgs = get_flashed_messages(with_categories=true) %}
  {% if msgs %}
  <div class="wrap">
    {% for cat, m in msgs %}
      <div class="flash flash-{{ cat }}">{{ m }}</div>
    {% endfor %}
  </div>
  {% endif %}
{% endwith %}

<main class="wrap">{% block body %}{% endblock %}</main>
<footer class="foot">© {{ SITE_NAME }} — Secure UPI Payments.</footer>
</body>
</html>
"""

FILES["app/templates/auth/login.html"] = r"""{% extends "base.html" %}
{% block title %}Login — {{ SITE_NAME }}{% endblock %}
{% block body %}
<div class="card form" style="max-width:400px; margin: 40px auto;">
  <h1>Welcome Back</h1>
  <p class="muted">Log in to access your downloads.</p>
  <form method="post">
    <input type="hidden" name="csrf" value="{{ csrf_token() }}">
    <label>Email <input type="email" name="email" required></label>
    <label>Password <input type="password" name="password" required></label>
    <button class="btn" style="margin-top:10px;">Login</button>
  </form>
  <p class="muted small" style="text-align:center; margin-top:15px;">
    Don't have an account? <a href="{{ url_for('auth.register') }}">Register here</a>.
  </p>
</div>
{% endblock %}
"""

FILES["app/templates/auth/register.html"] = r"""{% extends "base.html" %}
{% block title %}Register — {{ SITE_NAME }}{% endblock %}
{% block body %}
<div class="card form" style="max-width:400px; margin: 40px auto;">
  <h1>Create Account</h1>
  <p class="muted">Sign up to buy and download apps.</p>
  <form method="post">
    <input type="hidden" name="csrf" value="{{ csrf_token() }}">
    <label>Full Name <input name="name" required></label>
    <label>Email <input type="email" name="email" required></label>
    <label>Password (6+ chars) <input type="password" name="password" required minlength="6"></label>
    <button class="btn" style="margin-top:10px;">Create Account</button>
  </form>
  <p class="muted small" style="text-align:center; margin-top:15px;">
    Already have an account? <a href="{{ url_for('auth.login') }}">Login here</a>.
  </p>
</div>
{% endblock %}
"""

FILES["app/templates/store/home.html"] = r"""{% extends "base.html" %}
{% block title %}Apps — {{ SITE_NAME }}{% endblock %}
{% block body %}
<div style="text-align:center; margin: 30px 0;">
  <h1 style="font-size: 32px; color:#fff;">Premium Digital Store</h1>
  <p class="muted">Instant delivery after UPI verification.</p>
</div>

<div class="tabs" style="justify-content:center; margin-bottom:30px;">
  <a class="tab {% if current_cat == 'All' %}active{% endif %}" href="{{ url_for('store.home', cat='All') }}">All</a>
  <a class="tab {% if current_cat == 'App' %}active{% endif %}" href="{{ url_for('store.home', cat='App') }}">Apps</a>
  <a class="tab {% if current_cat == 'Game' %}active{% endif %}" href="{{ url_for('store.home', cat='Game') }}">Games</a>
  <a class="tab {% if current_cat == 'IG' %}active{% endif %}" href="{{ url_for('store.home', cat='IG') }}">IG Services</a>
</div>

<div class="grid">
  {% for p in products %}
    <article class="card product-card" style="padding:0; overflow:hidden; display:flex; flex-direction:column;">
      {% set imgs = p.images|from_json %}
      {% set img = imgs[0] if imgs else 'default.jpg' %}
      <img src="{{ url_for('store.product_image', name=img) }}" 
           alt="{{ p.name }}" 
           style="width:100%; height:180px; object-fit:cover;">
      <div style="padding:18px; display:flex; flex-direction:column; flex:1;">
        <span class="badge warn" style="margin-bottom:8px; align-self:flex-start;">{{ p.category }}</span>
        <h2 style="font-size:20px; margin:0 0 10px 0;">{{ p.name }}</h2>
        <p class="price" style="margin-top:auto;">₹{{ "%.2f"|format(p.price) }} {% if p.is_ig_service %}/ unit{% endif %}</p>
        <a class="btn" style="width:100%; text-align:center; box-sizing:border-box;" href="{{ url_for('store.product', slug=p.slug) }}">View Details</a>
      </div>
    </article>
  {% else %}
    <p class="muted">No products available in this category.</p>
  {% endfor %}
</div>
{% endblock %}
"""

FILES["app/templates/store/product.html"] = r"""{% extends "base.html" %}
{% block title %}{{ product.name }} — {{ SITE_NAME }}{% endblock %}
{% block body %}
<a class="back" href="{{ url_for('store.home') }}">← Back to store</a>
<div class="card" style="display:flex; gap:30px; flex-wrap:wrap;">
  
  <div style="flex:1; min-width:300px;">
    <img id="main-image" src="{{ url_for('store.product_image', name=imgs[0]) }}" 
         style="width:100%; border-radius:12px; border:1px solid #26314a; object-fit:contain; background:#000; max-height:400px;">
    
    {% if imgs|length > 1 %}
    <div style="display:flex; gap:10px; margin-top:10px; overflow-x:auto;">
      {% for img in imgs %}
        <img src="{{ url_for('store.product_image', name=img) }}" 
             onclick="document.getElementById('main-image').src=this.src"
             style="width:70px; height:70px; object-fit:cover; border-radius:8px; cursor:pointer; border:2px solid #26314a;">
      {% endfor %}
    </div>
    {% endif %}
  </div>

  <div style="flex:1; min-width:300px; display:flex; flex-direction:column; justify-content:center;">
    <h1>{{ product.name }}</h1>
    <p class="muted" style="font-size:16px;">{{ product.description }}</p>
    
    {% if product.is_ig_service %}
      <p class="price" style="font-size:32px; margin:20px 0;">₹{{ "%.2f"|format(product.price) }} <span style="font-size:16px; color:#93a2ba;">/ unit</span></p>
      <form method="post" action="{{ url_for('store.checkout') }}">
        <input type="hidden" name="csrf" value="{{ csrf_token() }}">
        <input type="hidden" name="product_id" value="{{ product.id }}">
        <label style="margin-bottom:15px;">Quantity (e.g. 1000) 
          <input type="number" name="quantity" min="1" value="100" required style="font-size:18px; padding:12px;">
        </label>
        <button class="btn" style="width:100%; font-size:18px; padding:15px;">Buy Now</button>
      </form>
    {% else %}
      <p class="price" style="font-size:32px; margin:20px 0;">₹{{ "%.2f"|format(product.price) }}</p>
      {% if already_bought %}
        <div style="background:#052e16; border:1px solid #14532d; padding:15px; border-radius:8px;">
          <h3 style="color:#4ade80; margin:0 0 10px 0;">✅ You already own this</h3>
          <a class="btn" style="width:100%; text-align:center; box-sizing:border-box;" href="{{ url_for('store.my_downloads') }}">Go to My Downloads</a>
        </div>
      {% else %}
        <form method="post" action="{{ url_for('store.checkout') }}">
          <input type="hidden" name="csrf" value="{{ csrf_token() }}">
          <input type="hidden" name="product_id" value="{{ product.id }}">
          <button class="btn" style="width:100%; font-size:18px; padding:15px;">Buy Now</button>
        </form>
      {% endif %}
    {% endif %}
  </div>
</div>
{% endblock %}
"""

FILES["app/templates/store/my_downloads.html"] = r"""{% extends "base.html" %}
{% block title %}My Downloads — {{ SITE_NAME }}{% endblock %}
{% block body %}
<div class="row-head">
  <h1>My Downloads</h1>
  <a class="back" href="{{ url_for('store.home') }}">← Store</a>
</div>
<p class="muted" style="margin-bottom:20px;">Here are all the products you have successfully purchased.</p>

<div class="grid">
  {% for o in orders %}
    {% set imgs = o.product.images|from_json %}
    {% set img = imgs[0] if imgs else 'default.jpg' %}
    <div class="card">
      <img src="{{ url_for('store.product_image', name=img) }}" 
           style="width:100%; height:120px; object-fit:cover; border-radius:8px; margin-bottom:10px;">
      <h3>{{ o.product.name }}</h3>
      <p class="muted small">Bought on: {{ o.approved_at.strftime('%d %b %Y') }}</p>
      {% if o.product.is_ig_service %}
        <p class="muted small" style="color:#4ade80;">Quantity: {{ o.quantity }}</p>
        <a class="btn" style="width:100%; text-align:center; box-sizing:border-box; margin-top:10px;" href="{{ url_for('store.support') }}">Contact Support for Delivery</a>
      {% else %}
        <a class="btn" style="width:100%; text-align:center; box-sizing:border-box; margin-top:10px;" 
           href="{{ url_for('store.download_page', token=o.download_token) }}">
           ⬇ Download Now
        </a>
      {% endif %}
    </div>
  {% else %}
    <div class="card" style="grid-column: 1 / -1; text-align:center; padding:40px;">
      <h2 class="muted">You haven't bought anything yet.</h2>
      <a class="btn" style="margin-top:15px;" href="{{ url_for('store.home') }}">Browse Apps</a>
    </div>
  {% endfor %}
</div>
{% endblock %}
"""

FILES["app/templates/store/order.html"] = r"""{% extends "base.html" %}
{% block title %}Order {{ order.order_code }} — {{ SITE_NAME }}{% endblock %}
{% block body %}
<a class="back" href="{{ url_for('store.home') }}">← Store</a>

{% if order.status == 'pending' and order.screenshot_path %}
  <meta http-equiv="refresh" content="20">
{% endif %}

<div class="card">
  <h1>Order {{ order.order_code }}</h1>
  <p><strong>{{ order.product.name }}</strong> {% if order.quantity > 1 %}(x{{ order.quantity }}){% endif %} — <span class="price">₹{{ "%.2f"|format(order.amount) }}</span></p>
  <p>Status:
    {% if order.status == 'pending' %}<span class="badge warn">Awaiting verification</span>
    {% elif order.status == 'approved' %}<span class="badge ok">Approved</span>
    {% else %}<span class="badge bad">Rejected</span>{% endif %}
  </p>
</div>

{% if order.status == 'approved' %}
  <div class="card" style="text-align:center;">
    <h2>🎉 Payment Verified!</h2>
    {% if order.product.is_ig_service %}
      <p>Your IG service is being processed. Contact support for updates.</p>
    {% else %}
      <p>Your download is ready.</p>
    {% endif %}
    <a class="btn" style="margin-top:15px;" href="{{ url_for('store.my_downloads') }}">Go to My Downloads</a>
  </div>

{% elif order.status == 'rejected' %}
  <div class="card">
    <h2>Payment not verified</h2>
    <p>Re-upload a clearer screenshot below.</p>
    {% if err %}<p class="err">{{ err }}</p>{% endif %}
    <form method="post" enctype="multipart/form-data" class="form">
      <input type="hidden" name="csrf" value="{{ csrf_token() }}">
      <label>New screenshot <input type="file" name="screenshot" accept="image/*" required></label>
      <button class="btn">Re-upload</button>
    </form>
  </div>

{% elif order.screenshot_path %}
  <div class="card" style="text-align:center;">
    <h2>⏳ Verification in progress</h2>
    <p style="color:#fbbf24; font-weight:bold; margin:15px 0;">Your payment will be verified in under 24 hours.</p>
    <p class="muted">Please return to this page in 24 hours to check your status.</p>
    <img class="shot" style="margin:20px auto;" src="{{ url_for('store.upload_file', name=order.screenshot_path) }}">
  </div>

{% else %}
  <div class="card paybox">
    <h2>1. Pay ₹{{ "%.2f"|format(order.amount) }}</h2>
    
    <img src="{{ url_for('static', filename='qr.png') }}" alt="UPI QR Code" style="width: 220px; height: 220px; border-radius: 10px; margin: 15px auto; background: white; padding: 10px; display:block;">
    
    <p>UPI ID: <code id="upiid">{{ config.UPI_ID }}</code>
       <button type="button" class="btn small" onclick="copyUpi()">Copy</button></p>
    <p class="muted small">Add the note <strong>{{ order.order_code }}</strong> to your payment.</p>
    
    <h2 style="margin-top:26px; border-top:1px solid #26314a; padding-top:20px;">2. Upload screenshot</h2>
    <p class="muted small" style="margin-bottom:15px;">Our AI will instantly read the image and verify your payment.</p>
    
    <form method="post" enctype="multipart/form-data" class="form" style="max-width:400px; margin:15px auto;">
      <input type="hidden" name="csrf" value="{{ csrf_token() }}">
      <input type="file" name="screenshot" accept="image/*" required style="padding:15px; border:2px dashed #2563eb; background:transparent;">
      <button class="btn" style="padding:15px;">Submit Payment Proof</button>
    </form>
  </div>

  <script>
    function copyUpi() {
      var id = document.getElementById('upiid').textContent;
      navigator.clipboard.writeText(id).then(function(){ alert('UPI ID copied!'); });
    }
  </script>
{% endif %}
{% endblock %}
"""

FILES["app/templates/store/download.html"] = r"""{% extends "base.html" %}
{% block title %}Downloading...{% endblock %}
{% block body %}
<div class="card" style="text-align:center; padding:50px;">
  <h1>⬇️ Downloading {{ order.product.name }}</h1>
  <p class="muted">If your download does not start automatically, click below.</p>
  <br>
  <a class="btn" href="{{ url }}" target="_blank" rel="noopener" style="font-size:18px; padding:15px 40px;">Click Here to Download</a>
</div>
{% endblock %}
"""

FILES["app/templates/store/support.html"] = r"""{% extends "base.html" %}
{% block title %}Customer Support — {{ SITE_NAME }}{% endblock %}
{% block body %}
<div class="row-head">
  <h1>Customer Support</h1>
  <a class="back" href="{{ url_for('store.home') }}">← Store</a>
</div>

<div class="card" style="height: 500px; display:flex; flex-direction:column;">
  <div style="flex:1; overflow-y:auto; padding-bottom:20px;">
    {% for m in messages %}
      <div style="margin-bottom:15px; text-align: {{ 'right' if not m.is_admin else 'left' }};">
        <div style="display:inline-block; padding:10px 15px; border-radius:10px; max-width:80%; background:{{ '#2563eb' if not m.is_admin else '#26314a' }}; color:#fff;">
          <span style="font-size:11px; color:#ccc; display:block; margin-bottom:5px;">{{ 'You' if not m.is_admin else 'Admin' }} • {{ m.created_at.strftime('%d %b, %H:%M') }}</span>
          {{ m.message }}
        </div>
      </div>
    {% else %}
      <p class="muted" style="text-align:center; margin-top:50px;">No messages yet. Start the conversation below!</p>
    {% endfor %}
  </div>
  
  <form method="post" style="display:flex; gap:10px; margin-top:20px; border-top:1px solid #26314a; padding-top:20px;">
    <input type="hidden" name="csrf" value="{{ csrf_token() }}">
    <input name="message" placeholder="Type your message here..." required style="flex:1; margin:0;">
    <button class="btn">Send</button>
  </form>
</div>
{% endblock %}
"""

FILES["app/templates/admin/login.html"] = r"""{% extends "base.html" %}
{% block title %}Admin Login{% endblock %}
{% block body %}
<div class="card form" style="max-width:380px; margin:40px auto;">
  <h1>Admin Login</h1>
  {% if err %}<p class="err">{{ err }}</p>{% endif %}
  <form method="post">
    <input type="hidden" name="csrf" value="{{ csrf_token() }}">
    <label>Username <input name="username" required></label>
    <label>Password <input type="password" name="password" required></label>
    <button class="btn">Log in</button>
  </form>
</div>
{% endblock %}
"""

FILES["app/templates/admin/setup.html"] = r"""{% extends "base.html" %}
{% block title %}Admin Setup{% endblock %}
{% block body %}
<div class="card form" style="max-width:380px; margin:40px auto;">
  <h1>Create Admin</h1>
  <p class="muted">First-time setup only.</p>
  {% if err %}<p class="err">{{ err }}</p>{% endif %}
  <form method="post">
    <input type="hidden" name="csrf" value="{{ csrf_token() }}">
    <label>Username <input name="username" required minlength="3"></label>
    <label>Password (10+ chars) <input type="password" name="password" required minlength="10"></label>
    <button class="btn">Create Admin</button>
  </form>
</div>
{% endblock %}
"""

FILES["app/templates/admin/dashboard.html"] = r"""{% extends "base.html" %}
{% block title %}Admin Dashboard{% endblock %}
{% block body %}
<div class="row-head">
  <h1>Dashboard</h1>
  <a class="back" href="{{ url_for('admin.logout') }}">Logout</a>
</div>

<div class="stats">
  <div class="stat"><span class="stat-num">{{ stats.pending }}</span><span>Pending Orders</span></div>
  <div class="stat ok"><span class="stat-num">{{ stats.approved }}</span><span>Approved</span></div>
  <div class="stat"><span class="stat-num">₹{{ "%.2f"|format(stats.revenue) }}</span><span>Total Revenue</span></div>
</div>

<p style="display:flex;gap:10px; margin:20px 0">
  <a class="btn" href="{{ url_for('admin.orders', f='pending') }}">Review Pending</a>
  <a class="btn alt" href="{{ url_for('admin.products') }}">Manage Products</a>
  <a class="btn alt" href="{{ url_for('admin.support_list') }}" style="background:#8b5cf6;">Support Chats</a>
</p>

<h2>Latest Pending Orders</h2>
{% for o in pending %}
  <div class="card">
    <strong>{{ o.order_code }}</strong> — {{ o.product.name }} · ₹{{ "%.2f"|format(o.amount) }}
    <div class="muted small">{{ o.user.name }} ({{ o.user.email }}) · {{ o.created_at.strftime('%d %b %H:%M') }}</div>
    <p><a class="btn small" href="{{ url_for('admin.orders', f='pending') }}">Review</a></p>
  </div>
{% else %}
  <p class="muted">Nothing pending 🎉</p>
{% endfor %}
{% endblock %}
"""

FILES["app/templates/admin/orders.html"] = r"""{% extends "base.html" %}
{% block title %}Manage Orders{% endblock %}
{% block body %}
<div class="row-head">
  <h1>Orders</h1>
  <a class="back" href="{{ url_for('admin.dashboard') }}">← Dashboard</a>
</div>

<div class="tabs">
  {% for k, v in [('pending','Pending'),('approved','Approved'),('rejected','Rejected'),('all','All')] %}
    <a class="tab {% if f == k %}active{% endif %}" href="{{ url_for('admin.orders', f=k) }}">{{ v }}</a>
  {% endfor %}
</div>

{% for o in orders %}
<div class="card">
  <div class="order-head">
    <div>
      <strong>{{ o.order_code }}</strong> — {{ o.product.name }} {% if o.quantity > 1 %}(x{{ o.quantity }}){% endif %} · ₹{{ "%.2f"|format(o.amount) }}
      <div class="muted small">{{ o.user.name }} · {{ o.user.email }} · {{ o.created_at.strftime('%d %b %Y %H:%M') }}</div>
    </div>
    <span class="badge {{ 'ok' if o.status == 'approved' else ('bad' if o.status == 'rejected' else 'warn') }}">{{ o.status }}</span>
  </div>

  {% if o.screenshot_path %}
    <a href="{{ url_for('store.upload_file', name=o.screenshot_path) }}" target="_blank">
      <img class="shot" src="{{ url_for('store.upload_file', name=o.screenshot_path) }}">
    </a>
    {% if o.ocr_text %}
      <div style="background:#0f1420; padding:10px; border-radius:8px; margin-top:10px; border:1px solid #26314a;">
        <p class="muted small" style="margin:0 0 5px 0;">AI Read:</p>
        <code style="font-size:11px; color:#93a2ba;">{{ o.ocr_text[:300] }}...</code>
      </div>
    {% endif %}
  {% else %}
    <p class="muted small">No screenshot uploaded.</p>
  {% endif %}

  <form method="post" action="{{ url_for('admin.verify', oid=o.id) }}" class="form row" style="margin-top:15px;">
    <input type="hidden" name="csrf" value="{{ csrf_token() }}">
    <input type="hidden" name="f" value="{{ f }}">
    <input name="note" placeholder="Optional note to buyer" value="{{ o.admin_note or '' }}" maxlength="255" style="flex:1;">
    <button class="btn ok" name="do" value="approved">Approve</button>
    <button class="btn bad" name="do" value="rejected">Reject</button>
  </form>
</div>
{% else %}
<p class="muted">No orders in this list.</p>
{% endfor %}
{% endblock %}
"""

FILES["app/templates/admin/products.html"] = r"""{% extends "base.html" %}
{% block title %}Manage Products{% endblock %}
{% block body %}
<div class="row-head">
  <h1>Products</h1>
  <a class="back" href="{{ url_for('admin.dashboard') }}">← Dashboard</a>
</div>

<div class="grid">
{% for p in products %}
  <div class="card">
    <img src="{{ url_for('store.product_image', name=p.img_list[0]) }}" 
         style="width:100%; height:120px; object-fit:cover; border-radius:8px; margin-bottom:10px;">
    <span class="badge warn" style="margin-bottom:5px;">{{ p.category }}</span>
    <strong>{{ p.name }}</strong> · ₹{{ "%.2f"|format(p.price) }} {% if p.is_ig_service %}/ unit{% endif %}
    <div class="muted small" style="margin-bottom:10px;">
      {{ p.img_list|length }} Image(s)
    </div>
    <form method="post">
      <input type="hidden" name="csrf" value="{{ csrf_token() }}">
      <input type="hidden" name="id" value="{{ p.id }}">
      <button class="btn small bad" name="action" value="delete" onclick="return confirm('Delete {{ p.name }}?')">Delete</button>
    </form>
  </div>
{% endfor %}
</div>

<h2 style="margin-top:40px">Add New Product</h2>
<form method="post" enctype="multipart/form-data" class="card form">
  <input type="hidden" name="csrf" value="{{ csrf_token() }}">
  <input type="hidden" name="action" value="add">
  
  <div style="display:grid; grid-template-columns:1fr 1fr; gap:15px;">
    <label>Name <input name="name" required maxlength="200"></label>
    <label>Category 
      <select name="category">
        <option value="App">App</option>
        <option value="Game">Game</option>
        <option value="IG">IG Service</option>
      </select>
    </label>
  </div>
  
  <label>Description <textarea name="description" rows="3"></textarea></label>
  <label>Price (₹) <input name="price" type="number" step="0.01" min="0.01" required></label>
  
  <label style="flex-direction:row; align-items:center; gap:10px; cursor:pointer;">
    <input type="checkbox" name="is_ig_service"> Is this an IG Service (price per unit)?
  </label>
  
  <div style="display:grid; grid-template-columns:1fr 1fr; gap:15px;">
    <label>Product Images (Select 1 to 4) <input type="file" name="images" accept="image/*" multiple required></label>
    <label>Product File (APK/ZIP — will save to GitHub) <input type="file" name="file"></label>
  </div>
  
  <label>Or External Download URL (optional) <input name="download_url"></label>
  <button class="btn">Publish Product</button>
</form>
{% endblock %}
"""

FILES["app/templates/admin/support_list.html"] = r"""{% extends "base.html" %}
{% block title %}Support Inbox{% endblock %}
{% block body %}
<div class="row-head">
  <h1>Support Inbox</h1>
  <a class="back" href="{{ url_for('admin.dashboard') }}">← Dashboard</a>
</div>

<div class="grid">
  {% for u in users %}
    <div class="card" style="display:flex; align-items:center; gap:15px;">
      <div style="width:50px; height:50px; border-radius:50%; background:#2563eb; display:flex; align-items:center; justify-content:center; font-weight:bold; font-size:20px;">
        {{ u.name[0]|upper }}
      </div>
      <div>
        <strong>{{ u.name }}</strong>
        <div class="muted small">{{ u.email }}</div>
        <a class="btn small" style="margin-top:10px;" href="{{ url_for('admin.support_chat', uid=u.id) }}">Open Chat</a>
      </div>
    </div>
  {% else %}
    <p class="muted">No support messages yet.</p>
  {% endfor %}
</div>
{% endblock %}
"""

FILES["app/templates/admin/support_chat.html"] = r"""{% extends "base.html" %}
{% block title %}Chat with {{ target_user.name }}{% endblock %}
{% block body %}
<div class="row-head">
  <h1>Chat: {{ target_user.name }}</h1>
  <a class="back" href="{{ url_for('admin.support_list') }}">← Inbox</a>
</div>

<div class="card" style="height: 500px; display:flex; flex-direction:column;">
  <div style="flex:1; overflow-y:auto; padding-bottom:20px;">
    {% for m in messages %}
      <div style="margin-bottom:15px; text-align: {{ 'right' if m.is_admin else 'left' }};">
        <div style="display:inline-block; padding:10px 15px; border-radius:10px; max-width:80%; background:{{ '#2563eb' if m.is_admin else '#26314a' }}; color:#fff;">
          <span style="font-size:11px; color:#ccc; display:block; margin-bottom:5px;">{{ 'Admin' if m.is_admin else target_user.name }} • {{ m.created_at.strftime('%d %b, %H:%M') }}</span>
          {{ m.message }}
        </div>
      </div>
    {% else %}
      <p class="muted" style="text-align:center; margin-top:50px;">No messages yet.</p>
    {% endfor %}
  </div>
  
  <form method="post" style="display:flex; gap:10px; margin-top:20px; border-top:1px solid #26314a; padding-top:20px;">
    <input type="hidden" name="csrf" value="{{ csrf_token() }}">
    <input name="message" placeholder="Reply to {{ target_user.name }}..." required style="flex:1; margin:0;">
    <button class="btn">Send</button>
  </form>
</div>
{% endblock %}
"""

FILES["app/templates/errors/error.html"] = r"""{% extends "base.html" %}
{% block title %}Error {{ code }}{% endblock %}
{% block body %}
<div class="card" style="text-align:center; margin-top:40px;">
  <h1 style="font-size:50px; color:#dc2626;">{{ code }}</h1>
  <p>{{ msg }}</p>
  <a class="btn" href="{{ url_for('store.home') }}">Go to Homepage</a>
</div>
{% endblock %}
"""

FILES["app/static/css/style.css"] = r"""*{box-sizing:border-box}
body{margin:0;font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;background:#0f1420;color:#e6ecf5;line-height:1.55}
.topbar{background:#161d2e;border-bottom:1px solid #26314a;padding:14px 20px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap; gap:10px;}
.brand{color:#7cc4ff;font-weight:700;text-decoration:none;font-size:18px}
.topbar nav a{color:#93a2ba;font-size:14px;text-decoration:none;margin-left:16px}
.topbar nav a:hover{color:#7cc4ff}
.wrap{max-width:1000px;margin:24px auto;padding:0 16px}
.foot{text-align:center;color:#5d6b85;font-size:13px;padding:30px 0; margin-top:40px;}
h1{font-size:26px;margin:0 0 12px}h2{font-size:19px;margin:0 0 10px}
a{color:#7cc4ff}
.card{background:#161d2e;border:1px solid #26314a;border-radius:12px;padding:18px;margin:0 0 16px}
.product-card:hover{transform:translateY(-2px); transition:0.2s; border-color:#2563eb;}
.grid{display:grid;gap:16px;grid-template-columns:repeat(auto-fill,minmax(280px,1fr))}
.price{color:#4ade80;font-size:20px;font-weight:700;margin:8px 0}
.muted{color:#93a2ba}.small{font-size:13px}
.btn{display:inline-block;background:#2563eb;color:#fff;border:0;border-radius:8px;padding:11px 18px;font-size:15px;cursor:pointer;text-decoration:none;font-weight:600; transition:0.2s;}
.btn:hover{background:#1d4ed8}
.btn.alt{background:#0ea5e9}.btn.ok{background:#16a34a}.btn.bad{background:#dc2626}
.btn.small{padding:5px 10px;font-size:13px}
.form{display:flex;flex-direction:column;gap:12px;margin-top:12px}
.form.row{flex-direction:row;flex-wrap:wrap;align-items:center}
label{display:flex;flex-direction:column;gap:6px;font-size:14px;color:#b7c4d8}
input,textarea,select{background:#0f1420;border:1px solid #2b3752;color:#e6ecf5;border-radius:8px;padding:10px;font:inherit; width:100%;}
input[name=note]{flex:1;min-width:180px}
code{background:#0f1420;padding:2px 6px;border-radius:5px;font-size:13px;word-break:break-all}
.err{color:#fca5a5;background:#3b1414;border:1px solid #7f1d1d;padding:10px;border-radius:8px}
.ok{color:#86efac}
.flash{padding:10px 14px;border-radius:8px;margin-bottom:16px; text-align:center;}
.flash-ok{background:#052e16;color:#86efac;border:1px solid #14532d}
.flash-err{background:#3b1414;color:#fca5a5;border:1px solid #7f1d1d}
.badge{padding:3px 10px;border-radius:20px;font-size:12px;font-weight:700;text-transform:uppercase}
.badge.warn{background:#422006;color:#fbbf24}
.badge.ok{background:#052e16;color:#4ade80}
.badge.bad{background:#450a0a;color:#f87171}
.paybox{text-align:center}
.shot{max-width:260px;border-radius:10px;border:1px solid #26314a;margin:10px 0;display:block}
.tabs{display:flex;gap:8px;margin:0 0 16px;flex-wrap:wrap}
.tab{padding:7px 14px;border-radius:8px;background:#161d2e;border:1px solid #26314a;text-decoration:none;color:#b7c4d8; cursor:pointer;}
.tab.active{background:#2563eb;color:#fff;border-color:#2563eb}
.order-head{display:flex;justify-content:space-between;gap:10px;align-items:flex-start;flex-wrap:wrap}
.back{color:#93a2ba;text-decoration:none;font-size:14px;display:inline-block;margin-bottom:12px}
.row-head{display:flex;justify-content:space-between;align-items:center}
.stats{display:grid;gap:12px;grid-template-columns:repeat(auto-fill,minmax(150px,1fr))}
.stat{background:#161d2e;border:1px solid #26314a;border-radius:12px;padding:14px;display:flex;flex-direction:column;gap:4px}
.stat-num{font-size:22px;font-weight:700}
.stat.ok .stat-num{color:#4ade80}
.stat.bad .stat-num{color:#f87171}

@media(max-width: 600px) {
  .topbar { flex-direction: column; text-align: center; }
  .topbar nav { margin-top: 10px; display: flex; flex-wrap: wrap; justify-content: center; gap: 10px; }
  .topbar nav a { margin-left: 0; }
  .grid { grid-template-columns: 1fr; }
  .form.row { flex-direction: column; align-items: stretch; }
  .stats { grid-template-columns: 1fr 1fr; }
}
"""

FILES[".env"] = r"""SECRET_KEY=__SECRET__
UPI_ID=9579059838@fam
UPI_NAME=Viraj
SITE_NAME=Viraj Store
HTTPS=false
GITHUB_TOKEN=
GITHUB_REPO=bodare207-ai/shop
"""

FILES[".gitignore"] = r"""__pycache__/
*.pyc
instance/
uploads/
files/
.env
.venv/
app/static/qr.png
app/static/products/
"""

def write_all():
    print("\n📦  Creating Ultimate AI Store in:", BASE, "\n")
    for rel, content in FILES.items():
        path = BASE / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if rel == ".env" and path.exists():
            print(f"  - {rel} already exists, left untouched")
            continue
        path.write_text(content.replace("__SECRET__", secrets.token_urlsafe(48)), encoding="utf-8")
        print(f"  ✓ {rel}")

    for d in ["instance", "uploads", "files", "app/static/products"]:
        (BASE / d).mkdir(parents=True, exist_ok=True)

    print("\n✅  Done! Project created.\n")
    print("Next steps:\n")
    print("  1. Edit .env and add your GITHUB_TOKEN")
    print("  2. git add . && git commit -m 'Ultimate Build' && git push")
    print("  3. Render will auto-deploy using Docker.")

if __name__ == "__main__":
    write_all()