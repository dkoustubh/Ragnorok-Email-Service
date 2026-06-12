"""Email processor — orchestrates fetching, parsing, and storing emails."""
from loguru import logger
from services.gmail_client import get_gmail_service, list_unread_messages, get_message_detail, download_attachment, mark_as_read
from services.storage_service import store_email


def process_new_emails() -> int:
    """Fetch unread emails, store them, and mark as read. Returns count processed."""
    service = get_gmail_service()
    messages = list_unread_messages(service)
    count = 0

    for msg_ref in messages:
        try:
            msg_id = msg_ref["id"]
            detail = get_message_detail(service, msg_id)

            # Download all attachments
            att_bytes = {}
            for att in detail.get("attachments", []):
                data = download_attachment(service, msg_id, att["attachment_id"])
                att_bytes[att["filename"]] = data

            # Store to filesystem
            store_email(detail, att_bytes)

            # Mark as read
            mark_as_read(service, msg_id)
            count += 1

        except Exception as e:
            logger.error(f"Error processing message {msg_ref.get('id')}: {e}")

    return count
