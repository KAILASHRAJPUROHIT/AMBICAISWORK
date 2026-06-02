import React, { useState, useEffect } from 'react';
import { login, verifyOTP } from '../api/client';
import './LoginPage.css';

const LoginPage: React.FC = () => {
    const [employeeId, setEmployeeId] = useState('');
    const [password, setPassword] = useState('');
    const [showPassword, setShowPassword] = useState(false);
    const [otp, setOtp] = useState('');
    const [email, setEmail] = useState('');
    const [step, setStep] = useState<'LOGIN' | 'OTP' | 'FORGOT'>('LOGIN');
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [success, setSuccess] = useState<string | null>(null);

    // Diagnostic Info
    const [diag, setDiag] = useState({ url: '', reachable: 'Checking...', status: 0, response: '' });

    // Captcha
    const [captcha, setCaptcha] = useState({ a: 0, b: 0, result: '' });
    
    const refreshCaptcha = () => {
        const a = Math.floor(Math.random() * 10) + 1;
        const b = Math.floor(Math.random() * 10) + 1;
        setCaptcha({ a, b, result: '' });
    };

    const updateDiag = (status: number, text: string) => {
        setDiag(prev => ({ ...prev, status, response: text.slice(0, 100) }));
    };

    useEffect(() => {
        refreshCaptcha();
        const apiBase = window.location.origin;
        setDiag(prev => ({ ...prev, url: `${apiBase}/api/auth/login` }));
        
        fetch(`${apiBase}/health`)
            .then(res => setDiag(prev => ({ ...prev, reachable: res.ok ? 'YES' : `NO (${res.status})` })))
            .catch(() => setDiag(prev => ({ ...prev, reachable: 'NO (NETWORK ERROR)' })));
    }, []);

    const handleLogin = async (e: React.FormEvent) => {
        e.preventDefault();
        setError(null);
        setSuccess(null);

        if (parseInt(captcha.result) !== (captcha.a + captcha.b)) {
            setError("Captcha incorrect. Please try again.");
            refreshCaptcha();
            return;
        }

        console.log("LOGIN REQUEST: employee_id submitted:", employeeId);
        setLoading(true);
        try {
            const res = await login(employeeId, password);
            updateDiag(200, JSON.stringify(res));
            console.log("LOGIN SUCCESS:", res);
            setSuccess("OTP sent to your registered email.");
            setStep('OTP');
        } catch (err: any) {
            console.error("LOGIN ERROR:", err);
            const msg = err.message || '';
            if (msg.includes('Failed to fetch') || msg.includes('NetworkError') || msg.includes('Server returned 0')) {
                 setError('SERVER OFFLINE OR LOGIN SERVICE UNAVAILABLE. Please restart Aradhana Auditor Server.');
            } else {
                 setError(msg);
            }
            refreshCaptcha();
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

    const handleForgot = async (e: React.FormEvent) => {
        e.preventDefault();
        setLoading(true);
        setError(null);
        try {
            const response = await fetch(`${window.location.origin}/api/auth/forgot-password`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email })
            });
            const data = await response.json();
            setSuccess(data.message || "Recovery instructions sent.");
            setStep('LOGIN');
        } catch (err: any) {
            setError("Failed to process recovery request.");
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
                {success && <div className="login-success">{success}</div>}

                {step === 'LOGIN' ? (
                    <form onSubmit={handleLogin} className="login-form">
                        <div className="form-group">
                            <label>Employee ID</label>
                            <input 
                                type="text" 
                                value={employeeId} 
                                onChange={(e) => setEmployeeId(e.target.value)}
                                placeholder="Enter your ID"
                                autoCapitalize="none"
                                autoCorrect="off"
                                autoComplete="off"
                                spellCheck={false}
                                required
                            />
                        </div>
                        <div className="form-group">
                            <label>Password</label>
                            <div className="password-input-wrapper">
                                <input 
                                    type={showPassword ? "text" : "password"} 
                                    value={password} 
                                    onChange={(e) => setPassword(e.target.value)}
                                    placeholder="••••••••"
                                    autoCapitalize="none"
                                    autoCorrect="off"
                                    autoComplete="current-password"
                                    spellCheck={false}
                                    required
                                />
                                <button 
                                    type="button"
                                    onClick={() => setShowPassword(!showPassword)}
                                    className="password-toggle-btn"
                                >
                                    {showPassword ? 'Hide' : 'Show'}
                                </button>
                            </div>
                        </div>

                        <div className="form-group captcha-group">
                             <label>Human Verification</label>
                             <div className="captcha-container">
                                <span className="captcha-question">What is {captcha.a} + {captcha.b}?</span>
                                <input 
                                    type="number" 
                                    className="captcha-input"
                                    value={captcha.result}
                                    onChange={e => setCaptcha({...captcha, result: e.target.value})}
                                    required
                                />
                             </div>
                        </div>

                        <button type="submit" disabled={loading} className="login-btn">
                            {loading ? 'Authenticating...' : 'Next: Verification'}
                        </button>

                        <div className="mt-6 text-center">
                            <button type="button" className="forgot-password-link" onClick={() => { setStep('FORGOT'); setSuccess(null); setError(null); }}>
                                Forgot Password?
                            </button>
                        </div>
                    </form>
                ) : step === 'OTP' ? (
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
                        <button type="submit" disabled={loading} className="login-btn">
                            {loading ? 'Verifying...' : 'Complete Login'}
                        </button>
                        <button type="button" className="btn-link" onClick={() => { setStep('LOGIN'); setSuccess(null); }}>
                            Back to Login
                        </button>
                    </form>
                ) : (
                    <form onSubmit={handleForgot} className="login-form">
                         <p className="recovery-hint">Password recovery requires access to your private security mailbox.</p>
                         <div className="form-group">
                            <label>Registered Email</label>
                            <input 
                                type="email" 
                                value={email}
                                onChange={e => setEmail(e.target.value)}
                                placeholder="owner@example.com" 
                                required 
                            />
                         </div>
                         <button type="submit" className="login-btn" disabled={loading}>
                            {loading ? 'Processing...' : 'Request Reset Link'}
                         </button>
                         <button type="button" className="btn-link w-full" onClick={() => { setStep('LOGIN'); setSuccess(null); }}>
                            Back to Login
                        </button>
                    </form>
                )}
                
                {/* Diagnostic Panel */}
                <div className="mt-8 p-4 bg-gray-900 rounded-xl font-mono text-[8px] text-gray-400">
                    <p className="text-gray-500 font-bold mb-1 uppercase tracking-widest">Login Diagnostics</p>
                    <div className="flex justify-between">
                        <span>API ENDPOINT:</span>
                        <span className="text-blue-400">{diag.url}</span>
                    </div>
                    <div className="flex justify-between">
                        <span>REACHABLE:</span>
                        <span className={diag.reachable === 'YES' ? 'text-green-400' : 'text-red-400'}>{diag.reachable}</span>
                    </div>
                    {diag.status > 0 && (
                        <div className="flex justify-between">
                            <span>LAST STATUS:</span>
                            <span className="text-orange-400">{diag.status}</span>
                        </div>
                    )}
                </div>

                <div className="login-footer">
                    <p>Physical LAN Connection Required</p>
                    <div className="lan-indicator online"></div>
                </div>
            </div>
        </div>
    );
};

export default LoginPage;
