interface YAMLPreviewProps {
  yaml: string
}

export default function YAMLPreview({ yaml }: YAMLPreviewProps) {
  const handleCopy = () => {
    navigator.clipboard.writeText(yaml)
  }

  const handleDownload = () => {
    const blob = new Blob([yaml], { type: 'text/yaml' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'agent_spec.yaml'
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="bg-gray-900 rounded-xl overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2 bg-gray-800">
        <span className="text-xs font-medium text-gray-400">agent_spec.yaml</span>
        <div className="flex gap-1">
          <button
            onClick={handleCopy}
            className="p-1.5 text-gray-400 hover:text-white transition-colors rounded"
            title="Copy YAML"
          >
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
            </svg>
          </button>
          <button
            onClick={handleDownload}
            className="p-1.5 text-gray-400 hover:text-white transition-colors rounded"
            title="Download YAML"
          >
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
            </svg>
          </button>
        </div>
      </div>

      {/* YAML content */}
      <div className="p-4 overflow-x-auto max-h-[500px] overflow-y-auto">
        <pre className="text-xs text-green-400 font-mono whitespace-pre leading-relaxed">
          {yaml}
        </pre>
      </div>
    </div>
  )
}
