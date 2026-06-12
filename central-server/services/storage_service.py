"""Email storage service — organizes emails into structured folder hierarchy."""
import json
import re
from datetime import datetime
from pathlib import Path
from loguru import logger
from app.config import STORAGE_ROOT


def _sanitize(name: str) -> str:
    """Sanitize string for use as directory name."""
    name = re.sub(r'[<>:"/\\|?*]', '_', name.strip())
    return name[:100] or "Unknown"


def _parse_sender(from_header: str) -> tuple[str, str]:
    """Extract company-like domain and person name from 'From' header.
    e.g. 'John Doe <john@acme.com>' -> ('acme', 'John Doe')
    """
    match = re.match(r'^"?(.+?)"?\s*<(.+?)>$', from_header)
    if match:
        name = match.group(1).strip()
        email = match.group(2).strip()
    else:
        name = from_header.split("@")[0] if "@" in from_header else from_header
        email = from_header

    # Company from domain
    domain = email.split("@")[-1] if "@" in email else "unknown"
    company = domain.split(".")[0].capitalize()

    return _sanitize(company), _sanitize(name)


def store_email(email_data: dict, attachment_bytes: dict[str, bytes]) -> Path:
    """Store email body and attachments in structured folders.

    Returns the created email directory path.
    Structure: STORAGE_ROOT/Company/Person/MAIL_TIMESTAMP/
    """
    company, person = _parse_sender(email_data["from"])

    # Parse timestamp
    try:
        dt = datetime.strptime(email_data["date"][:31], "%a, %d %b %Y %H:%M:%S %z")
        timestamp_dir = dt.strftime("%Y%m%d_%H%M%S")
    except (ValueError, IndexError):
        timestamp_dir = datetime.now().strftime("%Y%m%d_%H%M%S")

    email_dir = STORAGE_ROOT / company / person / timestamp_dir
    body_dir = email_dir / "Mail Body"
    att_dir = email_dir / "Attachments"

    body_dir.mkdir(parents=True, exist_ok=True)
    att_dir.mkdir(parents=True, exist_ok=True)

    # Save body as TXT
    (body_dir / "body.txt").write_text(email_data.get("body", ""), encoding="utf-8")

    # Save body as JSON (full metadata)
    body_json = {
        "subject": email_data.get("subject", ""),
        "from": email_data.get("from", ""),
        "date": email_data.get("date", ""),
        "body": email_data.get("body", ""),
        "attachment_count": len(attachment_bytes),
    }
    (body_dir / "body.json").write_text(json.dumps(body_json, indent=2, ensure_ascii=False), encoding="utf-8")

    # Save attachments
    for filename, data in attachment_bytes.items():
        safe_name = _sanitize(filename)
        (att_dir / safe_name).write_bytes(data)
        logger.debug(f"Saved attachment: {safe_name}")

    logger.info(f"Stored email: {email_dir}")
    return email_dir
