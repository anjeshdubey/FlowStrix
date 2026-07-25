import { ChevronDown, PanelLeft, Zap } from 'lucide-react'
import { Link } from 'react-router-dom'
import { HealthResponse } from '../../types'

interface TopBarProps {
  health: HealthResponse | null
  agentName: string | null
  onToggleRail: () => void
}

export default function TopBar({ health, agentName, onToggleRail }: TopBarProps) {
  return (
    <div className="h-14 flex-none flex items-center justify-between px-5 border-b border-border-subtle">
      <div className="flex items-center gap-6">
        <Link to="/" className="flex items-center gap-2">
          <div className="w-[22px] h-[22px] rounded-md bg-accent flex items-center justify-center shadow-glow-accent">
            <Zap size={12} className="text-surface-0" fill="currentColor" />
          </div>
          <span className="font-bold text-3 text-primary">FlowStrix</span>
        </Link>

        <div className="w-px h-5 bg-border" />

        <button
          onClick={onToggleRail}
          className="flex items-center gap-1.5 rounded-md border border-border p-1.5 text-secondary hover:border-border-strong hover:text-primary"
          title="Toggle agent rail"
        >
          <PanelLeft size={14} />
        </button>

        {agentName && (
          <button className="flex items-center gap-2 rounded-md border border-border bg-surface-1 px-3 py-1.5 hover:border-border-strong">
            <div className="w-4 h-4 rounded-sm bg-info opacity-85" />
            <span className="text-2 font-medium text-primary">{agentName}</span>
            <ChevronDown size={12} className="text-secondary opacity-60" />
          </button>
        )}
      </div>

      <div className="flex items-center gap-3.5">
        <div className="flex items-center gap-1.5 rounded-full border border-border bg-surface-1 px-3 py-1">
          <span
            className={`w-1.5 h-1.5 rounded-full ${health?.gateway_configured ? 'bg-success' : 'bg-warning'}`}
          />
          <span className="font-mono text-1 text-secondary">
            {health
              ? health.gateway_configured
                ? health.model
                  ? `Gateway Connected · ${health.model}`
                  : 'Gateway Connected'
                : 'No Gateway'
              : 'Checking…'}
          </span>
        </div>
      </div>
    </div>
  )
}
