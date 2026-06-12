"""FastAPI routes — Ingestion + Data Extraction APIs for downstream pipeline consumers."""
import base64
import json
import io
from typing import List, Optional
from fastapi import APIRouter, BackgroundTasks, File, Form, UploadFile, Query, HTTPException
from fastapi.responses import StreamingResponse
from services.email_processor import process_new_emails
from services.rabbitmq_publisher import publish_email_task
from services.db_service import get_db_connection

router = APIRouter(prefix="/api/v1", tags=["emails"])


# ──────────────────────────────────────────────────────────────
#  HEALTH
# ──────────────────────────────────────────────────────────────
@router.get("/health", tags=["system"])
async def health():
    return {"status": "ok", "service": "ragnarok-central-server"}


@router.get("/stats", tags=["system"])
async def stats():
    """Database statistics for monitoring."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM emails")
    total_emails = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM attachments")
    total_att = cur.fetchone()[0]
    cur.execute("SELECT COALESCE(SUM(size),0) FROM attachments")
    total_size = cur.fetchone()[0]
    cur.execute("SELECT COUNT(DISTINCT sender) FROM emails")
    unique_senders = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM emails WHERE processed_at >= CURRENT_DATE")
    today = cur.fetchone()[0]
    cur.close(); conn.close()
    return {
        "total_emails": total_emails,
        "total_attachments": total_att,
        "storage_bytes": total_size,
        "unique_senders": unique_senders,
        "emails_today": today,
    }


# ──────────────────────────────────────────────────────────────
#  EMAIL LISTING & SEARCH  (for downstream pipeline consumers)
# ──────────────────────────────────────────────────────────────
@router.get("/emails")
async def list_emails(
    limit: int = Query(50, ge=1, le=500, description="Max rows to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    sender: Optional[str] = Query(None, description="Filter by sender (substring match)"),
    subject: Optional[str] = Query(None, description="Filter by subject (substring match)"),
    date_from: Optional[str] = Query(None, description="Filter emails after this date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="Filter emails before this date (YYYY-MM-DD)"),
):
    """List emails with pagination, filtering, and attachment metadata.
    
    Use this as the primary extraction endpoint for downstream pipelines.
    """
    conn = get_db_connection()
    cur = conn.cursor()

    where_clauses = []
    params = []
    if sender:
        where_clauses.append("e.sender ILIKE %s")
        params.append(f"%{sender}%")
    if subject:
        where_clauses.append("e.subject ILIKE %s")
        params.append(f"%{subject}%")
    if date_from:
        where_clauses.append("e.processed_at >= %s::date")
        params.append(date_from)
    if date_to:
        where_clauses.append("e.processed_at <= %s::date + interval '1 day'")
        params.append(date_to)

    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    # Get total count
    cur.execute(f"SELECT COUNT(*) FROM emails e {where_sql}", params)
    total = cur.fetchone()[0]

    # Get paginated results
    cur.execute(f"""
        SELECT e.id, e.message_id, e.sender, e.subject, e.received_at,
               e.body, e.nas_backup_path, e.processed_at,
               COALESCE(json_agg(json_build_object(
                   'id', a.id, 'filename', a.filename,
                   'content_type', a.content_type, 'size', a.size
               )) FILTER (WHERE a.id IS NOT NULL), '[]') as attachments
        FROM emails e
        LEFT JOIN attachments a ON e.id = a.email_id
        {where_sql}
        GROUP BY e.id
        ORDER BY e.processed_at DESC
        LIMIT %s OFFSET %s
    """, params + [limit, offset])

    rows = cur.fetchall()
    cols = [d[0] for d in cur.description]
    cur.close(); conn.close()

    emails = []
    for row in rows:
        email = dict(zip(cols, row))
        for k in ("processed_at", "received_at"):
            if email.get(k):
                email[k] = str(email[k])
        emails.append(email)

    return {"total": total, "limit": limit, "offset": offset, "emails": emails}


@router.get("/emails/{email_id}")
async def get_email(email_id: int):
    """Get a single email by database ID with full body and attachment list."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT e.id, e.message_id, e.sender, e.subject, e.received_at,
               e.body, e.nas_backup_path, e.processed_at,
               COALESCE(json_agg(json_build_object(
                   'id', a.id, 'filename', a.filename,
                   'content_type', a.content_type, 'size', a.size
               )) FILTER (WHERE a.id IS NOT NULL), '[]') as attachments
        FROM emails e
        LEFT JOIN attachments a ON e.id = a.email_id
        WHERE e.id = %s
        GROUP BY e.id
    """, (email_id,))
    row = cur.fetchone()
    cur.close(); conn.close()
    if not row:
        raise HTTPException(status_code=404, detail=f"Email ID {email_id} not found")
    cols = ["id", "message_id", "sender", "subject", "received_at",
            "body", "nas_backup_path", "processed_at", "attachments"]
    email = dict(zip(cols, row))
    for k in ("processed_at", "received_at"):
        if email.get(k):
            email[k] = str(email[k])
    return email


# ──────────────────────────────────────────────────────────────
#  ATTACHMENT DOWNLOAD (binary file retrieval)
# ──────────────────────────────────────────────────────────────
@router.get("/attachments/{attachment_id}")
async def get_attachment_meta(attachment_id: int):
    """Get attachment metadata (without binary content)."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT a.id, a.email_id, a.filename, a.content_type, a.size, e.sender, e.subject
        FROM attachments a JOIN emails e ON a.email_id = e.id
        WHERE a.id = %s
    """, (attachment_id,))
    row = cur.fetchone()
    cur.close(); conn.close()
    if not row:
        raise HTTPException(status_code=404, detail=f"Attachment ID {attachment_id} not found")
    return {
        "id": row[0], "email_id": row[1], "filename": row[2],
        "content_type": row[3], "size": row[4],
        "email_sender": row[5], "email_subject": row[6],
    }


@router.get("/attachments/{attachment_id}/download")
async def download_attachment(attachment_id: int):
    """Download the raw binary file for an attachment. Returns the actual file."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT filename, content_type, content FROM attachments WHERE id = %s", (attachment_id,))
    row = cur.fetchone()
    cur.close(); conn.close()
    if not row:
        raise HTTPException(status_code=404, detail=f"Attachment ID {attachment_id} not found")
    filename, content_type, content = row
    return StreamingResponse(
        io.BytesIO(bytes(content)),
        media_type=content_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@router.get("/emails/{email_id}/attachments")
async def list_email_attachments(email_id: int):
    """List all attachments for a specific email."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, filename, content_type, size FROM attachments WHERE email_id = %s ORDER BY id
    """, (email_id,))
    rows = cur.fetchall()
    cur.close(); conn.close()
    return {
        "email_id": email_id,
        "attachments": [
            {"id": r[0], "filename": r[1], "content_type": r[2], "size": r[3]}
            for r in rows
        ]
    }


# ──────────────────────────────────────────────────────────────
#  SEARCH  (full-text search across subject + body)
# ──────────────────────────────────────────────────────────────
@router.get("/search")
async def search_emails(
    q: str = Query(..., description="Search term (matches subject and body)"),
    limit: int = Query(20, ge=1, le=100),
):
    """Full-text search across email subjects and bodies."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT e.id, e.message_id, e.sender, e.subject,
               e.processed_at, COUNT(a.id) as attachment_count
        FROM emails e
        LEFT JOIN attachments a ON e.id = a.email_id
        WHERE e.subject ILIKE %s OR e.body ILIKE %s
        GROUP BY e.id
        ORDER BY e.processed_at DESC
        LIMIT %s
    """, (f"%{q}%", f"%{q}%", limit))
    rows = cur.fetchall()
    cur.close(); conn.close()
    return {
        "query": q,
        "results": [
            {"id": r[0], "message_id": r[1], "sender": r[2], "subject": r[3],
             "processed_at": str(r[4]) if r[4] else None, "attachment_count": r[5]}
            for r in rows
        ]
    }


# ──────────────────────────────────────────────────────────────
#  SENDERS LIST (unique senders for pipeline mapping)
# ──────────────────────────────────────────────────────────────
@router.get("/senders")
async def list_senders():
    """List all unique senders with their email counts."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT sender, COUNT(*) as email_count,
               MAX(processed_at) as last_email_at
        FROM emails GROUP BY sender ORDER BY email_count DESC
    """)
    rows = cur.fetchall()
    cur.close(); conn.close()
    return {
        "senders": [
            {"sender": r[0], "email_count": r[1], "last_email_at": str(r[2]) if r[2] else None}
            for r in rows
        ]
    }


# ──────────────────────────────────────────────────────────────
#  BATCH EXPORT (for bulk pipeline ingestion)
# ──────────────────────────────────────────────────────────────
@router.get("/export")
async def export_emails(
    since_id: int = Query(0, description="Export emails with ID greater than this (for incremental sync)"),
    limit: int = Query(100, ge=1, le=1000),
):
    """Incremental export endpoint for pipeline consumers.
    
    Use `since_id` to track your last processed ID and fetch only new emails.
    Perfect for ETL jobs, data pipelines, and batch processing.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT e.id, e.message_id, e.sender, e.subject, e.received_at,
               e.body, e.processed_at,
               COALESCE(json_agg(json_build_object(
                   'id', a.id, 'filename', a.filename,
                   'content_type', a.content_type, 'size', a.size
               )) FILTER (WHERE a.id IS NOT NULL), '[]') as attachments
        FROM emails e
        LEFT JOIN attachments a ON e.id = a.email_id
        WHERE e.id > %s
        GROUP BY e.id
        ORDER BY e.id ASC
        LIMIT %s
    """, (since_id, limit))
    rows = cur.fetchall()
    cols = [d[0] for d in cur.description]
    cur.close(); conn.close()

    emails = []
    max_id = since_id
    for row in rows:
        email = dict(zip(cols, row))
        for k in ("processed_at", "received_at"):
            if email.get(k):
                email[k] = str(email[k])
        emails.append(email)
        max_id = max(max_id, email["id"])

    return {
        "since_id": since_id,
        "max_id": max_id,
        "count": len(emails),
        "has_more": len(emails) == limit,
        "emails": emails,
    }


# ──────────────────────────────────────────────────────────────
#  INGESTION ENDPOINTS (existing)
# ──────────────────────────────────────────────────────────────
@router.post("/emails/fetch", tags=["ingestion"])
async def fetch_emails_gmail(background_tasks: BackgroundTasks):
    """Trigger Gmail API email fetch cycle in the background."""
    background_tasks.add_task(process_new_emails)
    return {"message": "Email fetch triggered"}


@router.get("/emails/fetch/sync", tags=["ingestion"])
async def fetch_emails_sync():
    """Synchronous Gmail API email fetch — returns count."""
    count = process_new_emails()
    return {"processed": count}


@router.post("/emails/submit", tags=["ingestion"])
async def submit_email(
    message_id: str = Form(...),
    sender: str = Form(...),
    subject: str = Form(...),
    date: str = Form(...),
    body: str = Form(...),
    attachments: List[UploadFile] = File(default=[])
):
    """Direct ingestion from Sales Agent — accepts email + attachments, queues to RabbitMQ."""
    email_data = {
        "id": message_id,
        "from": sender,
        "subject": subject,
        "date": date,
        "body": body,
        "attachments": [{"filename": att.filename, "size": 0} for att in attachments]
    }
    att_encoded = {}
    for att in attachments:
        content = await att.read()
        att_encoded[att.filename] = base64.b64encode(content).decode("utf-8")
    publish_email_task(email_data, att_encoded)
    return {
        "status": "queued",
        "message_id": message_id,
        "subject": subject,
        "attachments_count": len(attachments)
    }
