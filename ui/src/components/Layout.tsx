import { HealthResponse } from '../types'
import { useTheme } from '../hooks/useTheme'

interface LayoutProps {
  children: React.ReactNode
  health: HealthResponse | null
}

export default function Layout({ children, health }: LayoutProps) {
  const [theme, toggleTheme] = useTheme()

  return (
    <div className="min-h-screen flex flex-col bg-gray-50 dark:bg-surface-0">
      {/* Header */}
      <header className="bg-white dark:bg-surface-1 border-b border-gray-200 dark:border-border-subtle px-6 py-4">
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-forge-600 dark:bg-accent rounded-lg flex items-center justify-center">
              <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
            </div>
            <h1 className="text-xl font-bold text-gray-900 dark:text-primary">FlowStrix</h1>
            <span className="text-xs bg-forge-100 dark:bg-accent/15 text-forge-700 dark:text-accent px-2 py-0.5 rounded-full font-medium">
              v0.1.0
            </span>
          </div>

          <div className="flex items-center gap-4 text-sm">
            {health && (
              <>
                <span className={`flex items-center gap-1.5 ${health.gateway_configured ? 'text-green-600 dark:text-success' : 'text-amber-600 dark:text-warning'}`}>
                  <span className={`w-2 h-2 rounded-full ${health.gateway_configured ? 'bg-green-500 dark:bg-success' : 'bg-amber-500 dark:bg-warning'}`} />
                  {health.gateway_configured ? 'Gateway Connected' : 'No Gateway'}
                </span>
                {health.model && (
                  <span className="text-gray-500 dark:text-secondary">
                    Model: <code className="bg-gray-100 dark:bg-surface-2 px-1.5 py-0.5 rounded text-xs">{health.model}</code>
                  </span>
                )}
              </>
            )}

            <button
              onClick={toggleTheme}
              aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
              className="p-1.5 rounded-md text-gray-500 dark:text-secondary hover:bg-gray-100 dark:hover:bg-surface-2 transition-colors"
            >
              {theme === 'dark' ? (
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
                </svg>
              ) : (
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
                </svg>
              )}
            </button>
          </div>
        </div>
      </header>

      {/* Main */}
      <main className="flex-1 max-w-6xl mx-auto w-full px-6 py-8">
        {children}
      </main>

      {/* Footer */}
      <footer className="border-t border-gray-100 dark:border-border-subtle px-6 py-3 text-center text-xs text-gray-400 dark:text-muted">
        FlowStrix — Agent-native workflow engine
      </footer>
    </div>
  )
}
