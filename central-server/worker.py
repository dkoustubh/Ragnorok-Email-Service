"""RabbitMQ Worker process to consume email tasks, save to Postgres, and backup to NAS."""
import os
import sys
import json
import time
import base64
import pika
from loguru import logger

# Add current folder to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.config import RABBITMQ_HOST, RABBITMQ_PORT, RABBITMQ_USER, RABBITMQ_PASSWORD, RABBITMQ_QUEUE
from services.db_service import init_db, save_email_to_db
from services.storage_service import store_email

# Configure logging
logger.remove()
logger.add(sys.stderr, level="INFO")
logger.add("logs/worker_{time}.log", rotation="10 MB", retention="30 days", level="DEBUG")


def callback(ch, method, properties, body):
    """Processes a single email task from RabbitMQ."""
    try:
        task = json.loads(body.decode("utf-8"))
        email_data = task["email_data"]
        attachments_encoded = task["attachments"]

        logger.info(f"Processing email task: {email_data.get('subject')} from {email_data.get('from')}")

        # Decode attachment bytes from base64
        attachment_bytes = {}
        for filename, b64_str in attachments_encoded.items():
            attachment_bytes[filename] = base64.b64decode(b64_str)

        # 1. Back up files to the remote NAS
        try:
            nas_backup_path = store_email(email_data, attachment_bytes)
            logger.info(f"NAS Backup complete: {nas_backup_path}")
        except Exception as e:
            logger.error(f"NAS Backup failed: {e}")
            nas_backup_path = "NAS_BACKUP_FAILED"

        # 2. Perform main CRUD / database persistence (metadata + raw attachment bytes)
        db_id = save_email_to_db(email_data, attachment_bytes, nas_backup_path)
        
        if db_id != -1:
            logger.info(f"Successfully processed and stored email DB ID: {db_id}")
            # Acknowledge completion of task
            ch.basic_ack(delivery_tag=method.delivery_tag)
        else:
            logger.error("Database storage failed. Retrying later (not acknowledging).")

    except Exception as e:
        logger.error(f"Failed to process task: {e}")


def main():
    logger.info("Initializing PostgreSQL schema...")
    init_db()

    logger.info("Connecting to RabbitMQ...")
    credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASSWORD)
    parameters = pika.ConnectionParameters(
        host=RABBITMQ_HOST,
        port=RABBITMQ_PORT,
        credentials=credentials,
        heartbeat=600,
        blocked_connection_timeout=300
    )

    while True:
        try:
            connection = pika.BlockingConnection(parameters)
            channel = connection.channel()
            channel.queue_declare(queue=RABBITMQ_QUEUE, durable=True)
            
            # Fair dispatch: distribute 1 message at a time to workers
            channel.basic_qos(prefetch_count=1)
            channel.basic_consume(queue=RABBITMQ_QUEUE, on_message_callback=callback)

            logger.info(f" [*] Worker listening on queue '{RABBITMQ_QUEUE}'. To exit press CTRL+C")
            channel.start_consuming()

        except pika.exceptions.AMQPConnectionError as e:
            logger.warning(f"RabbitMQ connection lost. Retrying in 5 seconds... ({e})")
            time.sleep(5)
        except KeyboardInterrupt:
            logger.info("Worker shutting down gracefully.")
            break
        except Exception as e:
            logger.error(f"Unexpected worker error: {e}")
            time.sleep(5)


if __name__ == "__main__":
    main()
