import { ExecutionSummary, GhostwriteRequest, GhostwriteResponse, HealthResponse, RunRequest, RunResponse, SpecDetail, SpecSummary, StepEvent } from './types'

// Local dev proxies /api -> localhost:8000 (see vite.config.ts). Anywhere else
// (the GitHub Pages demo at anjesh.ai/FlowStrix/) talks to the deployed Modal
// backend cross-origin — the FastAPI app sends permissive CORS.
const isLocal =
  typeof location !== 'undefined' &&
  (location.hostname === 'localhost' || location.hostname === '127.0.0.1')
const BASE = isLocal ? '/api' : 'https://anjeshdubey--flowstrix-demo-web.modal.run/api'

async function fetchJSON<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }))
    throw new Error(error.detail || `HTTP ${response.status}`)
  }
  return response.json()
}

// --- Endpoints ---

export async function getHealth(): Promise<HealthResponse> {
  return fetchJSON(`${BASE}/health`)
}

export async function getSpec(specPath: string): Promise<SpecSummary> {
  return fetchJSON(`${BASE}/specs/${specPath}`)
}

export async function getSpecDetail(specPath: string): Promise<SpecDetail> {
  return fetchJSON(`${BASE}/discover/${specPath}`)
}

export async function getSpecYaml(specPath: string): Promise<{ path: string; yaml_content: string }> {
  return fetchJSON(`${BASE}/yaml/${specPath}`)
}

export async function runJourney(request: RunRequest & { engine?: string; thread_id?: string }): Promise<RunResponse & { thread_id?: string }> {
  return fetchJSON(`${BASE}/run`, {
    method: 'POST',
    body: JSON.stringify(request),
  })
}

export async function resumeHITL(
  executionId: string,
  approved: boolean,
  notes?: string
): Promise<RunResponse> {
  return fetchJSON(`${BASE}/executions/${executionId}/resume`, {
    method: 'POST',
    body: JSON.stringify({ approved, notes }),
  })
}

export async function resumeHandoff(
  executionId: string,
  formData: Record<string, unknown>
): Promise<RunResponse> {
  return fetchJSON(`${BASE}/executions/${executionId}/resume_handoff`, {
    method: 'POST',
    body: JSON.stringify({ form_data: formData }),
  })
}

// --- Execution History ---

export async function listExecutions(): Promise<ExecutionSummary[]> {
  return fetchJSON(`${BASE}/executions`)
}

export async function getExecution(executionId: string): Promise<RunResponse> {
  return fetchJSON(`${BASE}/executions/${executionId}`)
}

// --- Specs Management ---

export interface SavedSpec {
  path: string
  agent: string
  persona_name: string
  journey_count: number
}

export async function listSpecs(): Promise<SavedSpec[]> {
  return fetchJSON(`${BASE}/specs`)
}

export async function saveSpec(filename: string, yaml_content: string): Promise<{ path: string; saved: boolean; message: string }> {
  return fetchJSON(`${BASE}/specs`, {
    method: 'POST',
    body: JSON.stringify({ filename, yaml_content }),
  })
}

// --- File Upload ---

export interface UploadResponse {
  filename: string
  content: string
  char_count: number
  truncated: boolean
}

export async function uploadFile(file: File): Promise<UploadResponse> {
  const formData = new FormData()
  formData.append('file', file)

  const response = await fetch(`${BASE}/upload`, {
    method: 'POST',
    body: formData,
  })
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }))
    throw new Error(error.detail || `HTTP ${response.status}`)
  }
  return response.json()
}

// --- Ghostwriter ---

export async function ghostwrite(request: GhostwriteRequest): Promise<GhostwriteResponse> {
  return fetchJSON(`${BASE}/ghostwrite`, {
    method: 'POST',
    body: JSON.stringify(request),
  })
}

// --- SSE Streaming ---

export function streamJourney(
  request: RunRequest,
  onStep: (event: StepEvent) => void,
  onResult: (result: RunResponse) => void,
  onError: (error: string) => void
): AbortController {
  const controller = new AbortController()

  fetch(`${BASE}/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
    signal: controller.signal,
  })
    .then(async (response) => {
      if (!response.ok) {
        const err = await response.json().catch(() => ({ detail: 'Stream failed' }))
        onError(err.detail || `HTTP ${response.status}`)
        return
      }

      const reader = response.body?.getReader()
      if (!reader) {
        onError('No response body')
        return
      }

      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        let currentEvent = ''
        for (const line of lines) {
          if (line.startsWith('event: ')) {
            currentEvent = line.slice(7).trim()
          } else if (line.startsWith('data: ')) {
            const data = line.slice(6)
            try {
              const parsed = JSON.parse(data)
              if (currentEvent === 'step') {
                onStep(parsed as StepEvent)
              } else if (currentEvent === 'result') {
                onResult(parsed as RunResponse)
              } else if (currentEvent === 'error') {
                onError(parsed.output_preview || 'Execution failed')
              }
            } catch {
              // Skip malformed JSON
            }
            currentEvent = ''
          }
        }
      }
    })
    .catch((err) => {
      if (err.name !== 'AbortError') {
        onError(err.message)
      }
    })

  return controller
}
