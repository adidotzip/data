"""Import committed ECI assembly archive JSON into an additive historical table.

This never writes to rounds_ac or constituency_status, so it cannot overwrite live
counting snapshots. Imports are idempotent by election/state/constituency/candidate.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
ARCHIVE_DIR = DATA_DIR / "json"
FILE_RE = re.compile(r"^(\d{4})Assembly-([A-Z]{2})\.json$")


def archive_files() -> list[Path]:
    """Return recognized committed archive files in deterministic order."""
    if not ARCHIVE_DIR.exists():
        return []
    return sorted(path for path in ARCHIVE_DIR.glob("*Assembly-*.json") if FILE_RE.match(path.name))


def parse_archive_file(path: Path) -> tuple[dict[str, Any], list[tuple]]:
    match = FILE_RE.match(path.name)
    if not match:
        raise ValueError(f"Unsupported archive filename: {path.name}")
    year_from_name, state_from_name = match.groups()
    payload = json.loads(path.read_text(encoding="utf-8"))
    year = int(payload.get("election_year") or year_from_name)
    state_code = str(payload.get("election_state") or state_from_name).strip().upper()
    election_id = str(payload.get("election_id") or f"AC-{year}-{state_code}").strip()
    election_name = str(payload.get("title") or f"{state_code} Assembly {year}")
    records: list[tuple] = []

    for item in payload.get("constituencywise_results") or []:
        voting_data = item.get("voting_data") or {}
        ac_no = int(voting_data.get("constituency_no") or 0)
        if ac_no <= 0:
            continue
        ac_name = str(voting_data.get("constituency") or f"AC-{ac_no}").strip()
        source_url = str(item.get("source_url") or "")
        for candidate in voting_data.get("voting_tally") or []:
            name = str(candidate.get("candidate") or "").strip()
            party = str(candidate.get("party") or "").strip()
            if not name:
                continue
            evm = _int_votes(candidate.get("evm_votes"))
            postal = _int_votes(candidate.get("postal_votes"))
            records.append((
                election_id, year, state_code, ac_no, ac_name, name, party,
                evm, postal, evm + postal, source_url,
            ))

    metadata = {
        "filename": path.name,
        "election_id": election_id,
        "election_year": year,
        "state_code": state_code,
        "election_name": election_name,
        "constituencies": len({row[3] for row in records}),
        "candidate_rows": len(records),
    }
    return metadata, records


def _int_votes(value: Any) -> int:
    text = str(value or "0").replace(",", "").strip()
    try:
        return int(text)
    except (ValueError, TypeError):
        return 0


def import_archive_data(conn, cursor, is_pg: bool, *, state: str | None = None,
                       year: int | None = None, dry_run: bool = False) -> dict[str, Any]:
    """Import matching archive files; additive, idempotent, and transaction-scoped."""
    files = archive_files()
    selected = []
    total_candidates = 0
    total_acs = 0
    for path in files:
        metadata, records = parse_archive_file(path)
        if state and metadata["state_code"] != state.upper():
            continue
        if year and metadata["election_year"] != year:
            continue
        selected.append((metadata, records))
        total_candidates += len(records)
        total_acs += metadata["constituencies"]

    summary = {
        "files_selected": len(selected),
        "files_available": len(files),
        "constituencies": total_acs,
        "candidate_rows": total_candidates,
        "dry_run": dry_run,
        "elections": [metadata for metadata, _ in selected],
    }
    if dry_run or not selected:
        return summary

    placeholder = "%s" if is_pg else "?"
    sql = f"""INSERT INTO historical_assembly_results
        (election_id, election_year, state_code, ac_no, ac_name, candidate,
         party_name, evm_votes, postal_votes, total_votes, source_url)
        VALUES ({','.join([placeholder] * 11)})
        ON CONFLICT (election_id, state_code, ac_no, candidate, party_name)
        DO UPDATE SET
          election_year = EXCLUDED.election_year,
          ac_name = EXCLUDED.ac_name,
          evm_votes = EXCLUDED.evm_votes,
          postal_votes = EXCLUDED.postal_votes,
          total_votes = EXCLUDED.total_votes,
          source_url = EXCLUDED.source_url"""
    try:
        for _, records in selected:
            if records:
                cursor.executemany(sql, records)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    summary["candidate_rows_written"] = total_candidates
    return summary
