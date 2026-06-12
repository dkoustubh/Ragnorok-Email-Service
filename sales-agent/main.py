"""Main entry point for the Sales Agent — monitors Outlook for RFQ emails with a gorgeous TUI dashboard."""
import sys
import time
from pathlib import Path
from dotenv import load_dotenv
from loguru import logger

import config.settings as settings
from database.repository import init_db, is_processed, mark_processed
from services.outlook_client import get_outlook, get_inbox_emails, read_email, forward_email
from services.rfq_detector import is_rfq_email
from services.tui import prompt_email, Dashboard, show_progress_bar, CLEAR_SCREEN, BOLD, RESET, RED

# Configure background file logging (does not print to stderr to avoid breaking TUI)
logger.remove()
logger.add(
    settings.LOG_DIR / "agent_{time}.log",
    rotation="10 MB",
    retention="30 days",
    level="DEBUG",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}"
)


def process_mailbox(dashboard: Dashboard):
    """Scan inbox, detect RFQs, forward and track."""
    dashboard.add_log("I", "Starting inbox scan (Latest 50 emails)...")
    
    try:
        namespace = get_outlook()
        messages = get_inbox_emails(namespace)
    except Exception as e:
        dashboard.update_checkpoint("outlook", "failed")
        dashboard.add_log("R", f"Outlook connection failed: {e}")
        logger.error(f"Outlook COM connection error: {e}")
        return 0

    dashboard.update_checkpoint("outlook", "ok")
    processed_count = 0
    total_messages = messages.Count

    for i in range(min(total_messages, 50)):
        try:
            mail = messages.Item(i + 1)
            data = read_email(mail)

            if is_processed(data["entry_id"]):
                continue

            if is_rfq_email(data["subject"], data["body"]):
                dashboard.add_log("Y", f"Found RFQ: '{data['subject'][:30]}...' from {data['sender']}")
                logger.info(f"RFQ Detected: {data['subject']} from {data['sender']}")
                
                dashboard.add_log("B", f"Forwarding to {settings.FORWARD_TO}...")
                forwarded = forward_email(mail)
                
                if forwarded:
                    dashboard.add_log("G", "Forward successful! Logged in local Database.")
                else:
                    dashboard.add_log("R", "Forwarding failed. Will retry next cycle.")
                
                mark_processed(data["entry_id"], data["subject"], data["sender"], forwarded)
                processed_count += 1
            else:
                # Silently mark as processed (non-RFQ) to avoid scanning again
                mark_processed(data["entry_id"], data["subject"], data["sender"], forwarded=False)

        except Exception as e:
            logger.error(f"Error processing email item index {i}: {e}")

    if processed_count > 0:
        dashboard.add_log("G", f"Interception cycle complete. {processed_count} new RFQs forwarded.")
    else:
        dashboard.add_log("I", "Interception cycle complete. No new RFQs found.")
        
    return processed_count


def main():
    # 1. Verify Monitored Email exists, if not, prompt user
    print(CLEAR_SCREEN, end="")
    monitored_email = settings.MONITORED_EMAIL
    
    if not monitored_email:
        monitored_email = prompt_email()
        # Reload env settings
        load_dotenv(Path(__file__).resolve().parent / ".env", override=True)
        import importlib
        importlib.reload(settings)
        settings.MONITORED_EMAIL = monitored_email

    # 2. Start TUI Dashboard
    dashboard = Dashboard(monitored_email, settings.FORWARD_TO)
    dashboard.draw()
    time.sleep(0.5)

    # 3. Process Checkpoint loaders
    # Checkpoint: Env Load
    show_progress_bar("Loading System Configurations...", 0.6)
    dashboard.update_checkpoint("env", "ok")
    dashboard.add_log("G", "Environment configurations parsed successfully.")

    # Checkpoint: DB Setup
    show_progress_bar("Initializing local database repository...", 0.8)
    try:
        init_db()
        dashboard.update_checkpoint("db", "ok")
        dashboard.add_log("G", "SQLite database verified (WAL mode enabled).")
    except Exception as e:
        dashboard.update_checkpoint("db", "failed")
        dashboard.add_log("R", f"Database initialization failed: {e}")
        logger.error(f"DB Init Error: {e}")
        sys.exit(1)

    # Checkpoint: Outlook COM Link
    show_progress_bar("Linking with Microsoft Outlook...", 1.0)
    try:
        get_outlook()
        dashboard.update_checkpoint("outlook", "ok")
        dashboard.add_log("G", "Outlook Desktop App link established.")
    except Exception as e:
        dashboard.update_checkpoint("outlook", "failed")
        dashboard.add_log("R", f"Failed to link with Outlook: {e}")
        logger.error(f"Outlook Link Error: {e}")
        # We don't exit here; the poller will retry in the loop.

    dashboard.update_checkpoint("poller", "ok")
    dashboard.add_log("G", "Ragnarok daemon started. Press Ctrl+C to stop.")

    # 4. Polling loop
    while True:
        try:
            process_mailbox(dashboard)
        except KeyboardInterrupt:
            print(f"\n{YELLOW}[Ragnarok] Exiting Sales Agent gracefully...{RESET}\n")
            sys.exit(0)
        except Exception as e:
            dashboard.add_log("R", f"Loop error: {e}")
            logger.error(f"Loop error: {e}")

        # Sleep interval countdown log on dashboard
        for sec in range(settings.CHECK_INTERVAL, 0, -1):
            if sec % 10 == 0 or sec <= 5:
                # Silently log interval updates in debug file, keep terminal static
                pass
            time.sleep(1)


if __name__ == "__main__":
    main()
