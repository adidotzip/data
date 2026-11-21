import unittest

from core.eci_pipeline import discover_constituencies, configured_partywise_urls
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

    def test_configured_sources_are_valid_and_deduplicated(self):
        urls = configured_partywise_urls()
        self.assertTrue(urls)
        self.assertEqual(len(urls), len(set(urls)))
        for url in urls:
            parse_partywise_url(url)


if __name__ == "__main__":
    unittest.main()
