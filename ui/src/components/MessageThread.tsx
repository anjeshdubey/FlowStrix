interface MessageThreadProps {
  messages: Array<{ role: string; content: string }>
}

export default function MessageThread({ messages }: MessageThreadProps) {
  if (messages.length === 0) return null

  return (
    <div className="space-y-2">
      <h3 className="text-sm font-semibold text-secondary uppercase tracking-wide">
        Agent Response
      </h3>
      <div className="space-y-2">
        {messages.map((msg, i) => (
          <div
            key={i}
            className={`p-3 rounded-lg text-sm ${
              msg.role === 'assistant'
                ? 'bg-accent/10 border border-accent/30 text-primary'
                : msg.role === 'user'
                ? 'bg-surface-2 border border-border-subtle text-primary'
                : 'bg-surface-1 border border-border-subtle text-secondary'
            }`}
          >
            <div className="flex items-center gap-2 mb-1">
              <span className="text-[10px] font-semibold uppercase tracking-wide text-muted">
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
