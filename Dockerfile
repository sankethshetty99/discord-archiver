# Discord Archiver Docker Image
FROM python:3.9-slim-bullseye

# Install system dependencies for .NET and Playwright
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget curl gnupg \
    && rm -rf /var/lib/apt/lists/*

# Install .NET 8.0 (Required for DiscordChatExporter)
RUN wget -q https://packages.microsoft.com/config/debian/11/packages-microsoft-prod.deb -O packages-microsoft-prod.deb \
    && dpkg -i packages-microsoft-prod.deb \
    && rm packages-microsoft-prod.deb \
    && apt-get update \
    && apt-get install -y --no-install-recommends dotnet-sdk-8.0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers
RUN playwright install --with-deps chromium

# Copy application code
COPY config.py app.py ./
COPY DiscordChatExporterCli ./DiscordChatExporterCli/

# Make exporter executable
RUN chmod +x ./DiscordChatExporterCli/DiscordChatExporter.Cli

EXPOSE 8501

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.headless=true"]
