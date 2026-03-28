import { ApiErrorResponse } from '../types/api'
import { calculateBackoff, getRateLimitBackoff, getServiceRecoveryBackoff } from '../utils/exponentialBackoff'
import { getTimeoutForEndpoint } from '../utils/fetchWithTimeout'
import {
  getCurrentCircuitBreakerStatus,
  getCircuitBreakerRetryDelay,
  getMostCriticalBreakerState,
} from './circuitBreakerClient'

export interface ApiClientOptions extends RequestInit {
  timeout?: number
  retryOptions?: {
    maxRetries?: number
    baseDelay?: number
    onRetry?: (attempt: number, reason: string, delay: number) => void
  }
}

export interface ApiResponse<T> {
  data?: T
  status: number
  ok: boolean
  error?: string
}

/**
 * Centralized API client with retry logic and circuit breaker awareness
 */
export class ApiClient {
  private retryableStatuses = [408, 429, 500, 502, 503, 504]

  /**
   * Make API request with automatic retry on failure
   */
  async request<T = any>(
    endpoint: string,
    options: ApiClientOptions = {}
  ): Promise<ApiResponse<T>> {
    const { timeout = getTimeoutForEndpoint(endpoint), retryOptions = {} } = options
    const { maxRetries = 3, baseDelay = 1000, onRetry } = retryOptions

    let lastError: Error | null = null

    for (let attempt = 0; attempt <= maxRetries; attempt++) {
      try {
        const response = await this.fetchWithTimeout(endpoint, options, timeout)

        // Success - return immediately
        if (response.ok) {
          const data = await this.parseResponse<T>(response)
          return { data, status: response.status, ok: true }
        }

        // Rate limited (429)
        if (response.status === 429) {
          if (attempt < maxRetries) {
            const delay = getRateLimitBackoff(attempt)
            onRetry?.(attempt + 1, 'Rate limited (429)', delay)
            await this.delay(delay)
            continue
          }

          const error = await this.parseError(response)
          return {
            status: response.status,
            ok: false,
            error: error.detail || 'Rate limit exceeded',
          }
        }

        // Server error - check circuit breakers
        if (response.status >= 500 && response.status < 600) {
          if (attempt < maxRetries) {
            // Get circuit breaker status to inform retry decision
            const cbStatus = await getCurrentCircuitBreakerStatus()
            const cbState = cbStatus ? getMostCriticalBreakerState(cbStatus) : 'CLOSED'

            if (cbState === 'OPEN') {
              // Don't retry immediately if CB is open, wait longer
              const delay = getCircuitBreakerRetryDelay('OPEN', attempt)
              onRetry?.(attempt + 1, `Server error with OPEN circuit breaker`, delay)
              await this.delay(delay)
            } else if (cbState === 'HALF_OPEN') {
              // Service recovering - wait moderately
              const delay = getCircuitBreakerRetryDelay('HALF_OPEN', attempt)
              onRetry?.(attempt + 1, `Server error with HALF_OPEN circuit breaker`, delay)
              await this.delay(delay)
            } else {
              // Service healthy - standard backoff
              const delay = getServiceRecoveryBackoff(attempt)
              onRetry?.(attempt + 1, `Server error (${response.status})`, delay)
              await this.delay(delay)
            }

            continue
          }

          const error = await this.parseError(response)
          return {
            status: response.status,
            ok: false,
            error: error.detail || `Server error: ${response.status}`,
          }
        }

        // Client error - don't retry
        if (response.status >= 400 && response.status < 500) {
          const error = await this.parseError(response)
          return {
            status: response.status,
            ok: false,
            error: error.detail || `Client error: ${response.status}`,
          }
        }

        // Other errors
        const error = await this.parseError(response)
        return {
          status: response.status,
          ok: false,
          error: error.detail || 'Unknown error',
        }
      } catch (error) {
        lastError = error as Error

        // Timeout or network error - retry with standard backoff
        if (attempt < maxRetries) {
          const delay = calculateBackoff(attempt, baseDelay)
          const reason = error instanceof Error ? error.message : 'Network error'
          onRetry?.(attempt + 1, reason, delay)
          await this.delay(delay)
          continue
        }
      }
    }

    return {
      status: 0,
      ok: false,
      error: lastError?.message || 'Request failed after max retries',
    }
  }

  /**
   * GET request
   */
  async get<T = any>(endpoint: string, options: ApiClientOptions = {}): Promise<ApiResponse<T>> {
    return this.request<T>(endpoint, { ...options, method: 'GET' })
  }

  /**
   * POST request
   */
  async post<T = any>(
    endpoint: string,
    body?: any,
    options: ApiClientOptions = {}
  ): Promise<ApiResponse<T>> {
    return this.request<T>(endpoint, {
      ...options,
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...options.headers },
      body: body ? JSON.stringify(body) : undefined,
    })
  }

  /**
   * PUT request
   */
  async put<T = any>(
    endpoint: string,
    body?: any,
    options: ApiClientOptions = {}
  ): Promise<ApiResponse<T>> {
    return this.request<T>(endpoint, {
      ...options,
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', ...options.headers },
      body: body ? JSON.stringify(body) : undefined,
    })
  }

  /**
   * DELETE request
   */
  async delete<T = any>(endpoint: string, options: ApiClientOptions = {}): Promise<ApiResponse<T>> {
    return this.request<T>(endpoint, { ...options, method: 'DELETE' })
  }

  /**
   * Private: Fetch with timeout
   */
  private async fetchWithTimeout(
    url: string,
    options: RequestInit,
    timeoutMs: number
  ): Promise<Response> {
    const controller = new AbortController()
    const timeoutHandle = setTimeout(() => controller.abort(), timeoutMs)

    try {
      return await fetch(url, {
        ...options,
        signal: controller.signal,
      })
    } finally {
      clearTimeout(timeoutHandle)
    }
  }

  /**
   * Private: Parse successful response
   */
  private async parseResponse<T>(response: Response): Promise<T | undefined> {
    const contentType = response.headers.get('content-type')
    if (contentType?.includes('application/json')) {
      try {
        return await response.json()
      } catch {
        return undefined
      }
    }
    return undefined
  }

  /**
   * Private: Parse error response
   */
  private async parseError(response: Response): Promise<ApiErrorResponse> {
    const contentType = response.headers.get('content-type')
    if (contentType?.includes('application/json')) {
      try {
        return await response.json()
      } catch {
        return { status_code: response.status, detail: response.statusText }
      }
    }
    return { status_code: response.status, detail: response.statusText }
  }

  /**
   * Private: Delay utility
   */
  private delay(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms))
  }
}

// Export singleton instance
export const apiClient = new ApiClient()
