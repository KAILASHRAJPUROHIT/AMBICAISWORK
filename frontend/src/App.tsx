import { BrowserRouter as Router, Routes, Route, NavLink, Navigate, useLocation } from 'react-router-dom';
import { useState, useEffect } from 'react';
import DashboardPage from './pages/DashboardPage';
import ReconciliationQueuePage from './pages/ReconciliationQueuePage';
import EscalationsPage from './pages/EscalationsPage';
import ReportsPage from './pages/ReportsPage';
import PrimeExtractionReviewPage from './pages/PrimeExtractionReviewPage';
import AuditLogsPage from './pages/AuditLogsPage';
import MasterConsolePage from './pages/MasterConsolePage';
import SystemHealthPage from './pages/SystemHealthPage';
import LoginPage from './pages/LoginPage';
import { logout } from './api/client';
import { useSecurityProtections } from './hooks/useSecurityProtections';
import { useSessionTimeout } from './hooks/useSessionTimeout';
import './index.css';

// Protected Route Component
const ProtectedRoute = ({ children, roles, user }: { children: React.ReactElement, roles?: string[], user: any }) => {
    const token = localStorage.getItem('aradhana_session_token');
    const location = useLocation();

    console.log(`[DEBUG] ProtectedRoute: path=${location.pathname}, hasToken=${!!token}, hasUser=${!!user}, role=${user?.role}`);

    if (!token || !user) {
        console.warn(`[DEBUG] ProtectedRoute: Unauthorized access attempt to ${location.pathname}. Redirecting to /login.`);
        return <Navigate to="/login" state={{ from: location }} replace />;
    }

    if (roles && user.role && !roles.includes(user.role.toLowerCase())) {
        console.warn(`[DEBUG] ProtectedRoute: Insufficient permissions for ${user.role} on ${location.pathname}. Redirecting to /dashboard.`);
        return <Navigate to="/dashboard" replace />;
    }

    return children;
};

function App() {
  const [user, setUser] = useState<any>(() => {
    const saved = localStorage.getItem('user');
    console.log(`[DEBUG] App: Initializing user state from localStorage. hasSavedUser=${!!saved}`);
    return saved ? JSON.parse(saved) : null;
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const handleAuthSuccess = () => {
        const saved = localStorage.getItem('user');
        if (saved) {
            console.log("[DEBUG] App: Auth success event received. Updating user state.");
            setUser(JSON.parse(saved));
        }
    };
    window.addEventListener('aradhana-auth-success', handleAuthSuccess);
    return () => window.removeEventListener('aradhana-auth-success', handleAuthSuccess);
  }, []);

  useEffect(() => {
    // PRE-FLIGHT CLEANUP: Remove old keys from previous versions
    ['token', 'sessionToken', 'auth_token', 'session_token'].forEach(k => localStorage.removeItem(k));

    const checkAuth = async () => {
        const token = localStorage.getItem('aradhana_session_token');
        console.log(`[DEBUG] App.checkAuth: tokenFound=${!!token}`);

        if (token) {
            try {
                console.log(`[DEBUG] App.checkAuth: Validating session with backend...`);
                const response = await fetch(`${window.location.origin}/api/auth/validate-session`, {
                   headers: {
                      'X-Session-Token': token
                   }
                });
                
                console.log(`[DEBUG] App.checkAuth: validate-session responseStatus=${response.status}`);

                if (!response.ok) {
                    const errorText = await response.text();
                    console.error(`[DEBUG] App.checkAuth: Backend rejected session. Status: ${response.status}, Body: ${errorText}`);
                    throw new Error(`Session validation failed with status ${response.status}`);
                }
                
                const validationData = await response.json();
                console.log(`[DEBUG] App.checkAuth: validationDataReceived=`, validationData);
                
                if (validationData.valid && validationData.user) {
                    console.log(`[DEBUG] App.checkAuth: Session is VALID. User: ${validationData.user.employee_id}`);
                    setUser(validationData.user);
                    localStorage.setItem('user', JSON.stringify(validationData.user));
                } else {
                    throw new Error("Invalid session data structure");
                }
            } catch (err) {
                console.error("[DEBUG] App.checkAuth: ERROR during validation:", err);
                // Only clear if we are NOT on login page? 
                // Actually, if it fails validation on startup, we should clear.
                localStorage.removeItem('aradhana_session_token');
                localStorage.removeItem('user');
                setUser(null);
            }
        } else {
            console.log(`[DEBUG] App.checkAuth: No token found. User is unauthenticated.`);
            setUser(null);
        }
        setLoading(false);
    };
    checkAuth();
  }, []);

  const handleLogout = async () => {
    try { await logout(); } catch(e) {}
    localStorage.removeItem('aradhana_session_token');
    localStorage.removeItem('user');
    setUser(null);
    window.location.href = '/login';
  };

  useSecurityProtections(user);
  useSessionTimeout(user, handleLogout);

  if (loading) {
    return <div className="h-screen flex items-center justify-center font-black text-2xl uppercase tracking-widest animate-pulse">Initializing Secure Environment...</div>;
  }

  const role = user?.role?.toLowerCase() || '';

  return (
    <Router>
      <Routes>
        <Route path="/login" element={!user ? <LoginPage /> : <Navigate to="/dashboard" replace />} />
        
        <Route path="/*" element={
          <ProtectedRoute user={user}>
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
                    <NavLink to="/dashboard" className={({ isActive }) => `flex items-center p-4 rounded-2xl text-xs font-black uppercase tracking-widest transition-all ${isActive ? 'bg-white text-black shadow-lg shadow-white/10' : 'text-gray-500 hover:text-white'}`}>
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
                    <Route path="/" element={<Navigate to="/dashboard" replace />} />
                    <Route path="/dashboard" element={<DashboardPage />} />
                    <Route path="/master-console" element={
                        <ProtectedRoute user={user} roles={['admin', 'owner']}><MasterConsolePage /></ProtectedRoute>
                    } />
                    <Route path="/reconciliation" element={
                        <ProtectedRoute user={user} roles={['admin', 'accountant', 'owner']}><ReconciliationQueuePage /></ProtectedRoute>
                    } />
                    <Route path="/escalations" element={
                        <ProtectedRoute user={user} roles={['admin', 'owner']}><EscalationsPage /></ProtectedRoute>
                    } />
                    <Route path="/reports" element={
                        <ProtectedRoute user={user} roles={['admin', 'owner', 'accountant']}><ReportsPage /></ProtectedRoute>
                    } />
                    <Route path="/prime-extraction-review" element={
                        <ProtectedRoute user={user} roles={['admin', 'accountant', 'owner']}><PrimeExtractionReviewPage /></ProtectedRoute>
                    } />
                    <Route path="/audit-logs" element={
                        <ProtectedRoute user={user} roles={['admin', 'owner', 'accountant', 'developer']}><AuditLogsPage /></ProtectedRoute>
                    } />
                    <Route path="/system-health" element={
                        <ProtectedRoute user={user} roles={['admin', 'owner', 'developer']}><SystemHealthPage /></ProtectedRoute>
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
