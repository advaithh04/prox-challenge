FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for PyMuPDF
RUN apt-get update && apt-get install -y \
    gcc \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for caching
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY backend/*.py ./

# Copy PDF files
COPY files/ ./files/

# Create knowledge directory
RUN mkdir -p knowledge

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Expose port (Railway sets PORT env var)
EXPOSE 8000

# Start command
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
