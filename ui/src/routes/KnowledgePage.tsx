import { useEffect, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import { BookOpen } from 'lucide-react'
import { getSpecDetail } from '../api'
import { SpecDetail } from '../types'
import { AgentWorkspaceContext } from './AgentWorkspace'

export default function KnowledgePage() {
  const { agentPath } = useOutletContext<AgentWorkspaceContext>()
  const [detail, setDetail] = useState<SpecDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!agentPath) return
    setLoading(true)
    setError(null)
    getSpecDetail(agentPath)
      .then(setDetail)
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load spec'))
      .finally(() => setLoading(false))
  }, [agentPath])

  if (!agentPath) {
    return <div className="text-2 text-muted">Select an agent from the rail to view its knowledge sources.</div>
  }
  if (loading) return <div className="text-2 text-muted">Loading…</div>
  if (error) return <div className="text-2 text-danger">{error}</div>
  if (!detail) return null

  return (
    <div className="max-w-xl space-y-4">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-md bg-surface-1 border border-border flex items-center justify-center">
          <BookOpen size={18} className="text-accent" />
        </div>
        <div>
          <h2 className="text-4 font-semibold text-primary">Knowledge sources</h2>
          <p className="text-2 text-secondary">
            {detail.knowledge_sources} source{detail.knowledge_sources === 1 ? '' : 's'} configured for{' '}
            <span className="text-primary font-medium">{detail.agent}</span>
          </p>
        </div>
      </div>

      {detail.knowledge_sources === 0 && (
        <p className="text-2 text-muted">
          This agent doesn't reference any knowledge documents yet. Upload one from the spec author view to ground its
          reasoning steps.
        </p>
      )}
    </div>
  )
}
