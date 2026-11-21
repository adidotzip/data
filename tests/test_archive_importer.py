import json
import tempfile
import unittest
from pathlib import Path

from core.archive_importer import parse_archive_file


class ArchiveImporterTests(unittest.TestCase):
    def test_parse_archive_rows_and_totals(self):
        payload = {
            "title": "Test Assembly 2024",
            "election_id": "AC-2024-01",
            "election_year": "2024",
            "election_state": "MH",
            "constituencywise_results": [{
                "source_url": "https://results.eci.gov.in/test/ConstituencywiseS131.htm",
                "voting_data": {
                    "constituency_no": "1",
                    "constituency": "TEST AC",
                    "voting_tally": [
                        {"candidate": "Candidate A", "party": "Party A", "evm_votes": "1,234", "postal_votes": "56"},
                        {"candidate": "Candidate B", "party": "Independent", "evm_votes": "100", "postal_votes": "4"},
                    ],
                },
            }],
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "2024Assembly-MH.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            metadata, records = parse_archive_file(path)

        self.assertEqual(metadata["state_code"], "MH")
        self.assertEqual(metadata["constituencies"], 1)
        self.assertEqual(metadata["candidate_rows"], 2)
        self.assertEqual(records[0][7:10], (1234, 56, 1290))
        self.assertEqual(records[1][7:10], (100, 4, 104))
        self.assertEqual(records[0][0], "AC-2024-01")


if __name__ == "__main__":
    unittest.main()
