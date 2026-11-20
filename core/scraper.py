"""Core scraping functions for ECI results."""

import re
import time
import threading
from selenium.common.exceptions import NoSuchElementException, TimeoutException, StaleElementReferenceException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


def parse_partywise_url(url: str) -> tuple[str, str]:
    """
    Parse a party-wise results URL to extract election identifier and state code.
    
    Expected format: https://results.eci.gov.in/<election_identifier>/partywiseresult-<state_code>.htm
    Example: https://results.eci.gov.in/ResultAcGenMay2026/partywiseresult-S22.htm
    
    Returns:
        tuple of (election_identifier, state_code)
    
    Raises:
        ValueError: If the URL doesn't match the expected format
    """
    pattern = r'^https://results\.eci\.gov\.in/([^/]+)/partywiseresult-([A-Z]\d+)\.htm$'
    match = re.match(pattern, url)
    if not match:
        raise ValueError(
            f"Invalid URL format. Expected: https://results.eci.gov.in/<election_identifier>/partywiseresult-<state_code>.htm\n"
            f"Example: https://results.eci.gov.in/ResultAcGenMay2026/partywiseresult-S22.htm"
        )
    return match.group(1), match.group(2)


def build_constituency_url(election_identifier: str, state_code: str, constituency_code: int) -> str:
    """
    Build the constituency results URL.
    
    Format: https://results.eci.gov.in/<election_identifier>/Constituencywise<state_code><constituency_code>.htm
    """
    return f"https://results.eci.gov.in/{election_identifier}/Constituencywise{state_code}{constituency_code}.htm"


def build_roundwise_url(election_identifier: str, state_code: str, constituency_code: int) -> str:
    """
    Build the round-wise results URL.
    
    Format: https://results.eci.gov.in/<election_identifier>/Roundwise<state_code><constituency_code>.htm
    Example: https://results.eci.gov.in/ResultAcGenMay2026/RoundwiseU071.htm
    """
    return f"https://results.eci.gov.in/{election_identifier}/Roundwise{state_code}{constituency_code}.htm"


STATE_CODES = {
    "Andhra Pradesh": "AP", "Arunachal Pradesh": "AR", "Assam": "AS",
    "Bihar": "BR", "Chhattisgarh": "CG", "Goa": "GA", "Gujarat": "GJ",
    "Haryana": "HR", "Himachal Pradesh": "HP", "Jammu & Kashmir": "JK",
    "Jharkhand": "JH", "Karnataka": "KA", "Kerala": "KL", "Ladakh": "LA",
    "Lakshadweep": "LD", "Madhya Pradesh": "MP", "Maharashtra": "MH",
    "Manipur": "MN", "Meghalaya": "ML", "Mizoram": "MZ", "Nagaland": "NL",
    "Odisha": "OD", "Puducherry": "PY", "Punjab": "PB", "Rajasthan": "RJ",
    "Sikkim": "SK", "Tamil Nadu": "TN", "Telangana": "TS", "Tripura": "TR",
    "Uttar Pradesh": "UP", "Uttarakhand": "UK", "West Bengal": "WB",
}
# ECI uses S/U codes in URLs (e.g. S25, U07) — map them to full names too.
ECI_STATE_NAMES = {
    "S01": "Andhra Pradesh", "S02": "Arunachal Pradesh", "S03": "Assam",
    "S04": "Bihar", "S05": "Goa", "S06": "Gujarat", "S07": "Haryana",
    "S08": "Himachal Pradesh", "S10": "Karnataka", "S11": "Kerala",
    "S12": "Madhya Pradesh", "S13": "Maharashtra", "S14": "Manipur",
    "S15": "Meghalaya", "S16": "Mizoram", "S17": "Nagaland", "S18": "Odisha",
    "S19": "Punjab", "S20": "Rajasthan", "S21": "Sikkim", "S22": "Tamil Nadu",
    "S23": "Tripura", "S24": "Uttar Pradesh", "S25": "West Bengal",
    "S26": "Chhattisgarh", "S27": "Jharkhand", "S28": "Uttarakhand",
    "S29": "Telangana",
    "U01": "Andaman and Nicobar Islands", "U02": "Chandigarh",
    "U03": "Dadra and Nagar Haveli and Daman and Diu",
    "U05": "NCT of Delhi", "U06": "Lakshadweep", "U07": "Puducherry",
    "U08": "Jammu & Kashmir", "U09": "Ladakh",
}
STATE_NAMES = {v: k for k, v in STATE_CODES.items()}
STATE_NAMES.update(ECI_STATE_NAMES)


def get_state_code(state_name: str) -> str:
    """
    Convert state name to state code.
    
    Args:
        state_name: Full state name (e.g., "West Bengal", "Tamil Nadu")
    
    Returns:
        State code (e.g., "WB", "TN") or empty string if not found
    """
    return STATE_CODES.get(state_name, "")


def get_state_name(state_code: str) -> str:
    """Convert state code to full state name (e.g. 'WB' -> 'West Bengal')."""
    return STATE_NAMES.get(state_code, state_code)


def extract_results(driver) -> dict:
    """Extract constituency results from a constituency page."""
    results = {}
    try:
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, 'h2')))
        full_text = driver.find_element(By.TAG_NAME, 'h2').find_element(By.TAG_NAME, 'span').text
        
        parts = full_text.split(' - ')
        constituency_no = parts[0].strip()
        
        state_match = re.search(r'\(([^)]+)\)\s*$', parts[1])
        if state_match:
            constituency_name = parts[1][:state_match.start()].strip()
        else:
            constituency_name = parts[1]

        results["constituency_no"] = constituency_no
        results["constituency"] = constituency_name
        results["voting_tally"] = []

        candidates = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, 'tbody')))
        for candidate in candidates.find_elements(By.TAG_NAME, 'tr'):
            fieldnames = ["serial_no", "candidate", "party", "evm_votes", "postal_votes"]
            results["voting_tally"].append(dict(zip(fieldnames, map(lambda d: d.text, candidate.find_elements(By.TAG_NAME, 'td')))))
    
    except (NoSuchElementException, TimeoutException) as e:
        print(f"Error extracting results: {e}")
    
    return results


def extract_roundwise_results(driver, round_num: int, constituency_info: dict = None) -> dict:
    """
    Extract round-wise results from a round-wise page.
    
    Validates that Previous Rounds + Current Round = Total.
    Issues warnings if validation fails.
    """
    results = {"constituency_no": "", "constituency": "Unknown", "round_tally": []}
    try:
        if constituency_info is None or round_num == 1:
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, 'h2')))
            full_text = driver.find_element(By.TAG_NAME, 'h2').find_element(By.TAG_NAME, 'span').text
            
            parts = full_text.split(' - ')
            constituency_no = parts[0].strip()
            
            state_match = re.search(r'\(([^)]+)\)\s*$', parts[1])
            if state_match:
                constituency_name = parts[1][:state_match.start()].strip()
            else:
                constituency_name = parts[1]
            
            results["constituency_no"] = constituency_no
            results["constituency"] = constituency_name
            results["round_num"] = round_num
        else:
            results["constituency_no"] = constituency_info.get("constituency_no", "")
            results["constituency"] = constituency_info.get("constituency", "Unknown")
            results["round_num"] = round_num
        
        results["round_tally"] = []

        try:
            round_button = driver.find_element(By.XPATH, f"//button[contains(text(), 'R{round_num}') or contains(text(), 'Round {round_num}')]")
            driver.execute_script("arguments[0].click();", round_button)
            time.sleep(0.2)
        except NoSuchElementException:
            pass
        
        target_div = None
        try:
            target_div = driver.find_element(By.ID, f"tab{round_num}")
        except NoSuchElementException:
            th_elements = driver.find_elements(By.XPATH, f"//th[contains(text(), 'Round {round_num}') or contains(text(), 'Round{round_num}')]")
            for th in th_elements:
                try:
                    target_div = th.find_element(By.XPATH, "./ancestor::div[contains(@class, 'tabcontent')]")
                    break
                except NoSuchElementException:
                    continue
        
        if target_div is not None:
            tbody = target_div.find_element(By.TAG_NAME, 'tbody')
            rows = tbody.find_elements(By.TAG_NAME, 'tr')
            
            for row in rows:
                cells = row.find_elements(By.TAG_NAME, 'td')
                if len(cells) < 4:
                    continue
                
                candidate_name = cells[0].text.strip()
                if not candidate_name or candidate_name.lower() == "total":
                    continue
                
                candidate_data = {
                    "serial_no": str(len(results["round_tally"]) + 1),
                    "candidate": candidate_name,
                    "party": cells[1].text.strip(),
                    "votes_brought_forward": cells[2].text.strip(),
                    "current_round": cells[3].text.strip(),
                    "total": cells[4].text.strip() if len(cells) > 4 else cells[3].text.strip()
                }
                
                try:
                    prev_votes = int(candidate_data["votes_brought_forward"])
                    curr_votes = int(candidate_data["current_round"])
                    total_votes = int(candidate_data["total"])
                    
                    if prev_votes + curr_votes != total_votes:
                        print(f"WARNING: Vote mismatch for {candidate_data['candidate']}: {prev_votes} + {curr_votes} ≠ {total_votes}")
                except ValueError:
                    pass
                
                results["round_tally"].append(candidate_data)
    
    except (NoSuchElementException, TimeoutException) as e:
        pass
    
    return results


def extract_all_roundwise_rounds(driver) -> dict:
    """
    Extract all available rounds from a round-wise page in a single pass.

    Instead of clicking through round buttons one by one (slow), reads every
    pre-rendered ``tab<N>`` div from the DOM.  This is safe because the ECI
    page renders all round data up-front; clicking a round button merely
    toggles CSS visibility.

    During a live election the page grows progressively as new rounds are
    counted — so this function simply returns whatever rounds are present
    in the DOM at the moment it runs.  Callers can re-invoke periodically
    to pick up newly-appeared rounds.

    Returns dict with keys: constituency_no, constituency, rounds.
    ``rounds`` is a list of ``{"round": int, "tally": [...]}`` sorted by
    round number.
    """
    results = {"constituency_no": "", "constituency": "Unknown", "rounds": []}

    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "h2"))
        )
        full_text = (
            driver.find_element(By.TAG_NAME, "h2")
            .find_element(By.TAG_NAME, "span")
            .text
        )

        parts = full_text.split(" - ")
        constituency_no = parts[0].strip()

        state_match = re.search(r"\(([^)]+)\)\s*$", parts[1])
        if state_match:
            constituency_name = parts[1][: state_match.start()].strip()
        else:
            constituency_name = parts[1]

        results["constituency_no"] = constituency_no
        results["constituency"] = constituency_name

        # ---- bulk extract: read every tab<N> div present in the DOM ----
        # Try the primary strategy (tab IDs) first.  If the page uses a
        # different structure, fall back to scanning <th> headers.
        tab_divs = driver.find_elements(By.CSS_SELECTOR, 'div[id^="tab"]')

        if tab_divs:
            for tab_div in tab_divs:
                tab_id = tab_div.get_attribute("id") or ""
                match = re.match(r"tab(\d+)$", tab_id)
                if not match:
                    continue
                round_num = int(match.group(1))
                tally = _extract_tally_from_element(tab_div)
                if tally:
                    results["rounds"].append({"round": round_num, "tally": tally})
        else:
            # Fallback: find round data via <th> headers (some page variants)
            th_elements = driver.find_elements(
                By.XPATH,
                "//th[contains(text(), 'Round ') or contains(text(), 'Round')]",
            )
            seen = set()
            for th in th_elements:
                th_match = re.search(r"Round\s*(\d+)", th.text)
                if not th_match:
                    continue
                round_num = int(th_match.group(1))
                if round_num in seen:
                    continue
                seen.add(round_num)
                try:
                    tab_div = th.find_element(
                        By.XPATH,
                        "./ancestor::div[contains(@class, 'tabcontent')]",
                    )
                    tally = _extract_tally_from_element(tab_div)
                    if tally:
                        results["rounds"].append(
                            {"round": round_num, "tally": tally}
                        )
                except NoSuchElementException:
                    continue

        results["rounds"].sort(key=lambda r: r["round"])

    except (NoSuchElementException, TimeoutException):
        pass

    return results


def _extract_tally_from_element(element) -> list:
    """Extract the candidate tally table from a single DOM element (tab div)."""
    tally = []
    try:
        tbody = element.find_element(By.TAG_NAME, "tbody")
        rows = tbody.find_elements(By.TAG_NAME, "tr")
    except NoSuchElementException:
        return tally

    for row in rows:
        try:
            cells = row.find_elements(By.TAG_NAME, "td")
        except StaleElementReferenceException:
            continue
        if len(cells) < 4:
            continue

        candidate_name = cells[0].text.strip()
        if not candidate_name or candidate_name.lower() == "total":
            continue

        candidate_data = {
            "serial_no": str(len(tally) + 1),
            "candidate": candidate_name,
            "party": cells[1].text.strip(),
            "votes_brought_forward": cells[2].text.strip(),
            "current_round": cells[3].text.strip(),
            "total": cells[4].text.strip() if len(cells) > 4 else cells[3].text.strip(),
        }

        try:
            prev_votes = int(candidate_data["votes_brought_forward"])
            curr_votes = int(candidate_data["current_round"])
            total_votes = int(candidate_data["total"])
            if prev_votes + curr_votes != total_votes:
                print(
                    f"WARNING: Vote mismatch for {candidate_data['candidate']}: "
                    f"{prev_votes} + {curr_votes} ≠ {total_votes}"
                )
        except ValueError:
            pass

        tally.append(candidate_data)

    return tally


def _extract_constituency_info(driver) -> dict:
    """Extract constituency_no and constituency name from the h2 tag."""
    info = {"constituency_no": "", "constituency": ""}
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "h2"))
        )
        full_text = (
            driver.find_element(By.TAG_NAME, "h2")
            .find_element(By.TAG_NAME, "span")
            .text
        )
        parts = full_text.split(" - ")
        info["constituency_no"] = parts[0].strip()
        state_match = re.search(r"\(([^)]+)\)\s*$", parts[1])
        if state_match:
            info["constituency"] = parts[1][: state_match.start()].strip()
        else:
            info["constituency"] = parts[1]
    except (NoSuchElementException, TimeoutException):
        pass
    return info


def scrape_ac_rounds_core(driver, election_identifier: str, state_code: str,
                          ac_no: int, start_round: int = 1) -> dict:
    """
    Core function to scrape all rounds for a single AC plus postal votes.

    This is the shared logic used by both /scrape/ac-rounds and /scrape/all-rounds.

    During a live election the page grows progressively as new rounds are
    counted.  Each invocation picks up whatever rounds are available;
    callers can re-invoke periodically to capture newly-appeared rounds.

    Round extraction is sequential within each AC (a second Chrome instance
    adds ~5s startup overhead that negates any parallel-clicking gain).
    Concurrency comes from the client running multiple ACs in parallel.
    """
    result = {"ac_no": ac_no, "rounds": [], "constituency": "", "postal_votes": []}

    try:
        roundwise_url = build_roundwise_url(election_identifier, state_code, ac_no)
        driver.get(roundwise_url)

        if "404" in driver.title:
            return {"status": "done"}

        # --- Constituency info (from h2) ---
        constituency_info = _extract_constituency_info(driver)
        result["constituency"] = constituency_info.get("constituency", "")

        # --- Round extraction: click through each round button ---
        for round_num in range(max(start_round, 1), 50):
            rr = extract_roundwise_results(driver, round_num, constituency_info)
            if not rr.get("round_tally"):
                break
            result["rounds"].append({
                "round": round_num,
                "tally": rr["round_tally"],
            })

        # --- Postal votes from constituency page ---
        constituency_url = build_constituency_url(election_identifier, state_code, ac_no)
        driver.get(constituency_url)
        final_result = extract_results(driver)
        result["constituency"] = final_result.get("constituency", result["constituency"])
        result["postal_votes"] = final_result.get("voting_tally", [])

        return {"status": "success", "data": result}

    except Exception as e:
        return {"status": "error", "error": str(e)}


def _fetch_eci_html(url: str, timeout: int = 25) -> tuple[str, int]:
    """Fetch ECI HTML with curl first (curl's TLS fingerprint is less likely to be blocked).

    The request/session approach is adapted from the MIT-licensed
    thecont1/india-votes-data live scraper. See upstream attribution in README.
    """
    import subprocess

    result = subprocess.run(
        ["curl", "-sS", "-L", "--compressed", "--max-time", str(timeout),
         "-A", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
         "-w", "\\n__HTTP_STATUS__:%{http_code}", url],
        capture_output=True, text=True, timeout=timeout + 5,
    )
    if result.returncode:
        raise RuntimeError(f"curl failed ({result.returncode}): {result.stderr[-300:]}")
    marker = "\\n__HTTP_STATUS__:"
    if marker not in result.stdout:
        raise RuntimeError("curl did not return an HTTP status marker")
    html, status_text = result.stdout.rsplit(marker, 1)
    return html, int(status_text.strip() or 0)


def _parse_eci_constituency_html(html: str, expected_no: int) -> dict:
    """Parse ECI constituency results from server-rendered HTML."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    body_text = soup.get_text(" ", strip=True)
    if re.search(r"404|page not found|not found", title, re.I) or re.search(
        r"page not found|this page is not available", body_text[:1500], re.I
    ):
        return {"not_found": True}

    header = soup.find("h2")
    if not header:
        raise ValueError("ECI page has no constituency heading (h2)")
    heading = header.get_text(" ", strip=True)
    match = re.search(r"\\d+\\s*[-–]\\s*(.+?)(?:\\s*\\([^)]*\\))?$", heading)
    constituency = match.group(1).strip() if match else heading.strip()

    table = None
    for candidate_table in soup.find_all("table"):
        header_cells = [c.get_text(" ", strip=True).lower() for c in candidate_table.find_all("th")]
        joined = " ".join(header_cells)
        if any("candidate" in h for h in header_cells) and any("party" in h for h in header_cells):
            table = candidate_table
            break
    if table is None:
        # ECI variants sometimes omit table headers; only accept a table with
        # candidate rows that have the expected 5+ cells and numeric vote fields.
        for candidate_table in soup.find_all("table"):
            if any(len(row.find_all("td")) >= 5 for row in candidate_table.find_all("tr")):
                table = candidate_table
                break
    if table is None:
        raise ValueError("No candidate results table recognized")

    header_cells = [c.get_text(" ", strip=True).lower() for c in table.find_all("th")]
    rows = []
    for tr in table.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all("td")]
        if len(cells) < 5:
            continue
        if cells[0].strip().lower() in {"total", "nota"} and cells[0].strip().lower() == "total":
            continue
        # Common ECI columns: serial, candidate, party, EVM, postal, total.
        # Older variants have serial, candidate, party, EVM, postal.
        serial, candidate, party, evm, postal = cells[:5]
        if not candidate or not re.search(r"\\d", evm.replace(",", "")) or not re.search(
            r"\\d", postal.replace(",", "")
        ):
            continue
        rows.append({
            "serial_no": serial.strip(),
            "candidate": candidate.strip(),
            "party": party.strip(),
            "evm_votes": evm.strip().replace(",", ""),
            "postal_votes": postal.strip().replace(",", ""),
        })
    if not rows:
        raise ValueError("Results table was found but no candidate rows parsed")
    return {"constituency_no": str(expected_no), "constituency": constituency,
            "voting_tally": rows}


def scrape_constituency_sync(election_identifier: str, state_code: str,
                              limit: int = None, respect_mode: bool = False) -> dict:
    """Scrape constituency pages using curl+BeautifulSoup, with Selenium fallback.

    Stops only at a confirmed 404. A blocked or unrecognized page is reported
    as an error rather than silently treated as an end-of-results condition.
    """
    from core.browser import create_chrome_driver

    results = {
        "constituencywise_results": [],
        "election_year": "",
        "election_type": "",
        "election_state": "",
    }
    failed_url = None
    source_error = None
    driver = None

    try:
        seq_no = 1
        while not limit or seq_no <= limit:
            url = build_constituency_url(election_identifier, state_code, seq_no)
            failed_url = url
            try:
                html, status = _fetch_eci_html(url)
                if status == 404:
                    if seq_no == 1 and not results["constituencywise_results"]:
                        source_error = "The ECI constituency results page does not exist or returned 404."
                    break
                if status >= 400:
                    raise RuntimeError(f"ECI returned HTTP {status}")
                parsed = _parse_eci_constituency_html(html, seq_no)
                if parsed.get("not_found"):
                    if seq_no == 1 and not results["constituencywise_results"]:
                        source_error = "The ECI constituency results page does not exist or returned 404."
                    break
                results["constituencywise_results"].append({
                    "source_url": url,
                    "voting_data": parsed,
                })
            except Exception as primary_error:
                # Fall back to Selenium only for an individual page fetch/parse
                # failure. Do not mask confirmed HTTP 404s.
                if "HTTP 404" in str(primary_error):
                    break
                if driver is None:
                    driver = create_chrome_driver()
                driver.get(url)
                title = (driver.title or "").lower()
                body = (driver.find_element(By.TAG_NAME, "body").text or "").lower()
                if "404" in title or "page not found" in body:
                    if seq_no == 1 and not results["constituencywise_results"]:
                        source_error = "The ECI constituency results page does not exist or returned 404."
                    break
                fallback = extract_results(driver)
                if not fallback.get("voting_tally"):
                    source_error = (
                        f"Could not parse ECI constituency page: {primary_error}; "
                        "Selenium fallback did not recognize its results table."
                    )
                    break
                results["constituencywise_results"].append({
                    "source_url": url,
                    "voting_data": fallback,
                })

            if respect_mode and seq_no % 10 == 0:
                time.sleep(1)
            seq_no += 1
    except Exception as e:
        source_error = f"Scraping failed: {e}"
        failed_url = locals().get("url", failed_url)
    finally:
        if driver is not None:
            driver.quit()

    if source_error:
        return {"error": source_error, "source_url": failed_url,
                "constituencywise_results": results["constituencywise_results"]}
    if not results["constituencywise_results"]:
        return {"error": "No constituency results were extracted from the source.",
                "source_url": failed_url, "constituencywise_results": []}
    return results

def scrape_worker(election_identifier: str, state_code: str,
                  result_list: list, state: dict, lock: threading.Lock,
                  respect_mode: bool = False):
    """Reusable worker that picks up AC numbers until end of results.

    Args:
        election_identifier: e.g. "ResultAcGenMay2026"
        state_code: e.g. "S22"
        result_list: shared list to append results to
        state: shared dict with keys 'current' (int) and 'end_of_results' (bool)
        lock: threading.Lock for shared state
        respect_mode: if True, pause every 10 URLs
    """
    from core.browser import create_chrome_driver
    driver = create_chrome_driver()

    try:
        while True:
            with lock:
                if state.get("end_of_results"):
                    break
                seq_no = state["current"]
                state["current"] += 1

            url = build_constituency_url(election_identifier, state_code, seq_no)
            driver.get(url)

            if "404" in driver.title:
                with lock:
                    if not state.get("end_of_results"):
                        state["end_of_results"] = True
                        print(f" {seq_no:03d}-STOP.")
                break

            result = extract_results(driver)
            if result:
                with lock:
                    result_list.append(result)
                    label = result.get("constituency")
                    suffix = f" {seq_no:03d}-{label}." if label else ""
                    print(f"{suffix} Done.")

            if respect_mode:
                with lock:
                    state["_count"] = state.get("_count", 0) + 1
                    if state["_count"] % 10 == 0:
                        print("[Respect mode] Pausing 1s...")
                        time.sleep(1)
    except (NoSuchElementException, TimeoutException, AssertionError) as e:
        with lock:
            print(f"Worker error: {e}")
    finally:
        driver.quit()
