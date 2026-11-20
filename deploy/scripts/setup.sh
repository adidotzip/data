#!/bin/bash
set -e

# India Votes Data API - Deployment Setup Script
# Run this script on your Linux server as root or with sudo

echo "=========================================="
echo "India Votes Data API - Setup Script"
echo "=========================================="
echo ""

# Configuration variables
APP_DIR="/opt/india-votes-data"
APP_USER="www-data"
APP_GROUP="www-data"
LOG_DIR="/var/log/india-votes-api"
PYTHON_VERSION="3.14"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo -e "${RED}This script must be run as root (use sudo)${NC}" 
   exit 1
fi

echo -e "${GREEN}Step 1: Installing system dependencies...${NC}"
apt-get update
apt-get install -y \
    python3.14 \
    python3.14-venv \
    python3-pip \
    postgresql \
    postgresql-contrib \
    nginx \
    git \
    curl \
    chromium-browser \
    chromium-chromedriver \
    tesseract-ocr \
    poppler-utils \
    build-essential \
    libpq-dev

echo ""
echo -e "${GREEN}Step 2: Creating application directory...${NC}"
mkdir -p $APP_DIR
mkdir -p $LOG_DIR
chown -R $APP_USER:$APP_GROUP $LOG_DIR

echo ""
echo -e "${GREEN}Step 3: Setting up Python virtual environment...${NC}"
cd $APP_DIR
python3.14 -m venv venv
source venv/bin/activate

echo ""
echo -e "${GREEN}Step 4: Installing Python dependencies...${NC}"
pip install --upgrade pip
pip install -r requirements.txt

echo ""
echo -e "${GREEN}Step 5: Setting up PostgreSQL database...${NC}"
read -p "Do you want to create a PostgreSQL database? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    read -p "Enter database name [election_results]: " DB_NAME
    DB_NAME=${DB_NAME:-election_results}
    
    read -p "Enter database user [election_user]: " DB_USER
    DB_USER=${DB_USER:-election_user}
    
    read -sp "Enter database password: " DB_PASS
    echo
    
    sudo -u postgres psql -c "CREATE DATABASE $DB_NAME;"
    sudo -u postgres psql -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASS';"
    sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;"
    
    echo -e "${GREEN}Database created successfully!${NC}"
    echo -e "${YELLOW}Add this to your .env file:${NC}"
    echo "DATABASE_URL=postgresql://$DB_USER:$DB_PASS@localhost:5432/$DB_NAME"
fi

echo ""
echo -e "${GREEN}Step 6: Setting up environment configuration...${NC}"
if [ ! -f "$APP_DIR/.env" ]; then
    cp .env.example .env
    echo -e "${YELLOW}Created .env file. Please edit it with your configuration.${NC}"
else
    echo -e "${YELLOW}.env file already exists. Skipping.${NC}"
fi

echo ""
echo -e "${GREEN}Step 7: Initializing database schema...${NC}"
read -p "Do you want to initialize the database schema? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    python -c "from db import init_db; init_db()"
    echo -e "${GREEN}Database schema initialized!${NC}"
fi

echo ""
echo -e "${GREEN}Step 8: Setting up systemd service...${NC}"
cp deploy/systemd/india-votes-api.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable india-votes-api.service
echo -e "${GREEN}Systemd service installed and enabled${NC}"

echo ""
echo -e "${GREEN}Step 9: Setting up Nginx...${NC}"
cp deploy/nginx/india-votes-api.conf /etc/nginx/sites-available/
ln -sf /etc/nginx/sites-available/india-votes-api.conf /etc/nginx/sites-enabled/
nginx -t
echo -e "${YELLOW}Please edit /etc/nginx/sites-available/india-votes-api.conf with your domain name${NC}"

echo ""
echo -e "${GREEN}Step 10: Setting permissions...${NC}"
chown -R $APP_USER:$APP_GROUP $APP_DIR
chmod -R 755 $APP_DIR
chmod 600 $APP_DIR/.env

echo ""
echo "=========================================="
echo -e "${GREEN}Setup Complete!${NC}"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Edit $APP_DIR/.env with your configuration"
echo "2. Edit /etc/nginx/sites-available/india-votes-api.conf with your domain"
echo "3. Start the service: sudo systemctl start india-votes-api"
echo "4. Check status: sudo systemctl status india-votes-api"
echo "5. Reload Nginx: sudo systemctl reload nginx"
echo "6. (Optional) Setup SSL with certbot:"
echo "   sudo apt-get install certbot python3-certbot-nginx"
echo "   sudo certbot --nginx -d your-domain.com"
echo ""
echo "View logs:"
echo "  Application: sudo journalctl -u india-votes-api -f"
echo "  Nginx: sudo tail -f /var/log/nginx/india-votes-api-error.log"
echo ""
