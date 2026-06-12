"""FastAPI routes for the Central Server API, supporting synchronous Gmail polls and direct API ingestion."""
import base64
import json
from typing import List
from fastapi import APIRouter, BackgroundTasks, File, Form, UploadFile
from services.email_processor import process_new_emails
from services.rabbitmq_publisher import publish_email_task

router = APIRouter(prefix="/api/v1", tags=["emails"])


@router.get("/health")
async def health():
    return {"status": "ok", "service": "ragnarok-central-server"}


@router.post("/emails/fetch")
async def fetch_emails(background_tasks: BackgroundTasks):
    """Trigger Gmail API email fetch cycle in the background."""
    background_tasks.add_task(process_new_emails)
    return {"message": "Email fetch triggered"}


@router.get("/emails/fetch/sync")
async def fetch_emails_sync():
    """Synchronous Gmail API email fetch — returns count."""
    count = process_new_emails()
    return {"processed": count}


@router.post("/emails/submit")
async def submit_email(
    message_id: str = Form(...),
    sender: str = Form(...),
    subject: str = Form(...),
    date: str = Form(...),
    body: str = Form(...),
    attachments: List[UploadFile] = File(default=[])
):
    """Direct ingestion API endpoint. 
    Accepts email metadata and attachments, and publishes them to RabbitMQ for async processing.
    """
    # 1. Format metadata matching Gmail parser structure
    email_data = {
        "id": message_id,
        "from": sender,
        "subject": subject,
        "date": date,
        "body": body,
        "attachments": [
            {"filename": att.filename, "size": 0} for att in attachments
        ]
    }

    # 2. Read attachment files and encode to base64 for RabbitMQ transmission
    att_encoded = {}
    for att in attachments:
        content = await att.read()
        att_encoded[att.filename] = base64.b64encode(content).decode("utf-8")

    # 3. Publish to RabbitMQ
    publish_email_task(email_data, att_encoded)

    return {
        "status": "queued",
        "message_id": message_id,
        "subject": subject,
        "attachments_count": len(attachments)
    }
