import unittest

from core.eci_pipeline import (
    discover_constituencies,
    discover_by_election_constituencies,
    configured_partywise_urls,
    parse_eci_index_url,
)
from core.scraper import parse_partywise_url


class EciPipelineTests(unittest.TestCase):
    def test_discover_hidden_constituency_list(self):
        html = """
        <input type="hidden" id="S03" value="1,North AC;2,South AC;3,Central AC;">
        """
        found = discover_constituencies(html, "S03")
        self.assertEqual(found, [
            {"ac_no": 1, "ac_name": "North AC"},
            {"ac_no": 2, "ac_name": "South AC"},
            {"ac_no": 3, "ac_name": "Central AC"},
        ])

    def test_discover_real_constituency_links_fallback(self):
        html = """
        <a href="ConstituencywiseS031.htm">1 - AC One</a>
        <a href="ConstituencywiseS032.htm">2 - AC Two</a>
        """
        found = discover_constituencies(html, "S03")
        self.assertEqual([row["ac_no"] for row in found], [1, 2])
        self.assertEqual(found[0]["ac_name"], "1 - AC One")

    def test_partywise_url_parsing(self):
        election_id, state_code = parse_partywise_url(
            "https://results.eci.gov.in/ResultAcGenMay2026/partywiseresult-S03.htm"
        )
        self.assertEqual(election_id, "ResultAcGenMay2026")
        self.assertEqual(state_code, "S03")

    def test_parse_official_by_election_index_url(self):
        election_id = parse_eci_index_url(
            "https://results.eci.gov.in/ResultAcByeOct2026/index.htm"
        )
        self.assertEqual(election_id, "ResultAcByeOct2026")

    def test_discover_mixed_state_by_election_links(self):
        html = """
        <a href="candidateswise-U079.htm">Thattanchavady</a>
        <a href="candidateswise-S2235.htm">Madurantakam</a>
        <a href="candidateswise-S22101.htm">Dharapuram</a>
        <a href="candidateswise-S2570.htm">Rejinagar</a>
        <a href="candidateswise-S25210.htm">Nandigram</a>
        """
        found = discover_by_election_constituencies(html, "ResultAcByeOct2026")
        self.assertEqual(
            [(row["eci_state_code"], row["ac_no"], row["state_code"]) for row in found],
            [("U07", 9, "PY"), ("S22", 35, "TN"), ("S22", 101, "TN"),
             ("S25", 70, "WB"), ("S25", 210, "WB")],
        )
        self.assertEqual(found[0]["url"],
            "https://results.eci.gov.in/ResultAcByeOct2026/ConstituencywiseU079.htm")
        self.assertEqual(found[1]["url"],
            "https://results.eci.gov.in/ResultAcByeOct2026/ConstituencywiseS2235.htm")

    def test_configured_sources_are_valid_and_deduplicated(self):
        urls = configured_partywise_urls()
        self.assertEqual(urls, [
            "https://results.eci.gov.in/ResultAcByeOct2026/index.htm"
        ])
        self.assertEqual(len(urls), len(set(urls)))
        for url in urls:
            parse_eci_index_url(url)


if __name__ == "__main__":
    unittest.main()
