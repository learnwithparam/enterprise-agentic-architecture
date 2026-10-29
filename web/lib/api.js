// Every request carries a signed ID token. The API verifies it against the identity provider's keys and
// Cedar decides what the user may do, so switching person here changes what the server allows, not what
// the page hides. The token lives in sessionStorage and the signed-in user's id in localStorage.
const WHO = 'mi-user';
const tokenKey = (user) => `mi-token-${user}`;

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

const read = (storage, key) => {
  try {
    return storage.getItem(key);
  } catch {
    return null; // private window: nothing is remembered
  }
};
const write = (storage, key, value) => {
  try {
    if (value === null) storage.removeItem(key);
    else storage.setItem(key, value);
  } catch {
    /* private window: the sign-in lasts until reload */
  }
};

export const who = () => read(localStorage, WHO);
export const signedIn = () => Boolean(who() && read(sessionStorage, tokenKey(who())));

/** Sign in with a password. Throws ApiError(401) when it is wrong. */
export async function login(user, password) {
  const r = await fetch('/api/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user, password }),
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new ApiError(r.status, data.detail || 'Sign in failed');
  write(localStorage, WHO, user);
  write(sessionStorage, tokenKey(user), data.token);
}

export function logout() {
  const user = who();
  if (user) write(sessionStorage, tokenKey(user), null);
  write(localStorage, WHO, null);
}

const headers = (body) => ({
  Authorization: `Bearer ${read(sessionStorage, tokenKey(who()))}`,
  ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
});

/** GET, or POST when a body is given. A 401 means the token expired: the shell shows the sign-in again. */
export async function api(path, body) {
  const r = await fetch(path, {
    method: body === undefined ? 'GET' : 'POST',
    headers: headers(body),
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await r.json().catch(() => ({}));
  if (r.status === 401) {
    logout();
    window.dispatchEvent(new Event('mi-signed-out'));
  }
  if (!r.ok) throw new ApiError(r.status, typeof data.detail === 'string' ? data.detail : `Request failed (${r.status})`);
  return data;
}

/**
 * Read a server-sent event stream with the bearer token (EventSource cannot set a header).
 * Calls onEvent(name, data) for every frame and resolves when the server closes the stream.
 */
export async function stream(path, onEvent, signal) {
  const r = await fetch(path, { headers: headers(), signal });
  if (!r.ok || !r.body) throw new ApiError(r.status, `Stream failed (${r.status})`);
  const reader = r.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = '';
  for (;;) {
    const { value, done } = await reader.read();
    if (done) return;
    buffer += value;
    for (let end = buffer.indexOf('\n\n'); end >= 0; end = buffer.indexOf('\n\n')) {
      const frame = buffer.slice(0, end);
      buffer = buffer.slice(end + 2);
      const name = /^event: (.*)$/m.exec(frame)?.[1];
      const data = /^data: (.*)$/m.exec(frame)?.[1];
      if (name && data) onEvent(name, JSON.parse(data));
    }
  }
}
