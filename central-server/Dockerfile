FROM python:3.10-slim

WORKDIR /app

# Install system dependencies for psycopg2 and curl
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Expose default FastAPI port
EXPOSE 8000

# Default command is uvicorn, can be overridden by docker-compose for the worker
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
