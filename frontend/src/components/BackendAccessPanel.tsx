import { useState, type FormEvent } from 'react';
import {
  DEMO_MODE,
  clearSession,
  login,
  type AuthSession,
} from '../services/backendApi';

interface Props {
  session: AuthSession | null;
  backendOnline: boolean;
  websocketOnline: boolean;
  connectionStatus?: 'connected' | 'connecting' | 'unreachable';
  onSessionChange: (session: AuthSession | null) => void;
}

/** Explicitly distinguish historical fixture mode from authenticated FastAPI access. */
export function BackendAccessPanel({ session, backendOnline, websocketOnline, connectionStatus, onSessionChange }: Props) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const statusLabel = backendOnline
    ? 'CONNECTED'
    : connectionStatus === 'connecting'
      ? 'CONNECTING (WAITING FOR RENDER COLD START)...'
      : 'UNREACHABLE (RETRYING)';

  async function signIn(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      const auth = await login(email.trim(), password);
      setPassword('');
      onSessionChange(auth);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : 'Unable to sign in to FastAPI');
    } finally {
      setBusy(false);
    }
  }

  function signOut() {
    clearSession();
    setError('');
    onSessionChange(null);
  }

  if (DEMO_MODE) {
    return (
      <aside role="status" className="border-b border-amber-700/40 bg-amber-950/40 px-5 py-2 text-[11px] text-amber-200 font-mono">
        HISTORICAL DEMONSTRATION · Illustrative and synthetic fixtures · No live flood monitoring, operational warnings, verified depth, or rescue dispatch.
        <span className="ml-2 text-amber-300/70">To test real backend records, set VITE_USE_MOCK_DATA=false in frontend/.env and restart Vite.</span>
      </aside>
    );
  }

  return (
    <aside className="border-b border-sky-800/40 bg-slate-950/95 px-5 py-2.5 text-xs text-slate-300" aria-label="Backend connection and authority authentication">
      <div className="flex flex-wrap items-center gap-3">
        <span className="font-mono text-[11px]">
          FASTAPI: {statusLabel} ·
          AUTHORITY: {session ? session.role.toUpperCase() : 'SIGN-IN REQUIRED'} ·
          EVENTS: {websocketOnline ? 'CONNECTED' : 'DISCONNECTED'}
        </span>
        {session ? (
          <button type="button" onClick={signOut} className="rounded border border-slate-500 px-3 py-1 text-slate-100 hover:bg-slate-800">
            Sign out
          </button>
        ) : (
          <form onSubmit={signIn} className="flex flex-wrap items-center gap-2">
            <label className="sr-only" htmlFor="authority-email">Authority email</label>
            <input id="authority-email" type="email" autoComplete="username" required value={email} onChange={e => setEmail(e.target.value)} placeholder="Authority email" className="w-44 rounded border border-slate-600 bg-slate-900 px-2 py-1 text-white" />
            <label className="sr-only" htmlFor="authority-password">Authority password</label>
            <input id="authority-password" type="password" autoComplete="current-password" required value={password} onChange={e => setPassword(e.target.value)} placeholder="Password" className="w-40 rounded border border-slate-600 bg-slate-900 px-2 py-1 text-white" />
            <button disabled={busy} className="rounded border border-sky-500 px-3 py-1 text-sky-100 hover:bg-sky-900 disabled:opacity-50">
              {busy ? 'Signing in…' : 'Sign in'}
            </button>
          </form>
        )}
      </div>
      <p className="mt-1 text-[10px] text-slate-400">
        Historical demo/test mode only. Signing in requires an existing authority/admin account; citizen self-registration cannot grant authority.
        Connected API status alone does not mean historical datasets are loaded.
      </p>
      {error && <p role="alert" className="mt-1 text-rose-300">{error}</p>}
    </aside>
  );
}
