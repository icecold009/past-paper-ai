import { useEffect, useMemo, useState } from 'react'
import { generateWeakSpotPaper, getMastery, getQuestions, getSubjects, submitAttempt } from './api.js'
import GeneratedPaper from './GeneratedPaper.jsx'
import MasteryDashboard from './MasteryDashboard.jsx'

const DEVELOPMENT_USER_ID = 1

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
  const steps = [
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

function SubjectPicker({ subjects, loading, error, selectedSubject, topic, onSubjectChange, onTopicChange, onStart, onOpenDashboard, onRetry }) {
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

function FeedbackScreen({ result, question, isLastQuestion, onNext }) {
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
  const [generatedPaper, setGeneratedPaper] = useState(null)
  const [paperLoading, setPaperLoading] = useState(false)
  const [paperError, setPaperError] = useState('')

  const question = questions[questionIndex]
  const isLastQuestion = questionIndex >= questions.length - 1
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
  } = {}) {
    setQuestionsLoading(true)
    setQuestionsError('')
    try {
      const loadedQuestions = await getQuestions({
        subject: subjectCode,
        topic: topicFilter,
        commandWord: commandWordFilter,
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

  useEffect(() => {
    loadSubjects()
  }, [])

  async function handleStart(event) {
    event.preventDefault()
    if (selectedSubject) {
      await loadQuestions({ subjectCode: selectedSubject, topicFilter: topic, commandWordFilter: '' })
    }
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
              onSubjectChange={setSelectedSubject}
              onTopicChange={setTopic}
              onStart={handleStart}
              onOpenDashboard={handleOpenDashboard}
              onRetry={loadSubjects}
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
            onNext={handleNext}
          />
        )}
      </main>
    </div>
  )
}
