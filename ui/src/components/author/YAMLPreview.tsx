import { Copy, Download } from 'lucide-react'

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
    <div className="bg-surface-2 rounded-xl overflow-hidden border border-border-subtle">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2 bg-surface-1">
        <span className="text-xs font-medium text-muted">agent_spec.yaml</span>
        <div className="flex gap-1">
          <button
            onClick={handleCopy}
            className="p-1.5 text-muted hover:text-primary transition-colors rounded"
            title="Copy YAML"
          >
            <Copy className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={handleDownload}
            className="p-1.5 text-muted hover:text-primary transition-colors rounded"
            title="Download YAML"
          >
            <Download className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* YAML content */}
      <div className="p-4 overflow-x-auto max-h-[500px] overflow-y-auto">
        <pre className="text-xs text-success font-mono whitespace-pre leading-relaxed">
          {yaml}
        </pre>
      </div>
    </div>
  )
}
