import unittest

from core.scraper import _parse_eci_constituency_html


class ECIParserTests(unittest.TestCase):
    def test_parses_candidate_table(self):
        html = """
        <html><head><title>Results</title></head><body>
        <h2><span>1 - Example AC (Example State)</span></h2>
        <table>
          <tr><th>Serial</th><th>Candidate</th><th>Party</th>
              <th>EVM Votes</th><th>Postal Votes</th><th>Total</th></tr>
          <tr><td>1</td><td>Candidate A</td><td>ABC</td>
              <td>1,234</td><td>56</td><td>1,290</td></tr>
          <tr><td>2</td><td>Candidate B</td><td>XYZ</td>
              <td>900</td><td>10</td><td>910</td></tr>
          <tr><td></td><td>Total</td><td></td><td>2,134</td><td>66</td><td>2,200</td></tr>
        </table></body></html>
        """
        parsed = _parse_eci_constituency_html(html, 1)
        self.assertEqual(parsed["constituency"], "Example AC")
        self.assertEqual(len(parsed["voting_tally"]), 2)
        self.assertEqual(parsed["voting_tally"][0]["candidate"], "Candidate A")
        self.assertEqual(parsed["voting_tally"][0]["evm_votes"], "1234")
        self.assertEqual(parsed["voting_tally"][0]["postal_votes"], "56")

    def test_detects_not_found(self):
        html = "<html><head><title>404 Not Found</title></head><body>Page not found</body></html>"
        self.assertTrue(_parse_eci_constituency_html(html, 1)["not_found"])

    def test_rejects_unknown_table(self):
        html = "<html><body><h2>1 - Example AC (State)</h2><table><tr><td>hello</td></tr></table></body></html>"
        with self.assertRaises(ValueError):
            _parse_eci_constituency_html(html, 1)


if __name__ == "__main__":
    unittest.main()
