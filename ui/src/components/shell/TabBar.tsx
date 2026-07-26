import { NavLink, useParams } from 'react-router-dom'

const TABS = [
  { to: 'journeys', label: 'Journeys' },
  { to: 'knowledge', label: 'Knowledge' },
  { to: 'simulations', label: 'Simulations' },
  { to: 'traces', label: 'Traces' },
  { to: 'chat', label: 'Chat' },
]

export default function TabBar() {
  const { agentId } = useParams<{ agentId: string }>()
  const encodedAgentId = agentId ? encodeURIComponent(agentId) : null

  return (
    <div className="h-11 flex-none flex items-center gap-1 px-5 border-b border-border-subtle overflow-x-auto">
      {TABS.map((tab) => (
        <NavLink
          key={tab.to}
          to={encodedAgentId ? `/agents/${encodedAgentId}/${tab.to}` : '#'}
          className={({ isActive }) =>
            `px-4 py-2.5 text-2 font-medium whitespace-nowrap -mb-px border-b-2 ${
              isActive
                ? 'text-primary font-semibold border-accent'
                : 'text-muted border-transparent hover:text-secondary'
            }`
          }
        >
          {tab.label}
        </NavLink>
      ))}
    </div>
  )
}
