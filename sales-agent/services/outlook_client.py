"""Outlook email reader, email forwarder, and direct HTTP API upload client."""
import os
import tempfile
import pythoncom
import win32com.client
import requests
from loguru import logger
from config.settings import OUTLOOK_FOLDER, FORWARD_TO, API_INGEST_URL


def get_outlook():
    """Initialize Outlook COM object."""
    pythoncom.CoInitialize()
    outlook = win32com.client.Dispatch("Outlook.Application")
    return outlook.GetNamespace("MAPI")


def get_inbox_emails(namespace):
    """Retrieve unread emails from configured Outlook folder."""
    inbox = namespace.GetDefaultFolder(6)  # 6 = olFolderInbox
    messages = inbox.Items
    messages.Sort("[ReceivedTime]", True)
    return messages


def read_email(mail_item) -> dict:
    """Extract metadata, body, and attachments metadata from a mail item."""
    attachments = []
    for i in range(1, mail_item.Attachments.Count + 1):
        att = mail_item.Attachments.Item(i)
        attachments.append({"name": att.FileName, "size": att.Size})

    return {
        "entry_id": mail_item.EntryID,
        "subject": mail_item.Subject or "",
        "sender": str(mail_item.SenderEmailAddress or ""),
        "sender_name": str(mail_item.SenderName or ""),
        "body": mail_item.Body or "",
        "html_body": mail_item.HTMLBody or "",
        "received_time": str(mail_item.ReceivedTime),
        "attachment_count": mail_item.Attachments.Count,
        "attachments": attachments,
    }


def forward_email(mail_item) -> bool:
    """Forward the email to the central server mailbox (Email mode)."""
    try:
        fwd = mail_item.Forward()
        fwd.Recipients.Add(FORWARD_TO)
        fwd.Send()
        logger.info(f"Forwarded: {mail_item.Subject} -> {FORWARD_TO}")
        return True
    except Exception as e:
        logger.error(f"Forward failed: {e}")
        return False


def upload_to_api(mail_item) -> bool:
    """Submit the email and attachments directly to the central server API (API mode)."""
    try:
        data = {
            "message_id": mail_item.EntryID,
            "sender": f"{mail_item.SenderName} <{mail_item.SenderEmailAddress}>",
            "subject": mail_item.Subject or "",
            "date": str(mail_item.ReceivedTime),
            "body": mail_item.Body or "",
        }

        files = []
        temp_files_to_clean = []

        # Temp directory context to extract Outlook attachments securely
        with tempfile.TemporaryDirectory() as tmpdir:
            for i in range(1, mail_item.Attachments.Count + 1):
                att = mail_item.Attachments.Item(i)
                temp_path = os.path.join(tmpdir, att.FileName)
                att.SaveAsFile(temp_path)
                # Read bytes
                with open(temp_path, "rb") as f:
                    file_content = f.read()
                # Store tuple for requests: (field_name, (filename, file_bytes))
                files.append(("attachments", (att.FileName, file_content)))

            # POST request
            res = requests.post(API_INGEST_URL, data=data, files=files, timeout=60)
            if res.status_code == 200:
                logger.info(f"Uploaded directly via API: {mail_item.Subject}")
                return True
            else:
                logger.error(f"API upload failed with status {res.status_code}: {res.text}")
                return False

    except Exception as e:
        logger.error(f"Direct API upload failed: {e}")
        return False
