#!/bin/bash
set -e

# India Votes Data API - Update Script
# Run this to update the application after pushing changes

APP_DIR="/opt/india-votes-data"

echo "=========================================="
echo "India Votes Data API - Update Script"
echo "=========================================="

cd $APP_DIR

echo "Pulling latest changes from git..."
git pull

echo "Activating virtual environment..."
source venv/bin/activate

echo "Updating dependencies..."
pip install -r requirements.txt --upgrade

echo "Restarting service..."
sudo systemctl restart india-votes-api

echo "Checking service status..."
sleep 2
sudo systemctl status india-votes-api --no-pager

echo ""
echo "Update complete! Check logs if needed:"
echo "  sudo journalctl -u india-votes-api -n 50"
