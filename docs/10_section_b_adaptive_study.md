# Section B — adaptive study engine

## Product boundary

The student application is not a PDF-management tool. Its runtime dependency is a normalized question bank containing
question text, subject/topic metadata, command words, marks, and mark-scheme points. PDFs, approved external datasets,
and AI-generated starter content are interchangeable upstream content providers.

```text
approved PDFs / external pack / AI starter job
                    ↓
             normalized content pack
                    ↓
              questions + rubrics
                    ↓
     attempts → mastery → personalized guidance
```

Users never upload or manually enter question papers. A content operator may periodically load a reviewed pack with
`python -m src.content_pack --path <pack.json>`. The existing PDF pipeline remains available for authentic past-paper
content, but it is optional and outside the student flow.

## Runtime contract

Every runtime question needs:

- subject code and display name;
- topic, optional subtopic, and command word;
- question text and possible marks;
- one or more concise mark-scheme points.

The starter pack in `content/packs/starter_bank.json` is a small development fixture, not a replacement for reviewed
exam content. It allows the guidance, attempt, mastery, and weak-spot flows to be tested without PDF collection.

## Personalization loop

`GET /guidance/{user_id}?subject=` selects the next useful action. With no evidence, it recommends a diagnostic
question. With low mastery, it recommends an unseen question from the weakest topic/command-word cell. With stronger
evidence, it recommends continued review. The reason is returned with the recommendation so the UI can explain the
choice to the student.

## Human review boundary

For each new subject pack, a subject-aware reviewer approves a sample of topics, command words, marks, and rubrics.
That review is the quality gate; manually typing every question is not.
