"""Centralized configuration for the central server."""
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

GMAIL_ADDRESS = os.getenv("GMAIL_ADDRESS", "atsit17@gmail.com")
CREDENTIALS_FILE = BASE_DIR / os.getenv("GMAIL_CREDENTIALS_FILE", "credentials/credentials.json")
TOKEN_FILE = BASE_DIR / os.getenv("GMAIL_TOKEN_FILE", "credentials/token.json")
STORAGE_ROOT = BASE_DIR / os.getenv("STORAGE_ROOT", "storage/Downloads/Emails")
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL_SECONDS", "120"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))

LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
