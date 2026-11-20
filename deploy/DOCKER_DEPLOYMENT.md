# Docker Deployment Guide

Deploy the India Votes API with Docker Compose.

## Requirements

- Docker Engine and Compose plugin
- Linux server
- 2 GB RAM recommended
- DNS for your API hostname pointing to the server

## Fresh installation

### 1. Clone the repository

```bash
git clone https://github.com/adidotzip/data.git
cd data
```

### 2. Configure secrets

```bash
cp .env.example .env
openssl rand -hex 32
nano .env
```

Set `DB_PASSWORD` to the generated value. Keep `.env` private and never commit it.

### 3. Validate and start

```bash
sudo docker compose config
sudo docker compose up -d --build
sudo docker compose ps
```

Database schema and reference rows are initialized automatically by the API's database package. Do not delete the `postgres_data` volume when updating.

## Updating an existing server

Back up the database first:

```bash
sudo docker compose exec -T postgres pg_dump -U election_user -d election_results > backup_$(date +%Y%m%d_%H%M%S).sql
```

Pull the updates:

```bash
git pull
```

If your existing database still uses the old default password `changeme`, generate a new secret and put it in `.env` before starting the updated Compose file. Then rotate the PostgreSQL role password while the database is running:

```bash
# After editing .env, load its simple KEY=value entries into this shell:
set -a
. ./.env
set +a

sudo docker compose exec postgres psql -U election_user -d election_results -c "ALTER USER election_user WITH PASSWORD '$DB_PASSWORD';"
```

Now validate and rebuild:

```bash
sudo docker compose config
sudo docker compose up -d --build
```

The Compose configuration no longer publishes PostgreSQL to the public network. The API port is bound to localhost, and public traffic should pass through Nginx.

## Verify

```bash
sudo docker compose ps
sudo docker compose logs --tail=100 api
curl -i http://127.0.0.1:8000/health
curl -i http://127.0.0.1/api/states
curl -i http://127.0.0.1/api/parties
```

For the configured domain:

```bash
curl -i http://api-mvin.adi.rest/health
curl -i http://api-mvin.adi.rest/api/states
```

The API health endpoint returns HTTP 200 when PostgreSQL is reachable and HTTP 503 when the database is unavailable.

## Service commands

```bash
sudo docker compose ps
sudo docker compose logs -f api
sudo docker compose logs -f postgres
sudo docker compose logs -f nginx
sudo docker compose restart api
sudo docker compose up -d --build api
sudo docker compose down
```

**Do not use `docker compose down -v` for routine updates.** It deletes the persistent database volume.

## Backups and restore

Backup:

```bash
sudo docker compose exec -T postgres pg_dump -U election_user -d election_results > backup.sql
```

Restore into an existing database:

```bash
cat backup.sql | sudo docker compose exec -T postgres psql -U election_user -d election_results
```

## SSL

The default Nginx config serves HTTP and the Certbot volumes are configured. Obtain a certificate using the webroot method after DNS points to the server and port 80 is reachable:

```bash
sudo docker compose run --rm certbot certonly --webroot -w /var/www/certbot -d api-mvin.adi.rest --email YOUR_EMAIL --agree-tos --no-eff-email
```

The repository's default Nginx config is HTTP-only. HTTPS requires switching Nginx to an SSL server config and publishing port 443; do not enable an SSL config until the certificate files exist.

## Troubleshooting

- **502 Bad Gateway:** check `sudo docker compose ps`, `sudo docker compose logs api`, and confirm Nginx upstream uses Docker service name `api:8000`, not `127.0.0.1:8000`.
- **500 Internal Server Error:** inspect `sudo docker compose logs --tail=100 api`. Verify the database initialized and reference CSVs exist under `data/`.
- **Database authentication failure:** ensure `.env` and PostgreSQL's role password match.
- **CSV not found:** the reference CSVs are `data/states.csv` and `data/parties.csv`; the DB module resolves them relative to the project root.

## Production security notes

- Keep `.env` out of Git.
- PostgreSQL is not published to the host.
- API port 8000 is localhost-only; Nginx is the public entry point.
- Use a strong database password.
- Add HTTPS before sending sensitive client traffic.
- Back up the database before schema or deployment changes.
