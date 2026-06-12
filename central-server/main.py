"""Central Server entry point — FastAPI app with background email polling."""
import sys
import asyncio
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI
from loguru import logger

from app.config import HOST, PORT, LOG_LEVEL, LOG_DIR, CHECK_INTERVAL
from app.routes import router
from services.email_processor import process_new_emails

# Configure logging
logger.remove()
logger.add(sys.stderr, level=LOG_LEVEL)
logger.add(LOG_DIR / "server_{time}.log", rotation="10 MB", retention="30 days", level="DEBUG")


async def _poll_emails():
    """Background task that periodically checks for new emails."""
    while True:
        try:
            count = process_new_emails()
            logger.info(f"Poll cycle: {count} emails processed")
        except Exception as e:
            logger.error(f"Poll error: {e}")
        await asyncio.sleep(CHECK_INTERVAL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Ragnarok Central Server starting...")
    task = asyncio.create_task(_poll_emails())
    yield
    task.cancel()
    logger.info("Server shutting down")


app = FastAPI(
    title="Ragnarok Central Server",
    version="1.0.0",
    description="RFQ Email Processing & Storage Server",
    lifespan=lifespan,
)
app.include_router(router)


if __name__ == "__main__":
    uvicorn.run("main:app", host=HOST, port=PORT, reload=True)
