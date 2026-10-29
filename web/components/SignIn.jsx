'use client';
import { useEffect, useState } from 'react';
import { login } from '@/lib/api';
import { ROLE } from '@/lib/format';
import { Failure } from './ui';

/** Pick a tenant, then a person in it, then enter that person's password. The server checks it. */
export default function SignIn({ onSignedIn }) {
  const [options, setOptions] = useState(null);
  const [tenant, setTenant] = useState('quillon');
  const [user, setUser] = useState('');
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    fetch('/api/login-options').then((r) => r.json()).then(setOptions).catch(setError);
  }, []);

  if (!options) return <div className="frame"><main>{error ? <Failure error={error} /> : <p className="empty">Loading</p>}</main></div>;

  const listed = options.people.length > 0; // a real deployment lists nobody: the person types a user id
  const people = options.people.filter((p) => p.tenant === tenant);
  const chosen = listed ? people.find((p) => p.id === user) || people[0] : { id: user };

  async function submit(ev) {
    ev.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(chosen.id, new FormData(ev.target).get('password'));
      onSignedIn();
    } catch (e) {
      setError(e);
      setBusy(false);
    }
  }

  return (
    <div className="frame">
      <main>
        <section><div className="wrap tight">
          <div className="head"><div>
            <h1 className="page">Sign in</h1>
            <p>Each person belongs to one client. The server checks the password, signs a token, and Cedar decides what that person may do. Local demo password: <code>local-demo-only</code>.</p>
          </div></div>
          <form className="form" id="signin" onSubmit={submit}>
            {listed ? (
              <>
                <div className="fld"><label htmlFor="tenant">Client</label>
                  <select id="tenant" value={tenant} onChange={(e) => { setTenant(e.target.value); setUser(''); }}>
                    {options.tenants.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
                  </select></div>
                <div className="fld"><label htmlFor="person">Person</label>
                  <select id="person" value={chosen.id} onChange={(e) => setUser(e.target.value)}>
                    {people.map((p) => <option key={p.id} value={p.id}>{p.name}, {ROLE[p.role] || p.role} {p.country === 'ALL' ? '' : p.country}</option>)}
                  </select></div>
              </>
            ) : (
              <div className="fld w"><label htmlFor="userid">User id</label>
                <input id="userid" value={user} onChange={(e) => setUser(e.target.value)} autoComplete="username" required /></div>
            )}
            <div className="fld w"><label htmlFor="password">Password</label>
              <input id="password" name="password" type="password" autoComplete="current-password" required /></div>
            {error && <div className="fld w"><Failure error={error} /></div>}
            <div className="fld w"><button className="btn dark" type="submit" disabled={busy}>Sign in</button></div>
          </form>
        </div></section>
      </main>
    </div>
  );
}
