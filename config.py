import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# Get the DATABASE_URL from the environment
db_url = os.environ.get("DATABASE_URL")

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-key-change-me")
    
    if db_url:
        # Neon provides a standard 'postgresql://' URL.
        # We need to change it to 'postgresql+psycopg2://' for SQLAlchemy.
        if db_url.startswith("postgresql://"):
            db_url = db_url.replace("postgresql://", "postgresql+psycopg2://", 1)
        SQLALCHEMY_DATABASE_URI = db_url
    else:
        # Fallback to local SQLite for development
        DATA_DIR = os.environ.get("DATA_DIR", str(BASE_DIR))
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{os.path.join(DATA_DIR, 'instance', 'store.db')}"
        
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # The `pool_pre_ping` option is recommended by Neon to handle idle connections
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 300 
    }

    SESSION_COOKIE_SECURE   = os.environ.get("HTTPS", "false").lower() == "true"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 24 * 7

    MAX_CONTENT_LENGTH = 100 * 1024 * 1024 # 100 MB

    UPI_ID      = os.environ.get("UPI_ID", "9579059838@fam")
    UPI_NAME    = os.environ.get("UPI_NAME", "Viraj")
    SITE_NAME   = os.environ.get("SITE_NAME", "Viraj Store")
    
    EXPECTED_NAMES = ["shivrudra", "viraj", "santosh", "bodare"]
    EXPECTED_UPI = "9579059838"

    DOWNLOAD_EXPIRY_DAYS = 30
    DOWNLOAD_MAX_COUNT   = 50

    GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
    GITHUB_REPO = os.environ.get("GITHUB_REPO", "")