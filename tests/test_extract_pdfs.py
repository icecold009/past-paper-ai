from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.extract_pdfs import extract_subject_pdfs


class ExtractPdfScopeTests(unittest.TestCase):
    def test_extraction_skips_papers_outside_variant_scope(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            raw_root = Path(temp_dir) / "raw_pdfs"
            raw_root.mkdir()
            (raw_root / "9618_p1_2023_mj_12_qp.pdf").touch()
            (raw_root / "9618_p1_2023_mj_11_qp.pdf").touch()
            (raw_root / "9618_p2_2023_mj_22_qp.pdf").touch()

            def fake_extract(pdf_path: Path) -> list[dict[str, object]]:
                return [
                    {
                        "filename": pdf_path.name,
                        "subject": "9618",
                        "paper": pdf_path.name.split("_")[1],
                        "year": 2023,
                        "session": "May/June",
                        "variant": pdf_path.name.split("_")[4],
                        "doc_type": "qp",
                        "page": 1,
                        "text": pdf_path.name,
                    }
                ]

            with patch("src.extract_pdfs.extract_pdf_pages", side_effect=fake_extract):
                with patch(
                    "src.extract_pdfs.pages_csv_path",
                    return_value=raw_root / "pages.csv",
                ):
                    extracted = extract_subject_pdfs(
                        "9618",
                        raw_pdf_root=raw_root,
                        allowed_papers={"p1", "p2"},
                        allowed_variants={"2"},
                    )

        self.assertEqual(extracted["filename"].tolist(), [
            "9618_p1_2023_mj_12_qp.pdf",
            "9618_p2_2023_mj_22_qp.pdf",
        ])
        self.assertEqual(extracted["variant"].tolist(), ["12", "22"])


if __name__ == "__main__":
    unittest.main()
