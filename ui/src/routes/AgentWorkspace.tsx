import { useEffect, useState } from 'react'
import { Outlet, useParams } from 'react-router-dom'
import { listSpecs, SavedSpec } from '../api'
import Rail from '../components/shell/Rail'
import TabBar from '../components/shell/TabBar'
import TopBar from '../components/shell/TopBar'
import { useHealth } from '../context/HealthContext'
import { useAgentExecution } from '../hooks/useAgentExecution'

export interface AgentWorkspaceContext {
  agentId: string | undefined
  agentPath: string | null
  specEntry: SavedSpec | null
  specs: SavedSpec[]
  execution: ReturnType<typeof useAgentExecution>
}

export default function AgentWorkspace() {
  const { agentId } = useParams<{ agentId: string }>()
  const health = useHealth()
  const [specs, setSpecs] = useState<SavedSpec[]>([])
  const [loadingSpecs, setLoadingSpecs] = useState(true)
  const [railCollapsed, setRailCollapsed] = useState(false)
  const execution = useAgentExecution()

  useEffect(() => {
    listSpecs()
      .then(setSpecs)
      .catch(() => setSpecs([]))
      .finally(() => setLoadingSpecs(false))
  }, [])

  const agentPath = agentId ? decodeURIComponent(agentId) : null
  const specEntry = specs.find((s) => s.path === agentPath) ?? null

  return (
    <div className="flex flex-col h-screen bg-surface-0 text-primary">
      <TopBar
        health={health}
        agentName={specEntry?.agent ?? agentPath}
        onToggleRail={() => setRailCollapsed((c) => !c)}
      />
      <TabBar />
      <div className="flex-1 flex min-h-0">
        <Rail specs={specs} loading={loadingSpecs} activeAgentId={agentId} collapsed={railCollapsed} />
        <div className="flex-1 min-w-0 overflow-y-auto p-8">
          <Outlet context={{ agentId, agentPath, specEntry, specs, execution } satisfies AgentWorkspaceContext} />
        </div>
      </div>
    </div>
  )
}
