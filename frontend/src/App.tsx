import { BrowserRouter as Router, Routes, Route, NavLink } from 'react-router-dom';
import DashboardPage from './pages/DashboardPage';
import ReviewsPage from './pages/ReviewsPage';
import EscalationsPage from './pages/EscalationsPage';
import ReportsPage from './pages/ReportsPage';
import './App.css';
import './Dashboard.css';

function App() {
  return (
    <Router>
      <div className="dashboard-container">
        <aside className="sidebar">
          <h2>Auditor</h2>
          <nav>
            <NavLink to="/" end>Dashboard</NavLink>
            <NavLink to="/reviews">Reviews</NavLink>
            <NavLink to="/escalations">Escalations</NavLink>
            <NavLink to="/reports">Reports</NavLink>
          </nav>
        </aside>

        <main className="main-content">
          <Routes>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/reviews" element={<ReviewsPage />} />
            <Route path="/escalations" element={<EscalationsPage />} />
            <Route path="/reports" element={<ReportsPage />} />
          </Routes>
        </main>
      </div>
    </Router>
  );
}

export default App;
