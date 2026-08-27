# Section B content packs

Section B treats the database question bank—not PDF files—as the runtime content contract.

Each pack is a JSON document containing normalized questions, topic metadata, and mark-scheme points. The pack loader
is repeatable and updates the matching natural key, so content can come from an approved external dataset, an AI
starter-bank job, or the optional PDF pipeline.

Load a pack locally with:

```powershell
.\.venv\Scripts\python.exe -m src.content_pack --path content/packs/starter_bank.json
```

The included starter pack is intentionally small and clearly marked as starter content. It exists to make the
personalized-guidance loop testable without requiring users to upload PDFs. Replace it with reviewed subject packs
before treating generated feedback as exam-preparation content.
