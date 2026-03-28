import { useSelector } from 'react-redux'
import { RootState } from '../store/store'

export default function HealthIndicator() {
  const { isHealthy, error, services } = useSelector((state: RootState) => state.health)

  // Determine indicator color and state
  let indicatorColor = 'bg-green-500'
  let indicatorState = 'Healthy'
  let hoverText = 'All services operational'

  if (error) {
    indicatorColor = 'bg-red-500'
    indicatorState = 'Error'
    hoverText = `Check failed: ${error}`
  } else if (!isHealthy) {
    indicatorColor = 'bg-yellow-500'
    indicatorState = 'Degraded'
    const unavailable = Object.entries(services)
      .filter(([, status]) => status === 'unavailable')
      .map(([key]) => key)
    hoverText = `Unavailable: ${unavailable.join(', ')}`
  }

  return (
    <div className="flex items-center space-x-2">
      {/* Animated status indicator */}
      <div className="relative inline-flex items-center justify-center">
        <div className={`w-3 h-3 rounded-full ${indicatorColor} ${isHealthy ? 'pulse' : ''}`} />
        <div
          className={`absolute w-3 h-3 rounded-full ${indicatorColor} ${
            isHealthy ? 'pulse-ring' : ''
          }`}
        />
      </div>

      {/* Status text with tooltip */}
      <div className="relative group">
        <span className="text-sm font-medium text-gray-700 cursor-help">
          {indicatorState}
        </span>
        <div className="absolute invisible group-hover:visible bg-gray-900 text-white text-xs rounded py-1 px-2 right-0 top-full mt-1 whitespace-nowrap z-10">
          {hoverText}
          <div
            className="absolute bottom-full right-2 w-0 h-0 border-l-4 border-r-4 border-t-4 border-l-transparent border-r-transparent"
            style={{ borderTopColor: 'rgb(17, 24, 39)' }}
          />
        </div>
      </div>
    </div>
  )
}
