import { useEffect, useState } from 'react'
import { getSpec, listSpecs, SavedSpec } from '../api'
import { SpecSummary } from '../types'

interface SpecLoaderProps {
  onSpecLoaded: (spec: SpecSummary, specPath: string) => void
}

export default function SpecLoader({ onSpecLoaded }: SpecLoaderProps) {
  const [specPath, setSpecPath] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [savedSpecs, setSavedSpecs] = useState<SavedSpec[]>([])
  const [loadingSpecs, setLoadingSpecs] = useState(true)

  // Load available specs on mount
  useEffect(() => {
    listSpecs()
      .then(setSavedSpecs)
      .catch(() => setSavedSpecs([]))
      .finally(() => setLoadingSpecs(false))
  }, [])

  const loadSpec = async (path: string) => {
    setLoading(true)
    setError(null)
    try {
      const spec = await getSpec(path)
      onSpecLoaded(spec, path)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load spec')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold text-gray-900 dark:text-primary mb-1">Load Agent Spec</h2>
        <p className="text-sm text-gray-500 dark:text-secondary">Choose a saved spec or enter a custom path.</p>
      </div>

      {/* Saved specs from server */}
      {loadingSpecs ? (
        <div className="text-sm text-gray-400 dark:text-muted">Loading specs...</div>
      ) : savedSpecs.length > 0 ? (
        <div className="flex flex-wrap gap-2">
          {savedSpecs.map((s) => (
            <button
              key={s.path}
              onClick={() => {
                setSpecPath(s.path)
                loadSpec(s.path)
              }}
              disabled={loading}
              className="px-3 py-1.5 text-sm bg-forge-50 dark:bg-accent/10 text-forge-700 dark:text-accent rounded-md border border-forge-200 dark:border-accent/30 hover:bg-forge-100 dark:hover:bg-accent/20 transition-colors disabled:opacity-50"
            >
              <span className="font-medium">{s.agent}</span>
              {s.journey_count > 0 && (
                <span className="ml-1 text-forge-400 dark:text-accent/70 text-xs">({s.journey_count})</span>
              )}
            </button>
          ))}
        </div>
      ) : (
        <div className="text-sm text-gray-400 dark:text-muted">No specs found. Author one first!</div>
      )}

      {/* Custom path input */}
      <div className="flex gap-2">
        <input
          type="text"
          value={specPath}
          onChange={(e) => setSpecPath(e.target.value)}
          placeholder="path/to/agent_spec.yaml"
          className="flex-1 px-3 py-2 bg-white dark:bg-surface-1 text-gray-900 dark:text-primary border border-gray-300 dark:border-border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-forge-500 dark:focus:ring-accent focus:border-transparent"
          onKeyDown={(e) => {
            if (e.key === 'Enter' && specPath) loadSpec(specPath)
          }}
        />
        <button
          onClick={() => loadSpec(specPath)}
          disabled={!specPath || loading}
          className="px-4 py-2 bg-forge-600 dark:bg-accent text-white rounded-md text-sm font-medium hover:bg-forge-700 dark:hover:bg-accent/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {loading ? 'Loading...' : 'Load'}
        </button>
      </div>

      {error && (
        <div className="p-3 bg-red-50 dark:bg-danger/10 border border-red-200 dark:border-danger/30 rounded-md text-sm text-red-700 dark:text-danger">
          {error}
        </div>
      )}
    </div>
  )
}
