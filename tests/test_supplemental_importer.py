import unittest

from core.supplemental_importer import _norm, _state_code


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


if __name__ == "__main__":
    unittest.main()
