# Quick Reference - India Votes Data API

## Installation

### Automated Setup (Traditional)
```bash
sudo bash deploy/scripts/setup.sh
```

### Docker Quick Start
```bash
docker compose up -d
docker compose exec api python -c "from db import init_db; init_db()"
```

## Service Control

### Traditional (Systemd)
| Command | Description |
|---------|-------------|
| `sudo systemctl start india-votes-api` | Start service |
| `sudo systemctl stop india-votes-api` | Stop service |
| `sudo systemctl restart india-votes-api` | Restart service |
| `sudo systemctl status india-votes-api` | Check status |
| `sudo systemctl enable india-votes-api` | Enable auto-start |
| `sudo systemctl disable india-votes-api` | Disable auto-start |

### Docker
| Command | Description |
|---------|-------------|
| `docker compose up -d` | Start all services |
| `docker compose down` | Stop all services |
| `docker compose restart` | Restart all services |
| `docker compose ps` | List running containers |
| `docker compose logs -f` | Follow logs |
| `docker compose exec api bash` | Shell access |

## Logs

### View Logs
```bash
# Traditional
sudo journalctl -u india-votes-api -f          # Follow logs
sudo journalctl -u india-votes-api -n 100      # Last 100 lines
sudo journalctl -u india-votes-api --since "1 hour ago" | grep ERROR

# Docker
docker compose logs -f                          # All services
docker compose logs -f api                      # API only
docker compose logs --tail=100 api              # Last 100 lines
```

### Log Locations
- **Traditional**: `/var/log/india-votes-api/`
- **Docker**: Use `docker compose logs`
- **Nginx**: `/var/log/nginx/india-votes-api-*.log`

## Database

### Backup
```bash
# Traditional
pg_dump -U election_user election_results > backup_$(date +%Y%m%d).sql

# Docker
docker compose exec -T postgres pg_dump -U election_user election_results > backup_$(date +%Y%m%d).sql
```

### Restore
```bash
# Traditional
psql -U election_user election_results < backup_20260520.sql

# Docker
cat backup_20260520.sql | docker compose exec -T postgres psql -U election_user election_results
```

### Database Shell
```bash
# Traditional
psql -U election_user election_results

# Docker
docker compose exec postgres psql -U election_user election_results
```

## Health Checks

```bash
# API health
curl http://localhost:8000/health

# Service status
sudo systemctl status india-votes-api    # Traditional
docker compose ps                         # Docker

# Monitoring script
bash deploy/scripts/monitor.sh
```

## Updates

### Pull and Restart
```bash
# Traditional
cd /opt/india-votes-data
git pull
source venv/bin/activate
pip install -r requirements.txt --upgrade
sudo systemctl restart india-votes-api

# Or use script
sudo bash deploy/scripts/update.sh

# Docker
git pull
docker compose up -d --build
```

## Configuration

### Environment Variables (.env)
```bash
DATABASE_URL=postgresql://user:pass@localhost:5432/election_results
HOST=0.0.0.0
PORT=8000
WORKERS=4
LOG_LEVEL=info
ALLOWED_ORIGINS=*
```

### Edit Configuration
```bash
# Traditional
sudo nano /opt/india-votes-data/.env
sudo systemctl restart india-votes-api

# Docker
nano .env
docker compose up -d
```

## Nginx

### Control
```bash
sudo systemctl start nginx
sudo systemctl stop nginx
sudo systemctl restart nginx
sudo systemctl reload nginx        # Reload config without downtime
sudo nginx -t                      # Test configuration
```

### Logs
```bash
sudo tail -f /var/log/nginx/india-votes-api-access.log
sudo tail -f /var/log/nginx/india-votes-api-error.log
```

## SSL/HTTPS

### Obtain Certificate (Let's Encrypt)
```bash
# Traditional
sudo certbot --nginx -d api.yourdomain.com

# Docker
docker compose run --rm certbot certonly \
  --webroot --webroot-path=/var/www/certbot \
  -d api.yourdomain.com \
  --email your@email.com --agree-tos
```

### Renew Certificate
```bash
# Traditional
sudo certbot renew

# Docker
docker compose run --rm certbot renew
docker compose restart nginx
```

## Monitoring

### Resource Usage
```bash
# CPU and Memory
htop
top -p $(pgrep -f india-votes-api)
docker stats                       # Docker

# Disk Usage
df -h /opt/india-votes-data

# Active Connections
netstat -an | grep :8000 | grep ESTABLISHED | wc -l
```

### Health Monitoring Script
```bash
bash deploy/scripts/monitor.sh
```

## Troubleshooting

### Service Won't Start
```bash
# Check logs
sudo journalctl -u india-votes-api -xe
docker compose logs api

# Check port
sudo lsof -i :8000
sudo netstat -tlnp | grep 8000

# Check permissions
ls -la /opt/india-votes-data
```

### Database Connection Failed
```bash
# Test connection
psql -U election_user -d election_results -h localhost

# Check PostgreSQL
sudo systemctl status postgresql
docker compose ps postgres

# View DB logs
sudo tail -f /var/log/postgresql/postgresql-*-main.log
docker compose logs postgres
```

### High CPU/Memory
```bash
# Check usage
htop
docker stats

# Reduce workers in .env
WORKERS=2

# Restart
sudo systemctl restart india-votes-api
docker compose restart api
```

### Reset Everything (DANGER!)
```bash
# Traditional
sudo systemctl stop india-votes-api
sudo -u postgres dropdb election_results
sudo -u postgres createdb election_results
python -c "from db import init_db; init_db()"
sudo systemctl start india-votes-api

# Docker (removes all data!)
docker compose down -v
docker compose up -d
docker compose exec api python -c "from db import init_db; init_db()"
```

## Common Tasks

### Add New State Data
```bash
# Traditional
source venv/bin/activate
python cli.py --url "https://results.eci.gov.in/...partywiseresult-S22.htm" --csv --json

# Docker
docker compose exec api python cli.py --url "..." --csv --json
```

### Export Data
```bash
# Download via API
curl "http://localhost:8000/api/download?state=S22" -o results.xlsx

# Or access dashboard
# Navigate to http://your-server/
```

### Run Scraper
```bash
# Traditional
source venv/bin/activate
python scripts/eci-live-scraper.py --url "..." --live

# Docker
docker compose exec api python scripts/eci-live-scraper.py --url "..." --live
```

## Performance Tuning

### Adjust Workers
```bash
# Calculate: (2 × CPU_cores) + 1
# Edit .env
WORKERS=5

# Restart
sudo systemctl restart india-votes-api
docker compose restart api
```

### Database Optimization
```bash
sudo nano /etc/postgresql/*/main/postgresql.conf

# Adjust these
max_connections = 100
shared_buffers = 256MB
effective_cache_size = 2GB

# Restart
sudo systemctl restart postgresql
```

## File Locations

### Traditional Deployment
- **Application**: `/opt/india-votes-data/`
- **Logs**: `/var/log/india-votes-api/`
- **Service**: `/etc/systemd/system/india-votes-api.service`
- **Nginx Config**: `/etc/nginx/sites-available/india-votes-api.conf`
- **SSL Certs**: `/etc/letsencrypt/live/`

### Docker Deployment
- **Project**: `./` (git clone directory)
- **Volumes**: Docker-managed
- **Logs**: `docker compose logs`

## API Endpoints

```bash
# Health check
curl http://localhost:8000/health

# Get elections
curl http://localhost:8000/api/elections

# Get seat tally
curl "http://localhost:8000/api/seat-tally?state=S22"

# Get AC races
curl "http://localhost:8000/api/ac-races?state=S22"

# Download data
curl "http://localhost:8000/api/download?state=S22" -o data.xlsx

# Interactive docs
# Open http://localhost:8000/docs in browser
```

## Emergency Procedures

### Service Down
```bash
# 1. Check logs
sudo journalctl -u india-votes-api -n 50
# or
docker compose logs --tail=50 api

# 2. Try restart
sudo systemctl restart india-votes-api
# or
docker compose restart api

# 3. If still down, check port and database
sudo lsof -i :8000
sudo systemctl status postgresql
```

### Database Corrupted
```bash
# 1. Stop service
sudo systemctl stop india-votes-api

# 2. Restore from backup
psql -U election_user election_results < /backups/latest_backup.sql

# 3. Start service
sudo systemctl start india-votes-api
```

### Out of Disk Space
```bash
# 1. Check usage
df -h

# 2. Clean logs
sudo journalctl --vacuum-time=7d
docker system prune -a

# 3. Remove old backups
rm /backups/old_*.sql
```

## Support

- **Documentation**: [DEPLOYMENT.md](DEPLOYMENT.md), [DOCKER_DEPLOYMENT.md](DOCKER_DEPLOYMENT.md)
- **Issues**: GitHub Issues
- **Schema**: [docs/SCHEMA.md](../docs/SCHEMA.md)
