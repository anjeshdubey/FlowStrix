import { useState } from 'react'
import { Check, TriangleAlert, X } from 'lucide-react'
import { HITLInfo } from '../types'

interface HITLPanelProps {
  hitlInfo: HITLInfo
  onDecision: (approved: boolean, notes?: string) => void
  loading: boolean
}

export default function HITLPanel({ hitlInfo, onDecision, loading }: HITLPanelProps) {
  const [notes, setNotes] = useState('')

  return (
    <div className="border-2 border-warning/40 bg-warning/10 rounded-lg p-5 animate-slide-in">
      <div className="flex items-start gap-3">
        <div className="w-10 h-10 bg-warning/20 rounded-full flex items-center justify-center flex-shrink-0">
          <TriangleAlert className="w-5 h-5 text-warning" />
        </div>

        <div className="flex-1">
          <h3 className="font-semibold text-warning text-lg">Human Decision Required</h3>
          <p className="text-sm text-warning/80 mt-1">
            Execution paused — this step requires human approval before proceeding.
          </p>

          {/* Escalation details */}
          <div className="mt-3 bg-surface-1 rounded-md border border-warning/30 p-3 space-y-2">
            <div className="flex justify-between text-sm">
              <span className="text-muted">Step:</span>
              <span className="font-medium text-primary">{hitlInfo.step_name}</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-muted">Escalation:</span>
              <span className="font-medium text-primary">{hitlInfo.escalation_type}</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-muted">Escalate to:</span>
              <span className="font-medium text-primary">{hitlInfo.escalate_to}</span>
            </div>
            {Object.keys(hitlInfo.context).length > 0 && (
              <div className="pt-2 border-t border-warning/20">
                <span className="text-xs text-muted block mb-1">Context:</span>
                <pre className="text-xs font-mono bg-surface-2 rounded p-2 overflow-x-auto">
                  {JSON.stringify(hitlInfo.context, null, 2)}
                </pre>
              </div>
            )}
          </div>

          {/* Notes input */}
          <div className="mt-3">
            <label className="block text-sm font-medium text-warning mb-1">Notes (optional)</label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Reason for decision..."
              rows={2}
              className="w-full px-3 py-2 bg-surface-1 border border-warning/30 rounded-md text-sm text-primary focus:outline-none focus:ring-2 focus:ring-warning resize-none"
            />
          </div>

          {/* Action buttons */}
          <div className="mt-4 flex gap-3">
            <button
              onClick={() => onDecision(true, notes || undefined)}
              disabled={loading}
              className="flex-1 py-2 bg-success text-surface-0 rounded-md font-medium hover:brightness-110 transition-all disabled:opacity-50 flex items-center justify-center gap-1.5"
            >
              <Check className="w-4 h-4" />
              Approve
            </button>
            <button
              onClick={() => onDecision(false, notes || undefined)}
              disabled={loading}
              className="flex-1 py-2 bg-danger text-surface-0 rounded-md font-medium hover:brightness-110 transition-all disabled:opacity-50 flex items-center justify-center gap-1.5"
            >
              <X className="w-4 h-4" />
              Reject
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
