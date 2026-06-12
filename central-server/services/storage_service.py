"""Storage service supporting local folder storage and remote WebDAV NAS uploads."""
import json
import re
from datetime import datetime
from pathlib import Path
import requests
from loguru import logger
from app.config import STORAGE_ROOT, STORAGE_MODE, NAS_URL, NAS_USER, NAS_PASSWORD, NAS_FOLDER


def _sanitize(name: str) -> str:
    """Sanitize string for use as directory/file name."""
    name = re.sub(r'[<>:"/\\|?*]', '_', name.strip())
    return name[:100] or "Unknown"


def _parse_sender(from_header: str) -> tuple[str, str]:
    """Extract company-like domain and person name from 'From' header."""
    match = re.match(r'^"?(.+?)"?\s*<(.+?)>$', from_header)
    if match:
        name = match.group(1).strip()
        email = match.group(2).strip()
    else:
        name = from_header.split("@")[0] if "@" in from_header else from_header
        email = from_header

    domain = email.split("@")[-1] if "@" in email else "unknown"
    company = domain.split(".")[0].capitalize()
    return _sanitize(company), _sanitize(name)


def _ensure_webdav_dirs(base_url: str, relative_parts: list[str], auth: tuple[str, str]):
    """Recursively create nested directories on the WebDAV server."""
    current_url = base_url
    for part in relative_parts:
        current_url = f"{current_url.rstrip('/')}/{part}"
        # WebDAV check if directory exists (PROPFIND) or just attempt to create it (MKCOL)
        res = requests.request("MKCOL", current_url, auth=auth)
        # 201 Created or 405 Method Not Allowed (already exists) are acceptable
        if res.status_code not in (201, 405):
            logger.warning(f"WebDAV MKCOL status {res.status_code} for {current_url}: {res.text}")


def store_email(email_data: dict, attachment_bytes: dict[str, bytes]) -> str:
    """Store email body and attachments either locally or to remote NAS via WebDAV."""
    company, person = _parse_sender(email_data["from"])

    # Parse timestamp
    try:
        dt = datetime.strptime(email_data["date"][:31], "%a, %d %b %Y %H:%M:%S %z")
        timestamp_dir = dt.strftime("%Y%m%d_%H%M%S")
    except Exception:
        timestamp_dir = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Relative path structure
    rel_path_str = f"{company}/{person}/{timestamp_dir}"
    body_rel_dir = f"{rel_path_str}/Mail Body"
    att_rel_dir = f"{rel_path_str}/Attachments"

    # Save data structure for JSON
    body_json = {
        "subject": email_data.get("subject", ""),
        "from": email_data.get("from", ""),
        "date": email_data.get("date", ""),
        "body": email_data.get("body", ""),
        "attachment_count": len(attachment_bytes),
    }

    if STORAGE_MODE == "nas":
        auth = (NAS_USER, NAS_PASSWORD)
        base_nas_url = f"{NAS_URL.rstrip('/')}/{NAS_FOLDER.lstrip('/')}"
        
        # Ensure remote folders exist
        _ensure_webdav_dirs(NAS_URL, [NAS_FOLDER] + rel_path_str.split("/"), auth)
        _ensure_webdav_dirs(NAS_URL, [NAS_FOLDER] + body_rel_dir.split("/"), auth)
        if attachment_bytes:
            _ensure_webdav_dirs(NAS_URL, [NAS_FOLDER] + att_rel_dir.split("/"), auth)

        # Upload body.txt
        txt_url = f"{base_nas_url}/{body_rel_dir}/body.txt"
        requests.put(txt_url, data=email_data.get("body", "").encode("utf-8"), auth=auth)

        # Upload body.json
        json_url = f"{base_nas_url}/{body_rel_dir}/body.json"
        requests.put(json_url, data=json.dumps(body_json, indent=2, ensure_ascii=False).encode("utf-8"), auth=auth)

        # Upload attachments
        for filename, data in attachment_bytes.items():
            safe_name = _sanitize(filename)
            att_url = f"{base_nas_url}/{att_rel_dir}/{safe_name}"
            requests.put(att_url, data=data, auth=auth)
            logger.debug(f"Uploaded attachment to NAS: {safe_name}")

        storage_path = f"nas://{NAS_FOLDER}/{rel_path_str}"
        logger.info(f"Stored email to remote NAS: {storage_path}")
        return storage_path

    else:
        # Local fallback
        email_dir = STORAGE_ROOT / company / person / timestamp_dir
        body_dir = email_dir / "Mail Body"
        att_dir = email_dir / "Attachments"

        body_dir.mkdir(parents=True, exist_ok=True)
        att_dir.mkdir(parents=True, exist_ok=True)

        (body_dir / "body.txt").write_text(email_data.get("body", ""), encoding="utf-8")
        (body_dir / "body.json").write_text(json.dumps(body_json, indent=2, ensure_ascii=False), encoding="utf-8")

        for filename, data in attachment_bytes.items():
            safe_name = _sanitize(filename)
            (att_dir / safe_name).write_bytes(data)

        logger.info(f"Stored email locally: {email_dir}")
        return str(email_dir)
