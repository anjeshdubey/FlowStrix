interface MessageThreadProps {
  messages: Array<{ role: string; content: string }>
}

export default function MessageThread({ messages }: MessageThreadProps) {
  if (messages.length === 0) return null

  return (
    <div className="space-y-2">
      <h3 className="text-sm font-semibold text-gray-700 dark:text-secondary uppercase tracking-wide">
        Agent Response
      </h3>
      <div className="space-y-2">
        {messages.map((msg, i) => (
          <div
            key={i}
            className={`p-3 rounded-lg text-sm ${
              msg.role === 'assistant'
                ? 'bg-forge-50 dark:bg-accent/10 border border-forge-200 dark:border-accent/30 text-forge-900 dark:text-primary'
                : msg.role === 'user'
                ? 'bg-gray-100 dark:bg-surface-2 border border-gray-200 dark:border-border-subtle text-gray-800 dark:text-primary'
                : 'bg-gray-50 dark:bg-surface-1 border border-gray-200 dark:border-border-subtle text-gray-600 dark:text-secondary'
            }`}
          >
            <div className="flex items-center gap-2 mb-1">
              <span className="text-[10px] font-semibold uppercase tracking-wide text-gray-500 dark:text-muted">
                {msg.role}
              </span>
            </div>
            <p className="whitespace-pre-wrap">{msg.content}</p>
          </div>
        ))}
      </div>
    </div>
  )
}
