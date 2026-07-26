import { useState } from 'react'
import { Check, ClipboardList, Loader2 } from 'lucide-react'
import { HandoffInfo } from '../types'

interface HandoffFormProps {
  handoffInfo: HandoffInfo
  onSubmit: (formData: Record<string, unknown>) => void
  loading: boolean
}

export default function HandoffForm({ handoffInfo, onSubmit, loading }: HandoffFormProps) {
  const [formData, setFormData] = useState<Record<string, unknown>>(() => {
    // Initialize with prefilled values
    const initial: Record<string, unknown> = {}
    for (const field of handoffInfo.fields) {
      if (field.prefilled_value !== null && field.prefilled_value !== undefined) {
        initial[field.id] = field.prefilled_value
      } else if (field.field_type === 'checkbox') {
        initial[field.id] = false
      } else if (field.field_type === 'multiselect') {
        initial[field.id] = []
      } else {
        initial[field.id] = ''
      }
    }
    return initial
  })

  const [errors, setErrors] = useState<Record<string, string>>({})

  const handleChange = (fieldId: string, value: unknown) => {
    setFormData((prev) => ({ ...prev, [fieldId]: value }))
    setErrors((prev) => {
      const next = { ...prev }
      delete next[fieldId]
      return next
    })
  }

  const handleSubmit = () => {
    // Validate required fields
    const newErrors: Record<string, string> = {}
    for (const field of handoffInfo.fields) {
      if (field.required) {
        const value = formData[field.id]
        if (value === '' || value === null || value === undefined || value === false) {
          newErrors[field.id] = 'This field is required'
        }
        if (field.field_type === 'multiselect' && Array.isArray(value) && value.length === 0) {
          newErrors[field.id] = 'Select at least one option'
        }
      }
    }

    if (Object.keys(newErrors).length > 0) {
      setErrors(newErrors)
      return
    }

    onSubmit(formData)
  }

  const renderField = (field: typeof handoffInfo.fields[0]) => {
    const value = formData[field.id]
    const error = errors[field.id]

    const baseInputClass = `w-full px-3 py-2 bg-surface-2 border rounded-md text-sm text-primary focus:outline-none focus:ring-2 focus:ring-accent focus:border-transparent ${
      error ? 'border-danger bg-danger/10' : 'border-border'
    }`

    switch (field.field_type) {
      case 'textarea':
        return (
          <textarea
            value={(value as string) || ''}
            onChange={(e) => handleChange(field.id, e.target.value)}
            placeholder={field.placeholder || ''}
            rows={3}
            className={`${baseInputClass} resize-none`}
          />
        )

      case 'select':
        return (
          <select
            value={(value as string) || ''}
            onChange={(e) => handleChange(field.id, e.target.value)}
            className={baseInputClass}
          >
            <option value="">{field.placeholder || 'Select...'}</option>
            {field.options.map((opt) => (
              <option key={opt} value={opt}>{opt}</option>
            ))}
          </select>
        )

      case 'multiselect':
        return (
          <div className="space-y-1.5">
            {field.options.map((opt) => {
              const selected = Array.isArray(value) && (value as string[]).includes(opt)
              return (
                <label
                  key={opt}
                  className={`flex items-center gap-2 px-3 py-1.5 rounded-md border cursor-pointer transition-colors ${
                    selected
                      ? 'border-accent bg-accent/10 text-accent'
                      : 'border-border-subtle hover:border-border text-secondary'
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={selected}
                    onChange={(e) => {
                      const current = (value as string[]) || []
                      if (e.target.checked) {
                        handleChange(field.id, [...current, opt])
                      } else {
                        handleChange(field.id, current.filter((v) => v !== opt))
                      }
                    }}
                    className="rounded border-border bg-surface-2 text-accent focus:ring-accent"
                  />
                  <span className="text-sm">{opt}</span>
                </label>
              )
            })}
          </div>
        )

      case 'checkbox':
        return (
          <label className="flex items-start gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={Boolean(value)}
              onChange={(e) => handleChange(field.id, e.target.checked)}
              className="mt-0.5 rounded border-border bg-surface-2 text-accent focus:ring-accent"
            />
            <span className="text-sm text-secondary">{field.label}</span>
          </label>
        )

      default: // text
        return (
          <input
            type="text"
            value={(value as string) || ''}
            onChange={(e) => handleChange(field.id, e.target.value)}
            placeholder={field.placeholder || ''}
            className={baseInputClass}
          />
        )
    }
  }

  return (
    <div className="border-2 border-accent/40 bg-accent/10 rounded-lg p-5 animate-slide-in">
      <div className="flex items-start gap-3">
        <div className="w-10 h-10 bg-accent/20 rounded-full flex items-center justify-center flex-shrink-0">
          <ClipboardList className="w-5 h-5 text-accent" />
        </div>

        <div className="flex-1">
          <h3 className="font-semibold text-accent text-lg">Structured Input Required</h3>
          <p className="text-sm text-accent/80 mt-1">
            {handoffInfo.transition_message}
          </p>

          {/* Form Fields */}
          <div className="mt-4 space-y-4 bg-surface-1 rounded-md border border-accent/30 p-4">
            {handoffInfo.fields.map((field) => (
              <div key={field.id}>
                {field.field_type !== 'checkbox' && (
                  <label className="block text-sm font-medium text-secondary mb-1">
                    {field.label}
                    {field.required && <span className="text-danger ml-0.5">*</span>}
                  </label>
                )}
                {renderField(field)}
                {errors[field.id] && (
                  <p className="mt-1 text-xs text-danger">{errors[field.id]}</p>
                )}
              </div>
            ))}
          </div>

          {/* Submit button */}
          <button
            onClick={handleSubmit}
            disabled={loading}
            className="mt-4 w-full py-2.5 bg-accent text-surface-0 rounded-md font-medium hover:brightness-110 transition-all disabled:opacity-50 flex items-center justify-center gap-2"
          >
            {loading ? (
              <>
                <Loader2 className="animate-spin w-4 h-4" />
                Submitting...
              </>
            ) : (
              <>
                <Check className="w-4 h-4" />
                Submit
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  )
}
