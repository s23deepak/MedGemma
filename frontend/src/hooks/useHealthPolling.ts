import { useEffect } from 'react'
import { useDispatch } from 'react-redux'
import { AppDispatch } from '../store/store'
import { setHealthUpdate, setHealthError } from '../store/healthSlice'
import { HealthResponse, StatusResponse, CircuitBreakerState } from '../types/api'

/**
 * Hook that polls /api/health and /api/status every 5 seconds
 * Updates Redux store with health and circuit breaker state
 */
export default function useHealthPolling() {
  const dispatch = useDispatch<AppDispatch>()

  useEffect(() => {
    let pollInterval: NodeJS.Timeout

    const pollHealth = async () => {
      try {
        // Fetch both health and status endpoints
        const [healthRes, statusRes] = await Promise.all([
          fetch('/api/health'),
          fetch('/api/status'),
        ])

        if (!healthRes.ok || !statusRes.ok) {
          throw new Error('Health check failed')
        }

        const health = (await healthRes.json()) as HealthResponse
        const status = (await statusRes.json()) as StatusResponse

        // Extract services and circuit breakers
        const services: Record<string, 'ready' | 'unavailable'> = {}
        Object.entries(health.services || {}).forEach(([key, value]) => {
          services[key] = value.status as 'ready' | 'unavailable'
        })

        const circuitBreakers: Record<string, CircuitBreakerState> = {}
        Object.entries(status.circuit_breakers || {}).forEach(([key, value]) => {
          circuitBreakers[key] = value as CircuitBreakerState
        })

        // Check if any service is unavailable
        const anyUnavailable = Object.values(services).some((s) => s === 'unavailable')
        const isHealthy = !anyUnavailable

        dispatch(
          setHealthUpdate({
            services,
            circuitBreakers,
            isHealthy,
          })
        )
      } catch (error) {
        const message = error instanceof Error ? error.message : 'Health check failed'
        dispatch(setHealthError(message))
      }
    }

    // Poll immediately on mount
    pollHealth()

    // Then set up interval for every 5 seconds
    pollInterval = setInterval(pollHealth, 5000)

    return () => {
      if (pollInterval) clearInterval(pollInterval)
    }
  }, [dispatch])
}
