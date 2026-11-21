"""End-to-end ECI partywise discovery, constituency scrape, and PostgreSQL ingestion.

This pipeline intentionally discovers constituency numbers from the ECI party-wise
page's hidden inputs or links. It does not stop at a guessed AC number sequence.
"""
from __future__ import annotations

import hashlib
import random
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

from core.scraper import (
    _fetch_eci_html,
    _parse_eci_constituency_html,
    build_constituency_url,
    parse_partywise_url,
)

CONFIG_PATH = Path(__file__).resolve().parent.parent / "election.conf"


def configured_partywise_urls() -> list[str]:
    """Return valid, configured ECI partywise URLs, deduplicated."""
    urls: list[str] = []
    if not CONFIG_PATH.exists():
        return urls
    for line in CONFIG_PATH.read_text(encoding="utf-8").splitlines():
        url = line.strip()
        if not url or url.startswith("#"):
            continue
        try:
            parse_partywise_url(url)
        except ValueError:
            continue
        if url not in urls:
            urls.append(url)
    return urls


def _fetch_html(url: str) -> str:
    html, status = _fetch_eci_html(url)
    if status != 200:
        raise RuntimeError(f"ECI returned HTTP {status} for {url}")
    if not html or len(html.strip()) < 100:
        raise RuntimeError(f"ECI returned an empty/short HTML response for {url}")
    return html


def discover_constituencies(partywise_html: str, state_code: str) -> list[dict[str, Any]]:
    """Discover AC number/name pairs from hidden input data and actual links."""
    soup = BeautifulSoup(partywise_html, "html.parser")
    found: dict[int, str] = {}

    # ECI commonly embeds the constituency list in a hidden input value:
    # "1,AC Name;2,Another AC;..." with the input id being the state code.
    for inp in soup.find_all("input", {"type": "hidden"}):
        input_id = str(inp.get("id") or "")
        value = str(inp.get("value") or "")
        if input_id != state_code and not input_id.startswith(state_code):
            continue
        for entry in value.strip().rstrip(";").split(";"):
            parts = entry.split(",", 1)
            if len(parts) != 2 or not parts[0].strip().isdigit():
                continue
            ac_no = int(parts[0].strip())
            ac_name = parts[1].strip()
            if ac_no > 0:
                found[ac_no] = ac_name

    # Fallback/addition: parse real constituency links exposed on the page.
    link_pattern = re.compile(r"Constituencywise" + re.escape(state_code) + r"(\d+)\.htm", re.I)
    for link in soup.find_all("a", href=True):
        match = link_pattern.search(str(link["href"]))
        if match:
            ac_no = int(match.group(1))
            label = link.get_text(" ", strip=True)
            found.setdefault(ac_no, label or f"AC-{ac_no}")

    return [{"ac_no": no, "ac_name": name} for no, name in sorted(found.items())]


def _scrape_one(election_id: str, state_code: str, ac_no: int) -> dict[str, Any]:
    url = build_constituency_url(election_id, state_code, ac_no)
    html = _fetch_html(url)
    parsed = _parse_eci_constituency_html(html, ac_no)
    if parsed.get("not_found"):
        raise RuntimeError(f"ECI constituency page returned not-found for AC {ac_no}")
    rows = parsed.get("voting_tally") or []
    if not rows:
        raise RuntimeError(f"No candidate rows parsed for AC {ac_no}")
    return {"source_url": url, "voting_data": parsed}


def scrape_partywise_source(url: str, limit: int = 1000, respect: bool = True,
                            max_workers: int = 3) -> dict[str, Any]:
    """Discover ACs from one validated partywise page, scrape them, and report failures."""
    election_id, state_code = parse_partywise_url(url)
    page = _fetch_html(url)
    acs = discover_constituencies(page, state_code)
    if not acs:
        raise RuntimeError(f"Could not discover constituency list from party-wise source: {url}")
    selected = acs[:limit]
    workers = 1 if respect else max(1, min(max_workers, 3))
    results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    if workers == 1:
        for item in selected:
            try:
                results.append(_scrape_one(election_id, state_code, item["ac_no"]))
            except Exception as exc:
                errors.append({"ac_no": item["ac_no"], "error": str(exc)})
            if respect:
                time.sleep(random.uniform(0.8, 1.5))
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_scrape_one, election_id, state_code, item["ac_no"]): item for item in selected}
            for future in as_completed(futures):
                item = futures[future]
                try:
                    results.append(future.result())
                except Exception as exc:
                    errors.append({"ac_no": item["ac_no"], "error": str(exc)})
                time.sleep(random.uniform(0.3, 0.8))

    results.sort(key=lambda r: int(r["voting_data"]["constituency_no"]))
    return {
        "election_id": election_id,
        "state_code": state_code,
        "source_url": url,
        "discovered_constituencies": len(acs),
        "attempted": len(selected),
        "scraped": len(results),
        "errors": errors,
        "constituencywise_results": results,
    }


def _votes(value: Any) -> int:
    text = str(value or "").replace(",", "").strip()
    return int(text) if text.isdigit() else 0


def _party_abv(raw_party: str, existing: list[dict[str, Any]]) -> str:
    raw = (raw_party or "").strip()
    if not raw or raw.lower() in {"independent", "independents"}:
        return "IND"
    for row in existing:
        abv = str(row.get("abv") or "")
        name = str(row.get("name") or "")
        aliases = str(row.get("aliases") or "").split(",")
        if raw.casefold() in {abv.casefold(), name.casefold(), *(a.strip().casefold() for a in aliases if a.strip())}:
            return abv
    # Unknown names get a stable acronym, falling back to a hash suffix if empty.
    words = re.findall(r"[A-Za-z0-9]+", raw)
    abv = "".join(w[0] for w in words).upper()[:12]
    if not abv:
        abv = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8].upper()
    if any(str(row.get("abv") or "").casefold() == abv.casefold() for row in existing):
        abv = re.sub(r"[^A-Z0-9]", "", raw.upper())[:8] or "UNK"
    return abv


def ingest_final_results(source_result: dict[str, Any], conn, cursor, is_pg: bool) -> dict[str, int]:
    """Idempotently persist scraped final results as EVM (998) and EVM+postal (999)."""
    placeholder = "%s" if is_pg else "?"
    cursor.execute("SELECT abv, name, aliases FROM parties")
    existing = [dict(row) if hasattr(row, "keys") else {"abv": row[0], "name": row[1], "aliases": row[2]} for row in cursor.fetchall()]
    inserted_candidates = 0
    processed_acs = 0

    for entry in source_result.get("constituencywise_results", []):
        data = entry.get("voting_data", {})
        ac_no = int(data.get("constituency_no") or 0)
        state_code = source_result["state_code"]
        ac_name = str(data.get("constituency") or f"AC-{ac_no}")
        candidates = data.get("voting_tally") or []
        if ac_no <= 0 or not candidates:
            continue

        normalized: list[tuple[str, str, int, int]] = []
        for candidate in candidates:
            name = str(candidate.get("candidate") or "").strip()
            party_raw = str(candidate.get("party") or "").strip()
            if not name:
                continue
            evm = _votes(candidate.get("evm_votes"))
            postal = _votes(candidate.get("postal_votes"))
            abv = _party_abv(party_raw, existing)
            normalized.append((name, abv, evm, postal))
            if not any(str(row.get("abv") or "").casefold() == abv.casefold() for row in existing):
                cursor.execute(
                    f"INSERT INTO parties (abv, name) VALUES ({placeholder}, {placeholder}) ON CONFLICT (abv) DO NOTHING",
                    (abv, party_raw or abv),
                )
                existing.append({"abv": abv, "name": party_raw or abv, "aliases": ""})

        if not normalized:
            continue
        winner = max(normalized, key=lambda item: item[2] + item[3])
        for candidate, party_abv, evm, postal in normalized:
            for round_no, vote_total in ((998, evm), (999, evm + postal)):
                cursor.execute(
                    f"""INSERT INTO rounds_ac
                    (state_code, ac_no, ac_name, round_no, candidate, party_abv, votes)
                    VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})
                    ON CONFLICT (state_code, ac_no, round_no, candidate, party_abv)
                    DO UPDATE SET ac_name = EXCLUDED.ac_name, votes = EXCLUDED.votes""",
                    (state_code, ac_no, ac_name, round_no, candidate, party_abv, vote_total),
                )
                inserted_candidates += 1

        cursor.execute(
            f"""INSERT INTO constituency_status
            (state_code, ac_no, ac_name, status, current_round, total_rounds, error_count, won)
            VALUES ({placeholder}, {placeholder}, {placeholder}, 'DONE', 999, 999, 0, 1)
            ON CONFLICT (state_code, ac_no)
            DO UPDATE SET ac_name = EXCLUDED.ac_name, status = 'DONE',
                current_round = 999, total_rounds = 999, error_count = 0, won = 1""",
            (state_code, ac_no, ac_name),
        )
        processed_acs += 1

    conn.commit()
    return {"constituencies_ingested": processed_acs, "candidate_snapshots_written": inserted_candidates}
