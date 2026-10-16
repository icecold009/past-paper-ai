function ReviewError({ message, onRetry }) {
  if (!message) return null
  return (
    <div className="error-state" role="alert">
      <p>{message}</p>
      {onRetry && <button className="button button-secondary" type="button" onClick={onRetry}>Try again</button>}
    </div>
  )
}

function QuestionContext({ question }) {
  return (
    <>
      <p className="source-context">
        {question.subject.code} · {question.paper.toUpperCase()} · {question.session} {question.year} · Variant {question.variant}
      </p>
      <div className="question-meta" aria-label="Question tags">
        {question.topic && <span className="tag">Topic: {question.topic}</span>}
        {question.subtopic && <span className="tag">Subtopic: {question.subtopic}</span>}
        {question.command_word && <span className="tag">Command word: {question.command_word}</span>}
      </div>
    </>
  )
}

export function MistakeQueue({
  queue,
  activeSession,
  loading,
  error,
  starting,
  onRetry,
  onStart,
  onResume,
}) {
  const items = queue?.items || []

  return (
    <section className="panel mistake-panel" aria-labelledby="mistake-queue-heading">
      <p className="eyebrow">Review recorded mistakes</p>
      <h2 id="mistake-queue-heading">A short retry set</h2>
      <p className="intro-copy">
        This queue uses partial or incorrect scored attempts and questions you chose to revisit. Previous answers and feedback stay hidden until you submit a fresh retry.
      </p>
      {loading && <p className="status-message" role="status">Loading your review queue…</p>}
      <ReviewError message={error} onRetry={onRetry} />

      {!loading && !error && activeSession && (
        <div className="review-resume-card">
          <h3>Review in progress</h3>
          <p>{activeSession.completed_count} of {activeSession.total_count} retries submitted. Your saved answers are ready to resume.</p>
          <button className="button button-primary" type="button" onClick={onResume}>Resume review</button>
        </div>
      )}

      {!loading && !error && items.length === 0 && !activeSession && (
        <p className="empty-dashboard" role="status">No questions are waiting for review. Partial or incorrect scored attempts and questions you explicitly flag will appear here.</p>
      )}

      {!loading && !error && items.length > 0 && (
        <>
          <div className="mistake-queue-summary" aria-live="polite">
            <strong>{items.length} {items.length === 1 ? 'question' : 'questions'}</strong>
            <span>· one subject · original question context included</span>
          </div>
          <ul className="mistake-queue-list">
            {items.map((item) => (
              <li className="mistake-queue-item" key={item.original_attempt_id}>
                <div>
                  <strong>{item.question.subject.code} · {item.question.question_number}{item.question.sub_label ? ` ${item.question.sub_label}` : ''}</strong>
                  <p>{item.question.topic || 'Question review'} · {item.question.paper.toUpperCase()} · {item.question.session} {item.question.year}</p>
                  <span className="review-source-label">
                    {item.source === 'user_confirmed' ? 'You marked this for review' : 'Recorded partial or incorrect attempt'}
                    {item.state === 'reopened' && ' · reopened'}
                    {item.state === 'revisit' && ' · revisit'}
                  </span>
                </div>
                <span className="review-retry-count">{item.retry_count} {item.retry_count === 1 ? 'retry' : 'retries'}</span>
              </li>
            ))}
          </ul>
          <button className="button button-primary" type="button" onClick={onStart} disabled={starting || Boolean(activeSession)}>
            {starting ? 'Preparing review…' : activeSession ? 'Resume the active review above' : `Start ${items.length}-question review`}
          </button>
          <p className="field-help review-privacy-note">The original answer and feedback are not shown before you try again.</p>
        </>
      )}
    </section>
  )
}

export function MistakeQuestion({
  item,
  position,
  total,
  answer,
  selfAssessment,
  saving,
  editingLocked,
  error,
  onAnswerChange,
  onSelfAssessmentChange,
  onSubmit,
  onSaveAndLeave,
}) {
  if (!item) return <section className="panel mistake-panel"><p role="status">Loading this review item…</p></section>
  const { question } = item

  return (
    <section className="panel question-panel mistake-question-panel" aria-labelledby="mistake-question-heading">
      <div className="mistake-progress-row">
        <p className="eyebrow">Mistake review · Question {position} of {total}</p>
        <span className="review-progress" aria-label={`${position} of ${total} questions`}>{position} / {total}</span>
      </div>
      <QuestionContext question={question} />
      <div className="mistake-reason">
        {item.source === 'user_confirmed' ? 'You chose to revisit this attempt.' : 'A previous scored attempt did not receive full marks.'}
        <span> Your earlier answer and feedback are hidden for now.</span>
      </div>
      <h2 id="mistake-question-heading">{question.question_number}{question.sub_label ? ` ${question.sub_label}` : ''}</h2>
      <p className="question-text">{question.raw_text}</p>

      <form className="answer-form" onSubmit={onSubmit}>
        <label htmlFor="mistake-answer">Try the question again</label>
        <textarea
          id="mistake-answer"
          value={answer}
          onChange={(event) => onAnswerChange(event.target.value)}
          placeholder="Write a fresh answer before viewing your earlier attempt…"
          rows={8}
          disabled={saving || editingLocked}
          aria-describedby="mistake-answer-help"
        />
        <p id="mistake-answer-help" className="field-help">This retry is saved as a new attempt and is not automatically graded.</p>
        <label htmlFor="mistake-self-assessment">After writing your retry, how did it feel?</label>
        <select
          id="mistake-self-assessment"
          value={selfAssessment}
          onChange={(event) => onSelfAssessmentChange(event.target.value)}
          disabled={saving || editingLocked}
        >
          <option value="got_it">I can explain it now</option>
          <option value="partly">I understand part of it</option>
          <option value="still_unsure">I am still unsure</option>
        </select>
        <p className="field-help">Self-assessment only. It does not change your marks or mastery.</p>
        <ReviewError message={error} />
        <div className="mistake-actions">
          <button className="button button-primary" type="submit" disabled={saving || !answer.trim()}>
            {saving ? 'Saving retry…' : editingLocked ? 'Retry the same submission' : 'Submit retry'}
          </button>
          <button className="button button-secondary" type="button" onClick={onSaveAndLeave} disabled={saving || editingLocked}>
            Save and leave
          </button>
        </div>
      </form>
    </section>
  )
}

export function MistakeFeedback({
  item,
  position,
  total,
  retry,
  history,
  revealing,
  error,
  advancing,
  onReveal,
  onResolve,
  onRevisit,
}) {
  if (!item || !retry) return <section className="panel mistake-panel"><p role="status">Loading retry feedback…</p></section>
  const assessmentLabels = {
    got_it: 'I can explain it now',
    partly: 'I understand part of it',
    still_unsure: 'I am still unsure',
  }

  return (
    <section className="panel feedback-panel mistake-feedback-panel" aria-labelledby="mistake-feedback-heading">
      <p className="eyebrow">Retry saved · Question {position} of {total}</p>
      <h2 id="mistake-feedback-heading">How the retry felt</h2>
      <p className="self-assessment-result"><strong>Self-assessment:</strong> {assessmentLabels[retry.self_assessment]}</p>
      <p className="field-help">This is your reflection, not a score or a mastery update.</p>
      {!history && (
        <>
          <ReviewError message={error} onRetry={onReveal} />
          <button className="button button-secondary" type="button" onClick={onReveal} disabled={revealing}>
            {revealing ? 'Loading earlier attempt…' : 'Reveal my earlier answer and feedback'}
          </button>
        </>
      )}
      {history && (
        <section className="mistake-history" aria-labelledby="mistake-history-heading">
          <h3 id="mistake-history-heading">Earlier attempt</h3>
          {history.marks_earned !== null && history.marks_possible !== null && (
            <p className="review-score">Recorded score: {history.marks_earned} / {history.marks_possible}</p>
          )}
          <div className="review-answer-copy">
            <h4>Your earlier answer</h4>
            <p>{history.original_answer_text}</p>
          </div>
          {history.points_hit.length > 0 && <PointList title="Points recorded" points={history.points_hit} />}
          {history.points_missed.length > 0 && <PointList title="Points missed" points={history.points_missed} />}
          {history.feedback && <div className="feedback-copy"><h4>Earlier feedback</h4><p>{history.feedback}</p></div>}
          {history.retries.length > 0 && (
            <div className="review-answer-copy">
              <h4>Your retry</h4>
              <p>{history.retries[history.retries.length - 1].answer_text}</p>
            </div>
          )}
        </section>
      )}
      <div className="review-state-actions">
        <button className="button button-secondary" type="button" onClick={onRevisit} disabled={advancing}>
          Revisit later
        </button>
        <button className="button button-primary" type="button" onClick={onResolve} disabled={advancing}>
          {advancing ? 'Saving…' : position === total ? 'Resolve and finish' : 'Resolve and continue'}
        </button>
      </div>
    </section>
  )
}

function PointList({ title, points }) {
  return (
    <section className="review-points">
      <h4>{title}</h4>
      <ul>{points.map((point, index) => <li key={`${point}-${index}`}>{point}</li>)}</ul>
    </section>
  )
}

export function MistakeCompletion({ session, loading, error, onRetry, onReopen }) {
  return (
    <section className="panel mistake-panel" aria-labelledby="mistake-completion-heading">
      <p className="eyebrow">Review complete</p>
      <h2 id="mistake-completion-heading">You reached the end of this set</h2>
      <p className="intro-copy">{session?.completed_count || 0} of {session?.total_count || 0} retries saved. Revisit items remain in your queue; resolved items can be reopened below.</p>
      <ReviewError message={error} onRetry={onRetry} />
      <ul className="mistake-queue-list">
        {(session?.items || []).map((item) => (
          <li className="mistake-queue-item" key={item.review_id}>
            <div>
              <strong>{item.question.question_number}{item.question.sub_label ? ` ${item.question.sub_label}` : ''}</strong>
              <p>{item.question.topic || 'Question review'} · {item.review_state}</p>
            </div>
            {item.review_state === 'resolved' && (
              <button className="button button-secondary" type="button" onClick={() => onReopen(item.review_id)} disabled={loading}>
                Reopen
              </button>
            )}
          </li>
        ))}
      </ul>
      {loading && <p className="status-message" role="status">Updating review…</p>}
      <p className="completion-note">Your retry answers remain linked to the original attempt. Self-assessments do not change marks or mastery.</p>
    </section>
  )
}
