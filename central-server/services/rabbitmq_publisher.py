"""RabbitMQ publisher to queue incoming email tasks for async processing."""
import json
import pika
from loguru import logger
from app.config import RABBITMQ_HOST, RABBITMQ_PORT, RABBITMQ_USER, RABBITMQ_PASSWORD, RABBITMQ_QUEUE


def publish_email_task(email_data: dict, attachment_bytes: dict[str, str]):
    """Publish email details to RabbitMQ.
    Note: attachment_bytes are serialized as base64 or passed directly if already encoded,
    but since we want to pass them to RabbitMQ, we will encode attachment bytes to base64 string
    for json serialization.
    """
    try:
        credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASSWORD)
        parameters = pika.ConnectionParameters(
            host=RABBITMQ_HOST,
            port=RABBITMQ_PORT,
            credentials=credentials,
            heartbeat=600,
            blocked_connection_timeout=300
        )
        connection = pika.BlockingConnection(parameters)
        channel = connection.channel()
        channel.queue_declare(queue=RABBITMQ_QUEUE, durable=True)

        message = {
            "email_data": email_data,
            "attachments": attachment_bytes  # dict of {filename: base64_str}
        }

        channel.basic_publish(
            exchange="",
            routing_key=RABBITMQ_QUEUE,
            body=json.dumps(message),
            properties=pika.BasicProperties(
                delivery_mode=2,  # make message persistent
            )
        )
        connection.close()
        logger.info(f"Published email task to RabbitMQ queue: {email_data.get('subject')}")
    except Exception as e:
        logger.error(f"Failed to publish email task to RabbitMQ: {e}")
        raise e
