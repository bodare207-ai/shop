import os, secrets, json, tempfile
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
                
                # 1. Upload APK File to GitHub
                f = request.files.get("file")
                if f and f.filename:
                    ext = os.path.splitext(f.filename)[1].lower()
                    if ext in ALLOWED_PRODUCT_EXT:
                        fname = f"{slug}-{secrets.token_hex(4)}{ext}"
                        # Use tempfile to save to a writable directory
                        temp_file_path = os.path.join(tempfile.gettempdir(), fname)
                        f.save(temp_file_path)
                        
                        success = upload_to_github(temp_file_path, fname)
                        if success:
                            p.download_url = f"https://raw.githubusercontent.com/{current_app.config['GITHUB_REPO']}/main/uploads/{fname}"
                        else:
                            p.file_path = fname
                            flash("File saved locally (GitHub upload failed).", "err")
                        
                        # Clean up temp file
                        if os.path.exists(temp_file_path):
                            os.remove(temp_file_path)

                # 2. Upload Images to GitHub
                uploaded_images = request.files.getlist("images")
                saved_images = []
                for img in uploaded_images:
                    if img and img.filename:
                        ext = os.path.splitext(img.filename)[1].lower()
                        if ext in ALLOWED_IMG_EXT and len(saved_images) < 4:
                            iname = f"img-{slug}-{secrets.token_hex(4)}{ext}"
                            # Use tempfile to save to a writable directory
                            temp_img_path = os.path.join(tempfile.gettempdir(), iname)
                            img.save(temp_img_path)
                            
                            gh_success = upload_to_github(temp_img_path, iname)
                            if gh_success:
                                gh_url = f"https://raw.githubusercontent.com/{current_app.config['GITHUB_REPO']}/main/uploads/{iname}"
                                saved_images.append(gh_url)
                            else:
                                saved_images.append("default.jpg")
                                
                            # Clean up temp file
                            if os.path.exists(temp_img_path):
                                os.remove(temp_img_path)
                
                if not saved_images: 
                    saved_images = ["default.jpg"]
                
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
