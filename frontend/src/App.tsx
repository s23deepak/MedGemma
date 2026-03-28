import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom'
import Header from './components/Header'
import HealthPolling from './hooks/useHealthPolling'
import './styles/globals.css'

// Page placeholders - will be replaced with actual migrated components
const EncounterPage = () => <div className="p-8"><h1>Encounter Page (Coming Soon)</h1></div>
const AiPortalPage = () => <div className="p-8"><h1>AI Portal (Coming Soon)</h1></div>
const MonitoringDashboard = () => <div className="p-8"><h1>Monitoring Dashboard (Coming Soon)</h1></div>
const HistoryPage = () => <div className="p-8"><h1>History (Coming Soon)</h1></div>
const CompliancePage = () => <div className="p-8"><h1>Compliance (Coming Soon)</h1></div>

function App() {
  // Start health polling on app load
  HealthPolling()

  return (
    <Router>
      <div className="min-h-screen bg-gray-50">
        <Header />
        <main className="flex-1">
          <Routes>
            <Route path="/" element={<Navigate to="/encounters" replace />} />
            <Route path="/encounters" element={<EncounterPage />} />
            <Route path="/ai-portal" element={<AiPortalPage />} />
            <Route path="/monitoring" element={<MonitoringDashboard />} />
            <Route path="/history" element={<HistoryPage />} />
            <Route path="/compliance" element={<CompliancePage />} />
          </Routes>
        </main>
      </div>
    </Router>
  )
}

export default App
