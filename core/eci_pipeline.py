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
    get_state_code,
    get_state_name,
)

CONFIG_PATH = Path(__file__).resolve().parent.parent / "election.conf"


def parse_eci_index_url(url: str) -> str:
    """Validate an official ECI assembly by-election index URL and return its directory."""
    match = re.fullmatch(
        r"https://results\.eci\.gov\.in/([^/]+)/(?:index\.htm|index\.html)",
        url.strip(),
        flags=re.IGNORECASE,
    )
    if not match or "ResultAcBye" not in match.group(1):
        raise ValueError("Expected an official ECI assembly by-election index URL ending in /index.htm")
    return match.group(1)


def _validate_eci_source_url(url: str) -> tuple[str, str]:
    """Accept legacy partywise pages or official assembly by-election index pages."""
    try:
        return parse_partywise_url(url)
    except ValueError:
        election_id = parse_eci_index_url(url)
        return election_id, "MIXED"


def configured_partywise_urls() -> list[str]:
    """Return configured ECI sources (partywise pages or by-election indexes)."""
    urls: list[str] = []
    if not CONFIG_PATH.exists():
        return urls
    for line in CONFIG_PATH.read_text(encoding="utf-8").splitlines():
        url = line.strip()
        if not url or url.startswith("#"):
            continue
        try:
            _validate_eci_source_url(url)
        except ValueError:
            continue
        if url not in urls:
            urls.append(url)
    return urls


def discover_by_election_constituencies(index_html: str, election_id: str) -> list[dict[str, Any]]:
    """Discover ACs from ECI by-election index links, including mixed states."""
    soup = BeautifulSoup(index_html, "html.parser")
    found: dict[tuple[str, int], dict[str, Any]] = {}
    pattern = re.compile(
        r"(?:candidateswise|Constituencywise)(?:-)?([SU]\d{2})(\d+)\.htm",
        re.IGNORECASE,
    )
    base = f"https://results.eci.gov.in/{election_id}/"
    for anchor in soup.find_all("a", href=True):
        href = str(anchor["href"])
        match = pattern.search(href)
        if not match:
            continue
        eci_state_code = match.group(1).upper()
        ac_no = int(match.group(2))
        target_path = re.sub(
            r"candidateswise-?([SU]\d{2})(\d+)\.htm",
            r"Constituencywise\1\2.htm",
            href,
            flags=re.IGNORECASE,
        )
        if not re.search(r"Constituencywise", target_path, re.IGNORECASE):
            target_path = f"Constituencywise{eci_state_code}{ac_no}.htm"
        target_url = target_path if target_path.startswith("https://") else base + target_path.lstrip("./")
        state_name = get_state_name(eci_state_code)
        normalized_state = get_state_code(state_name)
        if not normalized_state:
            raise ValueError(f"Could not map ECI state code {eci_state_code} to database state code")
        found[(eci_state_code, ac_no)] = {
            "ac_no": ac_no,
            "eci_state_code": eci_state_code,
            "state_code": normalized_state,
            "ac_name": anchor.get_text(" ", strip=True) or f"AC-{ac_no}",
            "url": target_url,
        }
    return sorted(found.values(), key=lambda row: (row["state_code"], row["ac_no"]))


def _fetch_html(url: str) -> str:
    """Fetch with curl first, falling back to Selenium for blocked/JS variants."""
    primary_error = None
    try:
        html, status = _fetch_eci_html(url)
        if status == 404:
            raise RuntimeError(f"ECI page not found (HTTP 404): {url}")
        if status == 200 and html and len(html.strip()) >= 100:
            return html
        primary_error = RuntimeError(f"curl returned HTTP {status} or an empty response")
    except Exception as exc:
        if "HTTP 404" in str(exc):
            raise
        primary_error = exc

    try:
        from core.browser import create_chrome_driver
        driver = create_chrome_driver()
        try:
            driver.get(url)
            title = (driver.title or "").lower()
            body = (driver.find_element("tag name", "body").text or "").lower()
            if "404" in title or "page not found" in body or "not found" in title:
                raise RuntimeError(f"ECI page not found in Selenium fallback: {url}")
            html = driver.page_source or ""
            if len(html.strip()) < 100:
                raise RuntimeError("Selenium returned an empty/short HTML response")
            return html
        finally:
            driver.quit()
    except Exception as fallback_error:
        raise RuntimeError(
            f"ECI fetch failed with curl ({primary_error}) and Selenium fallback ({fallback_error})"
        ) from fallback_error


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


def _scrape_one_url(url: str, ac_no: int, state_code: str) -> dict[str, Any]:
    """Scrape one discovered ECI constituency result URL."""
    html = _fetch_html(url)
    parsed = _parse_eci_constituency_html(html, ac_no)
    if parsed.get("not_found"):
        raise RuntimeError(f"ECI constituency page returned not-found for AC {ac_no}")
    rows = parsed.get("voting_tally") or []
    if not rows:
        raise RuntimeError(f"No candidate rows parsed for AC {ac_no}")
    return {"source_url": url, "state_code": state_code, "voting_data": parsed}


def _scrape_one(election_id: str, state_code: str, ac_no: int) -> dict[str, Any]:
    normalized_state = get_state_code(get_state_name(state_code)) or state_code
    url = build_constituency_url(election_id, state_code, ac_no)
    return _scrape_one_url(url, ac_no, normalized_state)


def scrape_partywise_source(url: str, limit: int = 1000, respect: bool = True,
                            max_workers: int = 3) -> dict[str, Any]:
    """Scrape partywise pages or discover constituencies from an ECI bye-election index."""
    election_id, state_code = _validate_eci_source_url(url)
    is_index = state_code == "MIXED"
    page = _fetch_html(url)
    if is_index:
        acs = discover_by_election_constituencies(page, election_id)
    else:
        normalized_state = get_state_code(get_state_name(state_code)) or state_code
        acs = [
            {
                **item,
                "state_code": normalized_state,
                "url": build_constituency_url(election_id, state_code, item["ac_no"]),
            }
            for item in discover_constituencies(page, state_code)
        ]
    if not acs:
        raise RuntimeError(f"Could not discover constituency list from ECI source: {url}")
    selected = acs[:limit]
    workers = 1 if respect else max(1, min(max_workers, 3))
    results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    def scrape_item(item: dict[str, Any]) -> dict[str, Any]:
        return _scrape_one_url(item["url"], item["ac_no"], item["state_code"])

    if workers == 1:
        for item in selected:
            try:
                results.append(scrape_item(item))
            except Exception as exc:
                errors.append({"state_code": item["state_code"], "ac_no": item["ac_no"], "error": str(exc)})
            if respect:
                time.sleep(random.uniform(0.8, 1.5))
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(scrape_item, item): item for item in selected}
            for future in as_completed(futures):
                item = futures[future]
                try:
                    results.append(future.result())
                except Exception as exc:
                    errors.append({"state_code": item["state_code"], "ac_no": item["ac_no"], "error": str(exc)})
                time.sleep(random.uniform(0.3, 0.8))

    results.sort(key=lambda r: (r.get("state_code", ""), int(r["voting_data"]["constituency_no"])))
    return {
        "election_id": election_id,
        "state_code": "MIXED" if is_index else get_state_code(get_state_name(state_code)) or state_code,
        "source_type": "assembly_by_election_index" if is_index else "partywise",
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
        base = re.sub(r"[^A-Z0-9]", "", raw.upper())[:8] or "UNK"
        suffix = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:4].upper()
        abv = f"{base[:8]}{suffix}"
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
        state_code = entry.get("state_code") or source_result["state_code"]
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

def ingest_round_results(state_code: str, ac_no: int, ac_name: str, rounds: list,
                        postal_votes: list, conn, cursor, is_pg: bool) -> dict[str, int]:
    """Persist round snapshots and final EVM / EVM+postal snapshots idempotently."""
    placeholder = "%s" if is_pg else "?"
    cursor.execute("SELECT abv, name, aliases FROM parties")
    existing = [dict(row) if hasattr(row, "keys") else {"abv": row[0], "name": row[1], "aliases": row[2]} for row in cursor.fetchall()]
    written = 0
    latest_by_candidate: dict[tuple[str, str], int] = {}
    latest_round = 0
    for round_data in sorted(rounds or [], key=lambda item: int(item.get("round", 0))):
        round_no = int(round_data.get("round") or 0)
        if round_no <= 0 or round_no >= 998:
            continue
        latest_round = max(latest_round, round_no)
        snapshot: list[tuple[str, str, int]] = []
        for candidate in round_data.get("tally", []):
            name = str(candidate.get("candidate") or "").strip()
            party_raw = str(candidate.get("party") or "").strip()
            if not name:
                continue
            votes = _votes(candidate.get("total"))
            abv = _party_abv(party_raw, existing)
            if not any(str(row.get("abv") or "").casefold() == abv.casefold() for row in existing):
                cursor.execute(f"INSERT INTO parties (abv, name) VALUES ({placeholder}, {placeholder}) ON CONFLICT (abv) DO NOTHING", (abv, party_raw or abv))
                existing.append({"abv": abv, "name": party_raw or abv, "aliases": ""})
            snapshot.append((name, abv, votes))
            latest_by_candidate[(name, abv)] = votes
        for name, abv, votes in snapshot:
            cursor.execute(
                f"""INSERT INTO rounds_ac (state_code, ac_no, ac_name, round_no, candidate, party_abv, votes)
                VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})
                ON CONFLICT (state_code, ac_no, round_no, candidate, party_abv)
                DO UPDATE SET ac_name = EXCLUDED.ac_name, votes = EXCLUDED.votes""",
                (state_code, ac_no, ac_name, round_no, name, abv, votes),
            )
            written += 1

    if latest_by_candidate:
        for (name, abv), evm_votes in latest_by_candidate.items():
            cursor.execute(
                f"""INSERT INTO rounds_ac (state_code, ac_no, ac_name, round_no, candidate, party_abv, votes)
                VALUES ({placeholder}, {placeholder}, {placeholder}, 998, {placeholder}, {placeholder}, {placeholder})
                ON CONFLICT (state_code, ac_no, round_no, candidate, party_abv)
                DO UPDATE SET ac_name = EXCLUDED.ac_name, votes = EXCLUDED.votes""",
                (state_code, ac_no, ac_name, name, abv, evm_votes),
            )
            written += 1

    postal_by_candidate: dict[tuple[str, str], int] = {}
    for row in postal_votes or []:
        name = str(row.get("candidate") or "").strip()
        party_raw = str(row.get("party") or "").strip()
        if not name:
            continue
        abv = _party_abv(party_raw, existing)
        postal_by_candidate[(name, abv)] = _votes(row.get("postal_votes"))
    for (name, abv), evm_votes in latest_by_candidate.items():
        final_votes = evm_votes + postal_by_candidate.get((name, abv), 0)
        cursor.execute(
            f"""INSERT INTO rounds_ac (state_code, ac_no, ac_name, round_no, candidate, party_abv, votes)
            VALUES ({placeholder}, {placeholder}, {placeholder}, 999, {placeholder}, {placeholder}, {placeholder})
            ON CONFLICT (state_code, ac_no, round_no, candidate, party_abv)
            DO UPDATE SET ac_name = EXCLUDED.ac_name, votes = EXCLUDED.votes""",
            (state_code, ac_no, ac_name, name, abv, final_votes),
        )
        written += 1

    status = "DONE" if postal_votes else "LIVE"
    current_round = latest_round or 0
    won_flag = 1 if postal_votes else 0
    cursor.execute(
        f"""INSERT INTO constituency_status (state_code, ac_no, ac_name, status, current_round, total_rounds, error_count, won)
        VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, 0, {placeholder})
        ON CONFLICT (state_code, ac_no)
        DO UPDATE SET ac_name = EXCLUDED.ac_name, status = EXCLUDED.status,
            current_round = EXCLUDED.current_round, total_rounds = EXCLUDED.total_rounds,
            error_count = 0, won = EXCLUDED.won""",
        (state_code, ac_no, ac_name, status, current_round, latest_round, won_flag),
    )
    conn.commit()
    return {"round_snapshots_written": written, "latest_round": latest_round, "status": status}