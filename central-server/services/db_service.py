"""PostgreSQL database service to manage connection, schema creation, metadata, and raw attachment binary storage."""
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from loguru import logger
from app.config import DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME


def init_db():
    """Ensure database and schema exist in PostgreSQL."""
    conn = None
    try:
        # Connect to default postgres DB to check/create the target DB
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            dbname="postgres"
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (DB_NAME,))
            if not cursor.fetchone():
                cursor.execute(f'CREATE DATABASE "{DB_NAME}"')
                logger.info(f"Created database: {DB_NAME}")
    except Exception as e:
        logger.error(f"Error checking/creating PostgreSQL database: {e}")
    finally:
        if conn:
            conn.close()

    # Create schema in target DB
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS emails (
                    id SERIAL PRIMARY KEY,
                    message_id VARCHAR(512) UNIQUE,
                    sender VARCHAR(512),
                    subject TEXT,
                    received_at TIMESTAMP,
                    body TEXT,
                    nas_backup_path VARCHAR(500),
                    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS attachments (
                    id SERIAL PRIMARY KEY,
                    email_id INTEGER REFERENCES emails(id) ON DELETE CASCADE,
                    filename VARCHAR(512),
                    content_type VARCHAR(255) DEFAULT 'application/octet-stream',
                    size INTEGER,
                    content BYTEA
                );
            """)
            conn.commit()
            # Auto-migrate: add content_type column if it doesn't exist (existing installs)
            cursor.execute("""
                DO $$ BEGIN
                    ALTER TABLE attachments ADD COLUMN content_type VARCHAR(255) DEFAULT 'application/octet-stream';
                EXCEPTION WHEN duplicate_column THEN NULL;
                END $$;
            """)
            conn.commit()
            logger.info("PostgreSQL database tables verified/created successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize PostgreSQL schema: {e}")
    finally:
        if conn:
            conn.close()


def get_db_connection():
    """Return connection to the target database."""
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        dbname=DB_NAME
    )


def _guess_mime(filename: str) -> str:
    """Guess MIME type from filename extension."""
    import mimetypes
    mime, _ = mimetypes.guess_type(filename)
    return mime or "application/octet-stream"


def save_email_to_db(email_data: dict, attachment_bytes: dict[str, bytes], nas_path: str) -> int:
    """Save email and binary attachment data directly into PostgreSQL.
    
    Returns the email DB ID or -1 on failure.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Insert email metadata and body
            cursor.execute(
                """
                INSERT INTO emails (message_id, sender, subject, received_at, body, nas_backup_path)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (message_id) DO UPDATE 
                SET nas_backup_path = EXCLUDED.nas_backup_path
                RETURNING id;
                """,
                (
                    email_data.get("id"),
                    email_data.get("from"),
                    email_data.get("subject"),
                    email_data.get("date"),
                    email_data.get("body"),
                    nas_path
                )
            )
            email_id = cursor.fetchone()[0]

            # Clear existing attachments if any to handle retries/updates cleanly
            cursor.execute("DELETE FROM attachments WHERE email_id = %s", (email_id,))

            # Insert attachments with binary content (BYTEA)
            for filename, data in attachment_bytes.items():
                cursor.execute(
                    """
                    INSERT INTO attachments (email_id, filename, content_type, size, content)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (email_id, filename, _guess_mime(filename), len(data), psycopg2.Binary(data))
                )
            conn.commit()
            logger.info(f"Successfully saved email and attachments directly to database (DB ID: {email_id})")
            return email_id
    except Exception as e:
        conn.rollback()
        logger.error(f"Failed to save email/attachments to DB: {e}")
        return -1
    finally:
        conn.close()
