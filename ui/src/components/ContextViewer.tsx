interface ContextViewerProps {
  data: Record<string, unknown>
  title?: string
}

export default function ContextViewer({ data, title = 'Context Data' }: ContextViewerProps) {
  if (Object.keys(data).length === 0) return null

  return (
    <div className="space-y-2">
      <h3 className="text-sm font-semibold text-gray-700 dark:text-secondary uppercase tracking-wide">{title}</h3>
      <div className="bg-gray-900 rounded-lg p-4 overflow-x-auto">
        <pre className="text-xs text-green-400 font-mono whitespace-pre-wrap">
          {JSON.stringify(data, null, 2)}
        </pre>
      </div>
    </div>
  )
}
