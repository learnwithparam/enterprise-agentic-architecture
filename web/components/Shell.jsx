'use client';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { api, logout, signedIn } from '@/lib/api';
import { ROLE } from '@/lib/format';
import SignIn from './SignIn';

const NAV = [
  ['Architecture', '/'],
  ['Inbox', '/inbox'],
  ['Review', '/review'],
  ['HCP 360', '/hcp'],
  ['Content', '/content'],
  ['Agents', '/agents'],
  ['Releases', '/releases'],
  ['Proof', '/proof'],
];

const Session = createContext(null);
/** The signed-in user, the platform mode and the date: {user, mode, model, today}. */
export const useSession = () => useContext(Session);

export default function Shell({ children }) {
  const path = usePathname();
  const [state, setState] = useState('checking'); // checking | signed-out | ready
  const [session, setSession] = useState(null);

  const load = useCallback(async () => {
    if (!signedIn()) return setState('signed-out');
    try {
      setSession(await api('/api/session'));
      setState('ready');
    } catch {
      setState('signed-out');
    }
  }, []);

  useEffect(() => {
    load();
    window.addEventListener('mi-signed-out', load);
    return () => window.removeEventListener('mi-signed-out', load);
  }, [load]);

  if (state === 'checking') return <div className="frame"><main><p className="empty">Loading</p></main></div>;
  if (state === 'signed-out') return <SignIn onSignedIn={load} />;

  const { user, mode, model, today } = session;
  const live = mode === 'live';
  return (
    <Session.Provider value={session}>
      <div className="frame">
        <nav className="top" aria-label="Console">
          <Link className="brand" href="/">
            <svg className="mark" width="20" height="20" viewBox="0 0 32 32" aria-hidden="true"><rect width="32" height="32" rx="8" fill="#171717" /><circle cx="15" cy="15" r="7" fill="none" stroke="#fff" strokeWidth="2.6" /><path d="M19 19l5 5" stroke="#fff" strokeWidth="2.6" strokeLinecap="round" /></svg>
            {user.tenant === 'marlowe' ? 'Marlowe MI' : 'Quillon MI'}
          </Link>
          {NAV.map(([title, href]) => <Link key={href} href={href} aria-current={path === href ? 'page' : undefined}>{title}</Link>)}
          <span className="grow" />
          <span id="mode" className={`chip ${live ? 'wait' : 'grey'}`} title={live ? 'Agent calls go to the model and are recorded' : 'Agent calls are replayed from recorded runs; tool calls still pass through the guards'}>
            {live ? 'Live' : 'Replay'}, {model}
          </span>
          <span className="who" id="who">{user.name}, {ROLE[user.role] || user.role} {user.country === 'ALL' ? '' : user.country}</span>
          <button className="btn sm" id="switch" onClick={() => { logout(); load(); }}>Switch person</button>
        </nav>
        <main>{children}</main>
        <footer className="foot">
          <span>Synthetic data. Quillon Biopharma, Marlowe Therapeutics, Veltrona and Ombrexa are invented.</span>
          <span id="today">Platform date {today}</span>
        </footer>
      </div>
    </Session.Provider>
  );
}
