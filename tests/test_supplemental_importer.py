import unittest

from core.supplemental_importer import _norm, _state_code, _supplemental_event_id


class SupplementalImporterTests(unittest.TestCase):
    def test_state_code_normalization(self):
        cases = {
            "Tamil Nadu": "TN",
            "West Bengal": "WB",
            "Jammu & Kashmir": "JK",
            "NCT of Delhi": "DL",
            "Puducherry": "PY",
            "Uttanchal": "UK",
            "Orissa": "OD",
            "Telangana": "TG",
        }
        for name, expected in cases.items():
            with self.subTest(name=name):
                self.assertEqual(_state_code(name), expected)

    def test_normalization(self):
        self.assertEqual(_norm("  Jammu & Kashmir "), "jammu and kashmir")

    def test_same_state_year_by_elections_get_distinct_ids(self):
        ids = {
            _supplemental_event_id(2021, "KA", "KA-AC-2021-01"),
            _supplemental_event_id(2021, "KA", "KA-AC-2021-02"),
        }
        self.assertEqual(len(ids), 2)

    def test_event_id_is_stable_and_safe(self):
        first = _supplemental_event_id(2021, "KA", "By-election: AC 12 / 2021")
        second = _supplemental_event_id(2021, "KA", "By-election: AC 12 / 2021")
        self.assertEqual(first, second)
        self.assertNotIn("/", first)


if __name__ == "__main__":
    unittest.main()
