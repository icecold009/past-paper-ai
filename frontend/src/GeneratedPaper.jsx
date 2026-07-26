function sourceLabel(sourceType) {
  return sourceType === 'ai_generated' ? 'AI-generated weak-spot question' : 'Real past-paper question'
}

export default function GeneratedPaper({ paper, loading, error, onRetry, onBack }) {
  if (loading) return <p className="status-message">Building your weak-spot paper…</p>

  if (error) {
    return (
      <section className="panel paper-panel" aria-labelledby="paper-error-heading">
        <h2 id="paper-error-heading">Could not build the paper</h2>
        <div className="error-state" role="alert">
          <p>{error}</p>
          <button className="button button-secondary" type="button" onClick={onRetry}>Try again</button>
        </div>
        <button className="button button-quiet" type="button" onClick={onBack}>Back to mastery</button>
      </section>
    )
  }

  if (!paper) return null

  return (
    <section className="panel paper-panel" aria-labelledby="paper-heading">
      <div className="dashboard-heading">
        <div>
          <p className="eyebrow">Targeted practice</p>
          <h2 id="paper-heading">Weak-spot practice paper</h2>
          <p className="intro-copy">
            {paper.subject.name} · {paper.paper.toUpperCase()} · {paper.total_marks} marks selected toward a {paper.target_marks}-mark target
          </p>
        </div>
        <span className="subject-code">{paper.subject.code}</span>
      </div>

      <div className="paper-question-list">
        {paper.questions.map((question) => (
          <article className={`paper-question ${question.source_type}`} key={`${question.position}-${question.id}`}>
            <div className="paper-question-topline">
              <span className="eyebrow">Question {question.position}</span>
              <span className={`source-badge ${question.source_type}`}>{sourceLabel(question.source_type)}</span>
            </div>
            <div className="question-meta" aria-label="Question tags">
              {question.topic && <span className="tag">Topic: {question.topic}</span>}
              {question.command_word && <span className="tag">Command word: {question.command_word}</span>}
              <span className="marks-badge">{question.marks} marks</span>
            </div>
            <p className="question-text">{question.raw_text}</p>
            {question.source_type === 'ai_generated' && (
              <p className="paper-source-note">Generated for this weak topic/command-word cell; it is not from a past paper.</p>
            )}
          </article>
        ))}
      </div>

      <button className="button button-secondary" type="button" onClick={onBack}>Back to mastery</button>
    </section>
  )
}
