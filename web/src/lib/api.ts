// Every request names the acting user. The API looks them up in Cognito and Cedar decides what they
// may do, so switching persona here changes what the server allows, not what the page hides.
const KEY = 'mi-user';

export function who(): string {
  try {
    return localStorage.getItem(KEY) || 'u-raman';
  } catch {
    return 'u-raman';
  }
}

export function setWho(id: string) {
  try {
    localStorage.setItem(KEY, id);
  } catch {
    /* private window: the default persona stays */
  }
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export async function api<T = any>(path: string, body?: unknown): Promise<T> {
  const r = await fetch(path, {
    method: body === undefined ? 'GET' : 'POST',
    headers: { 'X-User': who(), ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new ApiError(r.status, data.detail || `Request failed (${r.status})`);
  return data as T;
}

export const esc = (s: unknown) =>
  String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!);

export const $ = <T extends Element = HTMLElement>(sel: string) => document.querySelector(sel) as T;

// The six places a case can go. Colour carries meaning only: pass = the AI answered,
// wait = a human in the loop decides, fail = the AI does not answer.
export const ROUTE: Record<string, { label: string; tone: 'green' | 'wait' | 'red' | 'grey' }> = {
  send: { label: 'Sent automatically', tone: 'green' },
  review: { label: 'Medical review', tone: 'wait' },
  pv: { label: 'Pharmacovigilance', tone: 'red' },
  offlabel: { label: 'Off-label, medical writes', tone: 'red' },
  specialist: { label: 'Specialist', tone: 'wait' },
  decline: { label: 'Declined', tone: 'red' },
};

export const STATUS: Record<string, string> = {
  sent: 'Sent',
  awaiting_review: 'Awaiting review',
  with_pharmacovigilance: 'With pharmacovigilance',
  with_medical: 'With medical',
  with_specialist: 'With a specialist',
  declined: 'Declined, not answered',
  blocked_at_send: 'Blocked at send',
  rejected: 'Rejected by reviewer',
};

export const CHANNEL: Record<string, string> = {
  portal: 'HCP portal',
  email: 'Email',
  chatbot: 'Chatbot',
  contact_centre: 'Contact centre',
  crm: 'Field CRM',
  marketing: 'Marketing',
};

export const routeChip = (r: string) => {
  const x = ROUTE[r] || { label: r, tone: 'grey' };
  return `<span class="chip ${x.tone}">${esc(x.label)}</span>`;
};
export const block = (id: string, v?: number) => `<span class="chip purple">${esc(id)}${v ? ` v${v}` : ''}</span>`;
export const channel = (c: string) => `<span class="chip blue">${esc(CHANNEL[c] || c)}</span>`;
export const usd = (n: number) => `$${(n || 0).toFixed(n < 0.01 ? 5 : 4)}`;
export const short = (h: string) => (h ? h.slice(0, 10) : '');
export const when = (iso: string) => (iso ? iso.replace('T', ' ').slice(0, 16) : '');

export function toast(msg: string, tone: 'ok' | 'err' = 'ok') {
  const t = document.createElement('div');
  t.className = `toast ${tone}`;
  t.setAttribute('role', 'status');
  t.textContent = msg;
  document.body.append(t);
  setTimeout(() => t.remove(), 5200);
}

export function fail(el: HTMLElement, e: unknown) {
  el.innerHTML = `<p class="empty err">${esc(e instanceof Error ? e.message : e)}</p>`;
}
