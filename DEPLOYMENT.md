# Deployment Guide - India Votes Data API

This guide covers deploying the India Votes Data API on a Linux server (Ubuntu/Debian).

## Quick Start

For automated setup, run the setup script:

```bash
sudo bash deploy/scripts/setup.sh
```

The script will:
- Install system dependencies (Python, PostgreSQL, Nginx, Chrome, etc.)
- Create a virtual environment
- Install Python packages
- Set up PostgreSQL database (optional)
- Configure systemd service
- Configure Nginx reverse proxy
- Set up logging

## Manual Deployment

If you prefer manual setup or need to customize:

### 1. Prerequisites

#### System Requirements
- Linux server (Ubuntu 20.04+ or Debian 11+ recommended)
- Python 3.14+
- PostgreSQL 13+ (or SQLite for smaller deployments)
- Nginx or Apache
- Chrome/Chromium (for web scraping)
- 2GB+ RAM
- 10GB+ disk space

#### Install System Packages

**Ubuntu/Debian:**
```bash
sudo apt-get update
sudo apt-get install -y \
    python3.14 python3.14-venv python3-pip \
    postgresql postgresql-contrib \
    nginx \
    git curl \
    chromium-browser chromium-chromedriver \
    tesseract-ocr poppler-utils \
    build-essential libpq-dev
```

**RHEL/CentOS/Fedora:**
```bash
sudo dnf install -y \
    python3.14 python3-pip \
    postgresql-server postgresql-contrib \
    nginx \
    git curl \
    chromium chromium-chromedriver \
    tesseract poppler-utils \
    gcc gcc-c++ make libpq-devel
```

### 2. Application Setup

#### Clone Repository

```bash
sudo mkdir -p /opt/india-votes-data
sudo chown $USER:$USER /opt/india-votes-data
cd /opt/india-votes-data
git clone https://github.com/yourusername/india-votes-data.git .
```

#### Create Virtual Environment

```bash
python3.14 -m venv venv
source venv/bin/activate
```

#### Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Database Setup

#### Option A: PostgreSQL (Recommended for Production)

**Create Database:**
```bash
sudo -u postgres psql
```

```sql
CREATE DATABASE election_results;
CREATE USER election_user WITH PASSWORD 'your_secure_password';
GRANT ALL PRIVILEGES ON DATABASE election_results TO election_user;
\q
```

**Initialize Schema:**
```bash
export DATABASE_URL="postgresql://election_user:your_secure_password@localhost:5432/election_results"
python -c "from db import init_db; init_db()"
```

#### Option B: SQLite (For Development/Testing)

```bash
export DATABASE_URL="data/india-votes-data.db"
python -c "from db import init_db; init_db()"
```

### 4. Configuration

#### Create Environment File

```bash
cp .env.example .env
nano .env
```

**Example .env:**
```bash
# Database
DATABASE_URL=postgresql://election_user:password@localhost:5432/election_results

# Server
HOST=0.0.0.0
PORT=8000
WORKERS=4

# CORS (adjust for production)
ALLOWED_ORIGINS=https://yourdomain.com,https://www.yourdomain.com

# Logging
LOG_LEVEL=info
```

#### Set Permissions

```bash
sudo chown -R www-data:www-data /opt/india-votes-data
sudo chmod 600 /opt/india-votes-data/.env
```

### 5. Systemd Service Setup

#### Install Service

```bash
sudo cp deploy/systemd/india-votes-api.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable india-votes-api
sudo systemctl start india-votes-api
```

#### Check Status

```bash
sudo systemctl status india-votes-api
```

#### View Logs

```bash
# Follow live logs
sudo journalctl -u india-votes-api -f

# View recent logs
sudo journalctl -u india-votes-api -n 100
```

### 6. Nginx Setup

#### Install Configuration

```bash
sudo cp deploy/nginx/india-votes-api.conf /etc/nginx/sites-available/
sudo ln -s /etc/nginx/sites-available/india-votes-api.conf /etc/nginx/sites-enabled/
```

#### Edit Configuration

```bash
sudo nano /etc/nginx/sites-available/india-votes-api.conf
```

Replace `api.yourdomain.com` with your actual domain.

#### Test and Reload

```bash
sudo nginx -t
sudo systemctl reload nginx
```

### 7. SSL Certificate (Production)

#### Using Let's Encrypt (Certbot)

```bash
sudo apt-get install certbot python3-certbot-nginx
sudo certbot --nginx -d api.yourdomain.com
```

Certbot will automatically:
- Obtain SSL certificate
- Configure Nginx
- Set up auto-renewal

#### Manual Certificate

If using a different CA, place certificates in `/etc/ssl/` and update nginx config:

```nginx
ssl_certificate /etc/ssl/certs/your-cert.crt;
ssl_certificate_key /etc/ssl/private/your-key.key;
```

### 8. Firewall Configuration

```bash
# Allow HTTP and HTTPS
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# Allow SSH (if not already allowed)
sudo ufw allow 22/tcp

# Enable firewall
sudo ufw enable
```

### 9. Data Population

#### Load Reference Data

```bash
cd /opt/india-votes-data
source venv/bin/activate

# States and parties are loaded during init_db()
# If you have CSV data to import:
python scripts/ingest-csv-up-uk.py --state S25
```

#### Scrape Live Data

```bash
# Using CLI scraper
python cli.py --url "https://results.eci.gov.in/ResultAcGenMay2026/partywiseresult-S22.htm" --csv --json

# Using live client (for counting day)
python scripts/eci-live-scraper.py --url "..." --live
```

## Monitoring and Maintenance

### Health Check

```bash
curl http://localhost:8000/health
# Should return: {"status": "healthy"}
```

### Log Monitoring

```bash
# Application logs
sudo journalctl -u india-votes-api -f

# Nginx access logs
sudo tail -f /var/log/nginx/india-votes-api-access.log

# Nginx error logs
sudo tail -f /var/log/nginx/india-votes-api-error.log
```

### Database Backup

**PostgreSQL:**
```bash
# Backup
pg_dump -U election_user election_results > backup_$(date +%Y%m%d).sql

# Restore
psql -U election_user election_results < backup_20260520.sql
```

**SQLite:**
```bash
# Backup
cp data/india-votes-data.db data/backup_$(date +%Y%m%d).db

# Or use SQLite backup command
sqlite3 data/india-votes-data.db ".backup 'backup.db'"
```

### Updates

```bash
# Using update script
sudo bash deploy/scripts/update.sh

# Or manually
cd /opt/india-votes-data
git pull
source venv/bin/activate
pip install -r requirements.txt --upgrade
sudo systemctl restart india-votes-api
```

## Performance Tuning

### Gunicorn Workers

Edit `/etc/systemd/system/india-votes-api.service`:

```ini
# Formula: (2 × CPU cores) + 1
--workers 4
```

For a 2-core server, use 5 workers. Adjust based on your server specs.

### Database Connection Pool

For PostgreSQL, adjust `max_connections` in `/etc/postgresql/*/main/postgresql.conf`:

```ini
max_connections = 100
shared_buffers = 256MB
```

Restart PostgreSQL:
```bash
sudo systemctl restart postgresql
```

### Nginx Caching

Add to nginx config for static files:

```nginx
location /static {
    alias /opt/india-votes-data/static;
    expires 30d;
    add_header Cache-Control "public, immutable";
}
```

## Troubleshooting

### Service Won't Start

```bash
# Check detailed error logs
sudo journalctl -u india-votes-api -xe

# Common issues:
# 1. Port already in use
sudo lsof -i :8000

# 2. Permission issues
sudo chown -R www-data:www-data /opt/india-votes-data

# 3. Database connection
psql -U election_user -d election_results -h localhost
```

### High Memory Usage

```bash
# Check memory usage
free -h

# Reduce Gunicorn workers
sudo nano /etc/systemd/system/india-votes-api.service
# Decrease --workers value

sudo systemctl daemon-reload
sudo systemctl restart india-votes-api
```

### ChromeDriver Issues

```bash
# Install/update ChromeDriver
sudo apt-get update
sudo apt-get install --only-upgrade chromium-chromedriver

# Verify installation
which chromedriver
chromedriver --version
```

### Database Connection Errors

```bash
# Check PostgreSQL is running
sudo systemctl status postgresql

# Check connection from app
python -c "from db import _connect; print(_connect())"

# View PostgreSQL logs
sudo tail -f /var/log/postgresql/postgresql-*-main.log
```

## Security Hardening

### 1. Firewall Rules

```bash
# Only allow necessary ports
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp   # SSH
sudo ufw allow 80/tcp   # HTTP
sudo ufw allow 443/tcp  # HTTPS
sudo ufw enable
```

### 2. Fail2ban (Prevent Brute Force)

```bash
sudo apt-get install fail2ban
sudo systemctl enable fail2ban
sudo systemctl start fail2ban
```

### 3. Regular Updates

```bash
# Set up automatic security updates
sudo apt-get install unattended-upgrades
sudo dpkg-reconfigure -plow unattended-upgrades
```

### 4. Database Security

```bash
# PostgreSQL: edit pg_hba.conf
sudo nano /etc/postgresql/*/main/pg_hba.conf

# Change from 'trust' to 'md5' or 'scram-sha-256'
# Restart PostgreSQL
sudo systemctl restart postgresql
```

### 5. Environment Variables

Never commit `.env` file to git. Keep sensitive credentials secure:

```bash
chmod 600 /opt/india-votes-data/.env
```

## API Endpoints

Once deployed, your API will be available at:

- `GET /` - Live dashboard
- `GET /health` - Health check
- `GET /api/elections` - List all elections
- `GET /api/seat-tally` - Party-wise seat counts
- `GET /api/ac-races?state=S22` - Constituency races
- `GET /api/roundwise?state=S22` - Round-by-round data
- `GET /api/download?state=S22` - Download Excel dataset
- `POST /scrape` - Trigger scraping (see API docs)

Full API documentation: `http://your-domain.com/docs` (FastAPI auto-generated)

## Scaling Considerations

### Horizontal Scaling

Use a load balancer (nginx/HAProxy) with multiple app servers:

```nginx
upstream india_votes_api {
    server 10.0.0.1:8000;
    server 10.0.0.2:8000;
    server 10.0.0.3:8000;
}
```

### Database Replication

Set up PostgreSQL primary-replica replication:
- Write to primary
- Read from replicas
- Use connection pooling (PgBouncer)

### Caching Layer

Add Redis for frequently accessed data:

```bash
sudo apt-get install redis-server
pip install redis
```

## Support

- GitHub Issues: https://github.com/yourusername/india-votes-data/issues
- Documentation: See `docs/` folder
- Schema Reference: `docs/SCHEMA.md`

## License

MIT - See LICENSE file
