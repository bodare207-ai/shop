import re, secrets, platform, base64, requests
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
