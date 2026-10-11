import { useState } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';
import { useAuth } from '@/auth/AuthContext';

export function Login() {
  const { me, login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState('admin@kadelivery.app');
  const [password, setPassword] = useState('');
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (me) return <Navigate to="/" replace />;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      await login(email.trim(), password);
      navigate('/');
    } catch (e2) {
      setErr(e2 instanceof Error ? e2.message : 'Login failed');
      setBusy(false);
    }
  };

  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'linear-gradient(135deg,#5B3DF5,#19C6A5)' }}>
      <form onSubmit={submit} className="card" style={{ width: 380 }}>
        <h2 style={{ marginTop: 0 }}>
          Digi<span style={{ color: '#19C6A5' }}>Mess</span> Admin
        </h2>
        <p className="muted" style={{ marginTop: -8 }}>Operations & partner console. Admin access only.</p>
        {err && <div className="card" style={{ background: '#fee2e2', marginBottom: 12 }}>{err}</div>}
        <div className="field">
          <label>Email</label>
          <input value={email} onChange={(e) => setEmail(e.target.value)} type="email" autoFocus />
        </div>
        <div className="field">
          <label>Password</label>
          <input value={password} onChange={(e) => setPassword(e.target.value)} type="password" />
        </div>
        <button className="btn" style={{ width: '100%' }} disabled={busy || !email || !password}>
          {busy ? 'Signing in…' : 'Sign in'}
        </button>
        <p className="muted" style={{ fontSize: 12, marginBottom: 0 }}>
          Demo: admin@kadelivery.app / password123
        </p>
      </form>
    </div>
  );
}
