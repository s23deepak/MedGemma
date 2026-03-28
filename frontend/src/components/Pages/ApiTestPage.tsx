import { useState } from 'react'
import { useNotification } from '../hooks/useNotification'
import { apiClient } from '../services/api'
import { formatBackoffTime } from '../utils/exponentialBackoff'

interface TestResult {
  endpoint: string
  status: number
  success: boolean
  retriesPerformed: number
  totalTime: number
}

export default function ApiTestPage() {
  const notification = useNotification()
  const [results, setResults] = useState<TestResult[]>([])
  const [loading, setLoading] = useState(false)

  const testEndpoint = async (endpoint: string) => {
    setLoading(true)
    const startTime = Date.now()
    let retriesPerformed = 0

    try {
      const response = await apiClient.get(endpoint, {
        retryOptions: {
          maxRetries: 3,
          onRetry: (attempt, reason, delay) => {
            retriesPerformed = attempt
            notification.info(
              `Retrying ${endpoint} in ${formatBackoffTime(delay)}... (Attempt ${attempt})`
            )
          },
        },
      })

      const totalTime = Date.now() - startTime

      if (response.ok) {
        notification.success(`✓ ${endpoint} successful (${totalTime}ms)`)
        setResults((prev) => [
          ...prev,
          { endpoint, status: response.status, success: true, retriesPerformed, totalTime },
        ])
      } else {
        notification.error(`✗ ${endpoint} failed: ${response.error}`)
        setResults((prev) => [
          ...prev,
          { endpoint, status: response.status, success: false, retriesPerformed, totalTime },
        ])
      }
    } catch (error) {
      notification.error(`✗ ${endpoint} error: ${error}`)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="p-8 max-w-4xl mx-auto">
      <h1 className="text-3xl font-bold mb-6 text-gray-900">API Retry Logic Test</h1>

      <div className="bg-white rounded-lg shadow p-6 mb-6">
        <h2 className="text-lg font-semibold mb-4 text-gray-800">Test Endpoints</h2>
        <div className="space-y-3">
          <button
            onClick={() => testEndpoint('/api/health')}
            disabled={loading}
            className="w-full bg-blue-600 hover:bg-blue-700 disabled:bg-gray-400 text-white font-medium py-2 px-4 rounded transition"
          >
            Test /api/health
          </button>
          <button
            onClick={() => testEndpoint('/api/status')}
            disabled={loading}
            className="w-full bg-blue-600 hover:bg-blue-700 disabled:bg-gray-400 text-white font-medium py-2 px-4 rounded transition"
          >
            Test /api/status
          </button>
          <button
            onClick={() => testEndpoint('/api/non-existent')}
            disabled={loading}
            className="w-full bg-yellow-600 hover:bg-yellow-700 disabled:bg-gray-400 text-white font-medium py-2 px-4 rounded transition"
          >
            Test 404 (Should Not Retry)
          </button>
        </div>
      </div>

      <div className="bg-white rounded-lg shadow p-6">
        <h2 className="text-lg font-semibold mb-4 text-gray-800">
          Test Results ({results.length})
        </h2>
        {results.length === 0 ? (
          <p className="text-gray-500">No test results yet. Click a button above to test.</p>
        ) : (
          <div className="space-y-3 max-h-96 overflow-y-auto">
            {results.map((result, i) => (
              <div
                key={i}
                className={`border-l-4 p-4 rounded ${
                  result.success
                    ? 'border-green-500 bg-green-50'
                    : 'border-red-500 bg-red-50'
                }`}
              >
                <div className="flex justify-between items-start mb-2">
                  <span className={`font-semibold ${result.success ? 'text-green-700' : 'text-red-700'}`}>
                    {result.success ? '✓' : '✗'} {result.endpoint}
                  </span>
                  <span className="text-sm text-gray-600">{result.totalTime}ms</span>
                </div>
                <div className="text-sm text-gray-700">
                  Status: {result.status} | Retries: {result.retriesPerformed}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="mt-6 bg-blue-50 border border-blue-200 rounded-lg p-4">
        <h3 className="font-semibold text-blue-900 mb-2">How It Works</h3>
        <ul className="text-sm text-blue-800 space-y-1 ml-4 list-disc">
          <li>429 errors retry with 30s, 60s, 120s delays</li>
          <li>5xx errors retry with exponential backoff (depends on circuit breaker state)</li>
          <li>4xx errors do NOT retry (client error)</li>
          <li>Timeout/network errors retry with standard backoff</li>
          <li>Circuit breaker state affects retry strategy and delays</li>
          <li>Toasts show retry countdown and attempt number</li>
        </ul>
      </div>
    </div>
  )
}
