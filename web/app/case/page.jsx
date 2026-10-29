'use client';
import { Suspense, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { api } from '@/lib/api';
import { STATUS, short, usd, when, words } from '@/lib/format';
import { toast, useApi, useEventStream } from '@/lib/hooks';
import { Await, BlockChip, Chip, ChannelChip, RouteChip, Section } from '@/components/ui';

const NODE = { intake: 'Intake', safety_screen: 'Safety screen', classify: 'Classify', scope_check: 'Scope check', assemble: 'Assemble', verify: 'Verify', autonomy: 'Autonomy' };
const ORDER = Object.keys(NODE);
const val = (v) => (typeof v === 'boolean' ? (v ? 'yes' : 'no') : words(v));
const uniqueProblems = (ps) => [...new Set(ps.map((p) => p.replace('Ungrounded sentence: ', '')))];

function NodeText({ n }) {
  const d = n.detail;
  switch (n.node) {
    case 'intake': return <>{d}</>;
    case 'safety_screen': return <>{d.length ? `${d.length} signal${d.length > 1 ? 's' : ''} found` : 'No adverse event or special situation found by the rules or the safety agent.'}</>;
    case 'classify': return <>{d.questions.length} question{d.questions.length === 1 ? '' : 's'}{d.questions.map((q) => <span key={q.text}><br />"{q.text}" <Chip>{words(q.topic)}</Chip></span>)}</>;
    case 'scope_check': return <>{d.reasons.length ? d.reasons.join('. ') : 'Every question is inside the approved label for this country.'}</>;
    case 'assemble': return <>
      {d.answers.map((a, i) => <span key={i}>{a.block_ids.length ? a.block_ids.map((b) => <BlockChip key={b} id={b} />) : <Chip tone="red">No block</Chip>} </span>)}
      {d.uncovered.length > 0 && <><br />Not covered: {d.uncovered.join('; ')}</>}
      {d.rejected_ids.length > 0 && <><br />Ids refused by code: {d.rejected_ids.join(', ')}</>}</>;
    case 'verify': return <>{d.length ? d.join('. ') : 'Every sentence matched a current approved block.'}</>;
    case 'autonomy': return <>{d.reasons.length ? d.reasons.join('. ') : 'Every topic is cleared for automatic replies in this country.'}</>;
    default: return null;
  }
}

function Trace({ c }) {
  const ran = Object.fromEntries(c.nodes.map((n) => [n.node, n]));
  const last = c.nodes[c.nodes.length - 1].node;
  return (
    <ol className="trace" id="trace">
      {ORDER.map((k) => {
        const n = ran[k];
        if (!n) return <li className="skipped" key={k}><span className="dot skip" /><h4>{NODE[k]}</h4><p>Not run. The route was already decided.</p></li>;
        const stop = k === last;
        return (
          <li key={k}>
            <span className={`dot ${stop ? 'stop' : 'pass'}`} />
            <h4>{NODE[k]} <small>{n.ms} ms</small></h4>
            <div className="facts">{Object.entries(n.facts).map(([f, v]) => <span key={f} className={f === c.decision.fact ? 'fact hit' : 'fact'}>{words(f)} <b>{val(v)}</b></span>)}</div>
            <p><NodeText n={n} /></p>
            {stop && <div className="decision"><b>{c.decision.rule < 10 ? `Rule ${c.decision.rule + 1} matched` : 'Every rule passed'}: <RouteChip route={c.route} /></b>{c.decision.why}</div>}
          </li>
        );
      })}
    </ol>
  );
}

function Stapled({ c }) {
  const check = c.status === 'blocked_at_send' || c.status === 'sent' ? c.send_check || c.verification : c.verification;
  const roles = Object.fromEntries(c.draft.segments.map((s) => [s.block_id, s.role]));
  const problems = uniqueProblems(check.problems);
  return (
    <div className="doc reply">
      <div className="dt">
        <div><b>Reply to {c.hcp?.name || 'sender'}</b><span className="dsub">{c.product}, {c.country}, {STATUS[c.status] || c.status}{c.sent_at ? ` ${when(c.sent_at)}` : ''}</span></div>
        <span className="dst">{check.sentences.length} sentences, {check.sentences.filter((s) => s.ok).length} traced</span>
      </div>
      <ol className="staple">
        {check.sentences.map((s, i) => {
          const now = c.content_now?.[s.block_id];
          const stale = now && !now.current;
          return (
            <li key={i} className={`${roles[s.block_id] || 'answer'}${!s.ok || stale ? ' bad' : ''}`}>
              <span>{s.sentence}</span>
              <span className="rail"><b>{s.block_id || 'No source'}{s.version ? ` v${s.version}` : ''}</b>{s.ok ? s.mlr_ref : s.reason}{stale && s.ok && <span>Now: {now.why_not}</span>}</span>
            </li>
          );
        })}
      </ol>
      {problems.length > 0 && <p className="empty err">{problems.join('. ')}</p>}
      <div className="legend"><span><i />Answer block</span><span className="s"><i />Safety information</span><span className="d"><i />AI disclosure</span><span className="t"><i />Template</span></div>
    </div>
  );
}

const STAMP = {
  pv: ['Not answered', 'red', 'This message describes a possible adverse event or special situation. Pharmacovigilance owns it from here and has its own clock. The AI drafted nothing, and the case went to the pharmacovigilance intake queue with the quoted words below.'],
  offlabel: ['Not answered', 'red', 'The question is outside the approved label in this country. Medical writes any reply by hand; the AI does not draft off-label content.'],
  decline: ['Not answered', 'red', 'No reply was drafted. The reason is recorded in the ledger.'],
  review: ['Medical writes the reply', 'wait', 'Approved content does not cover every question, so the AI has no complete draft to offer. A medical reviewer writes the reply by hand.'],
  specialist: ['Passed to a specialist', 'wait', 'A medical information specialist reads this and decides what to do. The AI drafted nothing.'],
};

function Stamp({ c }) {
  const [t, tone, p] = STAMP[c.route] || ['Not answered', 'red', ''];
  const rules = c.injection?.rules || [];
  return (
    <div className="stamp">
      <span className={`mark ${tone === 'wait' ? 'wait' : ''}`}>{t}</span>
      <p>{p}</p><p><b>{c.decision.why}</b></p>
      {c.signals?.length > 0 && <ul className="signals">{c.signals.map((s, i) => <li key={i}><Chip tone="red">{s.kind}</Chip> <mark>{s.quote}</mark> <span className="muted">found by {s.source}</span></li>)}</ul>}
      {(rules.length > 0 || c.injection?.model) && <ul className="signals">
        {rules.map((r) => <li key={r}><Chip tone="red">rule</Chip> <mark>{r}</mark></li>)}
        {c.injection.model && <li><Chip tone="red">triage agent</Chip> flagged an attempt to change its instructions</li>}</ul>}
    </div>
  );
}

/** Approve re-asks for the password: that is the e-signature. Reject needs only a note. */
function Decide({ c, reload }) {
  const [note, setNote] = useState(c.status === 'blocked_at_send' ? 'Content withdrawn after drafting' : '');
  const [signing, setSigning] = useState(false);
  const blocked = c.status === 'blocked_at_send';

  async function approve(ev) {
    ev.preventDefault();
    try {
      const d = await api(`/api/cases/${encodeURIComponent(c.id)}/approve`, { password: new FormData(ev.target).get('password') });
      toast(d.status === 'sent' ? 'Approved and sent' : 'Send blocked: the draft no longer matches current content', d.status === 'sent' ? 'ok' : 'err');
    } catch (e) { toast(e.message, 'err'); }
    setSigning(false);
    reload();
  }
  async function reject() {
    try { await api(`/api/cases/${encodeURIComponent(c.id)}/reject`, { note }); toast('Rejected'); } catch (e) { toast(e.message, 'err'); }
    reload();
  }

  return (
    <div className="decide">
      <p>{blocked
        ? 'The draft failed its check at the moment of sending, because content it used is no longer current. Nothing was sent. Reject it so Medical writes a new reply.'
        : `A medical reviewer for ${c.country} approves or rejects this draft. Approving asks for your password again, which is the signature, and runs the sentence check against content as it is now; if a block was withdrawn since drafting, the send is blocked.`}</p>
      <textarea id="note" aria-label="Reason for rejecting" placeholder={blocked ? 'Reason' : 'Reason, if you reject'} value={note} onChange={(e) => setNote(e.target.value)} />
      {signing && <form className="form" id="sign" onSubmit={approve}>
        <div className="fld"><label htmlFor="sign-password">Password to sign</label>
          <input id="sign-password" name="password" type="password" autoComplete="current-password" required autoFocus /></div>
        <div className="fld"><button className="btn dark" type="submit">Sign and send</button></div>
      </form>}
      <div className="btns">
        {!blocked && !signing && <button className="btn dark" id="approve" onClick={() => setSigning(true)}>Approve and send</button>}
        <button className="btn" id="reject" onClick={reject}>Reject</button>
      </div>
    </div>
  );
}

function Calls({ c }) {
  const spans = c.trace?.spans || [];
  if (!c.agent_calls.length) return <p className="empty">No agent was called.</p>;
  return c.agent_calls.map((a, i) => {
    const sp = spans.find((s) => s.name === `agent.${a.agent}`);
    const u = a.usage || {};
    return (
      <article className="call" key={i}>
        <header>
          <h4>{a.agent[0].toUpperCase() + a.agent.slice(1)} agent</h4>
          <span className="meta"><span>{a.mode}</span>
            <span className="num">{(u.input_tokens || 0) + (u.cache_read_input_tokens || 0) + (u.cache_creation_input_tokens || 0)} in, {u.output_tokens || 0} out</span>
            <b className="num">{usd(a.cost_usd)}</b></span>
        </header>
        {a.tool_calls.length > 0 && <ul className="tools">{a.tool_calls.map((t, j) => (
          <li key={j}>
            <Chip tone={t.allowed ? 'green' : 'red'}>{t.allowed ? 'Allowed' : 'Blocked'}</Chip>
            <span><b>{t.tool.replace('mcp__mi__', '')}</b> {JSON.stringify(t.input)}<br />
              <span className="muted">{t.reason}. Returned {t.returned?.length ? t.returned.map((b) => <BlockChip key={b} id={b} />) : 'nothing'}</span></span>
          </li>))}</ul>}
        {sp && <pre>{JSON.stringify(sp.output, null, 1)}</pre>}
      </article>
    );
  });
}

function summary(e) {
  switch (e.type) {
    case 'case_received': return <>From <ChannelChip channel={e.channel} />, text hash {short(e.text_sha256)}</>;
    case 'agent_call': return `${e.agent} agent, ${e.model}, prompt ${e.prompt_version}, ${e.mode}`;
    case 'tool_call': return `${e.tool?.replace('mcp__mi__', '')} ${e.allowed ? 'allowed' : 'blocked'}`;
    case 'routed': return <>Route <RouteChip route={e.route} /></>;
    case 'reply_sent': return `Sent${e.approved_by ? ` after approval by ${e.approved_by}` : ' automatically'}, ${e.blocks.length} blocks`;
    case 'authz': return `${e.user} ${e.action} ${e.allowed ? 'allowed' : 'denied'}: ${e.reason}`;
    case 'send_blocked': return `Nothing sent: ${uniqueProblems(e.problems).join('. ')}`;
    case 'draft_invalidated': return <>Draft failed its check: <BlockChip id={e.block} /> was withdrawn</>;
    case 'approved': return `Approved by ${e.user}`;
    case 'rejected': return `Rejected by ${e.user}: ${e.note}`;
    default: return JSON.stringify(Object.fromEntries(Object.entries(e).filter(([k]) => !['at', 'case', 'type'].includes(k))));
  }
}

function Ledger({ rows }) {
  return (
    <table className="tbl chain"><thead><tr><th>Seq</th><th>Entry</th><th>What happened</th><th>Hash</th><th>Previous</th></tr></thead>
      <tbody>{rows.map((r) => (
        <tr key={r.seq}><td className="num">{r.seq}</td><td className="ty">{words(r.entry.type)}</td><td>{summary(r.entry)}</td>
          <td className="hash">{short(r.hash)}{r.signature && <><br /><Chip tone="green">Signed</Chip></>}</td><td className="hash">{short(r.prev)}</td></tr>
      ))}</tbody></table>
  );
}

/** Agents work on a case in the background: follow its history live while a person is still needed. */
function LiveTimeline({ id, active, onChange }) {
  const [live, setLive] = useState([]);
  useEventStream(`/v1/cases/${encodeURIComponent(id)}/events`, active, (name, data) => {
    if (name === 'history') setLive((l) => [...l, data]);
    if (name === 'status') onChange();
  });
  if (!live.length) return null;
  return (
    <div id="live"><h2 className="sec">Live from the agents</h2>
      <ul className="tl">{live.map((h, i) => <li key={i}><time>{when(h.at)}</time><span>{h.event}{h.detail ? <><br /><span className="muted">{Array.isArray(h.detail) ? h.detail.join('. ') : h.detail}</span></> : null}</span></li>)}</ul></div>
  );
}

function CaseView({ id }) {
  const state = useApi(`/api/cases/${encodeURIComponent(id)}`);
  return (
    <Await state={state}>{(c) => {
      if (c.redacted) {
        return <Section><div className="head"><div><h1 className="page">Case {c.id}</h1><p>{c.redacted}</p></div><div className="row"><RouteChip route={c.route} /></div></div></Section>;
      }
      const inq = c.inquiry;
      return (
        <>
          <Section id="top">
            <div className="head"><div><h1 className="page">Case {c.id}</h1><p>{c.decision.why}</p></div>
              <div className="row"><RouteChip route={c.route} /><Chip>{STATUS[c.status] || c.status}</Chip></div></div>
            <blockquote className="quote">{inq.text}</blockquote>
            <div className="meta">
              <span>From <b>{c.hcp?.name || inq.sender || 'Unknown'}</b>{c.hcp ? `, ${c.hcp.specialty}, ${c.hcp.city}` : ''}</span>
              <span><ChannelChip channel={inq.channel} /></span>
              <span>Received <b className="num">{when(inq.received)}</b></span>
              <span>Product <b>{c.product || 'none'}</b></span>
              <span>Country <b>{c.country}</b></span>
              <span>Cost <b className="num">{usd(c.cost_usd)}</b></span>
              <span>Latency <b className="num">{c.latency_ms} ms</b></span>
              <span>Agents <b>{c.mode}</b></span>
            </div>
            {c.history?.length > 0 && <ul className="tl">{c.history.map((h, i) => (
              <li key={i}><time>{when(h.at)}</time><span>{h.event}{h.detail ? <><br /><span className="muted">{Array.isArray(h.detail) ? h.detail.join('. ') : h.detail}</span></> : null}</span></li>))}</ul>}
            <LiveTimeline id={c.id} active={c.status === 'awaiting_review'} onChange={state.reload} />
          </Section>
          <Section>
            <div className="case">
              <div><h2 className="sec">How it was decided</h2><p className="sub">Each node sets facts. The first routing rule that matches stops the graph.</p><Trace c={c} /></div>
              <div><h2 className="sec">The reply</h2>
                <p className="sub" id="replysub">{c.draft ? 'Every sentence is a whole sentence from an approved block. The margin shows which block, which version and its MLR approval.' : 'The AI wrote nothing for this case.'}</p>
                <div className="paper" id="reply">
                  {c.draft ? <Stapled c={c} /> : <Stamp c={c} />}
                  {c.draft && ['awaiting_review', 'blocked_at_send'].includes(c.status) && <Decide c={c} reload={state.reload} />}
                </div></div>
            </div>
          </Section>
          <Section>
            <h2 className="sec">Agent calls and guards</h2>
            <p className="sub">What each agent was asked, what it returned, and every tool call it tried with the Cedar decision that allowed or blocked it. In replay the recorded tool calls run through the guards again.</p>
            <div className="calls" id="calls"><Calls c={c} /></div>
          </Section>
          <Section>
            <h2 className="sec">Ledger entries for this case</h2>
            <p className="sub">Append-only and hash-chained. Each entry carries the hash of the one before it; every tenth is signed with a KMS key and copied to a locked S3 archive.</p>
            <div id="ledger"><Ledger rows={c.ledger} /></div>
          </Section>
        </>
      );
    }}</Await>
  );
}

function Inner() {
  const id = useSearchParams().get('id') || '';
  return <CaseView key={id} id={id} />;
}

export default function CasePage() {
  return <Suspense fallback={<Section><p className="empty">Loading</p></Section>}><Inner /></Suspense>;
}
