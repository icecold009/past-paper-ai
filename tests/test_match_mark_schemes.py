from __future__ import annotations

import logging
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from src.match_mark_schemes import match_mark_schemes


class MatchMarkSchemesTests(unittest.TestCase):
    def test_matches_qp_and_ms_but_warns_for_mismatched_variant(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            pages_csv = temp_path / "9618_pages.csv"
            output_csv = temp_path / "9618_qp_ms_pairs.csv"
            pd.DataFrame(
                [
                    {
                        "filename": "9618_p1_2023_mj_11_qp.pdf",
                        "subject": "9618",
                        "paper": "p1",
                        "year": 2023,
                        "session": "May/June",
                        "variant": "11",
                        "doc_type": "qp",
                        "page": 1,
                        "text": "Question paper page 1",
                    },
                    {
                        "filename": "9618_p1_2023_mj_11_ms.pdf",
                        "subject": "9618",
                        "paper": "p1",
                        "year": 2023,
                        "session": "May/June",
                        "variant": "11",
                        "doc_type": "ms",
                        "page": 1,
                        "text": "Mark scheme page 1",
                    },
                    {
                        "filename": "9618_p1_2023_mj_12_ms.pdf",
                        "subject": "9618",
                        "paper": "p1",
                        "year": 2023,
                        "session": "May/June",
                        "variant": "12",
                        "doc_type": "ms",
                        "page": 1,
                        "text": "Mismatched variant",
                    },
                ]
            ).to_csv(pages_csv, index=False)

            with self.assertLogs("src.match_mark_schemes", level=logging.WARNING) as captured:
                pairs = match_mark_schemes(
                    subject="9618",
                    pages_csv=pages_csv,
                    output_csv=output_csv,
                )

            written = pd.read_csv(output_csv)

        self.assertEqual(len(pairs), 1)
        self.assertEqual(written.loc[0, "qp_filename"], "9618_p1_2023_mj_11_qp.pdf")
        self.assertEqual(written.loc[0, "ms_filename"], "9618_p1_2023_mj_11_ms.pdf")
        self.assertEqual(written.loc[0, "qp_text"], "Question paper page 1")
        self.assertEqual(written.loc[0, "ms_text"], "Mark scheme page 1")
        self.assertTrue(any("No matching question paper" in message for message in captured.output))


if __name__ == "__main__":
    unittest.main()
