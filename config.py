import os
import json
import base64

# Load local .env if it exists (for local dev)
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(_env_path):
    try:
        with open(_env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    # Remove surrounding quotes if any
                    k_str = k.strip()
                    v_str = v.strip().strip("'\"")
                    os.environ[k_str] = v_str
    except Exception as e:
        print(f"Warning: Could not load .env file: {e}")

# ─────────────────────────────────────────────────────────────────────────────
#  API KEYS & LLM CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

# Supported LLM Providers: "gemini", "groq", "openrouter"
DEFAULT_LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "groq")

# Gemini Configurations
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

# Groq Configurations (Free API for Llama 3)
# The user can get a free key from https://console.groq.com
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

# OpenRouter Configurations (Free models available)
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "meta-llama/llama-3-8b-instruct:free")

# ─────────────────────────────────────────────────────────────────────────────
#  GOOGLE DRIVE & SHEETS CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

# For deployment: store credentials.json content as a base64-encoded env var
# On Render, set GOOGLE_CREDENTIALS_B64 to the base64 of your credentials.json
CREDENTIALS_FILE = "credentials.json"
_creds_b64 = os.environ.get("GOOGLE_CREDENTIALS_B64", "")
if _creds_b64 and not os.path.exists(CREDENTIALS_FILE):
    try:
        with open(CREDENTIALS_FILE, "w") as f:
            f.write(base64.b64decode(_creds_b64).decode("utf-8"))
    except Exception as e:
        print(f"Warning: Could not write credentials.json from env: {e}")

GOOGLE_SHEET_TITLE = os.environ.get("GOOGLE_SHEET_TITLE", "Resume Task")
GOOGLE_SPREADSHEET_ID = os.environ.get("GOOGLE_SPREADSHEET_ID", "1Ay_K_QoWJokFcvzXLSgD64XdLy4iM83KTTWgnZbgtZs")
DEFAULT_SHEET_TAB = os.environ.get("DEFAULT_SHEET_TAB", "NIRAV PATEL")
MASTER_RESUME_FILE = os.environ.get("MASTER_RESUME_FILE", "master_resume.docx")
RESUME_DRIVE_FOLDER = os.environ.get("RESUME_DRIVE_FOLDER", "1ZWSCgAjgy4fSC5L72sT9GGx5v1CKO7Kh")
SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/documents",
]

# ─────────────────────────────────────────────────────────────────────────────
#  SCRAPER & JOB SEARCH CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────
# Default search keywords/roles
_kw_env = os.environ.get("DEFAULT_KEYWORDS", "")
DEFAULT_KEYWORDS = [k.strip() for k in _kw_env.split(",") if k.strip()] if _kw_env else [
    "React Developer",
    "Python Developer",
    "Full Stack Engineer",
    "Node.js Developer",
    "Frontend Engineer",
]

# We Work Remotely Feed URLs / APIs
WWR_FEEDS = [
    "https://weworkremotely.com/categories/remote-programming-jobs.rss"
]

# RemoteOK API URL
REMOTEOK_FEED = "https://remoteok.com/api"

# Default scheduler interval
SCAN_INTERVAL_HOURS = 1
MINIMUM_ATS_SCORE = 65
