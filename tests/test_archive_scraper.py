import unittest

from scripts.eci_archive_scraper import split_archive_url, discover_legacy_acs, parse_legacy_candidates


class ArchiveScraperTests(unittest.TestCase):
    def test_split_archive_url(self):
        prefix, original = split_archive_url(
            "https://web.archive.org/web/20230602041714/https://results.eci.gov.in/OldElection/ConstituencywiseS101.htm?ac=1"
        )
        self.assertEqual(prefix, "https://web.archive.org/web/20230602041714/")
        self.assertTrue(original.startswith("https://results.eci.gov.in/"))

    def test_discover_hidden_ac_list(self):
        html = '<input type="hidden" id="S10" value="1,One AC;2,Two AC;">'
        self.assertEqual(discover_legacy_acs(html, "S10"), [
            {"ac_no": 1, "ac_name": "One AC"},
            {"ac_no": 2, "ac_name": "Two AC"},
        ])

    def test_parse_candidate_table(self):
        html = """
        <h2>Karnataka - Nippani - 1</h2>
        <table><tr><th>S.N.</th><th>Candidate</th><th>Party</th><th>EVM</th><th>Postal</th><th>Total</th></tr>
        <tr><td>1</td><td>Candidate A</td><td>Party A</td><td>1,000</td><td>10</td><td>1,010</td></tr>
        <tr><td>2</td><td>Candidate B</td><td>Party B</td><td>900</td><td>8</td><td>908</td></tr></table>
        """
        name, candidates = parse_legacy_candidates(html)
        self.assertEqual(len(candidates), 2)
        self.assertEqual(candidates[0]["evm_votes"], "1000")
        self.assertEqual(candidates[0]["postal_votes"], "10")


if __name__ == "__main__":
    unittest.main()
