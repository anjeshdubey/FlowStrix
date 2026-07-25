import { Link } from 'react-router-dom'
import { Plus } from 'lucide-react'
import { SavedSpec } from '../../api'

interface RailProps {
  specs: SavedSpec[]
  loading: boolean
  activeAgentId: string | undefined
  collapsed: boolean
}

export default function Rail({ specs, loading, activeAgentId, collapsed }: RailProps) {
  if (collapsed) {
    return (
      <div className="w-16 flex-none border-r border-border-subtle flex flex-col items-center py-4 gap-2">
        {specs.map((s) => {
          const active = decodeURIComponent(activeAgentId ?? '') === s.path
          return (
            <Link
              key={s.path}
              to={`/agents/${encodeURIComponent(s.path)}/journeys`}
              title={s.agent}
              className={`w-9 h-9 rounded-md flex items-center justify-center text-xs font-semibold ${
                active
                  ? 'bg-surface-1 border-l-2 border-accent text-primary'
                  : 'text-secondary hover:bg-surface-1 hover:text-primary'
              }`}
            >
              {s.agent.slice(0, 1).toUpperCase()}
            </Link>
          )
        })}
        <div className="flex-1" />
      </div>
    )
  }

  return (
    <div className="w-60 flex-none border-r border-border-subtle flex flex-col p-3 gap-0.5 overflow-y-auto">
      <div className="font-mono text-[10px] tracking-wider text-muted px-2.5 pt-1.5 pb-2.5">AGENTS</div>

      {loading && <div className="px-2.5 py-2 text-2 text-muted">Loading agents…</div>}
      {!loading && specs.length === 0 && (
        <div className="px-2.5 py-2 text-2 text-muted">No agents yet.</div>
      )}

      {specs.map((s) => {
        const active = decodeURIComponent(activeAgentId ?? '') === s.path
        return (
          <Link
            key={s.path}
            to={`/agents/${encodeURIComponent(s.path)}/journeys`}
            className={`flex items-center justify-between rounded-md px-2.5 py-2.5 text-2 ${
              active
                ? 'bg-surface-1 border-l-2 border-accent font-semibold text-primary'
                : 'text-secondary hover:bg-surface-1 hover:text-primary'
            }`}
          >
            <span className="truncate">{s.agent}</span>
            <span className={`font-mono text-1 ${active ? 'text-accent' : 'text-muted'}`}>
              {s.journey_count}
            </span>
          </Link>
        )
      })}

      <div className="flex-1" />

      <button className="flex items-center gap-2 rounded-md border border-dashed border-border p-2.5 text-2 font-medium text-secondary hover:border-border-strong hover:text-primary">
        <Plus size={15} />
        New agent
      </button>
    </div>
  )
}
