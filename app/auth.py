import re
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
