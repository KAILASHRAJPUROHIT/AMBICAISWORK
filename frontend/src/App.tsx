import { BrowserRouter as Router, Routes, Route, NavLink } from 'react-router-dom';
import DashboardPage from './pages/DashboardPage';
import ReconciliationQueuePage from './pages/ReconciliationQueuePage';
import EscalationsPage from './pages/EscalationsPage';
import ReportsPage from './pages/ReportsPage';
import PrimeRobotMonitoringPage from './pages/PrimeRobotMonitoringPage';
import PrimeExtractionReviewPage from './pages/PrimeExtractionReviewPage';
import AuditLogsPage from './pages/AuditLogsPage';
import './index.css'; // Global Tailwind and base styles

function App() {
  return (
    <Router>
      <div className="flex min-h-screen bg-gray-100">
        {/* Sidebar */}
        <aside className="w-64 bg-white shadow-lg p-5 flex flex-col">
          <div className="text-2xl font-bold text-gray-800 mb-8 text-center">
            Aradhana <span className="text-blue-600">Auditor</span>
          </div>
          <nav className="flex-1">
            <NavLink
              to="/"
              end
              className={({ isActive }) =>
                `flex items-center p-3 mb-3 rounded-lg text-gray-700 hover:bg-blue-50 hover:text-blue-600 transition-colors duration-200
                ${isActive ? 'bg-blue-100 text-blue-700 font-semibold' : ''}`
              }
            >
              Dashboard
            </NavLink>
            <NavLink
              to="/reconciliation"
              className={({ isActive }) =>
                `flex items-center p-3 mb-3 rounded-lg text-gray-700 hover:bg-blue-50 hover:text-blue-600 transition-colors duration-200
                ${isActive ? 'bg-blue-100 text-blue-700 font-semibold' : ''}`
              }
            >
              Reconciliation Queue
            </NavLink>
            <NavLink
              to="/escalations"
              className={({ isActive }) =>
                `flex items-center p-3 mb-3 rounded-lg text-gray-700 hover:bg-blue-50 hover:text-blue-600 transition-colors duration-200
                ${isActive ? 'bg-blue-100 text-blue-700 font-semibold' : ''}`
              }
            >
              Escalations
            </NavLink>
            <NavLink
              to="/reports"
              className={({ isActive }) =>
                `flex items-center p-3 mb-3 rounded-lg text-gray-700 hover:bg-blue-50 hover:text-blue-600 transition-colors duration-200
                ${isActive ? 'bg-blue-100 text-blue-700 font-semibold' : ''}`
              }
            >
              Reports
            </NavLink>
            <NavLink
              to="/prime-robot-monitoring"
              className={({ isActive }) =>
                `flex items-center p-3 mb-3 rounded-lg text-gray-700 hover:bg-blue-50 hover:text-blue-600 transition-colors duration-200
                ${isActive ? 'bg-blue-100 text-blue-700 font-semibold' : ''}`
              }
            >
              Prime Robot Monitoring
            </NavLink>
            <NavLink
              to="/prime-extraction-review"
              className={({ isActive }) =>
                `flex items-center p-3 mb-3 rounded-lg text-gray-700 hover:bg-blue-50 hover:text-blue-600 transition-colors duration-200
                ${isActive ? 'bg-blue-100 text-blue-700 font-semibold' : ''}`
              }
            >
              Prime Extraction Review
            </NavLink>
            <NavLink
              to="/audit-logs"
              className={({ isActive }) =>
                `flex items-center p-3 mb-3 rounded-lg text-gray-700 hover:bg-blue-50 hover:text-blue-600 transition-colors duration-200
                ${isActive ? 'bg-blue-100 text-blue-700 font-semibold' : ''}`
              }
            >
              Audit Logs
            </NavLink>
          </nav>
        </aside>

        {/* Main content */}
        <main className="flex-1 p-8 overflow-y-auto">
          <Routes>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/reconciliation" element={<ReconciliationQueuePage />} />
            <Route path="/escalations" element={<EscalationsPage />} />
            <Route path="/reports" element={<ReportsPage />} />
            <Route path="/prime-robot-monitoring" element={<PrimeRobotMonitoringPage />} />
            <Route path="/prime-extraction-review" element={<PrimeExtractionReviewPage />} />
            <Route path="/audit-logs" element={<AuditLogsPage />} />
          </Routes>
        </main>
      </div>
    </Router>
  );
}

export default App;
