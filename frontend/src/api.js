const API_BASE_URL = import.meta.env?.VITE_API_BASE_URL || '/api'

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      Accept: 'application/json',
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      ...options.headers,
    },
    ...options,
  })

  let payload = null
  try {
    payload = await response.json()
  } catch {
    // Keep the HTTP status as the useful error when the server returns no JSON.
  }

  if (!response.ok) {
    const detail = typeof payload?.detail === 'string' ? payload.detail : `Request failed (${response.status})`
    throw new Error(detail)
  }

  return payload
}

export function getSubjects() {
  return request('/subjects')
}

export function getGuidance({ userId, subject }) {
  const params = new URLSearchParams({ subject })
  return request(`/guidance/${userId}?${params.toString()}`)
}

export function buildQuestionsPath({ subject, topic = '', commandWord = '' }) {
  const params = new URLSearchParams({ subject, limit: '100' })
  if (topic.trim()) params.set('topic', topic.trim())
  if (commandWord.trim()) params.set('command_word', commandWord.trim())
  return `/questions?${params.toString()}`
}

export function getQuestions(filters) {
  return request(buildQuestionsPath(filters))
}

export function getMastery({ userId, subject }) {
  const params = new URLSearchParams({ subject })
  return request(`/mastery/${userId}?${params.toString()}`)
}

export function submitAttempt({ userId, questionId, submittedAnswerText }) {
  return request('/attempts', {
    method: 'POST',
    body: JSON.stringify({
      user_id: userId,
      question_id: questionId,
      submitted_answer_text: submittedAnswerText,
    }),
  })
}

export function generateWeakSpotPaper({ userId, subject, paper, targetMarks }) {
  return request('/papers/generate', {
    method: 'POST',
    body: JSON.stringify({
      user_id: userId,
      subject,
      mode: 'weak_spot',
      ...(paper ? { paper } : {}),
      ...(targetMarks ? { target_marks: targetMarks } : {}),
    }),
  })
}
