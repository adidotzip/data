#!/usr/bin/env python3
"""Incremental scraper for archived legacy ECI results pages.

Adapted with attribution from the MIT-licensed thecont1/india-votes-data
archive scraper. Outputs CSV/JSON only because the current API schema has no
separate election_id dimension for historical elections.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

CSV_COLUMNS = [
    "election_id", "election_year", "election_type", "state_code",
    "constituency", "constituency_no", "serial_no", "candidate",
    "party", "evm_votes", "postal_votes",
]


def split_archive_url(url: str) -> tuple[str, str]:
    match = re.match(r"(https://web\.archive\.org/web/\d+/)(https?://.+)$", url)
    if not match:
        raise ValueError("Expected an archive.org URL with a timestamp and original ECI URL")
    return match.group(1), match.group(2)


def archive_raw_url(prefix: str, original_url: str) -> str:
    return prefix.rstrip("/") + "id_/" + original_url


def fetch_archive_html(url: str, timeout: int = 35) -> str:
    proc = subprocess.run(
        ["curl", "-sS", "-L", "--compressed", "--max-time", str(timeout), url],
        capture_output=True, text=True, timeout=timeout + 5,
    )
    if proc.returncode:
        raise RuntimeError(f"curl failed ({proc.returncode}): {proc.stderr[-300:]}")
    if len(proc.stdout.strip()) < 100:
        raise RuntimeError("Archive returned an empty/short response")
    return proc.stdout


def discover_legacy_acs(html: str, raw_code: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    discovered: dict[int, str] = {}
    for inp in soup.find_all("input", {"type": "hidden"}):
        ident = str(inp.get("id") or "")
        value = str(inp.get("value") or "")
        if ident != raw_code and not ident.startswith(raw_code):
            continue
        for item in value.rstrip(";").split(";"):
            pair = item.split(",", 1)
            if len(pair) == 2 and pair[0].strip().isdigit():
                discovered[int(pair[0].strip())] = pair[1].strip()
    return [{"ac_no": n, "ac_name": name} for n, name in sorted(discovered.items())]


def parse_legacy_candidates(html: str) -> tuple[str, list[dict[str, str]]]:
    soup = BeautifulSoup(html, "html.parser")
    heading = soup.find(["h1", "h2", "h3"])
    constituency = heading.get_text(" ", strip=True) if heading else ""
    constituency = re.sub(r"^.*?[-:]\s*", "", constituency).strip()
    table = None
    for candidate_table in soup.find_all("table"):
        headers = [th.get_text(" ", strip=True).lower() for th in candidate_table.find_all("th")]
        if any("s.n" in h or h.replace(".", "") == "sn" for h in headers):
            table = candidate_table
            break
    if table is None:
        for candidate_table in soup.find_all("table"):
            if any(len(row.find_all("td")) >= 6 for row in candidate_table.find_all("tr")):
                table = candidate_table
                break
    if table is None:
        raise ValueError("Legacy ECI candidate table was not recognized")

    candidates = []
    for row in table.find_all("tr"):
        cells = [td.get_text(" ", strip=True) for td in row.find_all("td")]
        if len(cells) < 6 or not cells[0].isdigit():
            continue
        name = cells[1].strip()
        if not name or name.upper() == "TOTAL":
            continue
        party = cells[2].strip()
        evm = cells[3].replace(",", "").strip()
        postal = cells[4].replace(",", "").strip()
        if not evm.isdigit() or not postal.isdigit():
            continue
        candidates.append({
            "serial_no": cells[0], "candidate": name, "party": party,
            "evm_votes": evm, "postal_votes": postal,
        })
    if not candidates:
        raise ValueError("No candidate rows parsed from archived page")
    return constituency, candidates


def run_archive_scrape(archive_url: str, election_id: str, state_code: str,
                       output_dir: Path, dry_run: bool = False) -> dict[str, Any]:
    prefix, original = split_archive_url(archive_url)
    match = re.search(r"/([^/]+)/Constituencywise([A-Z]\d+)\.htm", original)
    if not match:
        raise ValueError("Archive URL must point to a legacy ECI Constituencywise page")
    eci_election = match.group(1)
    raw_code = match.group(2)
    first_html = fetch_archive_html(archive_raw_url(prefix, original))
    acs = discover_legacy_acs(first_html, raw_code)
    if not acs:
        raise ValueError("Could not discover historical constituency list from archive page")
    if dry_run:
        acs = acs[:3]

    year_match = re.search(r"(\d{4})", election_id)
    year = year_match.group(1) if year_match else ""
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / f"{election_id}-{state_code}.csv"
    json_path = output_dir / f"{election_id}-{state_code}.json"
    already: set[int] = set()
    if csv_path.exists():
        with csv_path.open(newline="", encoding="utf-8") as file:
            for row in csv.DictReader(file):
                if row.get("constituency_no", "").isdigit():
                    already.add(int(row["constituency_no"]))
    if not csv_path.exists() or csv_path.stat().st_size == 0:
        with csv_path.open("w", newline="", encoding="utf-8") as file:
            csv.DictWriter(file, fieldnames=CSV_COLUMNS).writeheader()

    json_results: list[dict[str, Any]] = []
    if json_path.exists():
        try:
            json_results = json.loads(json_path.read_text(encoding="utf-8")).get("constituencywise_results", [])
        except (json.JSONDecodeError, OSError):
            json_results = []

    errors = []
    for ac in acs:
        no = ac["ac_no"]
        if no in already:
            continue
        eci_url = f"https://results.eci.gov.in/{eci_election}/Constituencywise{raw_code}{no}.htm?ac={no}"
        raw_url = archive_raw_url(prefix, eci_url)
        try:
            page = fetch_archive_html(raw_url)
            name, candidates = parse_legacy_candidates(page)
            if not name:
                name = ac["ac_name"]
            entry = {
                "source_url": eci_url,
                "voting_data": {
                    "constituency_no": str(no), "constituency": name,
                    "voting_tally": candidates,
                },
            }
            with csv_path.open("a", newline="", encoding="utf-8") as file:
                writer = csv.DictWriter(file, fieldnames=CSV_COLUMNS)
                for candidate in candidates:
                    writer.writerow({
                        "election_id": election_id, "election_year": year,
                        "election_type": "Assembly", "state_code": state_code,
                        "constituency": name, "constituency_no": no, **candidate,
                    })
            json_results = [r for r in json_results if str(r.get("voting_data", {}).get("constituency_no")) != str(no)]
            json_results.append(entry)
            json_path.write_text(json.dumps({
                "election_id": election_id, "election_year": year,
                "election_type": "Assembly", "state_code": state_code,
                "constituencywise_results": sorted(json_results, key=lambda r: int(r.get("voting_data", {}).get("constituency_no", 0))),
            }, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as exc:
            errors.append({"ac_no": no, "error": str(exc)})
        time.sleep(1.0)

    return {"discovered": len(acs), "already_scraped": len(already), "errors": errors,
            "csv": str(csv_path), "json": str(json_path)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Incrementally scrape archived ECI constituency results")
    parser.add_argument("archive_url", help="archive.org URL for constituency page 1")
    parser.add_argument("--election-id", required=True, help="Historical election identifier, e.g. AC-2023")
    parser.add_argument("--state-code", required=True, help="Output state abbreviation")
    parser.add_argument("--output-dir", default="data/archive")
    parser.add_argument("--dry-run", action="store_true", help="Only scrape the first 3 constituencies")
    args = parser.parse_args()
    result = run_archive_scrape(args.archive_url, args.election_id, args.state_code, Path(args.output_dir), args.dry_run)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
