# Discord Archiver

Archive Discord channels to high-fidelity PDFs with Cloud Support and Parallel Processing.

## 🚀 Live App

👉 **[Open App](https://discord-archiver-999941660092.us-central1.run.app)**

---

## Features

- **Parallel Downloads**: 4 channels at once
- **Google Drive Sync**: Auto-upload PDFs
- **Cloud Hosted**: Runs on Google Cloud Run

---

## Quick Start

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt
playwright install chromium

# Run
streamlit run app.py
```

### Docker

```bash
docker compose up --build
```

### Deploy to Cloud

```bash
./deploy_gcp.sh
```

---

## Environment Variables

| Variable | Description |
|----------|-------------|
| `DISCORD_BOT_TOKEN` | Your Discord bot token |
| `GOOGLE_DRIVE_TOKEN_BASE64` | Base64 Drive credentials (cloud only) |
| `IS_CLOUD` | Set `true` for cloud deployment |

---

## Project Structure

```
├── app.py              # Streamlit web app
├── config.py           # Shared configuration
├── Dockerfile          # Container definition
├── docker-compose.yml  # Local Docker setup
├── deploy_gcp.sh       # Cloud Run deployment
└── DiscordChatExporterCli/  # Export tool
```

---

## Troubleshooting

- **Missing token**: Create `.env` with `DISCORD_BOT_TOKEN=your_token`
- **No credentials.json**: Download from [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
- **Upload failures**: Auto-retried; backups saved to `Local_Backup_PDFs/`
