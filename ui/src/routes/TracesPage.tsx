import { useEffect, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import { Activity, Loader2 } from 'lucide-react'
import { getExecution, listExecutions } from '../api'
import { ExecutionSummary, RunResponse } from '../types'
import { mapStatus } from '../hooks/useAgentExecution'
import ResultSummary from '../components/ResultSummary'
import StepTimeline from '../components/StepTimeline'
import { AgentWorkspaceContext } from './AgentWorkspace'

const STATUS_DOT: Record<string, string> = {
  completed: 'bg-success',
  failed: 'bg-danger',
  waiting_hitl: 'bg-warning',
  running: 'bg-accent',
}

export default function TracesPage() {
  const { agentPath } = useOutletContext<AgentWorkspaceContext>()
  const [executions, setExecutions] = useState<ExecutionSummary[]>([])
  const [loadingList, setLoadingList] = useState(true)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [detail, setDetail] = useState<RunResponse | null>(null)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoadingList(true)
    listExecutions()
      .then((all) => {
        const forAgent = all
          .filter((e) => e.spec_path === agentPath)
          .sort((a, b) => b.created_at - a.created_at)
        setExecutions(forAgent)
        setSelectedId(forAgent[0]?.id ?? null)
      })
      .catch(() => setExecutions([]))
      .finally(() => setLoadingList(false))
  }, [agentPath])

  useEffect(() => {
    if (!selectedId) {
      setDetail(null)
      return
    }
    setLoadingDetail(true)
    setError(null)
    getExecution(selectedId)
      .then(setDetail)
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load execution'))
      .finally(() => setLoadingDetail(false))
  }, [selectedId])

  if (loadingList) {
    return (
      <div className="flex items-center justify-center h-64 text-muted text-2">
        <div className="flex items-center gap-2">
          <Loader2 className="animate-spin w-5 h-5" />
          Loading traces...
        </div>
      </div>
    )
  }

  if (executions.length === 0) {
    return (
      <div className="flex items-center justify-center h-64 text-muted text-2">
        <div className="text-center">
          <Activity size={44} className="mx-auto mb-3 text-muted" strokeWidth={1.5} />
          <p>Run a journey from the Journeys tab to see its execution trace here.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
      {/* Execution list */}
      <div className="lg:col-span-4 space-y-2">
        {executions.map((e) => (
          <button
            key={e.id}
            onClick={() => setSelectedId(e.id)}
            className={`w-full text-left p-3 rounded-lg border transition-colors ${
              selectedId === e.id
                ? 'border-accent bg-accent/10'
                : 'border-border-subtle bg-surface-1 hover:border-border'
            }`}
          >
            <div className="flex items-center justify-between gap-2">
              <span className="font-medium text-sm text-primary truncate">{e.journey_name}</span>
              <span className={`w-2 h-2 rounded-full flex-shrink-0 ${STATUS_DOT[e.status] || 'bg-muted'}`} />
            </div>
            <p className="text-xs text-muted mt-0.5">
              {new Date(e.created_at * 1000).toLocaleString()}
            </p>
          </button>
        ))}
      </div>

      {/* Selected execution detail */}
      <div className="lg:col-span-8 space-y-6">
        {loadingDetail && (
          <div className="flex items-center gap-2 text-muted text-2">
            <Loader2 className="animate-spin w-4 h-4" />
            Loading execution...
          </div>
        )}

        {error && (
          <div className="p-3 bg-danger/10 border border-danger/30 rounded-lg text-sm text-danger">
            {error}
          </div>
        )}

        {!loadingDetail && detail && (
          <>
            <ResultSummary result={detail} />
            <StepTimeline
              steps={detail.traces.map((t) => ({
                step_name: t.step_name,
                step_type: t.step_type,
                status: mapStatus(t.status),
                duration_ms: t.duration_ms,
                output_preview: t.output_preview,
              }))}
            />
          </>
        )}
      </div>
    </div>
  )
}
