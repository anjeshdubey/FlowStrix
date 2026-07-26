import { X } from 'lucide-react'
import { FlowStep } from './FlowCanvas'

interface StepEditorProps {
  step: FlowStep
  index: number
  onClose: () => void
}

export default function StepEditor({ step, index, onClose }: StepEditorProps) {
  return (
    <div className="bg-surface-1 border border-border-subtle rounded-xl shadow-2 overflow-hidden animate-slide-in">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 bg-surface-2 border-b border-border-subtle">
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold uppercase tracking-wide text-secondary">
            Step {index + 1}
          </span>
          <span className="text-xs bg-accent/10 text-accent px-2 py-0.5 rounded-full font-medium">
            {step.type}
          </span>
        </div>
        <button
          onClick={onClose}
          className="p-1 text-muted hover:text-secondary transition-colors"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Content */}
      <div className="p-4 space-y-4">
        {/* Name */}
        <div>
          <label className="block text-xs font-semibold text-secondary uppercase tracking-wide mb-1">
            Name
          </label>
          <input
            type="text"
            defaultValue={step.name}
            className="w-full px-3 py-2 bg-surface-2 border border-border-subtle rounded-lg text-sm text-primary focus:outline-none focus:ring-2 focus:ring-accent focus:border-transparent"
          />
        </div>

        {/* Description */}
        <div>
          <label className="block text-xs font-semibold text-secondary uppercase tracking-wide mb-1">
            Description
          </label>
          <textarea
            defaultValue={step.description}
            rows={2}
            className="w-full px-3 py-2 bg-surface-2 border border-border-subtle rounded-lg text-sm text-primary focus:outline-none focus:ring-2 focus:ring-accent focus:border-transparent resize-none"
          />
        </div>

        {/* Prompt (for reason/respond steps) */}
        {(step.type === 'reason' || step.type === 'respond') && step.prompt && (
          <div>
            <label className="block text-xs font-semibold text-secondary uppercase tracking-wide mb-1">
              Prompt
            </label>
            <textarea
              defaultValue={step.prompt}
              rows={4}
              className="w-full px-3 py-2 bg-surface-2 border border-border-subtle rounded-lg text-sm font-mono text-primary focus:outline-none focus:ring-2 focus:ring-accent focus:border-transparent resize-none"
            />
          </div>
        )}

        {/* Condition (for branch steps) */}
        {step.type === 'branch' && (
          <>
            <div>
              <label className="block text-xs font-semibold text-secondary uppercase tracking-wide mb-1">
                Condition
              </label>
              <input
                type="text"
                defaultValue={step.condition}
                className="w-full px-3 py-2 bg-surface-2 border border-border-subtle rounded-lg text-sm font-mono text-primary focus:outline-none focus:ring-2 focus:ring-accent focus:border-transparent"
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-semibold text-success uppercase tracking-wide mb-1">
                  If True →
                </label>
                <input
                  type="text"
                  defaultValue={step.if_true}
                  className="w-full px-3 py-2 bg-surface-2 border border-success/30 rounded-lg text-sm text-primary focus:outline-none focus:ring-2 focus:ring-success focus:border-transparent"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-danger uppercase tracking-wide mb-1">
                  If False →
                </label>
                <input
                  type="text"
                  defaultValue={step.if_false}
                  className="w-full px-3 py-2 bg-surface-2 border border-danger/30 rounded-lg text-sm text-primary focus:outline-none focus:ring-2 focus:ring-danger focus:border-transparent"
                />
              </div>
            </div>
          </>
        )}

        {/* Escalation (for hitl steps) */}
        {step.type === 'hitl' && (
          <div>
            <label className="block text-xs font-semibold text-secondary uppercase tracking-wide mb-1">
              Escalate To
            </label>
            <input
              type="text"
              defaultValue={step.escalate_to}
              className="w-full px-3 py-2 bg-surface-2 border border-border-subtle rounded-lg text-sm text-primary focus:outline-none focus:ring-2 focus:ring-accent focus:border-transparent"
            />
          </div>
        )}
      </div>

      {/* Footer hint */}
      <div className="px-4 py-3 bg-surface-2 border-t border-border-subtle">
        <p className="text-xs text-muted">
          Changes are reflected in the YAML preview. Save to persist.
        </p>
      </div>
    </div>
  )
}
