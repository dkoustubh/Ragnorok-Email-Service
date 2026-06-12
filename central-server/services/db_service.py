"""PostgreSQL database service to manage connection, DB creation, schema, and metadata logging."""
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from loguru import logger
from app.config import DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME


def init_db():
    """Ensure database and schema exist in PostgreSQL."""
    conn = None
    try:
        # Step 1: Connect to default postgres DB to check/create the target DB
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

    # Step 2: Create schema in target DB
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS emails (
                    id SERIAL PRIMARY KEY,
                    message_id VARCHAR(255) UNIQUE,
                    sender VARCHAR(255),
                    subject VARCHAR(255),
                    received_at TIMESTAMP,
                    body TEXT,
                    storage_path VARCHAR(500),
                    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS attachments (
                    id SERIAL PRIMARY KEY,
                    email_id INTEGER REFERENCES emails(id) ON DELETE CASCADE,
                    filename VARCHAR(255),
                    size INTEGER
                );
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


def save_email_metadata(email_data: dict, storage_path: str) -> int:
    """Save email and attachment metadata into PostgreSQL."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Insert email metadata
            cursor.execute(
                """
                INSERT INTO emails (message_id, sender, subject, received_at, body, storage_path)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (message_id) DO UPDATE 
                SET storage_path = EXCLUDED.storage_path
                RETURNING id;
                """,
                (
                    email_data.get("id"),
                    email_data.get("from"),
                    email_data.get("subject"),
                    email_data.get("date"),
                    email_data.get("body"),
                    str(storage_path)
                )
            )
            email_id = cursor.fetchone()[0]

            # Insert attachments
            for att in email_data.get("attachments", []):
                cursor.execute(
                    "INSERT INTO attachments (email_id, filename, size) VALUES (%s, %s, %s)",
                    (email_id, att["filename"], att.get("size", 0))
                )
            conn.commit()
            logger.info(f"Saved email metadata to database (ID: {email_id})")
            return email_id
    except Exception as e:
        conn.rollback()
        logger.error(f"Failed to save email metadata to DB: {e}")
        return -1
    finally:
        conn.close()
