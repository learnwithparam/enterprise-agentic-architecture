'use client';
import { useState } from 'react';
import { AuthenticationDetails, CognitoUser, CognitoUserPool } from 'amazon-cognito-identity-js';
import { storeToken } from '@/lib/api';
import { Failure } from './ui';

/** Production sign-in. The browser proves the password to Cognito with SRP, so it never reaches our server. */
export default function CognitoSignIn({ config, onSignedIn }) {
  const [step, setStep] = useState('password'); // password | code | new-password
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [challenge, setChallenge] = useState(null); // the CognitoUser and the live callbacks, kept between steps
  const [name, setName] = useState('');

  const callbacks = (user) => ({
    onSuccess: (session) => {
      storeToken(name || user.getUsername(), session.getIdToken().getJwtToken());
      onSignedIn();
    },
    onFailure: (e) => { setError(new Error(e.message || 'Sign in failed')); setBusy(false); },
    totpRequired: () => { setChallenge({ user, kind: 'SOFTWARE_TOKEN_MFA' }); setStep('code'); setBusy(false); },
    mfaRequired: () => { setChallenge({ user, kind: 'SMS_MFA' }); setStep('code'); setBusy(false); },
    newPasswordRequired: () => { setChallenge({ user }); setStep('new-password'); setBusy(false); },
  });

  function submit(ev) {
    ev.preventDefault();
    const form = new FormData(ev.target);
    setBusy(true);
    setError(null);
    if (step === 'password') {
      const id = String(form.get('userid')).trim();
      setName(id);
      const pool = new CognitoUserPool({ UserPoolId: config.pool_id, ClientId: config.client_id });
      const user = new CognitoUser({ Username: id, Pool: pool });
      user.authenticateUser(new AuthenticationDetails({ Username: id, Password: String(form.get('password')) }), callbacks(user));
    } else if (step === 'code') {
      challenge.user.sendMFACode(String(form.get('code')).trim(), callbacks(challenge.user), challenge.kind);
    } else {
      challenge.user.completeNewPasswordChallenge(String(form.get('newpassword')), {}, callbacks(challenge.user));
    }
  }

  return (
    <div className="frame">
      <main>
        <section><div className="wrap tight">
          <div className="head"><div>
            <h1 className="page">Sign in</h1>
            <p>Sign in with your company account. Your browser proves your password to the identity service directly, and the platform then decides what you may do.</p>
          </div></div>
          <form className="form" id="signin" onSubmit={submit} key={step}>
            {step === 'password' && (
              <>
                <div className="fld w"><label htmlFor="userid">User id</label>
                  <input id="userid" name="userid" autoComplete="username" required /></div>
                <div className="fld w"><label htmlFor="password">Password</label>
                  <input id="password" name="password" type="password" autoComplete="current-password" required /></div>
              </>
            )}
            {step === 'code' && (
              <div className="fld w"><label htmlFor="code">Code from your authenticator app</label>
                <input id="code" name="code" inputMode="numeric" autoComplete="one-time-code" required autoFocus /></div>
            )}
            {step === 'new-password' && (
              <div className="fld w"><label htmlFor="newpassword">Choose a new password</label>
                <input id="newpassword" name="newpassword" type="password" autoComplete="new-password" required autoFocus /></div>
            )}
            {error && <div className="fld w"><Failure error={error} /></div>}
            <div className="fld w"><button className="btn dark" type="submit" disabled={busy}>{step === 'password' ? 'Sign in' : 'Continue'}</button></div>
          </form>
        </div></section>
      </main>
    </div>
  );
}
