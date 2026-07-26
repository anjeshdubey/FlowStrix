interface ContextViewerProps {
  data: Record<string, unknown>
  title?: string
}

export default function ContextViewer({ data, title = 'Context Data' }: ContextViewerProps) {
  if (Object.keys(data).length === 0) return null

  return (
    <div className="space-y-2">
      <h3 className="text-sm font-semibold text-secondary uppercase tracking-wide">{title}</h3>
      <div className="bg-surface-2 rounded-lg p-4 overflow-x-auto">
        <pre className="text-xs text-success font-mono whitespace-pre-wrap">
          {JSON.stringify(data, null, 2)}
        </pre>
      </div>
    </div>
  )
}
