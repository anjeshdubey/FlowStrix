import { useState } from 'react'
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

    const baseInputClass = `w-full px-3 py-2 border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent ${
      error ? 'border-red-300 bg-red-50' : 'border-gray-300'
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
                      ? 'border-indigo-300 bg-indigo-50 text-indigo-800'
                      : 'border-gray-200 hover:border-gray-300'
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
                    className="rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
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
              className="mt-0.5 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
            />
            <span className="text-sm text-gray-700">{field.label}</span>
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
    <div className="border-2 border-indigo-300 bg-indigo-50 rounded-lg p-5 animate-slide-in">
      <div className="flex items-start gap-3">
        <div className="w-10 h-10 bg-indigo-100 rounded-full flex items-center justify-center flex-shrink-0">
          <svg className="w-5 h-5 text-indigo-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
        </div>

        <div className="flex-1">
          <h3 className="font-semibold text-indigo-900 text-lg">Structured Input Required</h3>
          <p className="text-sm text-indigo-700 mt-1">
            {handoffInfo.transition_message}
          </p>

          {/* Form Fields */}
          <div className="mt-4 space-y-4 bg-white rounded-md border border-indigo-200 p-4">
            {handoffInfo.fields.map((field) => (
              <div key={field.id}>
                {field.field_type !== 'checkbox' && (
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    {field.label}
                    {field.required && <span className="text-red-500 ml-0.5">*</span>}
                  </label>
                )}
                {renderField(field)}
                {errors[field.id] && (
                  <p className="mt-1 text-xs text-red-600">{errors[field.id]}</p>
                )}
              </div>
            ))}
          </div>

          {/* Submit button */}
          <button
            onClick={handleSubmit}
            disabled={loading}
            className="mt-4 w-full py-2.5 bg-indigo-600 text-white rounded-md font-medium hover:bg-indigo-700 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
          >
            {loading ? (
              <>
                <svg className="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                Submitting...
              </>
            ) : (
              <>
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
                Submit
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  )
}
