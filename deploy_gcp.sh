#!/bin/bash
set -e

APP_NAME="discord-archiver"
REGION="us-central1"

echo "=========================================="
echo "   ☁️  Deploying to Google Cloud Run      "
echo "=========================================="

# Check for gcloud
if ! command -v gcloud &> /dev/null; then
    echo "❌ Error: 'gcloud' CLI not installed"
    echo "Install at: https://cloud.google.com/sdk/docs/install"
    exit 1
fi

# Check for token.pickle
if [ ! -f "token.pickle" ]; then
    echo "❌ Error: token.pickle not found"
    echo "Run locally first to generate Google Drive credentials"
    exit 1
fi

# Generate base64 token
echo "🔑 Encoding credentials..."
TOKEN_B64=$(python3 -c "import base64; print(base64.b64encode(open('token.pickle', 'rb').read()).decode())")

if [ -z "$TOKEN_B64" ]; then
    echo "❌ Error: Could not encode token.pickle"
    exit 1
fi

# Read Discord token from .env
DISCORD_TOKEN=$(grep DISCORD_BOT_TOKEN .env | cut -d '=' -f2)
if [ -z "$DISCORD_TOKEN" ]; then
    echo "❌ Error: DISCORD_BOT_TOKEN not found in .env"
    exit 1
fi

echo "🚀 Deploying to Cloud Run..."

gcloud run deploy $APP_NAME \
    --source . \
    --platform managed \
    --region $REGION \
    --allow-unauthenticated \
    --set-env-vars "IS_CLOUD=true,DISCORD_BOT_TOKEN=$DISCORD_TOKEN,GOOGLE_DRIVE_TOKEN_BASE64=$TOKEN_B64" \
    --memory 2Gi \
    --cpu 2 \
    --port 8501

echo "=========================================="
echo "✅ Deployment complete!"
echo "=========================================="
