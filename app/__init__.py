import os
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
