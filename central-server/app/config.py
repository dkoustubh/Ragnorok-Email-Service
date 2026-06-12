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

# Database Configuration (PostgreSQL)
DB_HOST = os.getenv("DB_HOST", "192.168.11.86")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_USER = os.getenv("DB_USER", "admin")
DB_PASSWORD = os.getenv("DB_PASSWORD", "Ats@123*")
DB_NAME = os.getenv("DB_NAME", "email_service")

# NAS Configuration
NAS_URL = os.getenv("NAS_URL", "http://192.168.11.153:3000")
NAS_USER = os.getenv("NAS_USER", "AI-GPU")
NAS_PASSWORD = os.getenv("NAS_PASSWORD", "Atsit123*")
NAS_FOLDER = os.getenv("NAS_FOLDER", "Ragnarok_Email")
STORAGE_MODE = os.getenv("STORAGE_MODE", "nas")  # "nas" or "local"

# RabbitMQ Configuration
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "192.168.11.86")
RABBITMQ_PORT = int(os.getenv("RABBITMQ_PORT", "5672"))
RABBITMQ_USER = os.getenv("RABBITMQ_USER", "guest")
RABBITMQ_PASSWORD = os.getenv("RABBITMQ_PASSWORD", "guest")
RABBITMQ_QUEUE = os.getenv("RABBITMQ_QUEUE", "email_queue")

LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
if STORAGE_MODE == "local":
    STORAGE_ROOT.mkdir(parents=True, exist_ok=True)


