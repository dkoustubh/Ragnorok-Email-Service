"""FastAPI routes for the Central Server API."""
from fastapi import APIRouter, BackgroundTasks
from services.email_processor import process_new_emails

router = APIRouter(prefix="/api/v1", tags=["emails"])


@router.get("/health")
async def health():
    return {"status": "ok", "service": "ragnarok-central-server"}


@router.post("/emails/fetch")
async def fetch_emails(background_tasks: BackgroundTasks):
    """Trigger email fetch cycle manually."""
    background_tasks.add_task(process_new_emails)
    return {"message": "Email fetch triggered"}


@router.get("/emails/fetch/sync")
async def fetch_emails_sync():
    """Synchronous email fetch — returns count."""
    count = process_new_emails()
    return {"processed": count}
