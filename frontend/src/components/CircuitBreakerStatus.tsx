import { useSelector } from 'react-redux'
import { RootState } from '../store/store'
import { getCircuitBreakerColor, formatServiceName } from '../utils/formatters'

export default function CircuitBreakerStatus() {
  const { circuitBreakers } = useSelector((state: RootState) => state.health)

  // Filter for non-CLOSED breakers
  const activeBreakers = Object.entries(circuitBreakers).filter(
    ([, state]) => state.state !== 'CLOSED'
  )

  if (activeBreakers.length === 0) {
    return null
  }

  return (
    <div className="flex items-center space-x-2">
      <span className="text-sm font-medium text-gray-500">Services:</span>
      <div className="flex gap-2">
        {activeBreakers.map(([name, breaker]) => (
          <div
            key={name}
            className={`relative inline-flex items-center gap-1 px-2 py-1 rounded text-xs font-medium ${getCircuitBreakerColor(
              breaker.state
            )} cursor-help group`}
          >
            {/* Service status box */}
            <span>{formatServiceName(name)}</span>
            <span className="text-xs">
              {breaker.state === 'OPEN' && '✕'}
              {breaker.state === 'HALF_OPEN' && '⚠'}
            </span>

            {/* Tooltip */}
            <div className="absolute invisible group-hover:visible bg-gray-900 text-white text-xs rounded py-2 px-3 bottom-full right-0 mb-1 whitespace-nowrap z-10 w-max">
              <div className="font-semibold">{formatServiceName(name)}</div>
              <div>State: {breaker.state}</div>
              {breaker.failure_count !== undefined && (
                <div>Failures: {breaker.failure_count}</div>
              )}
              {breaker.recovery_timeout !== undefined && (
                <div>Recovery in: {(breaker.recovery_timeout / 1000).toFixed(0)}s</div>
              )}
              <div
                className="absolute top-full left-1/2 transform -translate-x-1/2 w-0 h-0 border-l-4 border-r-4 border-t-4 border-l-transparent border-r-transparent"
                style={{ borderTopColor: 'rgb(17, 24, 39)' }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
