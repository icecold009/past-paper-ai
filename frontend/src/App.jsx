import { useEffect, useMemo, useState } from 'react'
import {
  confirmMistakeForReview,
  createMistakeSession,
  generateWeakSpotPaper,
  getActiveMistakeSession,
  getGuidance,
  getMastery,
  getMistakeQueue,
  getQuestions,
  getSubjects,
  revealMistakeHistory,
  saveMistakeDraft,
  submitAttempt,
  submitMistakeRetry,
  submitMistakeSession,
  updateMistakeReviewState,
} from './api.js'
import GeneratedPaper from './GeneratedPaper.jsx'
import MasteryDashboard from './MasteryDashboard.jsx'
import { MistakeCompletion, MistakeFeedback, MistakeQueue, MistakeQuestion } from './MistakeReview.jsx'

const DEVELOPMENT_USER_ID = 1

function newIdempotencyKey() {
  return globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`
}

function LoadingState({ message }) {
  return <p className="status-message">{message}</p>
}

function ErrorState({ message, onRetry }) {
  return (
    <div className="error-state" role="alert">
      <p>{message}</p>
      {onRetry && (
        <button className="button button-secondary" type="button" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  )
}

function AppHeader({ screen, onStartOver, onOpenDashboard, selectedSubject }) {
  return (
    <header className="app-header">
      <div>
        <p className="eyebrow">Cambridge practice</p>
        <h1>Past Paper AI</h1>
      </div>
      <div className="header-actions">
        <span className="user-badge">Development user #{DEVELOPMENT_USER_ID}</span>
        {screen !== 'dashboard' && selectedSubject && (
          <button className="button button-quiet" type="button" onClick={onOpenDashboard}>
            View mastery
          </button>
        )}
        {screen !== 'picker' && (
          <button className="button button-quiet" type="button" onClick={onStartOver}>
            Change subject
          </button>
        )}
      </div>
    </header>
  )
}

function StepIndicator({ screen }) {
  const steps = screen.startsWith('mistake-') || screen === 'mistakes'
    ? [
      ['picker', 'Choose'],
      ['mistakes', 'Mistakes'],
      ['mistake-question', 'Retry'],
      ['mistake-feedback', 'Reflect'],
      ['mistake-complete', 'Done'],
    ]
    : [
      ['picker', 'Choose'],
      ['dashboard', 'Progress'],
      ['paper', 'Paper'],
      ['question', 'Answer'],
      ['feedback', 'Review'],
    ]
  const activeIndex = steps.findIndex(([id]) => id === screen)

  return (
    <nav className="step-indicator" aria-label="Practice steps">
      {steps.map(([id, label], index) => (
        <span className={index <= activeIndex ? 'step active' : 'step'} key={id}>
          <span className="step-number">{index + 1}</span>
          {label}
        </span>
      ))}
    </nav>
  )
}

function GuidanceCard({ guidance, loading, error, onRetry, onStart }) {
  if (loading) return <p className="status-message">Building your next study step…</p>
  if (error) return <ErrorState message={error} onRetry={onRetry} />
  if (!guidance) return null

  return (
    <section className="guidance-card" aria-labelledby="guidance-heading">
      <p className="eyebrow">Personalized guidance</p>
      <h3 id="guidance-heading">Your next best step</h3>
      <p>{guidance.explanation || guidance.summary}</p>
      {guidance.recommendation?.chapter && (
        <p className="guidance-detail">
          <strong>{guidance.recommendation.chapter.name}</strong> · {guidance.recommendation.activity_type || 'targeted practice'}
        </p>
      )}
      {guidance.recommendation?.decision_source === 'typesafe' ? (
        <p className="guidance-source">Adaptive selection</p>
      ) : guidance.recommendation ? (
        <p className="guidance-source">Recommended from your evidence</p>
      ) : null}
      {guidance.recommendation && (
        <button className="button button-primary" type="button" onClick={() => onStart(guidance.recommendation)}>
          Start recommended question
        </button>
      )}
    </section>
  )
}

function SubjectPicker({
  subjects,
  loading,
  error,
  selectedSubject,
  topic,
  guidance,
  guidanceLoading,
  guidanceError,
  mistakeQueue,
  mistakeQueueLoading,
  mistakeQueueError,
  activeMistakeError,
  activeMistakeLoading,
  activeMistakeSession,
  onSubjectChange,
  onTopicChange,
  onStart,
  onStartGuidance,
  onOpenDashboard,
  onOpenMistakes,
  onResumeMistakes,
  onRetry,
  onRetryGuidance,
  onRetryMistakes,
}) {
  return (
    <section className="panel picker-panel" aria-labelledby="picker-heading">
      <p className="eyebrow">Start a practice set</p>
      <h2 id="picker-heading">Choose what to practise</h2>
      <p className="intro-copy">Pick a subject, then optionally narrow the questions to a topic.</p>

      {loading && <LoadingState message="Loading available subjects…" />}
      {error && <ErrorState message={error} onRetry={onRetry} />}

      {!loading && !error && (
        <form className="picker-form" onSubmit={onStart}>
          <label htmlFor="subject">Subject</label>
          <select id="subject" value={selectedSubject} onChange={(event) => onSubjectChange(event.target.value)}>
            <option value="">Select a subject</option>
            {subjects.map((subject) => (
              <option key={subject.code} value={subject.code}>
                {subject.code} — {subject.name}
              </option>
            ))}
          </select>

          <label htmlFor="topic">Topic filter <span className="optional">(optional)</span></label>
          <input
            id="topic"
            type="text"
            value={topic}
            onChange={(event) => onTopicChange(event.target.value)}
            placeholder="For example, Data representation"
          />
          <p className="field-help">The topic must match a reviewed topic in the database.</p>

          <div className="picker-actions">
            <button className="button button-primary" type="submit" disabled={!selectedSubject}>
              Find questions
            </button>
            <button className="button button-secondary" type="button" onClick={onOpenDashboard} disabled={!selectedSubject}>
              View mastery
            </button>
          </div>
        </form>
      )}

      {selectedSubject && (
        <>
          <GuidanceCard
            guidance={guidance}
            loading={guidanceLoading}
            error={guidanceError}
            onRetry={onRetryGuidance}
            onStart={onStartGuidance}
          />
          {selectedSubject === '9618' && <section className="review-launch-card" aria-labelledby="review-launch-heading">
            <div>
              <p className="eyebrow">Mistake practice</p>
              <h3 id="review-launch-heading">Retry questions you missed or flagged</h3>
              <p>Only recorded partial attempts and questions you explicitly add to review are included.</p>
            </div>
            <div className="review-launch-actions">
              <span className="review-launch-count">
                {mistakeQueueLoading ? 'Loading queue…' : activeMistakeLoading ? 'Checking saved review…' : `${mistakeQueue?.items?.length || 0} waiting`}
              </span>
              <button className="button button-secondary" type="button" onClick={onOpenMistakes} disabled={mistakeQueueLoading}>
                Open mistake review
              </button>
              {activeMistakeSession && (
                <button className="button button-primary" type="button" onClick={onResumeMistakes}>
                  Resume saved review
                </button>
              )}
            </div>
            {(mistakeQueueError || activeMistakeError) && (
              <div className="review-launch-error" role="alert">
                <p>{mistakeQueueError || activeMistakeError}</p>
                <button className="button button-secondary" type="button" onClick={onRetryMistakes}>Retry queue</button>
              </div>
            )}
          </section>}
        </>
      )}
    </section>
  )
}

function QuestionScreen({ question, questionNumber, totalQuestions, answer, loading, error, onAnswerChange, onSubmit }) {
  return (
    <section className="panel question-panel" aria-labelledby="question-heading">
      <div className="question-topline">
        <div>
          <p className="eyebrow">Question {questionNumber} of {totalQuestions}</p>
          <p className="source-context">
            {question.subject.code} · {question.paper.toUpperCase()} · {question.session} {question.year} · Variant {question.variant}
          </p>
        </div>
        <span className="marks-badge">{question.marks ?? '—'} marks</span>
      </div>

      <h2 id="question-heading">
        {question.question_number}{question.sub_label ? ` ${question.sub_label}` : ''}
      </h2>
      <div className="question-meta" aria-label="Question tags">
        {question.topic && <span className="tag">Topic: {question.topic}</span>}
        {question.subtopic && <span className="tag">Subtopic: {question.subtopic}</span>}
        {question.command_word && <span className="tag">Command word: {question.command_word}</span>}
      </div>
      <p className="question-text">{question.raw_text}</p>

      <form className="answer-form" onSubmit={onSubmit}>
        <label htmlFor="answer">Your answer</label>
        <textarea
          id="answer"
          value={answer}
          onChange={(event) => onAnswerChange(event.target.value)}
          placeholder="Write your answer here…"
          rows={9}
          disabled={loading}
          aria-describedby="answer-help"
        />
        <p id="answer-help" className="field-help">Your answer is sent to the backend for mark-scheme-aware grading.</p>
        {error && <ErrorState message={error} />}
        <button className="button button-primary" type="submit" disabled={loading || !answer.trim()}>
          {loading ? 'Submitting…' : 'Submit answer'}
        </button>
      </form>
    </section>
  )
}

function PointList({ title, points, tone }) {
  return (
    <section className={`point-group ${tone}`} aria-labelledby={`${tone}-points-heading`}>
      <h3 id={`${tone}-points-heading`}>{title}</h3>
      {points.length > 0 ? (
        <ul>
          {points.map((point, index) => <li key={`${point}-${index}`}>{point}</li>)}
        </ul>
      ) : (
        <p className="empty-points">None recorded.</p>
      )}
    </section>
  )
}

function FeedbackScreen({ result, question, isLastQuestion, canAddReview, onNext, onMarkForReview, markingForReview, markedForReview, markReviewError }) {
  const percentage = result.marks_possible > 0 ? Math.round((result.marks_earned / result.marks_possible) * 100) : 0

  return (
    <section className="panel feedback-panel" aria-labelledby="feedback-heading">
      <p className="eyebrow">Grading complete</p>
      <h2 id="feedback-heading">Review your answer</h2>
      <p className="feedback-question">Question {question.question_number}{question.sub_label ? ` ${question.sub_label}` : ''}</p>

      <div className="score-card" aria-label={`You earned ${result.marks_earned} out of ${result.marks_possible} marks`}>
        <div>
          <span className="score-label">Score</span>
          <strong>{result.marks_earned} / {result.marks_possible}</strong>
        </div>
        <span className="score-percent">{percentage}%</span>
      </div>

      <div className="points-grid">
        <PointList title="Points hit" points={result.points_hit} tone="points-hit" />
        <PointList title="Points missed" points={result.points_missed} tone="points-missed" />
      </div>

      <section className="feedback-copy" aria-labelledby="feedback-text-heading">
        <h3 id="feedback-text-heading">Feedback</h3>
        <p>{result.feedback}</p>
      </section>

      <button className="button button-primary" type="button" onClick={onNext}>
        {isLastQuestion ? 'Choose another question set' : 'Next question'}
      </button>
      {canAddReview && (
        <>
          {markedForReview ? (
            <p className="review-confirmation" role="status">This attempt is in your mistake-review queue.</p>
          ) : (
            <button className="button button-secondary feedback-review-button" type="button" onClick={onMarkForReview} disabled={markingForReview}>
              {markingForReview ? 'Adding to review…' : 'Add this attempt to mistake review'}
            </button>
          )}
          {markReviewError && <ErrorState message={markReviewError} />}
        </>
      )}
    </section>
  )
}

export default function App() {
  const [screen, setScreen] = useState('picker')
  const [subjects, setSubjects] = useState([])
  const [subjectsLoading, setSubjectsLoading] = useState(true)
  const [subjectsError, setSubjectsError] = useState('')
  const [selectedSubject, setSelectedSubject] = useState('')
  const [topic, setTopic] = useState('')
  const [commandWord, setCommandWord] = useState('')
  const [mastery, setMastery] = useState(null)
  const [masteryLoading, setMasteryLoading] = useState(false)
  const [masteryError, setMasteryError] = useState('')
  const [questions, setQuestions] = useState([])
  const [questionIndex, setQuestionIndex] = useState(0)
  const [questionsLoading, setQuestionsLoading] = useState(false)
  const [questionsError, setQuestionsError] = useState('')
  const [answer, setAnswer] = useState('')
  const [attemptLoading, setAttemptLoading] = useState(false)
  const [attemptError, setAttemptError] = useState('')
  const [gradingResult, setGradingResult] = useState(null)
  const [guidance, setGuidance] = useState(null)
  const [guidanceLoading, setGuidanceLoading] = useState(false)
  const [guidanceError, setGuidanceError] = useState('')
  const [generatedPaper, setGeneratedPaper] = useState(null)
  const [paperLoading, setPaperLoading] = useState(false)
  const [paperError, setPaperError] = useState('')
  const [mistakeQueue, setMistakeQueue] = useState(null)
  const [mistakeQueueLoading, setMistakeQueueLoading] = useState(false)
  const [mistakeQueueError, setMistakeQueueError] = useState('')
  const [activeMistakeSession, setActiveMistakeSession] = useState(null)
  const [activeMistakeError, setActiveMistakeError] = useState('')
  const [activeMistakeLoading, setActiveMistakeLoading] = useState(false)
  const [mistakeSession, setMistakeSession] = useState(null)
  const [mistakeIndex, setMistakeIndex] = useState(0)
  const [mistakeAnswer, setMistakeAnswer] = useState('')
  const [mistakeSelfAssessment, setMistakeSelfAssessment] = useState('partly')
  const [mistakeRetry, setMistakeRetry] = useState(null)
  const [mistakeHistory, setMistakeHistory] = useState(null)
  const [mistakeError, setMistakeError] = useState('')
  const [mistakeLoading, setMistakeLoading] = useState(false)
  const [mistakeRevealing, setMistakeRevealing] = useState(false)
  const [pendingMistakeRetry, setPendingMistakeRetry] = useState(null)
  const [markingForReview, setMarkingForReview] = useState(false)
  const [markReviewError, setMarkReviewError] = useState('')
  const [markedAttemptIds, setMarkedAttemptIds] = useState(() => new Set())

  const question = questions[questionIndex]
  const isLastQuestion = questionIndex >= questions.length - 1
  const mistakeItem = mistakeSession?.items?.[mistakeIndex]
  const selectedSubjectName = useMemo(
    () => subjects.find((subject) => subject.code === selectedSubject)?.name,
    [selectedSubject, subjects],
  )

  async function loadSubjects() {
    setSubjectsLoading(true)
    setSubjectsError('')
    try {
      setSubjects(await getSubjects())
    } catch (error) {
      setSubjectsError(error.message || 'Could not load subjects.')
    } finally {
      setSubjectsLoading(false)
    }
  }

  async function loadQuestions({
    subjectCode = selectedSubject,
    topicFilter = topic,
    commandWordFilter = commandWord,
    chapterId = null,
  } = {}) {
    setQuestionsLoading(true)
    setQuestionsError('')
    try {
      const loadedQuestions = await getQuestions({
        subject: subjectCode,
        topic: topicFilter,
        commandWord: commandWordFilter,
        chapterId,
      })
      if (!loadedQuestions.length) {
        throw new Error('No reviewed questions match these filters. Try removing the topic filter.')
      }
      setSelectedSubject(subjectCode)
      setTopic(topicFilter)
      setCommandWord(commandWordFilter)
      setQuestions(loadedQuestions)
      setQuestionIndex(0)
      setAnswer('')
      setGradingResult(null)
      setAttemptError('')
      setScreen('question')
    } catch (error) {
      setQuestionsError(error.message || 'Could not load questions.')
    } finally {
      setQuestionsLoading(false)
    }
  }

  async function loadMastery(subjectCode = selectedSubject) {
    setMasteryLoading(true)
    setMasteryError('')
    try {
      setMastery(await getMastery({ userId: DEVELOPMENT_USER_ID, subject: subjectCode }))
    } catch (error) {
      setMasteryError(error.message || 'Could not load mastery data.')
    } finally {
      setMasteryLoading(false)
    }
  }

  async function loadGuidance(subjectCode = selectedSubject) {
    if (!subjectCode) return
    setGuidanceLoading(true)
    setGuidanceError('')
    try {
      setGuidance(await getGuidance({ userId: DEVELOPMENT_USER_ID, subject: subjectCode }))
    } catch (error) {
      setGuidanceError(error.message || 'Could not load personalized guidance.')
    } finally {
      setGuidanceLoading(false)
    }
  }

  async function loadMistakeQueue(subjectCode = selectedSubject) {
    if (!subjectCode) return
    setMistakeQueueLoading(true)
    setMistakeQueueError('')
    try {
      setMistakeQueue(await getMistakeQueue({ userId: DEVELOPMENT_USER_ID, subject: subjectCode }))
    } catch (error) {
      setMistakeQueueError(error.message || 'Could not load your mistake-review queue.')
    } finally {
      setMistakeQueueLoading(false)
    }
  }

  async function loadActiveMistake(subjectCode = selectedSubject) {
    if (!subjectCode) return
    setActiveMistakeLoading(true)
    setActiveMistakeError('')
    try {
      setActiveMistakeSession(await getActiveMistakeSession({ userId: DEVELOPMENT_USER_ID, subject: subjectCode }))
    } catch (error) {
      setActiveMistakeSession(null)
      setActiveMistakeError(error.message || 'Could not check for a saved review.')
    } finally {
      setActiveMistakeLoading(false)
    }
  }

  useEffect(() => {
    loadSubjects()
  }, [])

  useEffect(() => {
    if (selectedSubject) {
      loadGuidance(selectedSubject)
      loadMistakeQueue(selectedSubject)
      loadActiveMistake(selectedSubject)
    } else {
      setGuidance(null)
      setMistakeQueue(null)
      setActiveMistakeSession(null)
      setActiveMistakeError('')
    }
  }, [selectedSubject])

  async function handleStart(event) {
    event.preventDefault()
    if (selectedSubject) {
      await loadQuestions({ subjectCode: selectedSubject, topicFilter: topic, commandWordFilter: '' })
    }
  }

  async function handleStartGuidance(recommendation) {
    await loadQuestions({
      subjectCode: selectedSubject,
      topicFilter: recommendation.topic || '',
      commandWordFilter: recommendation.command_word || '',
      chapterId: recommendation.chapter?.id || null,
    })
  }

  async function handleOpenDashboard() {
    if (!selectedSubject) return
    setQuestionsError('')
    setScreen('dashboard')
    await loadMastery(selectedSubject)
  }

  async function handleDrillIntoCell(cell) {
    setQuestionsError('')
    await loadQuestions(
      {
        subjectCode: selectedSubject,
        topicFilter: cell.topic,
        commandWordFilter: cell.command_word,
      },
    )
  }

  async function handleGeneratePaper() {
    if (!selectedSubject) return
    setPaperLoading(true)
    setPaperError('')
    setGeneratedPaper(null)
    setScreen('paper')
    try {
      setGeneratedPaper(await generateWeakSpotPaper({ userId: DEVELOPMENT_USER_ID, subject: selectedSubject }))
    } catch (error) {
      setPaperError(error.message || 'Could not generate a weak-spot paper.')
    } finally {
      setPaperLoading(false)
    }
  }

  async function handleSubmit(event) {
    event.preventDefault()
    if (!question || !answer.trim()) return

    setAttemptLoading(true)
    setAttemptError('')
    try {
      const result = await submitAttempt({
        userId: DEVELOPMENT_USER_ID,
        questionId: question.id,
        submittedAnswerText: answer.trim(),
      })
      setGradingResult(result)
      setScreen('feedback')
    } catch (error) {
      setAttemptError(error.message || 'Could not submit this answer.')
    } finally {
      setAttemptLoading(false)
    }
  }

  async function handleMarkForReview() {
    if (!gradingResult?.attempt_id) return
    setMarkingForReview(true)
    setMarkReviewError('')
    try {
      await confirmMistakeForReview({ userId: DEVELOPMENT_USER_ID, attemptId: gradingResult.attempt_id })
      setMarkedAttemptIds((current) => new Set(current).add(gradingResult.attempt_id))
      await loadMistakeQueue(selectedSubject)
    } catch (error) {
      setMarkReviewError(error.message || 'Could not add this attempt to review.')
    } finally {
      setMarkingForReview(false)
    }
  }

  async function handleOpenMistakes() {
    setScreen('mistakes')
    setMistakeError('')
    await Promise.all([loadMistakeQueue(selectedSubject), loadActiveMistake(selectedSubject)])
  }

  async function handleRetryMistakes() {
    setMistakeError('')
    await Promise.all([loadMistakeQueue(selectedSubject), loadActiveMistake(selectedSubject)])
  }

  function showMistakeSession(review) {
    if (!review?.items?.length) {
      setMistakeSession(review)
      setMistakeError('This session has no review items.')
      setScreen('mistakes')
      return
    }
    const index = review.items.findIndex((item) => item.review_state === 'open' || item.review_state === 'reopened')
    const selectedIndex = index >= 0 ? index : 0
    const item = review.items[selectedIndex]
    setMistakeSession(review)
    setActiveMistakeSession(review.state === 'active' || review.state === 'draft' ? review : null)
    setMistakeIndex(selectedIndex)
    setMistakeAnswer(item.answer_text || '')
    setMistakeSelfAssessment(item.retry_self_assessment || 'partly')
    setMistakeRetry(item.retry_attempt_id
      ? { attempt_id: item.retry_attempt_id, self_assessment: item.retry_self_assessment || 'partly' }
      : null)
    setMistakeHistory(null)
    setMistakeError('')
    setPendingMistakeRetry(null)
    setScreen(item.retry_attempt_id ? 'mistake-feedback' : 'mistake-question')
  }

  async function handleStartMistakeSession() {
    if (activeMistakeSession) {
      showMistakeSession(activeMistakeSession)
      return
    }
    const attemptIds = mistakeQueue?.items?.map((item) => item.original_attempt_id) || []
    if (!attemptIds.length) return
    setMistakeLoading(true)
    setMistakeError('')
    try {
      const review = await createMistakeSession({
        userId: DEVELOPMENT_USER_ID,
        subject: selectedSubject,
        attemptIds,
        idempotencyKey: newIdempotencyKey(),
      })
      showMistakeSession(review)
    } catch (error) {
      setMistakeError(error.message || 'Could not start a mistake review.')
    } finally {
      setMistakeLoading(false)
    }
  }

  async function handleSubmitMistake(event) {
    event.preventDefault()
    if (!mistakeSession || !mistakeItem || !mistakeAnswer.trim()) return
    const submission = pendingMistakeRetry || {
      answerText: mistakeAnswer.trim(),
      selfAssessment: mistakeSelfAssessment,
      idempotencyKey: newIdempotencyKey(),
    }
    setPendingMistakeRetry(submission)
    setMistakeLoading(true)
    setMistakeError('')
    try {
      const retry = await submitMistakeRetry({
        userId: DEVELOPMENT_USER_ID,
        sessionId: mistakeSession.id,
        reviewId: mistakeItem.review_id,
        answerText: submission.answerText,
        selfAssessment: submission.selfAssessment,
        idempotencyKey: submission.idempotencyKey,
      })
      const updated = {
        ...mistakeSession,
        completed_count: mistakeSession.items.filter((item, index) => index === mistakeIndex || item.retry_attempt_id).length,
        items: mistakeSession.items.map((item, index) => index === mistakeIndex
          ? {
            ...item,
            answer_text: submission.answerText,
            answer_status: 'submitted',
            retry_attempt_id: retry.attempt_id,
            retry_self_assessment: retry.self_assessment,
          }
          : item),
      }
      setMistakeSession(updated)
      setActiveMistakeSession(updated)
      setMistakeAnswer(submission.answerText)
      setMistakeRetry(retry)
      setMistakeHistory(null)
      setPendingMistakeRetry(null)
      setScreen('mistake-feedback')
    } catch (error) {
      setMistakeError(error.message || 'Could not save your retry. Try submitting it again.')
    } finally {
      setMistakeLoading(false)
    }
  }

  async function handleSaveAndLeaveMistakes() {
    if (!mistakeSession || !mistakeItem) {
      setScreen('picker')
      return
    }
    if (pendingMistakeRetry) {
      setMistakeError('Retry the same submission before leaving so it is not recorded twice.')
      return
    }
    setMistakeLoading(true)
    setMistakeError('')
    try {
      const saved = await saveMistakeDraft({
        userId: DEVELOPMENT_USER_ID,
        sessionId: mistakeSession.id,
        reviewId: mistakeItem.review_id,
        answerText: mistakeAnswer,
      })
      setMistakeSession(saved)
      setActiveMistakeSession(saved)
      setScreen('picker')
    } catch (error) {
      setMistakeError(error.message || 'Could not save this draft.')
    } finally {
      setMistakeLoading(false)
    }
  }

  async function handleRevealMistake() {
    if (!mistakeSession || !mistakeItem) return
    setMistakeRevealing(true)
    setMistakeError('')
    try {
      setMistakeHistory(await revealMistakeHistory({
        userId: DEVELOPMENT_USER_ID,
        sessionId: mistakeSession.id,
        reviewId: mistakeItem.review_id,
      }))
    } catch (error) {
      setMistakeError(error.message || 'Could not load the earlier attempt.')
    } finally {
      setMistakeRevealing(false)
    }
  }

  async function handleAdvanceMistake(nextState) {
    if (!mistakeSession || !mistakeItem) return
    setMistakeLoading(true)
    setMistakeError('')
    try {
      await updateMistakeReviewState({
        userId: DEVELOPMENT_USER_ID,
        reviewId: mistakeItem.review_id,
        state: nextState,
      })
      const updated = {
        ...mistakeSession,
        items: mistakeSession.items.map((item, index) => index === mistakeIndex
          ? { ...item, review_state: nextState }
          : item),
      }
      setMistakeSession(updated)
      const nextIndex = mistakeIndex + 1
      if (nextIndex < updated.items.length) {
        const nextItem = updated.items[nextIndex]
        setMistakeIndex(nextIndex)
        setMistakeAnswer(nextItem.answer_text || '')
        setMistakeSelfAssessment(nextItem.retry_self_assessment || 'partly')
        setMistakeRetry(nextItem.retry_attempt_id
          ? { attempt_id: nextItem.retry_attempt_id, self_assessment: nextItem.retry_self_assessment || 'partly' }
          : null)
        setMistakeHistory(null)
        setPendingMistakeRetry(null)
        setScreen(nextItem.retry_attempt_id ? 'mistake-feedback' : 'mistake-question')
      } else {
        const completed = await submitMistakeSession({ userId: DEVELOPMENT_USER_ID, sessionId: updated.id })
        setMistakeSession(completed)
        setActiveMistakeSession(null)
        setScreen('mistake-complete')
        await loadMistakeQueue(selectedSubject)
      }
    } catch (error) {
      setMistakeError(error.message || 'Could not update this review item.')
    } finally {
      setMistakeLoading(false)
    }
  }

  async function handleReopenMistake(reviewId) {
    setMistakeLoading(true)
    setMistakeError('')
    try {
      await updateMistakeReviewState({ userId: DEVELOPMENT_USER_ID, reviewId, state: 'reopened' })
      setActiveMistakeSession(null)
      await loadMistakeQueue(selectedSubject)
      setScreen('mistakes')
    } catch (error) {
      setMistakeError(error.message || 'Could not reopen this review item.')
    } finally {
      setMistakeLoading(false)
    }
  }

  function handleNext() {
    if (isLastQuestion) {
      setScreen('picker')
      setQuestions([])
      setGradingResult(null)
      return
    }
    setQuestionIndex((index) => index + 1)
    setAnswer('')
    setGradingResult(null)
    setAttemptError('')
    setScreen('question')
  }

  function handleStartOver() {
    if (screen === 'mistake-question') {
      handleSaveAndLeaveMistakes()
      return
    }
    if (screen.startsWith('mistake-') && mistakeSession?.state === 'active') {
      setActiveMistakeSession(mistakeSession)
    }
    setScreen('picker')
    setQuestionsError('')
    setAttemptError('')
    setMasteryError('')
    setGradingResult(null)
    setGeneratedPaper(null)
    setPaperError('')
  }

  return (
    <div className="app-shell">
      <AppHeader
        screen={screen}
        onStartOver={handleStartOver}
        onOpenDashboard={handleOpenDashboard}
        selectedSubject={selectedSubject}
      />
      <main>
        <StepIndicator screen={screen} />
        {screen === 'picker' && (
          <>
            <SubjectPicker
              subjects={subjects}
              loading={subjectsLoading}
              error={subjectsError}
              selectedSubject={selectedSubject}
              topic={topic}
              guidance={guidance}
              guidanceLoading={guidanceLoading}
              guidanceError={guidanceError}
              mistakeQueue={mistakeQueue}
              mistakeQueueLoading={mistakeQueueLoading}
              mistakeQueueError={mistakeQueueError}
              activeMistakeError={activeMistakeError}
              activeMistakeLoading={activeMistakeLoading}
              activeMistakeSession={activeMistakeSession}
              onSubjectChange={setSelectedSubject}
              onTopicChange={setTopic}
              onStart={handleStart}
              onStartGuidance={handleStartGuidance}
              onOpenDashboard={handleOpenDashboard}
              onOpenMistakes={handleOpenMistakes}
              onResumeMistakes={() => showMistakeSession(activeMistakeSession)}
              onRetryMistakes={handleRetryMistakes}
              onRetry={loadSubjects}
              onRetryGuidance={() => loadGuidance(selectedSubject)}
            />
            {questionsLoading && <LoadingState message={`Loading ${selectedSubjectName || 'subject'} questions…`} />}
            {questionsError && !questionsLoading && (
              <ErrorState
                message={questionsError}
                onRetry={() => loadQuestions({ subjectCode: selectedSubject, topicFilter: topic, commandWordFilter: '' })}
              />
            )}
          </>
        )}
        {screen === 'dashboard' && (
          <MasteryDashboard
            subject={mastery?.subject || subjects.find((subject) => subject.code === selectedSubject)}
            cells={mastery?.cells || []}
            loading={masteryLoading}
            error={masteryError}
            questionLoading={questionsLoading}
            questionError={questionsError}
            onRetry={() => loadMastery(selectedSubject)}
            onRetryQuestion={() => loadQuestions({
              subjectCode: selectedSubject,
              topicFilter: topic,
              commandWordFilter: commandWord,
            })}
            onCellClick={handleDrillIntoCell}
            onGeneratePaper={handleGeneratePaper}
            paperLoading={paperLoading}
          />
        )}
        {screen === 'paper' && (
          <GeneratedPaper
            paper={generatedPaper}
            loading={paperLoading}
            error={paperError}
            onRetry={handleGeneratePaper}
            onBack={handleOpenDashboard}
          />
        )}
        {screen === 'question' && question && (
          <QuestionScreen
            question={question}
            questionNumber={questionIndex + 1}
            totalQuestions={questions.length}
            answer={answer}
            loading={attemptLoading}
            error={attemptError}
            onAnswerChange={setAnswer}
            onSubmit={handleSubmit}
          />
        )}
        {screen === 'question' && !question && (
          questionsLoading
            ? <LoadingState message="Loading questions…" />
            : <ErrorState
              message={questionsError || 'No question is currently available.'}
              onRetry={() => loadQuestions({
                subjectCode: selectedSubject,
                topicFilter: topic,
                commandWordFilter: commandWord,
              })}
            />
        )}
        {screen === 'feedback' && gradingResult && question && (
          <FeedbackScreen
            result={gradingResult}
            question={question}
            isLastQuestion={isLastQuestion}
            canAddReview={question.subject.code === '9618'}
            onNext={handleNext}
            onMarkForReview={handleMarkForReview}
            markingForReview={markingForReview}
            markedForReview={markedAttemptIds.has(gradingResult.attempt_id)}
            markReviewError={markReviewError}
          />
        )}
        {screen === 'mistakes' && (
          <MistakeQueue
            queue={mistakeQueue}
            activeSession={activeMistakeSession}
            loading={mistakeQueueLoading}
            error={mistakeQueueError || activeMistakeError || mistakeError}
            starting={mistakeLoading}
            onRetry={handleRetryMistakes}
            onStart={handleStartMistakeSession}
            onResume={() => showMistakeSession(activeMistakeSession)}
          />
        )}
        {screen === 'mistake-question' && (
          <MistakeQuestion
            item={mistakeItem}
            position={mistakeIndex + 1}
            total={mistakeSession?.total_count || 0}
            answer={mistakeAnswer}
            selfAssessment={mistakeSelfAssessment}
            saving={mistakeLoading}
            editingLocked={Boolean(pendingMistakeRetry)}
            error={mistakeError}
            onAnswerChange={setMistakeAnswer}
            onSelfAssessmentChange={setMistakeSelfAssessment}
            onSubmit={handleSubmitMistake}
            onSaveAndLeave={handleSaveAndLeaveMistakes}
          />
        )}
        {screen === 'mistake-feedback' && (
          <MistakeFeedback
            item={mistakeItem}
            position={mistakeIndex + 1}
            total={mistakeSession?.total_count || 0}
            retry={mistakeRetry}
            history={mistakeHistory}
            revealing={mistakeRevealing}
            error={mistakeError}
            advancing={mistakeLoading}
            onReveal={handleRevealMistake}
            onResolve={() => handleAdvanceMistake('resolved')}
            onRevisit={() => handleAdvanceMistake('revisit')}
          />
        )}
        {screen === 'mistake-complete' && (
          <MistakeCompletion
            session={mistakeSession}
            loading={mistakeLoading}
            error={mistakeError}
            onRetry={() => setMistakeError('')}
            onReopen={handleReopenMistake}
          />
        )}
      </main>
    </div>
  )
}
