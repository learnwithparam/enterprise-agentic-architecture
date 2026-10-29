'use client';
import Link from 'next/link';
import { api } from '@/lib/api';
import { short, usd, words } from '@/lib/format';
import { toast, useApi } from '@/lib/hooks';
import { Await, Chip, PageHead, RouteChip, Section } from '@/components/ui';

const Kpi = ({ value, label, ok }) => <div className={`kpi ${ok ? 'ok' : 'bad'}`}><b>{value}</b><span>{label}</span></div>;

function Kpis({ p }) {
  const m = p.evals?.metrics || {};
  return (
    <div className="kpis" id="kpis">
      <Kpi ok={p.ledger.ok} value={p.ledger.ok ? 'Intact' : `Broken at ${p.ledger.broken_at}`} label={`Ledger, ${p.ledger.entries} entries, ${p.ledger.checkpoints ?? 'no'} signed checkpoints`} />
      <Kpi ok={m.ae_recall === 1} value={m.ae_recall === undefined ? 'Not run' : `${Math.round(m.ae_recall * 100)}%`} label="Adverse events caught in the eval set" />
      <Kpi ok={m.ungrounded_sentences === 0} value={String(m.ungrounded_sentences ?? 'Not run')} label="Sentences without a current approved source" />
      <Kpi ok value={usd(p.spend.cost_usd)} label={`Model spend for ${p.spend.cases} cases, ${p.spend.live_cases} live`} />
    </div>
  );
}

function LedgerCard({ p, act }) {
  const v = p.ledger;
  return (
    <div className="card" id="ledgercard"><div className="call">
      <header><h4>{v.ok ? 'Every hash matches its entry and its predecessor' : `Entry ${v.broken_at} no longer matches its hash`}</h4>{v.head && <span className="hash">Head {short(v.head)}</span>}</header>
      {!v.ok && <p className="empty err">{v.reason || 'The chain is broken'}</p>}
      <div className="btns">
        <button className="btn" data-a="tamper" onClick={() => act('tamper')}>Change a past entry</button>
        <button className="btn" data-a="restore" onClick={() => act('restore')}>Restore from the archive</button>
        <button className="btn" data-a="delete-archive" onClick={() => act('delete-archive')}>Try to delete the archive</button>
      </div>
      <table className="tbl chain"><thead><tr><th>Seq</th><th>Case</th><th>Entry</th><th>Hash</th></tr></thead>
        <tbody>{p.recent.slice(0, 12).map((r) => (
          <tr key={r.seq}><td className="num">{r.seq}</td><td className="num">{r.entry.case || ''}</td>
            <td className="ty">{words(r.entry.type)} {r.entry.route && <RouteChip route={r.entry.route} />}</td>
            <td className="hash">{short(r.hash)}{r.signature && <> <Chip tone="green">Signed</Chip></>}</td></tr>))}</tbody></table>
    </div></div>
  );
}

function KillSwitches({ auto, set }) {
  return (
    <div className="card" id="autonomy"><div className="call">{Object.entries(auto).map(([c, s]) => (
      <div className="switch" key={c}>
        <div><b>{c}</b> <Chip tone={s.enabled ? 'green' : 'red'}>{s.enabled ? 'On' : 'Off'}</Chip><br />
          <span className="muted">{s.topics.length ? `Cleared topics: ${s.topics.map(words).join(', ')}` : 'No topic is cleared, so every draft goes to review'}</span></div>
        <button className="btn sm" data-c={c} data-on={s.enabled ? '0' : '1'} onClick={() => set(c, !s.enabled)}>{s.enabled ? 'Turn off' : 'Turn on'}</button>
      </div>))}</div></div>
  );
}

function Gate({ ev }) {
  if (!ev) return <p className="empty">No eval report yet. Run make evals.</p>;
  const m = ev.metrics;
  return (
    <>
      <p className="row"><Chip tone={ev.passed ? 'green' : 'red'}>{ev.passed ? 'Gate passed' : 'Gate failed'}</Chip>
        <span className="muted">{ev.model}, prompt {ev.prompt_version}, {m.cases} cases, at most {usd(m.max_cost_per_case_usd)} per case</span></p><br />
      <table className="tbl"><thead><tr><th>Inquiry</th><th>Expected</th><th>Got</th><th>Why it should go there</th></tr></thead>
        <tbody>{ev.cases.map((c) => (
          <tr key={c.id}><td className="num"><Link href={`/case?id=${encodeURIComponent(c.id)}`}>{c.id}</Link></td><td><RouteChip route={c.expect} /></td>
            <td><RouteChip route={c.route} />{!c.acceptable ? <> <Chip tone="red">Wrong</Chip></> : c.route !== c.expect ? <> <Chip>Also safe</Chip></> : null}</td>
            <td className="q">{c.why}</td></tr>))}</tbody></table>
    </>
  );
}

const Counts = ({ title, counts, render }) => (
  <div><h3>{title}</h3><ol className="tl">{counts.map(([k, n]) => <li key={k}><time className="num">{n}</time><span>{render(k)}</span></li>)}</ol></div>
);

export default function Proof() {
  const proof = useApi('/api/proof');
  const auto = useApi('/api/autonomy');

  async function run(fn, ok) {
    try { ok(await fn()); } catch (e) { toast(e.message, 'err'); }
    proof.reload();
    auto.reload();
  }
  const act = (a) => run(() => api(`/api/proof/${a}`, {}), (r) => {
    if (a === 'tamper') toast(`Entry ${r.tampered.seq} changed. Verify now fails at ${r.verify.broken_at}.`, 'err');
    else if (a === 'restore') toast(r.ok ? 'Restored from the archive. The chain verifies.' : 'Still broken');
    else toast(r.deleted ? 'Deleted, which should never happen' : `Refused: ${r.error}`, r.deleted ? 'err' : 'ok');
  });
  const set = (country, enabled) => run(() => api('/api/autonomy', { country, enabled }), () => toast(`Automatic replies ${enabled ? 'on' : 'off'} for ${country}`));

  return (
    <>
      <Section>
        <PageHead title="Proof for Compliance">
          What a compliance officer checks before trusting the platform, and the switches they hold. Ledger checks and the kill switch are allowed only for Compliance; try them as another persona and Cedar says no.
        </PageHead>
        <Await state={proof}>{(p) => <Kpis p={p} />}</Await>
      </Section>
      <Section>
        <h2 className="sec">The audit ledger</h2>
        <p className="sub">Change one past entry and the chain breaks at that point. Restore it and the chain verifies again. Deleting the archived copy fails because S3 Object Lock in compliance mode refuses it, even for the account owner.</p>
        <Await state={proof}>{(p) => <LedgerCard p={p} act={act} />}</Await>
      </Section>
      <Section>
        <h2 className="sec">Automatic replies per country</h2>
        <p className="sub">The kill switch. Turning a country off sends every new reply there to a medical reviewer; nothing else changes.</p>
        <Await state={auto}>{(a) => <KillSwitches auto={a} set={set} />}</Await>
      </Section>
      <Section>
        <h2 className="sec">Release gate</h2>
        <p className="sub">Every inquiry, including those that never reach the inbox, runs through the graph before a change ships. The gate fails on one missed adverse event, one ungrounded sentence, one unsafe automatic send or one call to a model outside the allowlist.</p>
        <div id="evals"><Await state={proof}>{(p) => <Gate ev={p.evals} />}</Await></div>
      </Section>
      <Section>
        <h2 className="sec">Operations</h2>
        <p className="sub">Route counts and the messages waiting in each handoff queue. In production the queues feed the safety database and the review tool.</p>
        <div className="two" id="ops"><Await state={proof}>{(p) => (
          <>
            <Counts title="Routes" counts={Object.entries(p.routes).sort((a, b) => b[1] - a[1])} render={(r) => <RouteChip route={r} />} />
            <Counts title="Handoff queues" counts={Object.entries(p.queues)} render={(q) => q} />
          </>)}</Await></div>
      </Section>
    </>
  );
}
