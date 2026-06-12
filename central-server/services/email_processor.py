"""Email processor — fetches unread emails and publishes tasks to RabbitMQ for async processing."""
import base64
from loguru import logger
from services.gmail_client import get_gmail_service, list_unread_messages, get_message_detail, download_attachment, mark_as_read
from services.rabbitmq_publisher import publish_email_task


def process_new_emails() -> int:
    """Fetch unread emails, serialize them, and push to RabbitMQ. Returns count processed."""
    try:
        service = get_gmail_service()
    except Exception as e:
        logger.error(f"Failed to connect to Gmail service: {e}")
        return 0

    try:
        messages = list_unread_messages(service)
    except Exception as e:
        logger.error(f"Failed to list unread messages: {e}")
        return 0

    count = 0
    for msg_ref in messages:
        try:
            msg_id = msg_ref["id"]
            detail = get_message_detail(service, msg_id)

            # Download all attachments and encode to base64 for transmission via RabbitMQ
            att_encoded = {}
            for att in detail.get("attachments", []):
                try:
                    data = download_attachment(service, msg_id, att["attachment_id"])
                    att_encoded[att["filename"]] = base64.b64encode(data).decode("utf-8")
                except Exception as e:
                    logger.error(f"Failed to download attachment {att.get('filename')}: {e}")

            # Publish task to RabbitMQ
            publish_email_task(detail, att_encoded)

            # Mark as read in Gmail
            mark_as_read(service, msg_id)
            count += 1

        except Exception as e:
            logger.error(f"Error forwarding message {msg_ref.get('id')} to RabbitMQ: {e}")

    return count
