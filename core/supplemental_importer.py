"""Import supplemental historical assembly election coverage from a public Parquet archive.

Existing archive rows are never overwritten. Each source election event is kept
separate, including by-elections held in the same state and year. Rows are merged into
an existing archive event only when the source event ID exactly matches it.
"""
from __future__ import annotations

import csv
import hashlib
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

SOURCE_URL = (
    "https://raw.githubusercontent.com/skthewimp/elections/main/"
    "assembly/data/assembly_candidate_results_since_2009.parquet"
)
SOURCE_REPOSITORY = "https://github.com/skthewimp/elections"
CACHE_PATH = Path(tempfile.gettempdir()) / "india-votes-assembly-supplement.parquet"

STATE_ALIASES = {
    "andaman and nicobar islands": "AN",
    "andaman nicobar": "AN",
    "chandigarh": "CH",
    "dadra and nagar haveli and daman and diu": "DN",
    "dadra nagar haveli": "DN",
    "daman and diu": "DN",
    "nct of delhi": "DL",
    "delhi": "DL",
    "lakshadweep": "LD",
    "puducherry": "PY",
    "pondicherry": "PY",
    "jammu and kashmir": "JK",
    "jammu & kashmir": "JK",
    "ladakh": "LA",
    "andhra pradesh": "AP",
    "arunachal pradesh": "AR",
    "assam": "AS",
    "bihar": "BR",
    "goa": "GA",
    "gujarat": "GJ",
    "haryana": "HR",
    "himachal pradesh": "HP",
    "karnataka": "KA",
    "kerala": "KL",
    "madhya pradesh": "MP",
    "maharashtra": "MH",
    "manipur": "MN",
    "meghalaya": "ML",
    "mizoram": "MZ",
    "nagaland": "NL",
    "odisha": "OD",
    "orissa": "OD",
    "punjab": "PB",
    "rajasthan": "RJ",
    "sikkim": "SK",
    "tamil nadu": "TN",
    "tripura": "TR",
    "uttar pradesh": "UP",
    "uttarakhand": "UK",
    "uttanchal": "UK",
    "west bengal": "WB",
    "chhattisgarh": "CG",
    "jharkhand": "JH",
    "telangana": "TG",
}


def _norm(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().replace("&", "and").split())


def _state_code(value: Any) -> str | None:
    return STATE_ALIASES.get(_norm(value))


def _supplemental_event_id(year: int, state_code: str, source_event: Any) -> str:
    """Build a deterministic event ID that distinguishes same-year by-elections."""
    source = str(source_event or f"{year}-{state_code}").strip()
    slug = re.sub(r"[^A-Za-z0-9]+", "-", source).strip("-").upper() or "EVENT"
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()[:10].upper()
    slug = f"{slug[:37]}-{digest}"
    return f"SUPP-AC-{year}-{state_code}-{slug}"


def _download_source() -> Path:
    if CACHE_PATH.exists() and CACHE_PATH.stat().st_size > 100_000:
        return CACHE_PATH
    temp_path = CACHE_PATH.with_suffix(".download")
    proc = subprocess.run(
        ["curl", "-fsSL", "--retry", "3", "--connect-timeout", "20",
         "--max-time", "180", SOURCE_URL, "-o", str(temp_path)],
        capture_output=True, text=True, timeout=190,
    )
    if proc.returncode:
        temp_path.unlink(missing_ok=True)
        raise RuntimeError(f"Supplemental dataset download failed: {proc.stderr[-500:]}")
    if temp_path.stat().st_size < 100_000:
        temp_path.unlink(missing_ok=True)
        raise RuntimeError("Downloaded supplemental Parquet is unexpectedly small")
    temp_path.replace(CACHE_PATH)
    return CACHE_PATH


def _column(row: dict[str, Any], *names: str, default: Any = None) -> Any:
    lowered = {str(k).lower(): v for k, v in row.items()}
    for name in names:
        if name.lower() in lowered:
            return lowered[name.lower()]
    return default


def import_supplemental_archive(conn, cursor, is_pg: bool, *,
                                state: str | None = None,
                                year: int | None = None,
                                dry_run: bool = True) -> dict[str, Any]:
    """Preview or import missing rows from a supplementary candidate-level dataset."""
    try:
        import duckdb
    except ImportError as exc:
        raise RuntimeError("duckdb is required to import the supplemental Parquet dataset") from exc

    parquet_path = _download_source()
    ddb = duckdb.connect(database=":memory:")
    try:
        raw = ddb.execute("SELECT * FROM read_parquet(?)", [str(parquet_path)])
        columns = [description[0] for description in raw.description]
        records = [dict(zip(columns, row)) for row in raw.fetchall()]
    finally:
        ddb.close()

    existing_events: set[tuple[str, int, str]] = set()
    cursor.execute(
        "SELECT state_code, election_year, election_id FROM historical_assembly_results "
        "GROUP BY state_code, election_year, election_id"
    )
    for row in cursor.fetchall():
        d = dict(row) if hasattr(row, "keys") else {
            "state_code": row[0], "election_year": row[1], "election_id": row[2]
        }
        existing_events.add((str(d["state_code"]).upper(), int(d["election_year"]), str(d["election_id"])))

    grouped: dict[tuple[str, int, str], list[tuple]] = {}
    skipped_unmapped = 0
    skipped_invalid = 0
    for item in records:
        state_code = _state_code(_column(item, "state_name", "state", "state_name_english"))
        try:
            election_year = int(_column(item, "election_year", "year"))
            ac_no = int(_column(item, "constituency_no", "ac_no", "constituency_number"))
            evm = int(float(_column(item, "evm_votes", "votes_evm", default=0) or 0))
            postal = int(float(_column(item, "postal_votes", "votes_postal", default=0) or 0))
            total = int(float(_column(item, "total_votes", "votes_total", default=evm + postal) or (evm + postal)))
        except (TypeError, ValueError):
            skipped_invalid += 1
            continue
        if not state_code:
            skipped_unmapped += 1
            continue
        if state and state_code != state.upper():
            continue
        if year and election_year != year:
            continue
        ac_name = str(_column(item, "constituency_name", "ac_name", "constituency", default=f"AC-{ac_no}") or f"AC-{ac_no}").strip()
        candidate = str(_column(item, "candidate", "candidate_name", default="") or "").strip()
        party = str(_column(item, "party", "party_name", default="") or "").strip()
        if ac_no <= 0 or not candidate:
            skipped_invalid += 1
            continue
        source_event = str(_column(item, "election_id", "event_id", default=f"{election_year}-{state_code}") or f"{election_year}-{state_code}")
        # Merge only on exact source-event identity. State/year alone would collapse by-elections.
        exact_existing = (state_code, election_year, source_event)
        normalized_id = source_event if exact_existing in existing_events else _supplemental_event_id(election_year, state_code, source_event)
        source_url = f"{SOURCE_REPOSITORY} (Parquet source: {SOURCE_URL}; source election ID: {source_event})"
        key = (state_code, election_year, normalized_id)
        grouped.setdefault(key, []).append((
            normalized_id, election_year, state_code, ac_no, ac_name,
            candidate, party, evm, postal, total, source_url,
        ))

    summary_events = []
    total_rows = 0
    total_constituencies = 0
    missing_events = 0
    for (state_code, election_year, normalized_id), rows in sorted(grouped.items()):
        acs = len({r[3] for r in rows})
        existing = (state_code, election_year, normalized_id) in existing_events
        summary_events.append({
            "state_code": state_code, "election_year": election_year,
            "election_id": normalized_id, "constituencies": acs,
            "candidate_rows": len(rows), "event_already_present": existing,
            "mode": "fill_missing_rows" if existing else "add_supplemental_event",
        })
        total_rows += len(rows)
        total_constituencies += acs
        if not existing:
            missing_events += 1

    summary = {
        "source": SOURCE_REPOSITORY,
        "source_rows_loaded": len(records),
        "events_selected": len(grouped),
        "events_missing_in_database": missing_events,
        "constituencies_in_selected_events": total_constituencies,
        "candidate_rows_selected": total_rows,
        "skipped_unmapped_states": skipped_unmapped,
        "skipped_invalid_rows": skipped_invalid,
        "dry_run": dry_run,
        "events": summary_events,
    }
    if dry_run or not grouped:
        return summary

    placeholder = "%s" if is_pg else "?"
    sql = f"""INSERT INTO historical_assembly_results
        (election_id, election_year, state_code, ac_no, ac_name, candidate,
         party_name, evm_votes, postal_votes, total_votes, source_url)
        VALUES ({','.join([placeholder] * 11)})
        ON CONFLICT (election_id, state_code, ac_no, candidate, party_name)
        DO NOTHING"""
    try:
        for rows in grouped.values():
            cursor.executemany(sql, rows)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    summary["candidate_rows_attempted"] = total_rows
    summary["existing_rows_preserved"] = True
    return summary
