import { useCallback, useRef, useState } from 'react'
import { resumeHITL, resumeHandoff, streamJourney } from '../api'
import { ExecutionStatus, RunRequest, RunResponse, SpecSummary, StepEvent, StepState } from '../types'

export function useAgentExecution() {
  const [status, setStatus] = useState<ExecutionStatus>('idle')
  const [spec, setSpec] = useState<SpecSummary | null>(null)
  const [specPath, setSpecPath] = useState('')
  const [steps, setSteps] = useState<StepState[]>([])
  const [result, setResult] = useState<RunResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [hitlLoading, setHitlLoading] = useState(false)
  const [handoffLoading, setHandoffLoading] = useState(false)

  const abortRef = useRef<AbortController | null>(null)

  const handleSpecLoaded = useCallback((loadedSpec: SpecSummary, path: string) => {
    setSpec(loadedSpec)
    setSpecPath(path)
    setStatus('ready')
    setSteps([])
    setResult(null)
    setError(null)
  }, [])

  const handleRun = useCallback((request: RunRequest) => {
    setStatus('running')
    setSteps([])
    setResult(null)
    setError(null)

    if (abortRef.current) {
      abortRef.current.abort()
    }

    const controller = streamJourney(
      request,
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
      (response: RunResponse) => {
        setResult(response)
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
        if (updated.status === 'waiting_hitl') {
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

  return {
    status,
    spec,
    specPath,
    steps,
    result,
    error,
    hitlLoading,
    handoffLoading,
    handleSpecLoaded,
    handleRun,
    handleHITLDecision,
    handleHandoffSubmit,
    handleReset,
  }
}

export type AgentExecution = ReturnType<typeof useAgentExecution>

export function mapStatus(status?: string): StepState['status'] {
  switch (status) {
    case 'completed': return 'completed'
    case 'failed': return 'failed'
    case 'waiting_hitl': return 'hitl'
    case 'running': return 'running'
    default: return 'completed'
  }
}
