import { useCallback, useEffect, useRef, useState } from 'react'
import { getHealth, resumeHITL, resumeHandoff, streamJourney } from './api'
import Layout from './components/Layout'
import SpecLoader from './components/SpecLoader'
import JourneyRunner from './components/JourneyRunner'
import StepTimeline from './components/StepTimeline'
import HITLPanel from './components/HITLPanel'
import HandoffForm from './components/HandoffForm'
import ContextViewer from './components/ContextViewer'
import MessageThread from './components/MessageThread'
import ResultSummary from './components/ResultSummary'
import AuthorView from './components/author/AuthorView'
import DiscoverView from './components/discover/DiscoverView'
import ChatView from './components/chat/ChatView'
import {
  ExecutionStatus,
  HealthResponse,
  RunRequest,
  RunResponse,
  SpecSummary,
  StepEvent,
  StepState,
} from './types'

type AppMode = 'run' | 'author' | 'discover' | 'chat'

export default function App() {
  const [mode, setMode] = useState<AppMode>('author')
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [status, setStatus] = useState<ExecutionStatus>('idle')
  const [spec, setSpec] = useState<SpecSummary | null>(null)
  const [specPath, setSpecPath] = useState('')
  const [steps, setSteps] = useState<StepState[]>([])
  const [result, setResult] = useState<RunResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [hitlLoading, setHitlLoading] = useState(false)
  const [handoffLoading, setHandoffLoading] = useState(false)

  const abortRef = useRef<AbortController | null>(null)

  // Check health on mount
  useEffect(() => {
    getHealth()
      .then(setHealth)
      .catch(() => setHealth(null))
  }, [])

  const handleSpecLoaded = useCallback((loadedSpec: SpecSummary, path: string) => {
    setSpec(loadedSpec)
    setSpecPath(path)
    setStatus('ready')
    setSteps([])
    setResult(null)
    setError(null)
  }, [])

  const handleRun = useCallback((request: RunRequest) => {
    // Reset state
    setStatus('running')
    setSteps([])
    setResult(null)
    setError(null)

    // Cancel any previous stream
    if (abortRef.current) {
      abortRef.current.abort()
    }

    // Start streaming
    const controller = streamJourney(
      request,
      // onStep
      (event: StepEvent) => {
        setSteps((prev) => {
          const existing = prev.find((s) => s.step_name === event.step_name)
          if (existing) {
            return prev.map((s) =>
              s.step_name === event.step_name
                ? { ...s, status: mapStatus(event.status), duration_ms: undefined, output_preview: event.output_preview }
                : s
            )
          }
          return [
            ...prev,
            {
              step_name: event.step_name || 'unknown',
              step_type: event.step_type || 'unknown',
              status: mapStatus(event.status),
              output_preview: event.output_preview,
            },
          ]
        })
      },
      // onResult
      (response: RunResponse) => {
        setResult(response)
        // Update steps with final data from traces
        setSteps(
          response.traces.map((t) => ({
            step_name: t.step_name,
            step_type: t.step_type,
            status: mapStatus(t.status),
            duration_ms: t.duration_ms,
            output_preview: t.output_preview,
          }))
        )
        if (response.status === 'waiting_hitl') {
          setStatus('waiting_hitl')
        } else if (response.status === 'failed') {
          setStatus('failed')
        } else {
          setStatus('completed')
        }
      },
      // onError
      (errMsg: string) => {
        setError(errMsg)
        setStatus('failed')
      }
    )

    abortRef.current = controller
  }, [])

  const handleHITLDecision = useCallback(
    async (approved: boolean, notes?: string) => {
      if (!result) return
      setHitlLoading(true)
      try {
        const updated = await resumeHITL(result.execution_id, approved, notes)
        setResult(updated)
        setStatus(updated.status === 'completed' ? 'completed' : 'failed')
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Resume failed')
      } finally {
        setHitlLoading(false)
      }
    },
    [result]
  )

  const handleHandoffSubmit = useCallback(
    async (formData: Record<string, unknown>) => {
      if (!result) return
      setHandoffLoading(true)
      try {
        const updated = await resumeHandoff(result.execution_id, formData)
        setResult(updated)
        // Update steps with new traces
        if (updated.traces) {
          setSteps(
            updated.traces.map((t) => ({
              step_name: t.step_name,
              step_type: t.step_type,
              status: mapStatus(t.status),
              duration_ms: t.duration_ms,
              output_preview: t.output_preview,
            }))
          )
        }
        if (updated.status === 'waiting_hitl' && updated.handoff_info) {
          setStatus('waiting_hitl')
        } else if (updated.status === 'waiting_hitl') {
          setStatus('waiting_hitl')
        } else if (updated.status === 'completed') {
          setStatus('completed')
        } else {
          setStatus('failed')
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Handoff resume failed')
      } finally {
        setHandoffLoading(false)
      }
    },
    [result]
  )

  const handleReset = useCallback(() => {
    setStatus('ready')
    setSteps([])
    setResult(null)
    setError(null)
  }, [])

  return (
    <Layout health={health}>
      {/* Mode Switcher */}
      <div className="flex items-center justify-center mb-8">
        <div className="inline-flex items-center bg-gray-100 dark:bg-surface-1 p-1 rounded-lg">
          <button
            onClick={() => setMode('author')}
            className={`px-4 py-2 rounded-md text-sm font-medium transition-all ${
              mode === 'author' ? 'bg-white dark:bg-surface-2 text-gray-900 dark:text-primary shadow-sm' : 'text-gray-600 dark:text-secondary hover:text-gray-900 dark:hover:text-primary'
            }`}
          >
            <span className="flex items-center gap-1.5">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
              </svg>
              Author
            </span>
          </button>
          <button
            onClick={() => setMode('discover')}
            className={`px-4 py-2 rounded-md text-sm font-medium transition-all ${
              mode === 'discover' ? 'bg-white dark:bg-surface-2 text-gray-900 dark:text-primary shadow-sm' : 'text-gray-600 dark:text-secondary hover:text-gray-900 dark:hover:text-primary'
            }`}
          >
            <span className="flex items-center gap-1.5">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
              </svg>
              Discover
            </span>
          </button>
          <button
            onClick={() => setMode('run')}
            className={`px-4 py-2 rounded-md text-sm font-medium transition-all ${
              mode === 'run' ? 'bg-white dark:bg-surface-2 text-gray-900 dark:text-primary shadow-sm' : 'text-gray-600 dark:text-secondary hover:text-gray-900 dark:hover:text-primary'
            }`}
          >
            <span className="flex items-center gap-1.5">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              Run
            </span>
          </button>
          <button
            onClick={() => setMode('chat')}
            className={`px-4 py-2 rounded-md text-sm font-medium transition-all ${
              mode === 'chat' ? 'bg-white dark:bg-surface-2 text-gray-900 dark:text-primary shadow-sm' : 'text-gray-600 dark:text-secondary hover:text-gray-900 dark:hover:text-primary'
            }`}
          >
            <span className="flex items-center gap-1.5">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
              </svg>
              Chat
            </span>
          </button>
        </div>
      </div>

      {/* Author Mode */}
      {mode === 'author' && <AuthorView />}

      {/* Discover Mode */}
      {mode === 'discover' && <DiscoverView />}

      {/* Chat Mode */}
      {mode === 'chat' && <ChatView specPath={specPath} />}

      {/* Run Mode */}
      {mode === 'run' && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
          {/* Left Panel — Controls */}
          <div className="lg:col-span-5 space-y-6">
            <SpecLoader onSpecLoaded={handleSpecLoaded} />

            {spec && (
              <JourneyRunner
                spec={spec}
                specPath={specPath}
                onRun={handleRun}
                disabled={status === 'running'}
              />
            )}

            {/* Reset button */}
            {(status === 'completed' || status === 'failed') && (
              <button
                onClick={handleReset}
                className="w-full py-2 text-sm text-gray-600 dark:text-secondary border border-gray-300 dark:border-border rounded-md hover:bg-gray-50 dark:hover:bg-surface-1 transition-colors"
              >
                Reset & Run Again
              </button>
            )}
          </div>

          {/* Right Panel — Execution Results */}
          <div className="lg:col-span-7 space-y-6">
            {/* Idle state */}
            {status === 'idle' && (
              <div className="flex items-center justify-center h-64 text-gray-400 dark:text-muted text-sm">
                <div className="text-center">
                  <svg className="w-12 h-12 mx-auto mb-3 text-gray-300 dark:text-muted" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M13 10V3L4 14h7v7l9-11h-7z" />
                  </svg>
                  <p>Load a spec and execute a journey to see results here.</p>
                </div>
              </div>
            )}

            {/* Ready state — spec loaded but not run */}
            {status === 'ready' && steps.length === 0 && !result && (
              <div className="flex items-center justify-center h-64 text-gray-400 dark:text-muted text-sm">
                <div className="text-center">
                  <svg className="w-12 h-12 mx-auto mb-3 text-forge-300 dark:text-accent/40" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  <p>Ready — hit <strong>Execute Journey</strong> to run.</p>
                </div>
              </div>
            )}

            {/* Running / Results */}
            {(status === 'running' || steps.length > 0 || result) && (
              <div className="space-y-6">
                {/* Result summary */}
                {result && <ResultSummary result={result} />}

                {/* Step timeline */}
                <StepTimeline steps={steps} />

                {/* Handoff Form (takes priority over HITL panel when both could apply) */}
                {status === 'waiting_hitl' && result?.handoff_info && (
                  <HandoffForm
                    handoffInfo={result.handoff_info}
                    onSubmit={handleHandoffSubmit}
                    loading={handoffLoading}
                  />
                )}

                {/* HITL Panel (only shown when no handoff form) */}
                {status === 'waiting_hitl' && result?.hitl_info && !result?.handoff_info && (
                  <HITLPanel
                    hitlInfo={result.hitl_info}
                    onDecision={handleHITLDecision}
                    loading={hitlLoading}
                  />
                )}

                {/* Messages */}
                {result && <MessageThread messages={result.messages} />}

                {/* Context data */}
                {result && Object.keys(result.context_data).length > 0 && (
                  <ContextViewer data={result.context_data} />
                )}
              </div>
            )}

            {/* Error */}
            {error && (
              <div className="p-4 bg-red-50 dark:bg-danger/10 border border-red-200 dark:border-danger/30 rounded-lg text-sm text-red-700 dark:text-danger animate-slide-in">
                <strong>Error:</strong> {error}
              </div>
            )}
          </div>
        </div>
      )}
    </Layout>
  )
}

function mapStatus(status?: string): StepState['status'] {
  switch (status) {
    case 'completed': return 'completed'
    case 'failed': return 'failed'
    case 'waiting_hitl': return 'hitl'
    case 'running': return 'running'
    default: return 'completed'
  }
}
