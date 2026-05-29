import os
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

load_dotenv(os.path.join(BASE_DIR, ".env"))

AI_PROVIDER = os.getenv("AI_PROVIDER", "deepseek")
AI_API_KEY = os.getenv("AI_API_KEY", "")
AI_BASE_URL = os.getenv("AI_BASE_URL", "https://api.deepseek.com")
AI_MODEL = os.getenv("AI_MODEL", "deepseek-chat")

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-v1")

OBSIDIAN_VAULT_PATH = os.getenv("OBSIDIAN_VAULT_PATH", "")

_raw_db = os.getenv("DATABASE_PATH", os.path.join(BASE_DIR, "data", "app.db"))
DATABASE_PATH = _raw_db if os.path.isabs(_raw_db) else os.path.join(BASE_DIR, _raw_db.lstrip("./"))

_raw_upload = os.getenv("UPLOAD_DIR", os.path.join(BASE_DIR, "data", "uploads"))
UPLOAD_DIR = _raw_upload if os.path.isabs(_raw_upload) else os.path.join(BASE_DIR, _raw_upload.lstrip("./"))

os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Feishu
FEISHU_APP_ID = os.getenv("FEISHU_APP_ID")
FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET")

# API
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", 8000))
