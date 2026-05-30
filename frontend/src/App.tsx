import { BrowserRouter as Router, Routes, Route, NavLink } from 'react-router-dom';
import DashboardPage from './pages/DashboardPage';
import ReconciliationQueuePage from './pages/ReconciliationQueuePage'; // New import
import EscalationsPage from './pages/EscalationsPage';
import ReportsPage from './pages/ReportsPage';
import PrimeRobotMonitoringPage from './pages/PrimeRobotMonitoringPage'; // New import
import AuditLogsPage from './pages/AuditLogsPage'; // New import
import './App.css';
// import './Dashboard.css'; // Removed as requested for redesign considerations

function App() {
  return (
    <Router>
      <div className="dashboard-container">
        <aside className="sidebar">
          <h2>Auditor</h2>
          <nav>
            <NavLink to="/" end>Dashboard</NavLink>
            <NavLink to="/reconciliation">Reconciliation Queue</NavLink> {/* Updated */}
            <NavLink to="/escalations">Escalations</NavLink>
            <NavLink to="/reports">Reports</NavLink>
            <NavLink to="/prime-robot-monitoring">Prime Robot Monitoring</NavLink> {/* New */}
            <NavLink to="/audit-logs">Audit Logs</NavLink> {/* New */}
          </nav>
        </aside>

        <main className="main-content">
          <Routes>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/reconciliation" element={<ReconciliationQueuePage />} /> {/* Updated */}
            <Route path="/escalations" element={<EscalationsPage />} />
            <Route path="/reports" element={<ReportsPage />} />
            <Route path="/prime-robot-monitoring" element={<PrimeRobotMonitoringPage />} /> {/* New */}
            <Route path="/audit-logs" element={<AuditLogsPage />} /> {/* New */}
          </Routes>
        </main>
      </div>
    </Router>
  );
}

export default App;
