function groupCells(cells) {
  const groups = new Map()

  for (const cell of cells) {
    const key = `${cell.topic}::${cell.command_word}`
    const existing = groups.get(key) || {
      key,
      topic: cell.topic,
      command_word: cell.command_word,
      subtopics: [],
      scores: [],
    }
    if (cell.subtopic && !existing.subtopics.includes(cell.subtopic)) {
      existing.subtopics.push(cell.subtopic)
    }
    if (cell.has_evidence) existing.scores.push(cell.score)
    groups.set(key, existing)
  }

  return [...groups.values()].map((cell) => ({
    ...cell,
    hasEvidence: cell.scores.length > 0,
    score: cell.scores.length ? Math.min(...cell.scores) : 0,
  }))
}

function statusForCell(cell) {
  if (!cell.hasEvidence) return { label: 'No evidence', className: 'score-none' }
  if (cell.score < 0.4) return { label: 'Needs practice', className: 'score-weak' }
  if (cell.score < 0.7) return { label: 'Developing', className: 'score-developing' }
  return { label: 'Strong', className: 'score-strong' }
}

function scoreLabel(cell) {
  return cell.hasEvidence ? `${Math.round(cell.score * 100)}%` : '—'
}

export default function MasteryDashboard({
  subject,
  cells,
  loading,
  error,
  questionLoading,
  questionError,
  onRetry,
  onRetryQuestion,
  onCellClick,
  onGeneratePaper,
  paperLoading,
}) {
  const groupedCells = groupCells(cells)
  const cellByKey = new Map(groupedCells.map((cell) => [cell.key, cell]))
  const topics = [...new Set(groupedCells.map((cell) => cell.topic))].sort()
  const commandWords = [...new Set(groupedCells.map((cell) => cell.command_word))].sort()
  const weakCells = groupedCells
    .filter((cell) => cell.hasEvidence)
    .sort((left, right) => left.score - right.score || left.topic.localeCompare(right.topic))
    .slice(0, 4)
  const weakestKeys = new Set(weakCells.map((cell) => cell.key))

  return (
    <section className="panel dashboard-panel" aria-labelledby="dashboard-heading">
      <div className="dashboard-heading">
        <div>
          <p className="eyebrow">Progress by subject</p>
          <h2 id="dashboard-heading">{subject?.name || 'Mastery dashboard'}</h2>
          <p className="intro-copy">Click any cell to practise that topic and command word.</p>
        </div>
        {subject && (
          <div className="dashboard-actions">
            <span className="subject-code">{subject.code}</span>
            <button className="button button-primary" type="button" onClick={onGeneratePaper} disabled={paperLoading}>
              {paperLoading ? 'Building paper…' : 'Generate weak-spot paper'}
            </button>
          </div>
        )}
      </div>

      {loading && <p className="status-message">Loading mastery data…</p>}
      {error && !loading && <div className="dashboard-error"><ErrorState message={error} onRetry={onRetry} /></div>}

      {!loading && !error && questionLoading && (
        <p className="status-message">Loading questions for this weak spot…</p>
      )}
      {!loading && !error && questionError && !questionLoading && (
        <div className="dashboard-error">
          <ErrorState message={questionError} onRetry={onRetryQuestion} />
        </div>
      )}

      {!loading && !error && !questionLoading && !questionError && !groupedCells.length && (
        <p className="empty-dashboard">No topic and command-word mastery cells are available for this subject yet.</p>
      )}

      {!loading && !error && !questionLoading && !questionError && groupedCells.length > 0 && (
        <>
          <section className="weak-spots" aria-labelledby="weak-spots-heading">
            <div className="section-heading-row">
              <h3 id="weak-spots-heading">Weak spots to revisit</h3>
              <span className="section-note">Lowest evidenced scores first</span>
            </div>
            {weakCells.length > 0 ? (
              <div className="weak-spot-list">
                {weakCells.map((cell) => (
                  <button
                    className="weak-spot-button"
                    key={cell.key}
                    type="button"
                    onClick={() => onCellClick(cell)}
                  >
                    <span><strong>{cell.topic}</strong> · {cell.command_word}</span>
                    <span className="weak-spot-score">{scoreLabel(cell)}</span>
                  </button>
                ))}
              </div>
            ) : (
              <p className="empty-dashboard">Complete an attempt to see evidenced weak spots here.</p>
            )}
          </section>

          <div className="heatmap-header">
            <h3 id="heatmap-heading">Topic × command word</h3>
            <div className="heatmap-legend" aria-label="Mastery score legend">
              <span><i className="legend-swatch score-weak" /> Needs practice</span>
              <span><i className="legend-swatch score-developing" /> Developing</span>
              <span><i className="legend-swatch score-strong" /> Strong</span>
              <span><i className="legend-swatch score-none" /> No evidence</span>
            </div>
          </div>
          <div
            className="heatmap"
            role="grid"
            aria-labelledby="heatmap-heading"
            style={{ gridTemplateColumns: `minmax(170px, 1.3fr) repeat(${commandWords.length}, minmax(115px, 1fr))` }}
          >
            <div className="heatmap-corner" role="columnheader">Topic / command word</div>
            {commandWords.map((commandWord) => (
              <div className="heatmap-column-label" key={commandWord} role="columnheader">{commandWord}</div>
            ))}
            {topics.map((topic) => (
              <div
                className="heatmap-row"
                key={topic}
                role="row"
                style={{ gridTemplateColumns: `minmax(170px, 1.3fr) repeat(${commandWords.length}, minmax(115px, 1fr))` }}
              >
                <div className="heatmap-row-label" role="rowheader">{topic}</div>
                {commandWords.map((commandWord) => {
                  const cell = cellByKey.get(`${topic}::${commandWord}`)
                  if (!cell) return <div className="heatmap-cell cell-unavailable" key={commandWord} role="gridcell">—</div>
                  const status = statusForCell(cell)
                  return (
                    <button
                      className={`heatmap-cell ${status.className}${weakestKeys.has(cell.key) ? ' weakest' : ''}`}
                      key={commandWord}
                      type="button"
                      role="gridcell"
                      title={`${topic} · ${commandWord}: ${status.label}. Click to practise.`}
                      aria-label={`${topic}, ${commandWord}: ${status.label}, score ${scoreLabel(cell)}. Click to practise.`}
                      onClick={() => onCellClick(cell)}
                    >
                      <strong>{scoreLabel(cell)}</strong>
                      <span>{status.label}</span>
                    </button>
                  )
                })}
              </div>
            ))}
          </div>
          <p className="heatmap-note">Cells with multiple subtopics use the lowest evidenced subtopic score, so a weak area is not hidden by a stronger neighbour.</p>
        </>
      )}
    </section>
  )
}

function ErrorState({ message, onRetry }) {
  return (
    <div className="error-state" role="alert">
      <p>{message}</p>
      {onRetry && <button className="button button-secondary" type="button" onClick={onRetry}>Try again</button>}
    </div>
  )
}
