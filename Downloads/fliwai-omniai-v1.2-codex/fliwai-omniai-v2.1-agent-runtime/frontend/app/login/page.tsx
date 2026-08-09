'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001';
type Mode = 'login'|'register'|'forgot'|'reset'|'invite';

export default function Login() {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [fullName, setFullName] = useState('');
  const [mfaCode, setMfaCode] = useState('');
  const [mfaRequired, setMfaRequired] = useState(false);
  const [token, setToken] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    const reset = q.get('reset_token');
    const invite = q.get('invite_token');
    if (reset) { setToken(reset); setMode('reset'); }
    if (invite) { setToken(invite); setMode('invite'); }
  }, []);

  async function post(path: string, body: unknown) {
    const r = await fetch(`${API_URL}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const b = await r.json().catch(() => ({}));
    return { r, b };
  }

  async function submit() {
    setLoading(true); setError(''); setNotice('');
    try {
      if (mode === 'forgot') {
        const { r, b } = await post('/security/password-reset/request', { email });
        if (!r.ok) throw new Error(b.detail || 'Request failed');
        setNotice('If that account exists, a reset email has been sent.');
        return;
      }
      if (mode === 'reset') {
        const { r, b } = await post('/security/password-reset/confirm', { token, new_password: password });
        if (!r.ok) throw new Error(b.detail || 'Reset failed');
        setMode('login'); setNotice('Password reset. Sign in with your new password.');
        return;
      }
      if (mode === 'invite') {
        const { r, b } = await post('/organizations/invitations/accept', { token, full_name: fullName, password });
        if (!r.ok) throw new Error(b.detail || 'Invitation failed');
        setEmail(b.email || ''); setMode('login'); setNotice('Invitation accepted. Sign in to continue.');
        return;
      }
      if (mode === 'register') {
        const { r, b } = await post('/auth/register', { email, password, full_name: fullName });
        if (!r.ok) throw new Error(b.detail || 'Registration failed');
      }
      const { r, b } = await post('/auth/login', { email, password, mfa_code: mfaCode || null });
      if (r.status === 428 && b.detail === 'MFA_REQUIRED') {
        setMfaRequired(true);
        throw new Error('Enter the 6-digit code from your authenticator app.');
      }
      if (!r.ok) throw new Error(b.detail || 'Login failed');
      localStorage.setItem('omniai_token', b.access_token);
      localStorage.setItem('omniai_user', JSON.stringify(b.user));
      router.push('/dashboard');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Something went wrong');
    } finally {
      setLoading(false);
    }
  }

  const title = mode === 'login' ? 'Welcome back' : mode === 'register' ? 'Create your account' : mode === 'forgot' ? 'Reset password' : mode === 'reset' ? 'Choose a new password' : 'Accept invitation';

  return <main className="authPage">
    <div className="card authCard">
      <p className="eyebrow">FLIWAI OMNIAI</p>
      <h1>{title}</h1>
      <div className="authForm">
        {(mode === 'register' || mode === 'invite') && <>
          <label className="srOnly" htmlFor="full-name">Full name</label>
          <input id="full-name" autoComplete="name" placeholder="Full name" value={fullName} onChange={e => setFullName(e.target.value)} />
        </>}
        {(mode === 'login' || mode === 'register' || mode === 'forgot') && <>
          <label className="srOnly" htmlFor="email">Email</label>
          <input id="email" autoComplete="email" placeholder="Email" type="email" value={email} onChange={e => setEmail(e.target.value)} />
        </>}
        {mode !== 'forgot' && <>
          <label className="srOnly" htmlFor="password">Password</label>
          <input id="password" autoComplete={mode === 'login' ? 'current-password' : 'new-password'} placeholder="Password (10+ characters)" type="password" value={password} onChange={e => setPassword(e.target.value)} />
        </>}
        {mode === 'login' && mfaRequired && <>
          <label className="srOnly" htmlFor="mfa-code">Authenticator code</label>
          <input id="mfa-code" autoComplete="one-time-code" placeholder="6-digit authenticator code" inputMode="numeric" maxLength={6} value={mfaCode} onChange={e => setMfaCode(e.target.value.replace(/\D/g, ''))} />
        </>}
        {error && <p className="errorText" role="alert">{error}</p>}
        {notice && <p className="successText" role="status">{notice}</p>}
        <button onClick={submit} disabled={loading || (mode !== 'reset' && mode !== 'invite' && !email) || (mode !== 'forgot' && password.length < 10) || (mfaRequired && mfaCode.length !== 6)}>{loading ? 'Please wait...' : title}</button>
        {(mode === 'login' || mode === 'register') && <button className="secondary" onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setError(''); }}>{mode === 'login' ? 'Need an account? Register' : 'Already registered? Sign in'}</button>}
        {mode === 'login' && <button className="secondary" onClick={() => setMode('forgot')}>Forgot password?</button>}
        {mode === 'forgot' && <button className="secondary" onClick={() => setMode('login')}>Back to sign in</button>}
      </div>
    </div>
  </main>;
}
