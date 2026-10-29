'use client';
import { STATUS } from '@/lib/format';
import { useApi } from '@/lib/hooks';
import { Await, CaseLink, PageHead, RouteChip, Section } from '@/components/ui';

const GROUPS = [
  ['Drafts awaiting a medical reviewer', 'A human in the loop approves or rejects. Approval re-checks every sentence against content as it is now.', ['awaiting_review', 'blocked_at_send']],
  ['With pharmacovigilance', 'Possible adverse events and special situations. No AI text exists for these.', ['with_pharmacovigilance']],
  ['With Medical and specialists', 'Off-label questions, unverified senders and unknown products. Written by hand.', ['with_medical', 'with_specialist']],
  ['Closed', 'Sent, declined or rejected.', ['sent', 'declined', 'rejected']],
];

const Queue = ({ title, sub, rows }) => (
  <>
    <h2 className="sec">{title} <span className="muted num">{rows.length}</span></h2>
    <p className="sub">{sub}</p>
    <table className="tbl"><thead><tr><th>Case</th><th>Country</th><th>Route</th><th>Status</th><th>Why</th><th /></tr></thead>
      <tbody>{rows.map((c) => (
        <tr key={c.id}>
          <td className="num">{c.id}</td><td>{c.country}</td><td><RouteChip route={c.route} /></td>
          <td>{STATUS[c.status] || c.status}</td>
          <td className="q">{c.redacted ? <span className="muted">{c.redacted}</span> : c.decision?.why}</td>
          <td className="act"><CaseLink id={c.id} className="btn sm">Open</CaseLink></td>
        </tr>
      ))}</tbody></table>
    <br /><br />
  </>
);

export default function Review() {
  const cases = useApi('/api/cases');
  return (
    <Section>
      <PageHead title="Review bench">
        Every case the agents did not finish on their own, grouped by who owns it. Drafts wait for a medical reviewer in the same country. Cases with no draft are owned by a team that works without AI.
      </PageHead>
      <div id="queues"><Await state={cases}>{(all) => all.length === 0
        ? <p className="empty">No cases yet. Run inquiries from the inbox.</p>
        : GROUPS.map(([t, s, st]) => {
          const rows = all.filter((c) => st.includes(c.status));
          return rows.length ? <Queue key={t} title={t} sub={s} rows={rows} /> : null;
        })}</Await></div>
    </Section>
  );
}
