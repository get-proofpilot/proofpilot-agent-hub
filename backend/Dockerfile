FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create default docs dir so the app works without a Volume
RUN mkdir -p temp_docs

EXPOSE 8000

# DATABASE_PATH and DOCS_DIR are runtime env vars set by Railway (or defaulted in code)
CMD uvicorn server:app --host 0.0.0.0 --port ${PORT:-8000}
