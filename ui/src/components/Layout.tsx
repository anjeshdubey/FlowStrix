import { HealthResponse } from '../types'

interface LayoutProps {
  children: React.ReactNode
  health: HealthResponse | null
}

export default function Layout({ children, health }: LayoutProps) {
  return (
    <div className="min-h-screen flex flex-col">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 px-6 py-4">
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-forge-600 rounded-lg flex items-center justify-center">
              <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
            </div>
            <h1 className="text-xl font-bold text-gray-900">FlowStrix</h1>
            <span className="text-xs bg-forge-100 text-forge-700 px-2 py-0.5 rounded-full font-medium">
              v0.1.0
            </span>
          </div>

          <div className="flex items-center gap-4 text-sm">
            {health && (
              <>
                <span className={`flex items-center gap-1.5 ${health.gateway_configured ? 'text-green-600' : 'text-amber-600'}`}>
                  <span className={`w-2 h-2 rounded-full ${health.gateway_configured ? 'bg-green-500' : 'bg-amber-500'}`} />
                  {health.gateway_configured ? 'Gateway Connected' : 'No Gateway'}
                </span>
                {health.model && (
                  <span className="text-gray-500">
                    Model: <code className="bg-gray-100 px-1.5 py-0.5 rounded text-xs">{health.model}</code>
                  </span>
                )}
              </>
            )}
          </div>
        </div>
      </header>

      {/* Main */}
      <main className="flex-1 max-w-6xl mx-auto w-full px-6 py-8">
        {children}
      </main>

      {/* Footer */}
      <footer className="border-t border-gray-100 px-6 py-3 text-center text-xs text-gray-400">
        FlowStrix — Agent-native workflow engine
      </footer>
    </div>
  )
}
