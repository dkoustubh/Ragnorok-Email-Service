"""Main entry point for the Sales Agent — monitors Outlook for RFQ emails."""
import sys
import time
from loguru import logger

from config.settings import CHECK_INTERVAL, LOG_LEVEL, LOG_DIR
from database.repository import init_db, is_processed, mark_processed
from services.outlook_client import get_outlook, get_inbox_emails, read_email, forward_email
from services.rfq_detector import is_rfq_email

# Configure logging
logger.remove()
logger.add(sys.stderr, level=LOG_LEVEL)
logger.add(LOG_DIR / "agent_{time}.log", rotation="10 MB", retention="30 days", level="DEBUG")


def process_mailbox():
    """Scan inbox, detect RFQs, forward and track."""
    namespace = get_outlook()
    messages = get_inbox_emails(namespace)
    processed_count = 0

    for i in range(min(messages.Count, 50)):  # Batch limit
        try:
            mail = messages.Item(i + 1)
            data = read_email(mail)

            if is_processed(data["entry_id"]):
                continue

            if is_rfq_email(data["subject"], data["body"]):
                forwarded = forward_email(mail)
                mark_processed(data["entry_id"], data["subject"], data["sender"], forwarded)
                processed_count += 1
                logger.info(f"RFQ detected & processed: {data['subject']}")
            else:
                mark_processed(data["entry_id"], data["subject"], data["sender"], forwarded=False)

        except Exception as e:
            logger.error(f"Error processing email {i}: {e}")

    return processed_count


def main():
    logger.info("Ragnarok Sales Agent starting...")
    init_db()

    while True:
        try:
            count = process_mailbox()
            logger.info(f"Cycle complete — {count} RFQs forwarded")
        except Exception as e:
            logger.error(f"Cycle error: {e}")

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
