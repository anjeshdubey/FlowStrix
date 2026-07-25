import { createContext, useContext, useEffect, useState } from 'react'
import { getHealth } from '../api'
import { HealthResponse } from '../types'

const HealthContext = createContext<HealthResponse | null>(null)

export function HealthProvider({ children }: { children: React.ReactNode }) {
  const [health, setHealth] = useState<HealthResponse | null>(null)

  useEffect(() => {
    getHealth()
      .then(setHealth)
      .catch(() => setHealth(null))
  }, [])

  return <HealthContext.Provider value={health}>{children}</HealthContext.Provider>
}

export function useHealth() {
  return useContext(HealthContext)
}
