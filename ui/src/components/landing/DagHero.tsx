// Static illustration of a journey DAG — the executed path (accent) versus an
// untaken HITL branch (dimmed, pulsing) — echoing how FlowStrix traces a run.
const NODES = [
  { top: 40, left: 280, kind: 'LOOKUP', name: 'fetch_order_history', treatment: 'deterministic' },
  { top: 150, left: 280, kind: 'REASON', name: 'determine_eligibility', treatment: 'probabilistic', badge: 'Qwen2.5-7B' },
  { top: 260, left: 280, kind: 'BRANCH', name: 'check_eligibility', treatment: 'deterministic' },
  { top: 370, left: 280, kind: 'BRANCH', name: 'check_amount_gate', treatment: 'deterministic' },
  { top: 500, left: 410, kind: 'TOOL', name: 'process_refund_action', treatment: 'deterministic' },
  { top: 630, left: 280, kind: 'RESPOND', name: 'confirm_refund', treatment: 'deterministic' },
]

const DIMMED_NODE = { top: 500, left: 150, kind: 'HITL GATE', name: 'escalate_high_value' }

export default function DagHero() {
  return (
    <div className="relative w-[560px] h-[720px] max-w-full">
      <svg width="560" height="720" viewBox="0 0 560 720" className="absolute inset-0">
        <path d="M280,70 L280,140" stroke="#2f8aff" strokeWidth="2" fill="none" />
        <path d="M280,170 L280,250" stroke="#2f8aff" strokeWidth="2" fill="none" />
        <path d="M280,280 L280,360" stroke="#2f8aff" strokeWidth="2" fill="none" />
        <path d="M280,390 L400,475" stroke="#2f8aff" strokeWidth="2" fill="none" />
        <path d="M410,530 L290,600" stroke="#2f8aff" strokeWidth="2" fill="none" />
        <g style={{ animation: 'branchDim 3600ms ease-in-out infinite' }}>
          <path d="M270,390 L165,475" stroke="#3d424c" strokeWidth="2" fill="none" />
          <path d="M150,530 L265,600" stroke="#3d424c" strokeWidth="2" fill="none" />
        </g>
        <circle r="5" fill="#2f8aff">
          <animateMotion
            path="M280,70 L280,140 L280,250 L280,360 L410,500 L280,630"
            dur="4.5s"
            repeatCount="indefinite"
          />
          <animate
            attributeName="opacity"
            values="0;1;1;1;1;0"
            keyTimes="0;0.05;0.4;0.6;0.9;1"
            dur="4.5s"
            repeatCount="indefinite"
          />
        </circle>
      </svg>

      {NODES.map((n) => (
        <div
          key={n.name}
          className={`absolute w-[190px] -translate-x-1/2 -translate-y-1/2 px-3.5 py-2.5 shadow-1 ${
            n.treatment === 'probabilistic' ? 'step--probabilistic' : 'step--deterministic'
          }`}
          style={{ top: n.top, left: n.left }}
        >
          <div className="flex items-center justify-between mb-1">
            <div
              className={`font-mono text-[10px] tracking-wider ${
                n.treatment === 'probabilistic' ? 'text-accent' : 'text-muted'
              }`}
            >
              {n.kind}
            </div>
            {n.badge && (
              <div className="font-mono text-[9px] text-muted bg-surface-2 px-1.5 py-0.5 rounded-full border border-border-subtle">
                {n.badge}
              </div>
            )}
          </div>
          <div className="text-2 font-semibold text-primary">{n.name}</div>
        </div>
      ))}

      <div
        className="absolute w-[170px] -translate-x-1/2 -translate-y-1/2 px-4 py-3 step--gate opacity-40"
        style={{ top: DIMMED_NODE.top, left: DIMMED_NODE.left, animation: 'branchDim 3600ms ease-in-out infinite' }}
      >
        <div className="font-mono text-[10px] tracking-wider text-warning mb-1">{DIMMED_NODE.kind}</div>
        <div className="text-2 font-semibold text-primary">{DIMMED_NODE.name}</div>
      </div>
    </div>
  )
}
