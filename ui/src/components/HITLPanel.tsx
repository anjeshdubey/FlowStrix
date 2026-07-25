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
    <div className="border-2 border-amber-300 bg-amber-50 rounded-lg p-5 animate-slide-in">
      <div className="flex items-start gap-3">
        <div className="w-10 h-10 bg-amber-100 rounded-full flex items-center justify-center flex-shrink-0">
          <TriangleAlert className="w-5 h-5 text-amber-600" />
        </div>

        <div className="flex-1">
          <h3 className="font-semibold text-amber-900 text-lg">Human Decision Required</h3>
          <p className="text-sm text-amber-700 mt-1">
            Execution paused — this step requires human approval before proceeding.
          </p>

          {/* Escalation details */}
          <div className="mt-3 bg-white rounded-md border border-amber-200 p-3 space-y-2">
            <div className="flex justify-between text-sm">
              <span className="text-gray-500">Step:</span>
              <span className="font-medium text-gray-900">{hitlInfo.step_name}</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-gray-500">Escalation:</span>
              <span className="font-medium text-gray-900">{hitlInfo.escalation_type}</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-gray-500">Escalate to:</span>
              <span className="font-medium text-gray-900">{hitlInfo.escalate_to}</span>
            </div>
            {Object.keys(hitlInfo.context).length > 0 && (
              <div className="pt-2 border-t border-amber-100">
                <span className="text-xs text-gray-500 block mb-1">Context:</span>
                <pre className="text-xs font-mono bg-gray-50 rounded p-2 overflow-x-auto">
                  {JSON.stringify(hitlInfo.context, null, 2)}
                </pre>
              </div>
            )}
          </div>

          {/* Notes input */}
          <div className="mt-3">
            <label className="block text-sm font-medium text-amber-800 mb-1">Notes (optional)</label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Reason for decision..."
              rows={2}
              className="w-full px-3 py-2 border border-amber-200 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-amber-500 resize-none"
            />
          </div>

          {/* Action buttons */}
          <div className="mt-4 flex gap-3">
            <button
              onClick={() => onDecision(true, notes || undefined)}
              disabled={loading}
              className="flex-1 py-2 bg-green-600 text-white rounded-md font-medium hover:bg-green-700 transition-colors disabled:opacity-50 flex items-center justify-center gap-1.5"
            >
              <Check className="w-4 h-4" />
              Approve
            </button>
            <button
              onClick={() => onDecision(false, notes || undefined)}
              disabled={loading}
              className="flex-1 py-2 bg-red-600 text-white rounded-md font-medium hover:bg-red-700 transition-colors disabled:opacity-50 flex items-center justify-center gap-1.5"
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
