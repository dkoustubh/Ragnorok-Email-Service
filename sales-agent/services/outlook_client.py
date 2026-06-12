"""Multi-backend Email Client — supports Outlook Desktop COM (Windows) and standard IMAP (Cross-platform)."""
import os
import tempfile
import requests
import email
from email.header import decode_header
from loguru import logger
from config.settings import OUTLOOK_FOLDER, FORWARD_TO, API_INGEST_URL, MONITORED_EMAIL, MAIL_CLIENT_MODE, IMAP_HOST, IMAP_PORT, IMAP_PASSWORD


class EmailClientWrapper:
    def __init__(self, mode: str):
        self.mode = mode
        self.imap_client = None
        self.outlook_namespace = None


class IMAPMessagesList:
    def __init__(self, ids, imap_client):
        self.ids = ids
        self.imap_client = imap_client
        self.Count = len(ids)

    def Item(self, index):
        # 1-based indexing to match Outlook MAPI Collections
        return (self.ids[index - 1], self.imap_client)


_client_instance = None


def get_outlook():
    """Initialize the configured email backend wrapper (Outlook COM or IMAP)."""
    global _client_instance
    if _client_instance is not None:
        return _client_instance

    mode = MAIL_CLIENT_MODE.lower()

    # 1. Try Outlook Desktop (Windows only, when Outlook is installed)
    if mode in ("auto", "outlook") and os.name == "nt":
        try:
            import pythoncom
            import win32com.client
            pythoncom.CoInitialize()
            outlook = win32com.client.Dispatch("Outlook.Application")
            namespace = outlook.GetNamespace("MAPI")
            # Verify Outlook works by fetching default Inbox folder
            _ = namespace.GetDefaultFolder(6)

            wrapper = EmailClientWrapper("outlook")
            wrapper.outlook_namespace = namespace
            _client_instance = wrapper
            logger.info("Successfully connected to Outlook Desktop COM namespace.")
            return wrapper
        except Exception as e:
            logger.warning(f"Outlook Desktop COM connection failed: {e}. Falling back to IMAP.")
            if mode == "outlook":
                raise Exception("Outlook COM mode requested but failed. Is Outlook installed and logged in?") from e

    # 2. Fallback to IMAP
    import imaplib
    wrapper = EmailClientWrapper("imap")

    # Auto-resolve common IMAP hosts based on domain
    host = IMAP_HOST
    if not host and MONITORED_EMAIL:
        domain = MONITORED_EMAIL.split("@")[-1].lower()
        if "gmail.com" in domain:
            host = "imap.gmail.com"
        elif any(d in domain for d in ("outlook.com", "hotmail.com", "office365", "live.com")):
            host = "outlook.office365.com"

    if not host:
        raise Exception("IMAP_HOST is not set and could not be auto-resolved from MONITORED_EMAIL.")
    if not IMAP_PASSWORD:
        raise Exception("IMAP_PASSWORD is not set in .env. An App Password is required for Gmail/Outlook IMAP.")

    logger.info(f"Connecting to IMAP server {host}:{IMAP_PORT} for {MONITORED_EMAIL}...")
    try:
        mail = imaplib.IMAP4_SSL(host, IMAP_PORT)
        mail.login(MONITORED_EMAIL, IMAP_PASSWORD)
        mail.select("INBOX")
        wrapper.imap_client = mail
        _client_instance = wrapper
        logger.info("Successfully authenticated with IMAP server.")
        return wrapper
    except Exception as e:
        logger.error(f"IMAP connection failed: {e}")
        raise e


def get_inbox_emails(namespace):
    """Retrieve the latest emails from the configured Inbox folder."""
    if namespace.mode == "outlook":
        inbox = None
        if MONITORED_EMAIL:
            for folder in namespace.outlook_namespace.Folders:
                if MONITORED_EMAIL.lower() in folder.Name.lower():
                    try:
                        inbox = folder.Folders(OUTLOOK_FOLDER)
                        break
                    except Exception:
                        pass
        if inbox is None:
            inbox = namespace.outlook_namespace.GetDefaultFolder(6)  # olFolderInbox = 6
        messages = inbox.Items
        messages.Sort("[ReceivedTime]", True)
        return messages
    else:
        # IMAP: fetch message IDs (newest first)
        status, messages = namespace.imap_client.search(None, "ALL")
        if status != "OK":
            return IMAPMessagesList([], namespace.imap_client)
        mail_ids = messages[0].split()
        mail_ids.reverse()
        return IMAPMessagesList(mail_ids[:50], namespace.imap_client)


def _read_imap_email(msg_id, imap_client) -> dict:
    """Fetch and parse raw email via IMAP."""
    status, data = imap_client.fetch(msg_id, "(RFC822)")
    if status != "OK" or not data or not data[0]:
        raise Exception(f"Failed to fetch IMAP message ID: {msg_id}")

    raw_email = data[0][1]
    msg = email.message_from_bytes(raw_email)

    # Decode Subject
    subject = ""
    subject_header = msg.get("Subject", "")
    if subject_header:
        for part, encoding in decode_header(subject_header):
            if isinstance(part, bytes):
                subject += part.decode(encoding or "utf-8", errors="ignore")
            else:
                subject += part

    # Sender info
    sender = msg.get("From", "")

    # Extract Body and Attachments
    body = ""
    html_body = ""
    attachments = []

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition"))

            if "attachment" in content_disposition:
                filename = part.get_filename()
                if filename:
                    decoded_filename = ""
                    for p, encoding in decode_header(filename):
                        if isinstance(p, bytes):
                            decoded_filename += p.decode(encoding or "utf-8", errors="ignore")
                        else:
                            decoded_filename += p
                    payload = part.get_payload(decode=True)
                    size = len(payload) if payload else 0
                    attachments.append({
                        "name": decoded_filename,
                        "size": size,
                        "part": part
                    })
            else:
                if content_type == "text/plain":
                    payload = part.get_payload(decode=True)
                    if payload:
                        body += payload.decode("utf-8", errors="ignore")
                elif content_type == "text/html":
                    payload = part.get_payload(decode=True)
                    if payload:
                        html_body += payload.decode("utf-8", errors="ignore")
    else:
        content_type = msg.get_content_type()
        payload = msg.get_payload(decode=True)
        if payload:
            if content_type == "text/plain" or content_type == "text/html":
                body = payload.decode("utf-8", errors="ignore")

    entry_id = msg_id.decode("utf-8") if isinstance(msg_id, bytes) else str(msg_id)

    return {
        "entry_id": entry_id,
        "subject": subject,
        "sender": sender,
        "sender_name": sender,
        "body": body or html_body,
        "html_body": html_body,
        "received_time": msg.get("Date", ""),
        "attachment_count": len(attachments),
        "attachments": [{"name": a["name"], "size": a["size"]} for a in attachments],
        "_attachments_parts": attachments,
        "_msg": msg
    }


def read_email(mail_item) -> dict:
    """Extract metadata, body, and attachment structures from Outlook/IMAP mail handle."""
    if isinstance(mail_item, tuple):
        msg_id, imap_client = mail_item
        return _read_imap_email(msg_id, imap_client)
    else:
        # Outlook COM
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
    """Forward the email details via SMTP (IMAP mode) or default Outlook Mail (Outlook mode)."""
    try:
        if isinstance(mail_item, tuple):
            import smtplib
            from email.mime.multipart import MIMEMultipart
            from email.mime.text import MIMEText

            msg_id, imap_client = mail_item
            data_dict = _read_imap_email(msg_id, imap_client)

            # Auto-resolve SMTP server details
            domain = MONITORED_EMAIL.split("@")[-1].lower()
            smtp_host = "smtp.gmail.com"
            if any(d in domain for d in ("outlook", "hotmail", "office365", "live.com")):
                smtp_host = "smtp.office365.com"

            smtp_port = 587

            fwd_msg = MIMEMultipart()
            fwd_msg["From"] = MONITORED_EMAIL
            fwd_msg["To"] = FORWARD_TO
            fwd_msg["Subject"] = f"FW: {data_dict['subject']}"

            body = (
                f"---------- Forwarded message ---------\n"
                f"From: {data_dict['sender']}\n"
                f"Date: {data_dict['received_time']}\n"
                f"Subject: {data_dict['subject']}\n\n"
                f"{data_dict['body']}"
            )
            fwd_msg.attach(MIMEText(body, "plain"))

            # Re-attach original files
            for att in data_dict.get("_attachments_parts", []):
                fwd_msg.attach(att["part"])

            # Connect and dispatch
            server = smtplib.SMTP(smtp_host, smtp_port)
            server.starttls()
            server.login(MONITORED_EMAIL, IMAP_PASSWORD)
            server.sendmail(MONITORED_EMAIL, FORWARD_TO, fwd_msg.as_string())
            server.quit()

            logger.info(f"Forwarded email via SMTP: {data_dict['subject']} -> {FORWARD_TO}")
            return True
        else:
            # Outlook
            fwd = mail_item.Forward()
            fwd.Recipients.Add(FORWARD_TO)
            fwd.Send()
            logger.info(f"Forwarded email via Outlook: {mail_item.Subject} -> {FORWARD_TO}")
            return True
    except Exception as e:
        logger.error(f"Email forwarding failed: {e}")
        return False


def upload_to_api(mail_item) -> bool:
    """Submit the email and attachments directly to the central server ingestion API."""
    try:
        if isinstance(mail_item, tuple):
            msg_id, imap_client = mail_item
            data_dict = _read_imap_email(msg_id, imap_client)

            data = {
                "message_id": data_dict["entry_id"],
                "sender": data_dict["sender"],
                "subject": data_dict["subject"],
                "date": data_dict["received_time"],
                "body": data_dict["body"],
            }

            files = []
            for att in data_dict.get("_attachments_parts", []):
                part = att["part"]
                payload = part.get_payload(decode=True)
                if payload is not None:
                    files.append(("attachments", (att["name"], payload)))

            res = requests.post(API_INGEST_URL, data=data, files=files, timeout=60)
            if res.status_code == 200:
                logger.info(f"Uploaded via IMAP + API: {data_dict['subject']}")
                return True
            else:
                logger.error(f"API Ingestion returned error code {res.status_code}: {res.text}")
                return False
        else:
            # Outlook COM
            data = {
                "message_id": mail_item.EntryID,
                "sender": f"{mail_item.SenderName} <{mail_item.SenderEmailAddress}>",
                "subject": mail_item.Subject or "",
                "date": str(mail_item.ReceivedTime),
                "body": mail_item.Body or "",
            }

            files = []
            with tempfile.TemporaryDirectory() as tmpdir:
                for i in range(1, mail_item.Attachments.Count + 1):
                    att = mail_item.Attachments.Item(i)
                    temp_path = os.path.join(tmpdir, att.FileName)
                    att.SaveAsFile(temp_path)
                    with open(temp_path, "rb") as f:
                        file_content = f.read()
                    files.append(("attachments", (att.FileName, file_content)))

                res = requests.post(API_INGEST_URL, data=data, files=files, timeout=60)
                if res.status_code == 200:
                    logger.info(f"Uploaded via Outlook + API: {mail_item.Subject}")
                    return True
                else:
                    logger.error(f"API Ingestion returned error code {res.status_code}: {res.text}")
                    return False
    except Exception as e:
        logger.error(f"Direct API upload failed: {e}")
        return False
