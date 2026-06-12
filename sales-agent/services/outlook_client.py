"""Outlook email reader and forwarder using pywin32 COM automation."""
import pythoncom
import win32com.client
from loguru import logger
from config.settings import OUTLOOK_FOLDER, FORWARD_TO


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
    """Extract metadata, body, and attachments from a mail item."""
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
    """Forward the email to the central server mailbox."""
    try:
        fwd = mail_item.Forward()
        fwd.Recipients.Add(FORWARD_TO)
        fwd.Send()
        logger.info(f"Forwarded: {mail_item.Subject} -> {FORWARD_TO}")
        return True
    except Exception as e:
        logger.error(f"Forward failed: {e}")
        return False
