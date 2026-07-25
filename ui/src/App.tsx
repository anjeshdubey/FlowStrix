import { Navigate, Route, Routes } from 'react-router-dom'
import { Compass } from 'lucide-react'
import AgentWorkspace from './routes/AgentWorkspace'
import ChatPage from './routes/ChatPage'
import JourneysPage from './routes/JourneysPage'
import KnowledgePage from './routes/KnowledgePage'
import Landing from './routes/Landing'
import SimulationsPage from './routes/SimulationsPage'
import TracesPage from './routes/TracesPage'

function EmptyAgentState() {
  return (
    <div className="flex items-center justify-center h-64 text-muted text-2">
      <div className="text-center">
        <Compass size={44} className="mx-auto mb-3 text-muted" strokeWidth={1.5} />
        <p>Pick an agent from the rail to get started.</p>
      </div>
    </div>
  )
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/agents" element={<AgentWorkspace />}>
        <Route index element={<EmptyAgentState />} />
        <Route path=":agentId" element={<Navigate to="journeys" replace />} />
        <Route path=":agentId/journeys" element={<JourneysPage />} />
        <Route path=":agentId/knowledge" element={<KnowledgePage />} />
        <Route path=":agentId/simulations" element={<SimulationsPage />} />
        <Route path=":agentId/traces" element={<TracesPage />} />
        <Route path=":agentId/chat" element={<ChatPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
