# Mistake-review adaptation evidence

## Reference access

- Requested reference: Duolingo at `https://www.duolingo.com`, using the user's authenticated dedicated Chrome profile.
- Requested CDP endpoint: `http://127.0.0.1:9222`.
- Current official REA source: `morluto/rea` `README.md`, `docs/installation.md`, and `docs/browser-observation.md` were read through the GitHub connector at `main` commit `1b97b0f3707b1cf78ac98bd4ae81638b33cc286f`. The installation docs specify `npx rea-agents setup` and the latest package runner; the browser docs distinguish passive CDP observation from Playwright scenarios.
- REA runtime: `npx --yes --cache "$env:TEMP\rea-npm-cache" rea-agents@latest --help` succeeded and reported `rea@6.5.0`. This enabled a direct REA CLI invocation in this task.
- Duolingo reference target: requested origin `https://www.duolingo.com`, requested CDP endpoint `http://127.0.0.1:9222`. REA call `rea list-browser-targets http://127.0.0.1:9222 --allowed-origins https://www.duolingo.com --format json` returned `provider_unavailable / endpoint_unreachable`. A separate endpoint request returned `No connection could be made because the target machine actively refused it. (127.0.0.1:9222)`.
- Duolingo result: target discovery failed, so there is no target ID, page inspection, screenshot, observation window, bundle analysis, or captured session. The user handled authentication; this task did not inspect credentials or authentication values.
- Successful implementation capture: REA `capture-browser-scenario` ran against the local synthetic app at `http://127.0.0.1:5173` using provider-owned Chromium `155.0.8059.79`. Evidence ID `ev_c50c11e19f1fb95c01ad196a2b494991374d4e61cca553d226ad3cce170acd1a`; 17 explicit actions; complete capture; all steps completed; cleanup terminated the owned browser. The fixture covered queue, fresh retry, feedback, history reveal, second item, completion, and reopen. It is evidence about this implementation only, not Duolingo.
- The curated REA receipt, full accessibility snapshots, and selected screenshots are in this directory. The raw CLI output SHA-256 is recorded in `mistake-review-ui-rea-receipt.json`. The browser scenario used a Vite middleware fixture and did not exercise the backend API.

## Evidence-to-design mapping

| Journey behavior | Evidence available | Past Paper AI implementation |
| --- | --- | --- |
| Communicate the queue and session scope | User requested scope/progress communication. No reference UI was captured. | The queue shows the count and each question's subject/source context; the session shows `item / total` progress. |
| Keep previous answers hidden before retry | User explicitly required a fresh retry before revealing prior answers or feedback. | Queue/session responses contain source question context and the current retry draft, but omit the original answer and feedback. The reveal endpoint returns them only after a submitted retry in that session. |
| Revisit incorrect items | User required explicit incorrect/partial evidence or user confirmation. Existing `Attempt` records carry grading status and marks; existing signed-owner helpers scope student records. | Queue eligibility requires a non-retry `graded`/`corrected` attempt with recorded marks below possible marks, or a separate owner-confirmed review row. Disputed, unscored, full-credit, and self-assessed attempts do not qualify by inference. |
| Separate retry feedback from continuation | User required feedback, next-item, resolved, and revisit behavior; no Duolingo-specific differences were observed. | Retry answers are appended with `self_assessed` provenance and no marks. Previous feedback is a separate reveal action; resolved/revisit is an explicit next action. |
| Leave and resume | User requested leave/resume behavior to be investigated. The reference behavior remains unknown. Existing `PracticeSession` and `PracticeAnswer` support persisted session/draft state. | Review drafts and active session items are saved and owner-scoped. An active-session endpoint supports resuming the same session. |
| Complete or reopen | User requested explicit completion and reopen behavior. No reference completion state was observed. | A session completes only after each retry has an explicit resolved/revisit state. Resolved items can be reopened and returned to the queue. |

The REA-specific rows above are not claims about Duolingo's observed interface. The local REA capture demonstrates only that the Past Paper AI implementation renders and transitions through its synthetic journey. The implementation follows the user's stated requirements and existing Past Paper AI ownership/provenance boundaries.

## Local implementation capture

The successful scenario captured these states with synthetic API responses:

| State | Capture |
| --- | --- |
| Queue | [Screenshot](mistake-review-ui-queue.png) |
| Fresh question | [Screenshot](mistake-review-ui-fresh-question.png) |
| Fresh answer before submission | [Screenshot](mistake-review-ui-fresh-answer.png) |
| Retry feedback | [Screenshot](mistake-review-ui-feedback.png) |
| Earlier answer and feedback after reveal | [Screenshot](mistake-review-ui-history-revealed.png) |
| Next item | [Screenshot](mistake-review-ui-next-question.png) |
| Completion | [Screenshot](mistake-review-ui-completion.png) |
| Reopened queue | [Screenshot](mistake-review-ui-reopened-queue.png) |

The [REA receipt](mistake-review-ui-rea-receipt.json) contains the evidence ID, provider/browser identity, step statuses, complete accessibility snapshots, image hashes, source-output digest, and REA completeness/limitations. These captures exercise the frontend with a local Vite middleware fixture; backend behavior is verified independently by the API tests.

## Unknowns and deliberate differences

- Unknown: Duolingo's actual queue count, queue ordering, wording, pre-answer information, feedback timing, next-item mechanics, completion screen, and leaving/resuming behavior.
- Unknown: any scheduling, mastery, or learning algorithm. No algorithm was inferred from articles or from the requested behavior.
- Deliberate differences: this is a Cambridge source-question retry flow with source paper context, explicit state controls, append-only linked attempts, and self-assessment where there is no trusted score. It does not copy Duolingo questions, illustrations, wording, branding, streaks, points, or XP.
- No automatic AI grading or new student-data provider was enabled. Existing `/attempts` grader approval behavior remains unchanged.

## Content and verification boundary

- Tests use synthetic 9618 records. The repository's `content/packs/starter_bank.json` is explicitly described as starter content and not reviewed exam-preparation content; it was not treated as reviewed evidence.
- No real CAIE question or mark scheme was included in the new tests. The repository backlog still records the real QP/MS and manual-review gates.
- Local synthetic browser interaction was captured with REA and is retained in this directory. Duolingo comparison, real content, and live reference interaction remain unverified until the authorized dedicated CDP endpoint is reachable.
