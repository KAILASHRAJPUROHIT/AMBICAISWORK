import { BrowserRouter as Router, Routes, Route, NavLink, Navigate, useLocation } from 'react-router-dom';
import { useState, useEffect } from 'react';
import DashboardPage from './pages/DashboardPage';
import ReconciliationQueuePage from './pages/ReconciliationQueuePage';
import EscalationsPage from './pages/EscalationsPage';
import ReportsPage from './pages/ReportsPage';
import PrimeExtractionReviewPage from './pages/PrimeExtractionReviewPage';
import AuditLogsPage from './pages/AuditLogsPage';
import MasterConsolePage from './pages/MasterConsolePage';
import LoginPage from './pages/LoginPage';
import BankActivityPage from './pages/BankActivityPage';
import { getMe, logout } from './api/client';
import './index.css';

// Protected Route Component
const ProtectedRoute = ({ children, roles }: { children: React.ReactElement, roles?: string[] }) => {
    const token = localStorage.getItem('session_token');
    const userStr = localStorage.getItem('user');
    const user = userStr ? JSON.parse(userStr) : null;
    const location = useLocation();

    if (!token || !user) {
        return <Navigate to="/login" state={{ from: location }} replace />;
    }

    if (roles && !roles.includes(user.role.toLowerCase())) {
        return <Navigate to="/" replace />;
    }

    return children;
};

function App() {
  const [user, setUser] = useState<any>(() => {
    const saved = localStorage.getItem('user');
    return saved ? JSON.parse(saved) : null;
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const checkAuth = async () => {
        const token = localStorage.getItem('session_token');
        if (token) {
            try {
                const userData = await getMe();
                // Ensure backend returned a valid object before overriding local cache
                if (userData && userData.role) {
                    setUser(userData);
                    localStorage.setItem('user', JSON.stringify(userData));
                }
            } catch (err) {
                console.error("Auth check failed", err);
                localStorage.removeItem('session_token');
                localStorage.removeItem('user');
                setUser(null);
            }
        } else {
            setUser(null);
        }
        setLoading(false);
    };
    checkAuth();
  }, []);

  const handleLogout = async () => {
    try { await logout(); } catch(e) {}
    setUser(null);
    window.location.href = '/login';
  };

  if (loading) {
    return <div className="h-screen flex items-center justify-center font-black text-2xl uppercase tracking-widest animate-pulse">Initializing Secure Environment...</div>;
  }

  const role = user?.role?.toLowerCase() || '';

  return (
    <Router>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/bank-activity" element={<BankActivityPage />} />
        
        <Route path="/*" element={
          <ProtectedRoute>
            <div className="flex min-h-screen bg-gray-100 font-sans">
                {/* Sidebar */}
                <aside className="w-72 bg-black shadow-2xl p-8 flex flex-col text-white">
                  <div className="flex items-center space-x-3 mb-12">
                    <div className="w-10 h-10 bg-white text-black flex items-center justify-center font-black rounded-xl text-xl">A</div>
                    <div className="text-xl font-black uppercase tracking-tighter">
                        Aradhana <span className="text-gray-500">Auditor</span>
                    </div>
                  </div>

                  <nav className="flex-1 space-y-2">
                    <NavLink to="/" end className={({ isActive }) => `flex items-center p-4 rounded-2xl text-xs font-black uppercase tracking-widest transition-all ${isActive ? 'bg-white text-black shadow-lg shadow-white/10' : 'text-gray-500 hover:text-white'}`}>
                      Dashboard
                    </NavLink>
                    
                    {['admin', 'owner'].includes(role) && (
                      <NavLink to="/master-console" className={({ isActive }) => `flex items-center p-4 rounded-2xl text-xs font-black uppercase tracking-widest transition-all ${isActive ? 'bg-white text-black shadow-lg shadow-white/10' : 'text-gray-500 hover:text-white'}`}>
                        Master Console
                      </NavLink>
                    )}

                    {['admin', 'accountant', 'owner'].includes(role) && (
                      <NavLink to="/reconciliation" className={({ isActive }) => `flex items-center p-4 rounded-2xl text-xs font-black uppercase tracking-widest transition-all ${isActive ? 'bg-white text-black shadow-lg shadow-white/10' : 'text-gray-500 hover:text-white'}`}>
                        Reconciliation
                      </NavLink>
                    )}
                    {['admin', 'owner', 'accountant'].includes(role) && (
                      <NavLink to="/bank-activity" className={({ isActive }) => `flex items-center p-4 rounded-2xl text-xs font-black uppercase tracking-widest transition-all ${isActive ? 'bg-white text-black shadow-lg shadow-white/10' : 'text-gray-500 hover:text-white'}`}>
                        Bank Activity
                      </NavLink>
                    )}
                    {['admin', 'owner'].includes(role) && (
                      <NavLink to="/escalations" className={({ isActive }) => `flex items-center p-4 rounded-2xl text-xs font-black uppercase tracking-widest transition-all ${isActive ? 'bg-white text-black shadow-lg shadow-white/10' : 'text-gray-500 hover:text-white'}`}>
                        Escalations
                      </NavLink>
                    )}
                    {['admin', 'owner', 'accountant'].includes(role) && (
                      <NavLink to="/reports" className={({ isActive }) => `flex items-center p-4 rounded-2xl text-xs font-black uppercase tracking-widest transition-all ${isActive ? 'bg-white text-black shadow-lg shadow-white/10' : 'text-gray-500 hover:text-white'}`}>
                        Reports
                      </NavLink>
                    )}
                    {['admin', 'accountant', 'owner'].includes(role) && (
                      <NavLink to="/prime-extraction-review" className={({ isActive }) => `flex items-center p-4 rounded-2xl text-xs font-black uppercase tracking-widest transition-all ${isActive ? 'bg-white text-black shadow-lg shadow-white/10' : 'text-gray-500 hover:text-white'}`}>
                        Extraction Review
                      </NavLink>
                    )}
                    {['admin', 'owner', 'accountant', 'developer'].includes(role) && (
                      <NavLink to="/audit-logs" className={({ isActive }) => `flex items-center p-4 rounded-2xl text-xs font-black uppercase tracking-widest transition-all ${isActive ? 'bg-white text-black shadow-lg shadow-white/10' : 'text-gray-500 hover:text-white'}`}>
                        Audit Logs
                      </NavLink>
                    )}
                    {['admin', 'owner', 'developer'].includes(role) && (
                      <NavLink to="/system-health" className={({ isActive }) => `flex items-center p-4 rounded-2xl text-xs font-black uppercase tracking-widest transition-all ${isActive ? 'bg-white text-black shadow-lg shadow-white/10' : 'text-gray-500 hover:text-white'}`}>
                        System Health
                      </NavLink>
                    )}
                  </nav>

                  <div className="mt-auto pt-8 border-t border-white/10">
                     <div className="flex items-center space-x-4 mb-6">
                        <div className="w-10 h-10 rounded-full bg-gradient-to-tr from-blue-500 to-purple-500"></div>
                        <div>
                           <div className="text-[10px] font-black uppercase tracking-widest text-gray-500">{user?.role || 'User'}</div>
                           <div className="text-sm font-black truncate max-w-[120px]">{user?.name || 'Unknown'}</div>
                        </div>
                     </div>
                     <button onClick={handleLogout} className="w-full p-4 rounded-2xl bg-white/5 hover:bg-red-500/20 text-red-400 text-xs font-black uppercase tracking-widest transition-all border border-white/5 hover:border-red-500/50">
                        Logout Securely
                     </button>
                  </div>
                </aside>

                {/* Main content */}
                <main className="flex-1 overflow-y-auto">
                  <Routes>
                    <Route path="/" element={<DashboardPage />} />
                    <Route path="/master-console" element={
                        <ProtectedRoute roles={['admin', 'owner']}><MasterConsolePage /></ProtectedRoute>
                    } />
                    <Route path="/reconciliation" element={
                        <ProtectedRoute roles={['admin', 'accountant', 'owner']}><ReconciliationQueuePage /></ProtectedRoute>
                    } />
                    <Route path="/escalations" element={
                        <ProtectedRoute roles={['admin', 'owner']}><EscalationsPage /></ProtectedRoute>
                    } />
                    <Route path="/reports" element={
                        <ProtectedRoute roles={['admin', 'owner', 'accountant']}><ReportsPage /></ProtectedRoute>
                    } />
                    <Route path="/prime-extraction-review" element={
                        <ProtectedRoute roles={['admin', 'accountant', 'owner']}><PrimeExtractionReviewPage /></ProtectedRoute>
                    } />
                    <Route path="/audit-logs" element={
                        <ProtectedRoute roles={['admin', 'owner', 'accountant', 'developer']}><AuditLogsPage /></ProtectedRoute>
                    } />
                    <Route path="/system-health" element={
                        <ProtectedRoute roles={['admin', 'owner', 'developer']}>
                            <div className="p-8"><h1 className="text-2xl font-black uppercase">System Health</h1><p>Diagnostic page for developers.</p></div>
                        </ProtectedRoute>
                    } />
                  </Routes>
                </main>
            </div>
          </ProtectedRoute>
        } />
      </Routes>
    </Router>
  );
}

export default App;
