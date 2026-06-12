"""Centralized configuration loaded from .env"""
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

FORWARD_TO = os.getenv("FORWARD_TO", "atsit17@gmail.com")
MONITORED_EMAIL = os.getenv("MONITORED_EMAIL", "")
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL_SECONDS", "60"))
OUTLOOK_FOLDER = os.getenv("OUTLOOK_FOLDER", "Inbox")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Delivery config
API_INGEST_URL = os.getenv("API_INGEST_URL", "http://192.168.11.86/api/v1/emails/submit")
DELIVERY_METHOD = os.getenv("DELIVERY_METHOD", "api")  # "api" or "email"



RFQ_KEYWORDS = [k.strip().lower() for k in os.getenv("RFQ_KEYWORDS", "rfq,request for quotation,quote request").split(",")]
FUZZY_MATCH_THRESHOLD = int(os.getenv("FUZZY_MATCH_THRESHOLD", "80"))

DB_PATH = BASE_DIR / "database" / "processed.db"
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
