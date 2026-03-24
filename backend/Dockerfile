FROM python:3.11-slim

# Cache-bust arg — change value to force full rebuild
ARG BUILD_VERSION=v24-seo-playbook

WORKDIR /app

# Install Node.js (for docx npm package — branded DOCX generation)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy ALL application code (invalidate cache on any file change)
COPY . .

# Install Node.js dependencies inline (no package.json to avoid Railpack static detection)
RUN npm init -y > /dev/null 2>&1 && npm install --omit=dev docx@9.5.3 jszip@3.10.1

# Ensure default directories exist
RUN mkdir -p temp_docs

EXPOSE 8000

CMD ["sh", "-c", "uvicorn server:app --host 0.0.0.0 --port ${PORT:-8000}"]
