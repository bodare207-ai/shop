import os, secrets, json
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
