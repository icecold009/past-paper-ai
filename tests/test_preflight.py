from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from src.preflight import build_preflight_report


class PreflightTests(unittest.TestCase):
    def test_reports_in_scope_pairs_and_out_of_scope_variants(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            raw_root = temp_path / "raw_pdfs"
            raw_root.mkdir()
            for filename in (
                "9618_p1_2023_mj_12_qp.pdf",
                "9618_p1_2023_mj_12_ms.pdf",
                "9618_p1_2023_mj_11_qp.pdf",
            ):
                (raw_root / filename).write_bytes(filename.encode("ascii"))

            report = build_preflight_report(
                requested_subjects=["9618"],
                raw_pdf_root=raw_root,
                extracted_dir=temp_path / "extracted",
                subject_plan={"9618": ["p1"]},
                allowed_variants={"2"},
            )

        self.assertEqual(len(report["raw_pdfs"]["valid_in_scope"]), 2)
        self.assertEqual(len(report["raw_pdfs"]["out_of_scope"]), 1)
        self.assertEqual(report["coverage"]["9618"]["p1"]["matched_pairs"], 1)
        self.assertEqual(report["coverage"]["9618"]["p1"]["status"], "ready")
        self.assertEqual(report["status"], "blocked")
        self.assertTrue(any("missing artifact" in reason for reason in report["failure_reasons"]))

    def test_reports_unmatched_files_and_missing_paper_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            raw_root = temp_path / "raw_pdfs"
            raw_root.mkdir()
            for filename in (
                "9618_p1_2023_mj_12_qp.pdf",
                "9618_p1_2023_mj_12_ms.pdf",
                "9618_p1_2024_mj_22_qp.pdf",
            ):
                (raw_root / filename).write_bytes(filename.encode("ascii"))
            extracted_dir = temp_path / "extracted"
            extracted_dir.mkdir()
            pd.DataFrame(
                [
                    {
                        "filename": "9618_p1_2023_mj_12_qp.pdf",
                        "subject": "9618",
                        "paper": "p1",
                        "year": 2023,
                        "session": "May/June",
                        "variant": "12",
                        "doc_type": "qp",
                        "page": 1,
                        "text": "Question paper",
                    }
                ]
            ).to_csv(extracted_dir / "9618_pages.csv", index=False)

            report = build_preflight_report(
                requested_subjects=["9618"],
                raw_pdf_root=raw_root,
                extracted_dir=extracted_dir,
                subject_plan={"9618": ["p1", "p2"]},
                allowed_variants={"2"},
            )

        coverage = report["coverage"]["9618"]["p1"]
        self.assertEqual(coverage["status"], "blocked")
        self.assertEqual(coverage["unmatched_qp_keys"], ["9618::p1::2024::May/June::22"])
        self.assertIn("p2", report["artifacts"]["9618"]["pages"]["missing_papers"])
        self.assertTrue(any("unmatched" in reason for reason in report["failure_reasons"]))


if __name__ == "__main__":
    unittest.main()
