"""Gmail API client for reading emails from the central mailbox."""
import base64
from typing import Optional
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from loguru import logger
from app.config import CREDENTIALS_FILE, TOKEN_FILE

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly", "https://www.googleapis.com/auth/gmail.modify"]


def get_gmail_service():
    """Authenticate and return Gmail API service."""
    creds: Optional[Credentials] = None

    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_FILE.write_text(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def list_unread_messages(service, max_results: int = 20) -> list[dict]:
    """Fetch unread messages from inbox."""
    result = service.users().messages().list(
        userId="me", q="is:unread", maxResults=max_results
    ).execute()
    return result.get("messages", [])


def get_message_detail(service, msg_id: str) -> dict:
    """Get full message details including body and attachments."""
    msg = service.users().messages().get(userId="me", id=msg_id, format="full").execute()
    headers = {h["name"]: h["value"] for h in msg["payload"].get("headers", [])}

    body_text = _extract_body(msg["payload"])
    attachments = _list_attachments(msg["payload"])

    return {
        "id": msg_id,
        "subject": headers.get("Subject", "No Subject"),
        "from": headers.get("From", "Unknown"),
        "date": headers.get("Date", ""),
        "body": body_text,
        "attachments": attachments,
    }


def download_attachment(service, msg_id: str, att_id: str) -> bytes:
    """Download attachment content as bytes."""
    att = service.users().messages().attachments().get(
        userId="me", messageId=msg_id, id=att_id
    ).execute()
    return base64.urlsafe_b64decode(att["data"])


def mark_as_read(service, msg_id: str):
    """Remove UNREAD label from message."""
    service.users().messages().modify(
        userId="me", id=msg_id, body={"removeLabelIds": ["UNREAD"]}
    ).execute()


def _extract_body(payload: dict) -> str:
    """Recursively extract plain text body."""
    if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")

    for part in payload.get("parts", []):
        text = _extract_body(part)
        if text:
            return text
    return ""


def _list_attachments(payload: dict) -> list[dict]:
    """Recursively find all attachments."""
    attachments = []
    for part in payload.get("parts", []):
        if part.get("filename") and part.get("body", {}).get("attachmentId"):
            attachments.append({
                "filename": part["filename"],
                "attachment_id": part["body"]["attachmentId"],
                "mime_type": part.get("mimeType", ""),
                "size": part.get("body", {}).get("size", 0),
            })
        attachments.extend(_list_attachments(part))
    return attachments
