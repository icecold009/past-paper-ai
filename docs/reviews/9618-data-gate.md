# 9618 data-trust gate

## Status

**Blocked — not passed**

Review date: 2026-08-11
Branch: `codex/9618-data-trust-gate`
Scope: 9618 Computer Science, configured papers `p1` and `p2`

The gate is intentionally stopped before real extraction, QP/MS review, Gemini calls, and full-dataset tagging. No mock output is being treated as evidence of real-paper quality.

## Blocking inputs

- `data/raw_pdfs/` contains no PDFs (`raw_pdf_count=0`).
- No matching 9618 QP/MS PDF pairs are available for `p1` or `p2`.
- No real Gemini tagging run can be performed without `GEMINI_API_KEY` and representative matched data.
- A manual syllabus reviewer and an approved school chapter map are not yet available. Chapter mapping is outside this gate and remains deferred.

## Current fixture evidence

The checked-in/generated 9618 artifacts are mock-scale and QP-only:

| Artifact | Rows | SHA-256 |
| --- | ---: | --- |
| `data/extracted/9618_pages.csv` | 2 | `8E0C7190AD5E494E8C2E12A684C34B58338D8BF110927E2A6E15E43C9688815C` |
| `data/extracted/9618_qp_ms_pairs.csv` | 0 | `B24B1078C1266848009EE9074C4995A0ABBEC49EE1123DFBAD9F66E9286774E` |
| `data/extracted/9618_questions.csv` | 4 | `396DF3D5915DD57A487CA25394930D38A4C306E8A559DAC98EBCA0CA11743CFF` |
| `data/extracted/9618_tagged_questions.csv` | 4 | `22D1846692BB68F9E59A24FA4273A117B01AEDAA720362C75C101BA8AFEFDC6F` |

The page fixture contains `qp=2` and no `ms` rows. The pair CSV therefore has zero pairs, and the tagged fixture contains empty tag and mark-scheme-point fields. These are expected fixture limitations, not gate passes.

## Execution record

The repository Python environment could not be used for validation:

- `.venv\Scripts\python.exe` is a Python 3.14 environment but is not executable from the current sandbox (`Access is denied`).
- The accessible bundled Python is 3.12 and cannot load the venv's Python 3.14 NumPy/Pandas wheels.
- A temporary dependency installation attempt was blocked by sandbox network policy and the approved retry timed out without installing packages.

Validation used the installed Python 3.14 interpreter directly with the venv package directory on `PYTHONPATH`:

```powershell
$project_python = 'C:\Users\91829\AppData\Local\Programs\Python\Python314\python.exe'
$env:PYTHONPATH = (Resolve-Path '.\.venv\Lib\site-packages').Path
```

Completed checks:

- `$project_python -m unittest discover -s tests -v` — **passed**, 16 tests.
- `$project_python -m src.cli validate --subject 9618` — **blocked by input state**, reported no PDFs for 9618.

The following real-data commands remain pending until the PDFs are supplied. They were not run against the mock fixture because doing so would overwrite the existing generated evidence:

```powershell
<project-python> -m src.cli extract --subject 9618 --fail-on-empty
<project-python> -m src.cli segment --subject 9618
<project-python> -m src.cli match --subject 9618
<project-python> -m src.cli tag --subject 9618 --limit 20 --dry-run
<project-python> -m src.cli tag --subject 9618 --limit 20
```

## Required next evidence

1. Add local, uncommitted 9618 QP/MS PDFs for matching `p1` and `p2` metadata.
2. Run extraction, segmentation, and matching one stage at a time.
3. Manually verify at least one QP/MS pair per selected paper, including page order, question boundaries, nested labels, and mark totals.
4. Run a bounded Gemini sample of no more than 20 questions after reviewing the dry-run prompts.
5. Record each reviewed question's tag assessment, correction, and error category against the Cambridge syllabus.
6. Keep full-dataset tagging, curriculum mapping, recommendations, and PostgreSQL release validation blocked until this evidence is accepted.
