# Discord Archiver Docker Image
FROM python:3.9-slim-bullseye

# Install system dependencies for Playwright
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget curl gnupg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers
RUN playwright install --with-deps chromium

# Copy application code
COPY config.py app.py discord_client.py html_builder.py ./

EXPOSE 8501

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.headless=true"]
