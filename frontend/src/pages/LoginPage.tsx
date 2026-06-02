import React, { useState } from 'react';
import { login, verifyOTP } from '../api/client';
import './LoginPage.css';

const LoginPage: React.FC = () => {
    const [employeeId, setEmployeeId] = useState('');
    const [password, setPassword] = useState('');
    const [otp, setOtp] = useState('');
    const [step, setStep] = useState<'LOGIN' | 'OTP'>('LOGIN');
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const handleLogin = async (e: React.FormEvent) => {
        e.preventDefault();
        setLoading(true);
        setError(null);
        try {
            await login(employeeId, password);
            setStep('OTP');
        } catch (err: any) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    };

    const handleVerify = async (e: React.FormEvent) => {
        e.preventDefault();
        setLoading(true);
        setError(null);
        try {
            const data = await verifyOTP(employeeId, otp);
            localStorage.setItem('session_token', data.token);
            localStorage.setItem('user', JSON.stringify(data.user));
            window.location.href = '/';
        } catch (err: any) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="login-container">
            <div className="login-card">
                <div className="login-header">
                    <div className="logo-placeholder">A</div>
                    <h1>Aradhana Auditor</h1>
                    <p>Secure Financial Gateway</p>
                </div>

                {error && <div className="login-error">{error}</div>}

                {step === 'LOGIN' ? (
                    <form onSubmit={handleLogin} className="login-form">
                        <div className="form-group">
                            <label>Employee ID</label>
                            <input 
                                type="text" 
                                value={employeeId} 
                                onChange={(e) => setEmployeeId(e.target.value.toUpperCase())}
                                placeholder="Enter your ID"
                                required
                            />
                        </div>
                        <div className="form-group">
                            <label>Password</label>
                            <input 
                                type="password" 
                                value={password} 
                                onChange={(e) => setPassword(e.target.value)}
                                placeholder="••••••••"
                                required
                            />
                        </div>
                        <button type="submit" disabled={loading}>
                            {loading ? 'Authenticating...' : 'Next: Verification'}
                        </button>
                    </form>
                ) : (
                    <form onSubmit={handleVerify} className="login-form">
                        <div className="form-group">
                            <label>One-Time Password</label>
                            <input 
                                type="text" 
                                value={otp} 
                                onChange={(e) => setOtp(e.target.value)}
                                placeholder="6-digit code"
                                maxLength={6}
                                required
                            />
                            <p className="otp-hint">OTP sent to your registered email.</p>
                        </div>
                        <button type="submit" disabled={loading}>
                            {loading ? 'Verifying...' : 'Complete Login'}
                        </button>
                        <button type="button" className="btn-link" onClick={() => setStep('LOGIN')}>
                            Back to Login
                        </button>
                    </form>
                )}
                
                <div className="login-footer">
                    <p>Physical LAN Connection Required</p>
                    <div className="lan-indicator online"></div>
                </div>
            </div>
        </div>
    );
};

export default LoginPage;
