import Link from 'next/link';
import { CHANNEL, ROUTE } from '@/lib/format';

export const Chip = ({ tone = 'grey', children, className = '' }) => <span className={`chip ${tone} ${className}`.trim()}>{children}</span>;

export const RouteChip = ({ route }) => {
  const r = ROUTE[route] || { label: route, tone: 'grey' };
  return <Chip tone={r.tone}>{r.label}</Chip>;
};
export const BlockChip = ({ id, version }) => <Chip tone="purple">{id}{version ? ` v${version}` : ''}</Chip>;
export const ChannelChip = ({ channel }) => <Chip tone="blue">{CHANNEL[channel] || channel}</Chip>;

/** A page section: the wrap every screen section sits in. */
export const Section = ({ children, id }) => (
  <section><div className="wrap tight" id={id}>{children}</div></section>
);

export const PageHead = ({ title, children, actions }) => (
  <div className="head">
    <div><h1 className="page">{title}</h1><p>{children}</p></div>
    {actions && <div className="btns">{actions}</div>}
  </div>
);

export const Failure = ({ error }) => <p className="empty err">{error?.message || String(error)}</p>;
export const Loading = () => <p className="empty">Loading</p>;

/** Render children once data has arrived, or the failure. */
export const Await = ({ state, children }) => {
  if (state.error && !state.data) return <Failure error={state.error} />;
  if (!state.data) return <Loading />;
  return children(state.data);
};

export const CaseLink = ({ id, children, className }) => (
  <Link className={className} href={`/case?id=${encodeURIComponent(id)}`}>{children ?? id}</Link>
);
