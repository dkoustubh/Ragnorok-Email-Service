"""Email processor — orchestrates fetching, parsing, storing to NAS, and saving metadata to PostgreSQL."""
from loguru import logger
from services.gmail_client import get_gmail_service, list_unread_messages, get_message_detail, download_attachment, mark_as_read
from services.storage_service import store_email
from services.db_service import init_db, save_email_metadata

# Latch to ensure database is initialized once at runtime
_db_initialized = False


def process_new_emails() -> int:
    """Fetch unread emails, store them on NAS, log metadata in PostgreSQL, and mark as read."""
    global _db_initialized
    if not _db_initialized:
        init_db()
        _db_initialized = True

    try:
        service = get_gmail_service()
    except Exception as e:
        logger.error(f"Failed to connect to Gmail service: {e}")
        return 0

    messages = list_unread_messages(service)
    count = 0

    for msg_ref in messages:
        try:
            msg_id = msg_ref["id"]
            detail = get_message_detail(service, msg_id)

            # Download all attachments
            att_bytes = {}
            for att in detail.get("attachments", []):
                try:
                    data = download_attachment(service, msg_id, att["attachment_id"])
                    att_bytes[att["filename"]] = data
                except Exception as e:
                    logger.error(f"Failed to download attachment {att.get('filename')}: {e}")

            # Store to filesystem or NAS
            storage_path = store_email(detail, att_bytes)

            # Save metadata to PostgreSQL database
            save_email_metadata(detail, storage_path)

            # Mark as read in Gmail
            mark_as_read(service, msg_id)
            count += 1

        except Exception as e:
            logger.error(f"Error processing message {msg_ref.get('id')}: {e}")

    return count
