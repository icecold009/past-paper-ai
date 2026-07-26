# UI/UX Design Brief

## 1. Status

This is the proposed design direction for the future student application. The current repository is CLI-only, so none of the visual tokens or screens below should be described as implemented.

- Reviewed against repository: 2026-07-26
- Primary product context: Cambridge Grades 8–12 school learning, with chapter-level weakness support rather than generic AI chat
- Design goal: make structure, marks, feedback, and progress understandable at a glance
- Accessibility target: WCAG 2.2 AA intent, verified during implementation with automated and manual checks

## 2. Experience principles

1. Focus over decoration: the question and answer are the main event.
2. Evidence over confidence: show marks possible, marks earned, and feedback provenance separately.
3. Calm urgency: support timed practice without making the interface stressful.
4. Progressive disclosure: keep setup simple, reveal detailed marking points on review.
5. Explainability: show why a subject/chapter is recommended and what evidence supports it.
6. Traceability: where useful, expose subject, paper, year, session, and variant context.
7. Recovery: never make a lost answer feel like the user’s fault.
8. Inclusive by default: keyboard, zoom, contrast, reduced motion, and screen readers are first-class requirements.

## 3. Visual personality

The visual language should feel like a well-organized study desk: quiet, precise, warm enough to be inviting, and clear enough to support long sessions. Avoid noisy gradients, achievement confetti, excessive animations, and gamification that competes with exam thinking.

The interface should feel like a personal Cambridge study coach and school learning workspace—not like a general-purpose AI answer box. The product should lead with “what should I work on next?” rather than “ask anything.”

## 4. Typography

### Primary typeface

- Preferred: Inter, with a system sans-serif fallback.
- Fallback stack: `Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`.

### Monospace typeface

- Use a readable system monospace for code, pseudocode, extracted metadata, and technical diagnostics.
- Do not render normal prose in monospace.

### Type scale

| Token | Size | Use |
|---|---:|---|
| `display` | 2.25–2.75rem | landing/dashboard headline, sparingly |
| `h1` | 1.75–2rem | page title |
| `h2` | 1.25–1.5rem | section title |
| `h3` | 1.05–1.15rem | card/question group |
| `body` | 1rem | default reading size |
| `small` | 0.875rem | metadata and helper text |
| `caption` | 0.75rem | compact labels only |

Use a line height of approximately 1.5 for question prose and no smaller than 0.875rem for essential information. Equations, code, and long extracted text may need their own rendering rules.

## 5. Color system

These tokens are a proposed starting point and must be checked for contrast in both light and dark themes if dark mode is shipped.

```text
--ink-950:       #142033   primary text and headings
--ink-700:       #425166   secondary text
--ink-500:       #718096   muted metadata
--paper-50:      #FBFAF7   app background
--surface-0:     #FFFFFF   cards and inputs
--line-200:      #E4E8ED   borders and dividers
--teal-700:      #087F83   primary action and positive progress
--teal-100:      #D8F1EF   selected/positive background
--blue-700:      #2456A6   links and informational state
--blue-100:      #E3ECFF   informational background
--amber-700:     #9A5B00   caution and pending review
--amber-100:     #FFF0CF   caution background
--red-700:       #B42318   destructive/error state
--red-100:       #FDE3E1   error background
```

Color must never be the only indicator. Pair status colors with text, icons, or patterns.

## 6. Layout and spacing

- Desktop content width: approximately 1100–1240px with generous side gutters.
- Reading column for questions: approximately 680–760px to avoid long lines.
- Persistent practice metadata rail: marks, progress, timer, and save state.
- Base spacing unit: 4px; common spacing values: 8, 12, 16, 24, 32, 48.
- Border radius: 8px for controls and cards; use larger radius only for prominent containers.
- Shadows should be subtle and supplement borders rather than define every surface.

Suggested responsive breakpoints:

- compact: under 640px;
- tablet: 640–959px;
- desktop: 960px and above.

On compact screens, move metadata into a readable top bar or disclosure panel and keep the answer field full width.

## 7. Component direction

### Buttons

- Primary: filled teal, one dominant action per region.
- Secondary: outlined or low-emphasis surface.
- Destructive: red only for irreversible actions.
- Disabled: visibly disabled but still readable; explain why when not obvious.
- Every icon-only button needs an accessible name and a tooltip is supplementary, not the label.

### Cards and panels

Use cards to group setup, diagnosis, feedback, and progress—not every sentence. A question should feel like a reading surface first, with marks and controls aligned consistently.

The dashboard is the product’s highest-leverage screen. It should answer three questions immediately:

1. Which subject or chapter needs attention?
2. Why has it been identified?
3. What is the smallest useful activity I can do now?

Show Grade 8–12/Cambridge stage, current subjects, a private weakness-support summary, confidence/evidence count, and one clear next action. Use supportive language such as “needs practice” or “developing” rather than labeling a student as weak.

### Diagnostic and chapter support

- Explain the purpose and expected time before a baseline begins.
- Show chapter coverage and distinguish checked, developing, strong, and not-yet-known states.
- Let students open a chapter view containing a short explanation/help action followed by targeted practice.
- Make the recommendation reason visible but concise.
- Never make a student feel publicly ranked or permanently defined by an early result.

### Question block

The block should display:

- source context such as `9618 · Paper 1 · May/June 2024` where appropriate;
- question number and sub-label;
- question text with preserved paragraph structure;
- marks possible adjacent to the relevant unit;
- answer area;
- save/submission state.

Nested labels such as `(a)(i)` must remain visually and semantically nested rather than flattened into ambiguous text.

### Tags

Topic, subtopic, command word, and difficulty should be compact chips with text labels. A tag pending review should say so; do not style an AI inference as a verified fact.

### Tables

Use tables for paper metadata, review queues, and detailed progress where repeated columns matter. On small screens, provide a stacked/card alternative rather than forcing horizontal scrolling for essential actions.

## 8. Practice screen composition

```text
┌──────────────────────────────────────────────────────────┐
│ Grade 10 · Computer Science   Chapter: Data Representation │
│ Recommended because: 2 recent attempts below target       │
│ Question 3 of 12   6 marks   Save                         │
├───────────────────────────────┬──────────────────────────┤
│                               │ Progress                 │
│  Question text                │ 3 / 12                   │
│  (a) ...                      │ Marks: 6                  │
│      (i) ...                 │ Timer (optional)          │
│                               │                          │
│  Answer field                │                          │
│                               │                          │
│  Back             Save  Next │                          │
└───────────────────────────────┴──────────────────────────┘
```

The layout is a guide, not a requirement for a literal two-column implementation. The question must remain usable when the side rail collapses.

## 9. Feedback and progress visuals

- Use a simple earned/possible fraction, for example `4 / 6`.
- A horizontal progress bar must include a text value.
- Recommendation cards should include target chapter, evidence count, confidence, and a short reason.
- Marking points can use met/partial/missed rows with explanatory text.
- Topic progress should show attempt count and recency to avoid false certainty.
- Chapter progress should distinguish “not enough evidence” from “needs practice.”
- Use charts only when they answer a clear question; a small table may be better than a decorative graph.

## 10. Content and tone

Use direct, respectful copy:

- “Saved locally” / “Submitting…” / “Submitted” rather than vague spinner-only states.
- “No reviewed questions match these filters” rather than “Nothing found”.
- “This marking scheme is not available yet” rather than implying a grading failure is the student’s fault.
- “This chapter is recommended because…” rather than unexplained AI-generated suggestions.
- “You have not practised this chapter enough to estimate it yet” rather than a premature weak label.
- “Report an issue with this question” for incorrect text, marks, or tags.

Avoid praise that feels automated or judgmental. Feedback should be specific and actionable.

## 11. Accessibility requirements

- All controls keyboard reachable in logical order.
- Visible focus indicator with sufficient contrast.
- Semantic headings and landmarks.
- Labels and instructions associated with inputs programmatically.
- Error messages connected to the relevant field.
- Minimum target size suitable for touch interaction.
- No essential information conveyed by color alone.
- Text remains usable at 200% zoom without loss of actions.
- Long questions and mark-scheme points reflow without horizontal clipping.
- Respect `prefers-reduced-motion`.
- Screen-reader announcement for save, submit, and grading state changes.
- Verify contrast for text, controls, disabled states, charts, and focus rings.

Automated checks are not sufficient: perform keyboard-only, screen-reader, zoom, and rendered-layout checks before release.

## 12. Visual QA checklist

- Check compact, tablet, and desktop widths.
- Check long question text, nested subquestions, `[12]` marks, and missing marks.
- Check empty, loading, error, pending-review, and completed states.
- Check dark mode only if it is explicitly supported.
- Check focus order and focus visibility.
- Check a session after refresh and after simulated network failure.
- Check tables with long subject names and source filenames.
- Check generated-paper content does not overflow or expose raw formatting unexpectedly.

## 13. Open design decisions

- Whether dark mode ships in the first frontend release.
- Whether the timer is optional, fixed, or configurable by session mode.
- Whether equations and diagrams need a dedicated renderer.
- How much source metadata a student sees by default.
- Whether detailed mark-scheme points are expanded automatically or on request.
