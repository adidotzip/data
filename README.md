# India Votes Data

A Python tool for scraping, storing, and visualizing Indian election results from the [Election Commission of India](https://www.eci.gov.in/) website.

## Overview

Scrapes constituency-wise election results — candidate names, party affiliations, vote counts — and stores them in a normalized SQLite or PostgreSQL database. Includes a FastAPI + Chart.js dashboard for live visualization on counting day.

## Features

- **Multi-threaded scraping** — 5 concurrent workers (CLI), 3 (live client)
- **Dual database backend** — SQLite (local) or PostgreSQL via `DATABASE_URL`
- **Normalized schema** — states, parties, rounds_ac, constituency_status ([schema docs](docs/SCHEMA.md))
- **Live dashboard** — FastAPI + Chart.js with seat tally, striped bars (leading) vs solid (declared), auto-refresh
- **Historical archive** — historical candidate-level results are stored separately from live counting snapshots
- **CSV/JSON export** — optional file output alongside database writes

## Setup

```bash
git clone https://github.com/thecont1/india-votes-data.git
cd india-votes-data
uv sync
```

Requires Python 3.14+, Chrome (for Selenium).

## Usage

### CLI Scraper

Scrapes final results from an ECI party-wise URL. Always writes to DB; optional CSV/JSON.

```bash
# DB only (round_no=999)
uv run cli.py --url "https://results.eci.gov.in/ResultAcGenMay2026/partywiseresult-S22.htm"

# DB + CSV
uv run cli.py --url "..." --csv

# DB + CSV + JSON
uv run cli.py --url "..." --csv --json

# Respectful mode (single-threaded, 1s pause every 10 URLs)
uv run cli.py --url "..." --respect

# Limit constituencies
uv run cli.py --url "..." 50
```

### Live Client

Monitors counting day results round-by-round. Connects to the API server.

```bash
# Continuous monitoring (every 5 minutes)
uv run eci-ResultsDayLiveClient.py --url "https://results.eci.gov.in/ResultAcGenMay2026/partywiseresult-S11.htm" --live

# Single pass (all rounds)
uv run eci-ResultsDayLiveClient.py --url "..."

# Start from specific round
uv run eci-ResultsDayLiveClient.py --url "..." --start-round 3

# Sequential mode (resource-constrained systems)
uv run eci-ResultsDayLiveClient.py --url "..." --sequential

# Multi-state: start server separately, then run clients with --no-server
uv run server.py --api
uv run eci-ResultsDayLiveClient.py --url "...S11.htm" --no-server
uv run eci-ResultsDayLiveClient.py --url "...S22.htm" --no-server
```

### API Server

FastAPI server for programmatic scraping.

```bash
uv run server.py --api
# or
uv run uvicorn server:app --reload
```

Endpoints:
- `GET /health` — Health check
- `GET /api/elections` and `/api/elections/current` — Election metadata
- `GET /api/archive/elections` — Historical archive coverage
- `GET /api/archive/results` — Historical candidate-level results (state, year, election, AC filters; pagination)
- `POST /archive/import` — Preview/import committed ECI archive JSON
- `POST /archive/import-supplemental` — Preview/import third-party supplemental archive (dry-run by default)
- `POST /scrape` — Scrape constituency results from party-wise URL
- `POST /scrape/ac-rounds` — Scrape all rounds for a single AC
- `POST /scrape/all-rounds` — Scrape all rounds for all ACs

### Dashboard

```bash
DATABASE_URL=data/india-votes-data.db uvicorn server:app --reload
# Open http://localhost:8000
```

### Database

Dual-backend via `DATABASE_URL`:

```bash
# SQLite (default)
DATABASE_URL="data/india-votes-data.db" uvicorn server:app --reload

# PostgreSQL
DATABASE_URL="postgresql://localhost:5432/election_results" uvicorn server:app --reload
```

## Project Structure

```
india-votes-data/
├── cli.py                       # CLI scraper (final results → DB)
├── server.py                    # FastAPI API server
├── eci-ResultsDayLiveClient.py  # Live client (round-by-round)
├── eci-live-scraper.py          # Alternative scraper (requests+BS4)
├── config.py                    # Election config (tracked states, URL template)
├── election.conf                # Party-wise URLs for current cycle
├── static/index.html            # Live dashboard (Chart.js)
├── db_utils.py                  # Database layer (SQLite + PostgreSQL)
├── core/
│   ├── scraper.py               # Selenium-based ECI extraction
│   ├── browser.py               # Chrome WebDriver setup
│   ├── output.py                # CSV/JSON writing (shared)
│   └── models.py                # Pydantic data models
├── tools/                       # Utilities and verification pipeline
│   ├── ocr_engine.py            # Vision LLM + Tesseract OCR engine
│   ├── normalize_parties.py     # Normalize party names in DB
│   ├── fetch_symbols.py         # Fetch party symbols from ECI
│   └── fetch_party_data.py      # Fetch party metadata
├── eci-verify-form20.py         # Form 20 batch verification CLI
├── data/
│   ├── states.csv               # 36 states/UTs reference
│   ├── parties.csv              # 30 major parties metadata
│   ├── csv/                     # CLI CSV output
│   ├── json/                    # CLI JSON output
│   └── india-votes-data.db      # SQLite database (gitignored)
├── docs/
│   └── SCHEMA.md                # Database schema docs
├── notebooks/
│   └── analyse-this.ipynb       # Analysis notebook
├── archive/                     # Historical files
├── pyproject.toml               # uv project config
└── README.md                    # This file
```

## Database

See [docs/SCHEMA.md](docs/SCHEMA.md) for full schema documentation.

Quick reference (row counts vary by deployment):

| Table | Purpose |
|-------|---------|
| `states` | State/UT reference data |
| `parties` | Party metadata + aliases |
| `elections` | Current live election metadata (ECI state codes) |
| `rounds_ac` | Live counting-round snapshots, not election-ID scoped |
| `rounds_pc` | Reserved/live parliamentary counting data |
| `constituency_status` | Live AC lifecycle tracking |
| `historical_assembly_results` | Historical candidate-level assembly results, isolated from live tables |


### Production database audit (read-only)

Run the PostgreSQL audit from the repository root on the server. It contains only SELECT statements and reports table counts, archive coverage, suspicious live election metadata, duplicate keys, vote-total inconsistencies, invalid rows, and constituency coverage.


```bash
sudo docker compose exec -T postgres psql -U election_user -d election_results -f - < scripts/production-audit.sql
```

Expected clean checks return no rows for duplicate keys or invalid vote totals. Metadata and coverage sections are review reports, not automatic error classifications. Review any suspicious output before making database changes.

## Scraping Strategy

1. **Primary**: `curl` subprocess + BeautifulSoup — bypasses ECI's Akamai TLS fingerprint blocking
2. **Fallback**: Selenium headless Chrome — for pages requiring JavaScript rendering
3. **Rate limiting**: 0.2-0.8s jitter between requests per thread

## Form 20 Verification

### What is Form 20?

Form 20 is the official election result document published by the Chief Electoral Officer of each state under Section 64 of the Representation of the People Act, 1951. It contains the complete, booth-wise breakdown of votes polled for every candidate in a constituency — the most granular official record of an election. This is the source document that returning officers sign before declaring results.

Our scraper captures aggregate vote totals from ECI's party-wise summary pages. Form 20 lets us verify those numbers against the original signed document.

### How it works

The verification pipeline (`eci-verify-form20.py` + `tools/ocr_engine.py`) downloads each constituency's Form 20 PDF, converts pages to images, and sends them to a Vision LLM (currently MiMo 2.5). The model reads candidate names and vote counts directly from the scanned document, then cross-checks them against our database.

Tesseract OCR runs as a fallback when no Vision API is configured. When Vision is available, Tesseract is skipped entirely — it takes 23 seconds per AC and the Vision LLM is more accurate on these tabular documents.

Page selection: the summary page (typically the last page) plus 20% random booth pages are sent to the Vision model. This balances thoroughness against API cost.

### Verification statuses

| Status | Meaning | Action |
|--------|---------|--------|
| **Verified** | All candidates confirmed, vote counts match | None — data is trustworthy |
| **Mismatch** | Vision LLM read different vote counts than our DB | Investigate — could be our data or LLM error |
| **Error** | Pipeline couldn't read the PDF (corrupt download, API failure) | Re-run — usually recovers on retry |
| **Unavailable** | No Form 20 URL set for this AC | Source the PDF from the CEO website |

### Running verification

```bash
# Verify all ACs in a state (skips already-verified, retries errors)
uv run eci-verify-form20.py S03

# Re-run everything from scratch
uv run eci-verify-form20.py S03 --force

# Single AC
uv run eci-verify-form20.py S25 110

# Tesseract only (no Vision API)
uv run eci-verify-form20.py S03 --skip-vision
```

The terminal shows a Braille grid — one block per AC, 20 per line. Pre-existing verified ACs appear as filled blocks from the start. Each new result appends to the grid in real time.

### Human in the loop

Automation catches gross errors (wrong totals, missing candidates) but cannot judge everything. Mismatched ACs need a human to decide: did the LLM misread a smudged scan, or does our scraped data have the wrong number? The dashboard sorts ACs by verification priority (Mismatch → Error → Unavailable → Verified) so the most suspicious constituencies surface first.

The goal is not zero mismatches — it's knowing exactly which constituencies to trust and which to double-check. That's what makes this data publishable.

## Output Files

CLI generates CSV/JSON in `data/csv/` and `data/json/`:

```
YYYY<Type>-<state>.csv   (e.g., 2026Assembly-WB.csv)
YYYY<Type>-<state>.json  (e.g., 2026Assembly-WB.json)
```

Also available at [Kaggle](https://www.kaggle.com/datasets/maheshshantaram/indian-elections-fresh-data/).

## Analysis

`analyse-this.ipynb` — Jupyter notebook for analyzing election results from CSVs. Includes:
- Party-wise vote shares and seat counts
- Victory margins and deposit losses
- Assembly composition treemaps
- Multi-state comparison across all available CSVs

Reads CSVs from `data/csv/`.

## Archive

Historical files in `archive/`:
- `eci-karnataka.html` — Karnataka election results page
- `2024 Parliamentary Elections India.csv` — 2024 Lok Sabha results

## Deployment

The API can be deployed to a Linux server using either traditional systemd or Docker. Full deployment guides are available:

### Traditional Deployment (Systemd + Nginx)

```bash
# Run automated setup
sudo bash deploy/scripts/setup.sh
```

Or follow the detailed guide: [DEPLOYMENT.md](DEPLOYMENT.md)

### Docker Deployment

```bash
# Copy the environment template and set a strong DB_PASSWORD
cp .env.example .env
# Edit .env and set DB_PASSWORD (generate one with: openssl rand -hex 32)

# Validate and start
docker compose config
docker compose up -d --build
```

The database schema and reference tables are initialized automatically when the API imports the database package. The API container is bound to `127.0.0.1:8000`; public traffic should go through Nginx.

**Existing installations:** if PostgreSQL already uses the old `changeme` password, rotate it in PostgreSQL after setting the new `DB_PASSWORD` in `.env`, before recreating the API container.

See [deploy/DOCKER_DEPLOYMENT.md](deploy/DOCKER_DEPLOYMENT.md) for complete instructions.

### Deployment Files

All deployment configurations are in the `deploy/` directory:
- `systemd/` - Systemd service file
- `nginx/` - Nginx reverse proxy configuration
- `scripts/` - Setup, update, and monitoring scripts
- `Dockerfile` and `docker-compose.yml` for containerized deployment

## API Endpoints

The root endpoint (`GET /`) returns API metadata and endpoint paths. It is not a dashboard.

- `GET /health` - API and database readiness (503 if DB is unavailable)
- `GET /api/elections` - List configured elections
- `GET /api/elections/current` - Most recent configured election
- `GET /api/states` - States/UTs and ECI codes
- `GET /api/parties` - Party metadata
- `GET /api/seat-tally?state=S22` - Party seat tally
- `GET /api/ac-races?state=S22` - Constituency races
- `GET /api/roundwise?state=S22` - Round-wise progression
- `GET /api/status?state=S22` - Counting progress
- `GET /api/constituency/S22/1` - One constituency's round data
- `GET /api/download?state=S22` - Excel dataset
- `GET /api/tv-channels` - TV channel metadata
- `POST /scrape` - Scrape constituency summary pages
- `POST /scrape/ac-rounds` - Scrape one AC's round-wise data
- `POST /scrape/all-rounds` - Scrape multiple ACs

Example:

```bash
curl https://api-mvin.adi.rest/health
curl https://api-mvin.adi.rest/api/states
curl "https://api-mvin.adi.rest/api/seat-tally?state=S22"
curl "https://api-mvin.adi.rest/api/ac-races?state=S22"
curl -L "https://api-mvin.adi.rest/api/download?state=S22" -o results.xlsx
```

Election IDs currently select their configured state list. The `rounds_ac` table does not yet store an election ID, so the API cannot distinguish historical result sets for the same state.

Full interactive API documentation: `https://api-mvin.adi.rest/docs`

## License

MIT — see [LICENSE](LICENSE).


## Scraper implementation attribution\n\nThe live ECI scraping strategy (curl-first HTTP fetching, BeautifulSoup parsing, and browser fallback) was informed by the MIT-licensed [thecont1/india-votes-data](https://github.com/thecont1/india-votes-data) project. This repository contains an independent adaptation for this API and PostgreSQL-backed deployment; no database schema or stored data is copied or replaced.\n

## ECI Scraping and Ingestion Pipeline

The API scraper now discovers constituency numbers from the actual ECI party-wise source page (hidden constituency-list inputs and real constituency links), instead of assuming ACs are numbered sequentially until a guessed 404. It fetches each discovered constituency page, validates candidate rows, and writes idempotent database snapshots:

- **Round 998:** final EVM-only totals
- **Round 999:** EVM + postal totals (the final-result snapshot)
- constituency_status is updated after successful ingestion.
- Unknown parties are inserted into parties with a stable abbreviation; existing party aliases are matched first.
- A failed/empty scrape is not reported as success and does not write scraped results.

### Scrape one configured or supplied source

POST /scrape retains the existing request shape. limit is the maximum constituencies to scrape (default 3), respect enables sequential respectful fetching.

### Scrape all configured ECI sources

POST /scrape/all-configured scrapes every validated party-wise URL in election.conf and ingests successful sources independently. It returns a per-source report and totals. This covers only URLs currently configured in election.conf; it is not a claim of complete historical ECI archive coverage.

Example request:

```json
{
  "limit_per_state": 1000,
  "respect": true
}
```

### Roundwise ingestion

POST /scrape/ac-rounds and POST /scrape/all-rounds now persist round snapshots to rounds_ac, along with final 998/999 snapshots when final/postal data is available. Writes use the existing natural-key conflict handling and preserve the database; no destructive migrations or data resets are performed.

### Run tests

```bash
python -m unittest discover -s tests -v
```

### Historical ECI archive scraping

Use the separate archive scraper for legacy ECI HTML preserved by the Internet Archive. It incrementally writes CSV and JSON output and resumes by constituency number:

```bash
python scripts/eci_archive_scraper.py "ARCHIVE.ORG_URL_FOR_CONSTITUENCY_1" \
  --election-id AC-2023 --state-code KA --output-dir data/archive
```

Use `--dry-run` to scrape only the first three constituencies.

Historical archive output is currently file-based. The production PostgreSQL schema does not have an election_id dimension in rounds_ac, so historical elections must not be inserted into the current counting-round table until a migration adds election separation. No migration or data reset is performed by this branch.

### Import the repository's historical state datasets

The repository includes archived ECI candidate-result JSON datasets for 20 state/UT election datasets covering 2022–2026. These are imported into the additive `historical_assembly_results` table, **not** into `rounds_ac` or `constituency_status`, so historical imports cannot overwrite live counting data.

Preview the available archive import without writing:

```bash
curl -sS -X POST http://127.0.0.1:8000/archive/import \\
  -H 'Content-Type: application/json' \\
  -d '{"dry_run":true}'
```

Import all archive files idempotently:

```bash
curl -sS -X POST http://127.0.0.1:8000/archive/import \\
  -H 'Content-Type: application/json' \\
  -d '{}'
```

Optional filters: `state` (standard two-letter code) and `year`. The import is additive/upsert-only and does not delete existing records.

Historical API:
- `GET /api/archive/elections` — imported dataset coverage by election/state.
- `GET /api/archive/results?state=TN&year=2026` — candidate vote totals for a state/year. Supports `election_id` and `ac_no`; returns all matching rows.

### Supplemental historical coverage (2009–2026)

A supplementary candidate-level Parquet dataset is available from [skthewimp/elections](https://github.com/skthewimp/elections). It contains 161,760 rows across 119 election IDs. Its provenance varies by period and is retained in the supplemental row's `source_url`. Existing archive records are never overwritten: conflicting primary-key rows are skipped, while missing rows may be filled.

Preview before writing (dry-run defaults to true):

```bash
curl -sS -X POST http://127.0.0.1:8000/archive/import-supplemental \
  -H 'Content-Type: application/json' \
  -d '{"dry_run":true}'
```

Filter the preview to a state/year:

```bash
curl -sS -X POST http://127.0.0.1:8000/archive/import-supplemental \
  -H 'Content-Type: application/json' \
  -d '{"state":"CG","year":2018,"dry_run":true}'
```

Only after reviewing the preview, import:

```bash
curl -sS -X POST http://127.0.0.1:8000/archive/import-supplemental \
  -H 'Content-Type: application/json' \
  -d '{"dry_run":false}'
```

The importer downloads the Parquet source to a temporary cache, maps state names to standard codes, reuses existing election IDs when state/year already exist, and otherwise creates stable `SUPP-AC-YYYY-ST` IDs. It uses conflict-ignore inserts and never deletes or updates existing archive rows. The source file is cached under the server's temporary directory.

### Coverage boundaries

- The configured bulk endpoint processes only the source URLs in election.conf.
- The archive CLI supports historical archive.org ECI pages and writes resumable CSV/JSON.
- Form 20 verification remains a separate validation workflow and is not yet automated by this change.

