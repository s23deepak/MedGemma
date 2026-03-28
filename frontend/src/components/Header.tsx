import { useSelector } from 'react-redux'
import { RootState } from '../store/store'
import HealthIndicator from './HealthIndicator'
import CircuitBreakerStatus from './CircuitBreakerStatus'
import '../styles/components.css'

export default function Header() {
  const isHealthy = useSelector((state: RootState) => state.health.isHealthy)

  return (
    <header className="bg-white border-b border-gray-200 shadow-sm">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between items-center h-16">
          {/* Logo/Title */}
          <div className="flex-shrink-0 flex items-center">
            <h1 className="text-xl font-semibold text-gray-900">MedGemma</h1>
          </div>

          {/* Navigation */}
          <nav className="hidden md:flex space-x-8">
            <a href="/" className="text-gray-600 hover:text-gray-900 text-sm font-medium">
              Encounters
            </a>
            <a href="/ai-portal" className="text-gray-600 hover:text-gray-900 text-sm font-medium">
              AI Portal
            </a>
            <a href="/history" className="text-gray-600 hover:text-gray-900 text-sm font-medium">
              History
            </a>
            <a href="/compliance" className="text-gray-600 hover:text-gray-900 text-sm font-medium">
              Compliance
            </a>
            <a href="/monitoring" className="text-gray-600 hover:text-gray-900 text-sm font-medium">
              Monitoring
            </a>
          </nav>

          {/* Health Status Indicators */}
          <div className="flex items-center space-x-4">
            <HealthIndicator />
            {!isHealthy && <CircuitBreakerStatus />}
          </div>
        </div>
      </div>
    </header>
  )
}
