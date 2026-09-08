import re

file_path = 'frontend/src/pages/LoginPage.tsx'
with open(file_path, 'r', encoding='utf-8') as f:
    text = f.read()

# Add SETUP_TOTP step
text = text.replace(
    "const [step, setStep] = useState<'LOGIN' | 'OTP' | 'FORGOT'>('LOGIN');",
    "const [step, setStep] = useState<'LOGIN' | 'OTP' | 'SETUP_TOTP' | 'FORGOT'>('LOGIN');"
)

# Add QR code / secret state and missing enrollTOTP import
text = text.replace(
    "import { login, verifyOTP } from '../api/client';",
    "import { login, verifyOTP, enrollTOTP } from '../api/client';"
)

text = text.replace(
    "const [maskedEmail, setMaskedEmail] = useState('');",
    "const [maskedEmail, setMaskedEmail] = useState('');\n    const [totpSecret, setTotpSecret] = useState('');\n    const [qrCode, setQrCode] = useState('');\n    const [totpVerifyMode, setTotpVerifyMode] = useState(false);"
)

# Update handleLogin
handle_login_old = '''            const res = await login(employeeId, password);
            console.log("LOGIN_RESPONSE_RECEIVED:", res);
            updateDiag(200, JSON.stringify(res));

            // Extract email for masking if available (we might need backend to return it)
            // For now use a placeholder or update backend to return email hint
            setMaskedEmail(res.email_hint || 'registered email');

            console.log("TRANSITIONING TO OTP STEP...");
            setSuccess("OTP sent to your registered email.");
            setStep('OTP');'''

handle_login_new = '''            const res = await login(employeeId, password);
            console.log("LOGIN_RESPONSE_RECEIVED:", res);
            updateDiag(200, JSON.stringify(res));

            if (res.status === 'totp_verify') {
                setTotpVerifyMode(true);
                setSuccess("Please enter your Authenticator code.");
                setStep('OTP');
            } else {
                setTotpVerifyMode(false);
                setMaskedEmail(res.masked_email || 'registered email');
                setSuccess("OTP sent to your registered email.");
                setStep('OTP');
            }'''

text = text.replace(handle_login_old, handle_login_new)

# Update handleVerify
handle_verify_old = '''    const handleVerify = async (e: React.FormEvent) => {
        e.preventDefault();
        setLoading(true);
        setError(null);
        try {
            const data = await verifyOTP(employeeId, otp.trim());
            localStorage.setItem('aradhana_session_token', data.token);
            localStorage.setItem('session_token', data.token);
            localStorage.setItem('user', JSON.stringify(data.user));
            window.location.href = '/';
        } catch (err: any) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    };'''

handle_verify_new = '''    const handleVerify = async (e: React.FormEvent) => {
        e.preventDefault();
        setLoading(true);
        setError(null);
        try {
            if (step === 'SETUP_TOTP') {
                const data = await enrollTOTP(employeeId, otp.trim());
                localStorage.setItem('aradhana_session_token', data.token);
                localStorage.setItem('session_token', data.token);
                localStorage.setItem('user', JSON.stringify(data.user));
                window.location.href = '/';
            } else {
                const data = await verifyOTP(employeeId, otp.trim());
                if (data.status === 'totp_setup') {
                    setTotpSecret(data.secret);
                    setQrCode(data.qr_b64);
                    setStep('SETUP_TOTP');
                    setOtp('');
                    setSuccess("Email verified. Please setup Authenticator.");
                } else {
                    localStorage.setItem('aradhana_session_token', data.token);
                    localStorage.setItem('session_token', data.token);
                    localStorage.setItem('user', JSON.stringify(data.user));
                    window.location.href = '/';
                }
            }
        } catch (err: any) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    };'''

text = text.replace(handle_verify_old, handle_verify_new)

# Update UI forms (OTP step)
otp_ui_old = '''                        <div className="mb-6 text-center">
                            <p className="text-[10px] font-black uppercase text-gray-400 tracking-widest mb-1">OTP sent to:</p>
                            <p className="font-black text-gray-900 text-sm">{maskedEmail}</p>
                        </div>'''

otp_ui_new = '''                        <div className="mb-6 text-center">
                            {totpVerifyMode ? (
                                <p className="font-black text-gray-900 text-sm">Enter Authenticator Code</p>
                            ) : (
                                <>
                                    <p className="text-[10px] font-black uppercase text-gray-400 tracking-widest mb-1">OTP sent to:</p>
                                    <p className="font-black text-gray-900 text-sm">{maskedEmail}</p>
                                </>
                            )}
                        </div>'''

text = text.replace(otp_ui_old, otp_ui_new)

# Disable resend timer stuff for totp_verify
expiry_ui_old = '''                                <div className="flex justify-between mt-2">
                                    <span className="text-[9px] font-bold text-gray-400 uppercase">Expires in {formatTime(expiryTimer)}</span>
                                    {expiryTimer === 0 && <span className="text-[9px] font-bold text-red-500 uppercase tracking-tighter animate-pulse">OTP Expired</span>}
                                </div>'''
expiry_ui_new = '''                                {!totpVerifyMode && (
                                    <div className="flex justify-between mt-2">
                                        <span className="text-[9px] font-bold text-gray-400 uppercase">Expires in {formatTime(expiryTimer)}</span>
                                        {expiryTimer === 0 && <span className="text-[9px] font-bold text-red-500 uppercase tracking-tighter animate-pulse">OTP Expired</span>}
                                    </div>
                                )}'''

text = text.replace(expiry_ui_old, expiry_ui_new)

resend_btn_old = '''                        <div className="mt-6 space-y-4 text-center">
                            <button 
                                type="button" 
                                disabled={resendTimer > 0 || loading}
                                onClick={handleResend}
                                className={`text-[10px] font-black uppercase tracking-widest ${resendTimer > 0 ? 'text-gray-300' : 'text-blue-600 hover:underline'}`}
                            >
                                {resendTimer > 0 ? `Resend OTP in ${resendTimer}s` : 'Resend OTP Now'}
                            </button>
                            <br/>
                            <button type="button" className="btn-link" onClick={() => { setStep('LOGIN'); setSuccess(null); }}>
                                Back to Login
                            </button>
                        </div>'''

resend_btn_new = '''                        <div className="mt-6 space-y-4 text-center">
                            {!totpVerifyMode && (
                                <button 
                                    type="button" 
                                    disabled={resendTimer > 0 || loading}
                                    onClick={handleResend}
                                    className={`text-[10px] font-black uppercase tracking-widest ${resendTimer > 0 ? 'text-gray-300' : 'text-blue-600 hover:underline'}`}
                                >
                                    {resendTimer > 0 ? `Resend OTP in ${resendTimer}s` : 'Resend OTP Now'}
                                </button>
                            )}
                            <br/>
                            <button type="button" className="btn-link" onClick={() => { setStep('LOGIN'); setSuccess(null); setOtp(''); }}>
                                Back to Login
                            </button>
                        </div>'''

text = text.replace(resend_btn_old, resend_btn_new)

# Change expiry disable condition
text = text.replace('disabled={loading || expiryTimer === 0}', 'disabled={loading || (!totpVerifyMode && expiryTimer === 0)}')

# Add SETUP_TOTP step in the main render
setup_ui = '''                ) : step === 'SETUP_TOTP' ? (
                    <div className="login-form">
                        <div className="mb-6 text-center">
                            <h2 className="text-lg font-black text-gray-900 mb-2">Secure Your Account</h2>
                            <p className="text-xs text-gray-500 font-medium mb-4">Scan this QR code with Google Authenticator or Authy to enroll.</p>
                            {qrCode && <img src={qrCode} alt="TOTP QR Code" className="mx-auto w-48 h-48 border-4 border-gray-100 rounded-xl mb-4 shadow-sm" />}
                            <p className="text-[10px] font-black uppercase text-gray-400 tracking-widest">Manual Setup Key:</p>
                            <p className="font-mono font-bold text-sm text-gray-900 bg-gray-50 py-2 rounded border border-gray-100 mb-6">{totpSecret}</p>
                        </div>
                        <form onSubmit={handleVerify}>
                            <div className="form-group">
                                <label>Authenticator Code</label>
                                <input 
                                    type="text" 
                                    value={otp} 
                                    onChange={(e) => setOtp(e.target.value)}
                                    placeholder="6-digit code"
                                    maxLength={6}
                                    required
                                />
                            </div>
                            <button type="submit" disabled={loading} className="login-btn">
                                {loading ? 'Enrolling...' : 'Verify & Complete Setup'}
                            </button>
                        </form>
                    </div>
                ) : (
                    <form onSubmit={handleForgot} className="login-form">'''

text = text.replace('''                ) : (
                    <form onSubmit={handleForgot} className="login-form">''', setup_ui)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(text)
print("LoginPage.tsx updated successfully.")
