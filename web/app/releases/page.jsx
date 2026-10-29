'use client';
import { usd, when, words } from '@/lib/format';
import { useApi } from '@/lib/hooks';
import { Await, Chip, PageHead, RouteChip, Section } from '@/components/ui';

const fmt = (k, v) => (typeof v !== 'number' ? String(v) : k.endsWith('_usd') ? usd(v) : Number.isInteger(v) ? String(v) : v.toFixed(3));

/** Each release is one column, newest first; a metric that moved against the older release is marked. */
function Trend({ runs }) {
  const keys = [...new Set(runs.flatMap((r) => Object.keys(r.metrics)))].filter((k) => typeof runs[0].metrics[k] === 'number');
  return (
    <table className="tbl" id="trend">
      <thead><tr><th>Metric</th>{runs.map((r) => <th key={r.release}>{r.release}<br /><span className="muted">{when(r.at)}</span></th>)}</tr></thead>
      <tbody>
        <tr><td>Gate</td>{runs.map((r) => <td key={r.release}><Chip tone={r.passed ? 'green' : 'red'}>{r.passed ? 'Passed' : 'Failed'}</Chip>
          {r.regressions?.length > 0 && <><br /><span className="muted">{r.regressions.join('. ')}</span></>}</td>)}</tr>
        {keys.map((k) => (
          <tr key={k}><td>{words(k)}</td>{runs.map((r) => <td className="num" key={r.release}>{fmt(k, r.metrics[k])}</td>)}</tr>))}
        <tr><td>Live calls</td>{runs.map((r) => <td className="num" key={r.release}>{r.live_calls}</td>)}</tr>
        <tr><td>Live cost</td>{runs.map((r) => <td className="num" key={r.release}>{usd(r.live_cost_usd)}</td>)}</tr>
      </tbody>
    </table>
  );
}

function Online({ rows }) {
  if (!rows.length) return <p className="empty">No live case has run yet.</p>;
  return (
    <table className="tbl" id="monitors">
      <thead><tr><th>Release</th><th>Cases</th><th>Routes</th><th>Reviewers rejected</th><th>Average cost</th><th>p50</th><th>p95</th></tr></thead>
      <tbody>{rows.map((m) => (
        <tr key={m.release}><td>{m.release}</td><td className="num">{m.cases}</td>
          <td>{Object.entries(m.routes).map(([r, n]) => <span key={r}><RouteChip route={r} /> <span className="num">{n}</span> </span>)}</td>
          <td className="num">{m.override_rate === null ? 'No decisions yet' : `${Math.round(m.override_rate * 100)}%`}</td>
          <td className="num">{usd(m.avg_cost_usd)}</td><td className="num">{m.p50_ms} ms</td><td className="num">{m.p95_ms} ms</td></tr>))}</tbody>
    </table>
  );
}

export default function Releases() {
  const trend = useApi('/api/releases');
  const online = useApi('/api/monitors');
  return (
    <>
      <Section>
        <PageHead title="Releases">
          A release pins the prompts, the model router, the retrieval setup and the policy table. Every call, trace and case carries its release id, so each release can be judged on the same eval set and on live traffic. Safety numbers are absolute; quality and cost are compared with the baseline.
        </PageHead>
        <Await state={trend}>{(runs) => runs.length ? <Trend runs={runs} /> : <p className="empty">No release has been evaluated yet. Run make evals.</p>}</Await>
      </Section>
      <Section>
        <h2 className="sec">Live traffic by release</h2>
        <p className="sub">How cases behaved under each release: the route mix, how often a reviewer rejected the draft, cost and latency. A canary is compared with the baseline here.</p>
        <Await state={online}>{(rows) => <Online rows={rows} />}</Await>
      </Section>
    </>
  );
}
