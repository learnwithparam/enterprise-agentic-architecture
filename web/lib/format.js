// Labels and formatters shared by every screen. Colour carries meaning only: green = the AI answered,
// wait = a human in the loop decides, red = the AI does not answer.
export const ROUTE = {
  send: { label: 'Sent automatically', tone: 'green' },
  review: { label: 'Medical review', tone: 'wait' },
  pv: { label: 'Pharmacovigilance', tone: 'red' },
  offlabel: { label: 'Off-label, medical writes', tone: 'red' },
  specialist: { label: 'Specialist', tone: 'wait' },
  decline: { label: 'Declined', tone: 'red' },
};

export const STATUS = {
  sent: 'Sent',
  awaiting_review: 'Awaiting review',
  with_pharmacovigilance: 'With pharmacovigilance',
  with_medical: 'With medical',
  with_specialist: 'With a specialist',
  declined: 'Declined, not answered',
  blocked_at_send: 'Blocked at send',
  rejected: 'Rejected by reviewer',
};

export const CHANNEL = {
  portal: 'HCP portal',
  email: 'Email',
  chatbot: 'Chatbot',
  contact_centre: 'Contact centre',
  crm: 'Field CRM',
  marketing: 'Marketing',
};

export const ROLE = {
  medical_reviewer: 'Reviewer',
  mi_specialist: 'MI specialist',
  compliance: 'Compliance',
  pv: 'Pharmacovigilance',
  content_owner: 'Content owner',
  field_rep: 'Field rep',
};

export const usd = (n) => `$${(n || 0).toFixed((n || 0) < 0.01 ? 5 : 4)}`;
export const short = (h) => (h ? h.slice(0, 10) : '');
export const when = (iso) => (iso ? iso.replace('T', ' ').slice(0, 16) : '');
export const words = (s) => String(s).replaceAll('_', ' ');
export const pct = (n) => `${Math.round(n * 100)}%`;
