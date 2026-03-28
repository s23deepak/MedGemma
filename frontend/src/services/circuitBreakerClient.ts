import { CircuitBreakerState } from '../types/api'

/**
 * Check if any circuit breaker is in a problematic state
 * @param circuitBreakers - Circuit breaker states from /api/status
 * @param targetServices - Services to check (default: all)
 * @returns true if any breaker is not CLOSED
 */
export function hasOpenCircuitBreakers(
  circuitBreakers: Record<string, CircuitBreakerState>,
  targetServices?: string[]
): boolean {
  const services = targetServices || Object.keys(circuitBreakers)
  return services.some((service) => {
    const breaker = circuitBreakers[service]
    return breaker && breaker.state !== 'CLOSED'
  })
}

/**
 * Get the most critical circuit breaker state
 * @param circuitBreakers - Circuit breaker states
 * @returns 'CLOSED' | 'HALF_OPEN' | 'OPEN' (in order of severity)
 */
export function getMostCriticalBreakerState(
  circuitBreakers: Record<string, CircuitBreakerState>
): 'CLOSED' | 'HALF_OPEN' | 'OPEN' {
  let mostCritical: 'CLOSED' | 'HALF_OPEN' | 'OPEN' = 'CLOSED'

  for (const breaker of Object.values(circuitBreakers)) {
    if (breaker.state === 'OPEN') {
      return 'OPEN'
    }
    if (breaker.state === 'HALF_OPEN') {
      mostCritical = 'HALF_OPEN'
    }
  }

  return mostCritical
}

/**
 * Fetch current circuit breaker status
 * @returns Status response or null if check fails
 */
export async function getCurrentCircuitBreakerStatus(): Promise<
  Record<string, CircuitBreakerState> | null
> {
  try {
    const response = await fetch('/api/status', {
      signal: AbortSignal.timeout(5000), // 5s timeout
    })

    if (!response.ok) {
      return null
    }

    const data = await response.json()
    return data.circuit_breakers || {}
  } catch (error) {
    console.warn('Failed to fetch circuit breaker status:', error)
    return null
  }
}

/**
 * Check if request should be retried based on circuit breaker state
 * @param response - Fetch response
 * @param circuitBreakerState - Current CB state
 * @returns true if request should be retried
 */
export function shouldRetryBasedOnCircuitBreaker(
  status: number,
  circuitBreakerState: 'CLOSED' | 'HALF_OPEN' | 'OPEN'
): boolean {
  // 5xx errors should be retried if not in OPEN state
  if (status >= 500 && status < 600) {
    return circuitBreakerState !== 'OPEN'
  }

  // Timeout or connection errors should be retried
  return false
}

/**
 * Get retry delay based on circuit breaker state
 * @param state - Circuit breaker state
 * @param attempt - Attempt number (0-based)
 * @returns Delay in milliseconds
 */
export function getCircuitBreakerRetryDelay(
  state: 'CLOSED' | 'HALF_OPEN' | 'OPEN',
  attempt: number
): number {
  if (state === 'OPEN') {
    // OPEN state: wait longer before next attempt (service is down)
    return Math.min(5000 * Math.pow(2, attempt), 60000)
  }

  if (state === 'HALF_OPEN') {
    // HALF_OPEN state: wait moderately (service is recovering)
    return Math.min(2000 * Math.pow(1.5, attempt), 30000)
  }

  // CLOSED state: normal backoff (service is healthy)
  return Math.min(1000 * Math.pow(2, attempt), 10000)
}
