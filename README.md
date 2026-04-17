# past-paper-ai

A free local project to generate CAIE practice papers from past papers.

## Goal
Build a simple Python workflow that:
1. Stores past paper PDFs for 9618 Paper 1 and Paper 2.
2. Extracts text from those PDFs.
3. Sends cleaned past-paper content to a free Gemini API model.
4. Generates a realistic practice paper for revision.

## Project structure

```text
past-paper-ai/
  src/
    extract.py
    extract_pdfs.py
    utils.py
  data/
    raw_pdfs/
      paper1/
        qp/
        ms/
      paper2/
        qp/
        ms/
    extracted/
  outputs/
  prompts/
  .env
```

## File naming rules
Rename PDFs exactly like this:

```text
9618_p1_2023_mj_11_qp.pdf
9618_p1_2023_mj_11_ms.pdf
9618_p2_2023_mj_21_qp.pdf
9618_p2_2023_mj_21_ms.pdf
```

### Meaning
- `9618` = subject code
- `p1` / `p2` = paper 1 or paper 2
- `2023` = year
- `mj` / `on` / `fm` = May/June, Oct/Nov, Feb/March
- `11 12 13` = Paper 1 variants
- `21 22 23` = Paper 2 variants
- `qp` = question paper
- `ms` = mark scheme

## Setup
Open a terminal in the project folder and install the libraries:

```bash
pip install pdfplumber pandas google-generativeai
```

## Step-by-step workflow

### 1. Download papers
Download CAIE 9618 Paper 1 and Paper 2 PDFs from 2021 to 2025.

Put them here:
- `data/raw_pdfs/paper1/qp/`
- `data/raw_pdfs/paper1/ms/`
- `data/raw_pdfs/paper2/qp/`
- `data/raw_pdfs/paper2/ms/`

### 2. Extract text
Run:

```bash
python -m src.extract
```

This creates:

```text
data/extracted/9618_pages.csv
```

This first pass extracts one row per PDF page, keeping the filename metadata and raw page text for later question segmentation.

### 3. Add your Gemini API key
Create a file called `.env` in the project root:

```env
GEMINI_API_KEY=your_api_key_here
```

## Current status
At the moment, the project is set up for:
- CAIE Computer Science 9618
- Paper 1 (theory)
- Paper 2 (programming)
- Local PDF extraction
- Future Gemini-based practice paper generation

## Notes
- This is meant to be fully free.
- Start with one subject only.
- More past papers usually improves the generated practice paper.
- Mark schemes are useful later for answer style and checking patterns.
