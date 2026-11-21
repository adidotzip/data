# Database Schema

India Votes Data uses a normalized SQLite or PostgreSQL database. The current schema is defined in `db/sqlite.py` and supports both backends. Historical assembly results are stored separately from live counting rounds.

## Tables

### states

Reference table for states and union territories. ECI codes are the primary key because every other table uses them.

| Column | Type | Description |
|--------|------|-------------|
| `state_code` | TEXT PK | ECI code: S03, S11, U07 |
| `state_code_std` | TEXT | Standard code: AS, KL, DL |
| `state_name` | TEXT | Full name |
| `state_capital` | TEXT | Capital city |
| `state_status` | TEXT | State or UT |
| `population_2011` | INTEGER | Census 2011 |
| `region` | TEXT | Geographic region |
| `districts` | INTEGER | Number of districts |
| `assembly_seats` | INTEGER | Assembly constituencies |
| `loksabha_seats` | INTEGER | Lok Sabha constituencies |
| `rajyasabha_seats` | INTEGER | Rajya Sabha seats |

Reference data is seeded from `data/states.csv` during database initialization.

### parties

Party metadata with normalization support. The `aliases` column holds variant spellings as comma-separated values.

| Column | Type | Description |
|--------|------|-------------|
| `abv` | TEXT PK | Canonical party name |
| `name` | TEXT | Full party name |
| `aliases` | TEXT | Comma-separated variant names |
| `chief` | TEXT | Party leader |
| `colour` | TEXT | Hex colour for charts |
| `founded` | INTEGER | Year founded |
| `symbol_name` | TEXT | Election symbol name |
| `symbol_emoji` | TEXT | Emoji representation |
| `seats_loksabha` | INTEGER | Current Lok Sabha seats |
| `seats_rajyasabha` | INTEGER | Current Rajya Sabha seats |
| `seats_assembly` | INTEGER | Current assembly seats |
| `wikipedia_url` | TEXT | Wikipedia link |
| `alliance` | TEXT | Alliance/coalition name |

Party rows are seeded from the repository data and may be supplemented by scraping/normalization workflows. Avoid treating a fixed row count as authoritative.

**Party normalization chain**: exact match → case-insensitive → aliases → raw name. Built into `_normalize_party()`.

### elections

Election metadata used by the election selector and API.

| Column | Type | Description |
|--------|------|-------------|
| `election_id` | TEXT PK | Stable event identifier |
| `name` | TEXT | Display name |
| `states` | TEXT | JSON array of state codes |
| `sort_date` | TEXT | Sort key for election ordering |

Live election metadata uses ECI state codes (`Sxx`/`Uxx`). Archive rows use standard state codes (AS, KL, etc.) and must not be copied into this live selector table. Live endpoints backed by `rounds_ac` are not election-ID scoped; they expose only current-year general-election metadata. Historical queries use the archive API.

### historical_assembly_results

Historical candidate-level assembly results, separate from the live counting tables.

| Column | Type | Description |
|--------|------|-------------|
| `election_id` | TEXT | Source election/event identifier |
| `election_year` | INTEGER | Election year |
| `state_code` | TEXT | Standard state/UT code |
| `ac_no` | INTEGER | Constituency number |
| `ac_name` | TEXT | Constituency name |
| `candidate` | TEXT | Candidate name |
| `party_name` | TEXT | Party label as recorded by source |
| `evm_votes` | INTEGER | EVM votes |
| `postal_votes` | INTEGER | Postal votes |
| `total_votes` | INTEGER | EVM + postal total |
| `source_url` | TEXT | Source/provenance text |

**Primary key**: `(election_id, state_code, ac_no, candidate, party_name)`

An index supports filtering by state and election year. Use `GET /api/archive/elections` for coverage and `GET /api/archive/results` for historical candidate results.

### rounds_ac

Vote counts per candidate per counting round. This is the core data table. The composite primary key prevents duplicate inserts.

| Column | Type | Description |
|--------|------|-------------|
| `state_code` | TEXT | ECI state code |
| `ac_no` | INTEGER | Assembly constituency number |
| `ac_name` | TEXT | Constituency name |
| `round_no` | INTEGER | Counting round (time axis) |
| `candidate` | TEXT | Candidate name |
| `party_abv` | TEXT | Party (FK → parties.abv) |
| `votes` | INTEGER | Vote count |

**Primary key**: `(state_code, ac_no, round_no, candidate, party_abv)`

Row counts are deployment-specific and change as data is scraped. `rounds_ac` is live-round data and is not election-ID scoped.

**Design decisions**:
- `round_no` records counting-round snapshots. This table is not keyed by `election_id`, so it must not be used to present historical elections as if it were election-specific. Historical candidate-level results use `historical_assembly_results`.
- No `id` column — the composite PK is the natural key.
- No `election_type` — the table name tells you it's Assembly data.
- No `scraped_at` — `round_no` is the temporal ordering.

### rounds_pc

Reserved for Parliamentary Constituency (Lok Sabha) results. Same schema shape as `rounds_ac` but with `pc_no` instead of `ac_no`.

| Column | Type | Description |
|--------|------|-------------|
| `state_code` | TEXT | ECI state code |
| `pc_no` | INTEGER | Parliamentary constituency number |
| `pc_name` | TEXT | Constituency name |
| `round_no` | INTEGER | Counting round |
| `candidate` | TEXT | Candidate name |
| `party_abv` | TEXT | Party (FK → parties.abv) |
| `votes` | INTEGER | Vote count |

**Primary key**: `(state_code, pc_no, round_no, candidate, party_abv)`

Row counts are deployment-specific.

### constituency_status

Lifecycle tracking per Assembly Constituency. Updated by the scraper as counting progresses.

| Column | Type | Description |
|--------|------|-------------|
| `state_code` | TEXT | ECI state code |
| `ac_no` | INTEGER | Constituency number |
| `ac_name` | TEXT | Constituency name |
| `status` | TEXT | PENDING / LIVE / DONE / ERROR |
| `current_round` | INTEGER | Latest round scraped |
| `total_rounds` | INTEGER | Total rounds expected |
| `error_count` | INTEGER | Consecutive errors |
| `won` | INTEGER | 1 if ECI confirms winner |
| `form20_url` | TEXT | URL to certified Form 20 PDF (when available) |
| `form20_status` | TEXT | UNAVAILABLE / UNVERIFIED / VERIFIED / MISMATCH |

**Primary key**: `(state_code, ac_no)`

Rows are seeded from state/constituency reference data and updated as live scraping proceeds.

## Relationships

```
states.state_code ←── rounds_ac.state_code
states.state_code ←── rounds_pc.state_code
states.state_code ←── constituency_status.state_code
parties.abv       ←── rounds_ac.party_abv
parties.abv       ←── rounds_pc.party_abv

historical_assembly_results is keyed by election, state, constituency, candidate, and party; it is intentionally separate from live-round tables.
```

## ECI State Codes

The ECI uses its own coding scheme for states:

| ECI Code | Standard | State |
|----------|----------|-------|
| S01 | AP | Andhra Pradesh |
| S03 | AS | Assam |
| S11 | KL | Kerala |
| S22 | TN | Tamil Nadu |
| S25 | WB | West Bengal |
| U07 | PY | Puducherry |

Full mapping in `data/states.csv`.

## Bye-Elections and election isolation

The historical archive table preserves distinct event IDs and is the supported source for past candidate-level results.

The live `rounds_ac` table does **not** contain an `election_id` column. Therefore it cannot safely represent multiple elections for the same constituency as separate events. Live endpoints accept only current-year general-election IDs (`AC-…`) and reject historical or by-election IDs. Historical candidate-level queries use `/api/archive/results`. A future live by-election architecture needs an explicit election/event key and a reviewed migration; do not treat higher `round_no` values as sufficient election identity.

## Backends

Switch via `DATABASE_URL`:

```bash
# SQLite
DATABASE_URL="data/india-votes-data.db"

# PostgreSQL
DATABASE_URL="postgresql://localhost:5432/election_results"
```

`db/sqlite.py` auto-detects the backend via `IS_PG`. SQL uses `?` (SQLite) or `%s` (PostgreSQL) via `_placeholder()`.
