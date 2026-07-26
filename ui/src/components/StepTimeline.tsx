import { Search, Brain, MessageSquare, GitBranch, UserCheck, Wrench, Clock, Settings } from 'lucide-react'
import { StepState } from '../types'

interface StepTimelineProps {
  steps: StepState[]
}

const STEP_TYPE_ICONS: Record<string, typeof Search> = {
  lookup: Search,
  reason: Brain,
  respond: MessageSquare,
  branch: GitBranch,
  hitl: UserCheck,
  tool: Wrench,
  wait: Clock,
}

const STATUS_LABELS: Record<string, string> = {
  pending: 'Pending',
  running: 'Running',
  completed: 'Completed',
  failed: 'Failed',
  hitl: 'Awaiting Human',
}

export default function StepTimeline({ steps }: StepTimelineProps) {
  if (steps.length === 0) return null

  return (
    <div className="space-y-3">
      <h3 className="text-1 font-semibold text-secondary uppercase tracking-wide">
        Execution Steps
      </h3>

      <div className="space-y-2">
        {steps.map((step, index) => {
          const Icon = STEP_TYPE_ICONS[step.step_type] || Settings
          return (
            <div
              key={`${step.step_name}-${index}`}
              className={`step-card animate-slide-in ${getCardClass(step.status)}`}
              style={{ animationDelay: `${index * 100}ms` }}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  {/* Status indicator */}
                  <div className={`w-2.5 h-2.5 rounded-full ${getStatusDotClass(step.status)}`}>
                    {step.status === 'running' && (
                      <div className="w-2.5 h-2.5 rounded-full bg-accent animate-ping" />
                    )}
                  </div>

                  {/* Step icon */}
                  <Icon size={14} className="text-secondary" />

                  {/* Step name */}
                  <span className="font-medium text-2">{step.step_name}</span>

                  {/* Step type badge */}
                  <span className="text-1 bg-surface-2 px-1.5 py-0.5 rounded border border-border-subtle text-secondary">
                    {step.step_type}
                  </span>
                </div>

                <div className="flex items-center gap-2 text-1">
                  {step.duration_ms !== undefined && (
                    <span className="text-muted">
                      {step.duration_ms.toFixed(0)}ms
                    </span>
                  )}
                  <span className="font-medium">{STATUS_LABELS[step.status]}</span>
                </div>
              </div>

              {/* Output preview */}
              {step.output_preview && (
                <div className="mt-2 text-1 font-mono bg-surface-2 rounded p-2 truncate">
                  {step.output_preview}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

function getCardClass(status: string): string {
  switch (status) {
    case 'running': return 'step-card-running'
    case 'completed': return 'step-card-completed'
    case 'failed': return 'step-card-failed'
    case 'hitl': return 'step-card-hitl'
    default: return 'step-card-pending'
  }
}

function getStatusDotClass(status: string): string {
  switch (status) {
    case 'running': return 'bg-accent'
    case 'completed': return 'bg-success'
    case 'failed': return 'bg-danger'
    case 'hitl': return 'bg-warning'
    default: return 'bg-muted'
  }
}
