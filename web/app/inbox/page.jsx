'use client';
import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { api } from '@/lib/api';
import { STATUS, when } from '@/lib/format';
import { toast, useApi } from '@/lib/hooks';
import { Await, CaseLink, ChannelChip, PageHead, RouteChip, Section } from '@/components/ui';

function Row({ r, run, running }) {
  return (
    <tr className={r.eval_only ? 'off' : ''}>
      <td className="num">{when(r.received)}<br /><ChannelChip channel={r.channel} /></td>
      <td>{r.from || 'Unknown sender'}<br /><span className="muted">{r.country || ''}{r.submitted_by ? ', via field rep' : ''}</span></td>
      <td className="q">{r.text === null ? <span className="muted">Hidden from field reps. Only Medical sees inquiry text.</span> : r.text}</td>
      <td>{r.case
        ? <><RouteChip route={r.case.route} /><br /><span className="muted">{STATUS[r.case.status] || r.case.status}</span></>
        : <span className="muted">Not run yet</span>}</td>
      <td className="act">{r.case
        ? <CaseLink id={r.id} className="btn sm">Open case</CaseLink>
        : <button className="btn sm" disabled={running === r.id} onClick={() => run(r.id)}>{running === r.id ? 'Running' : 'Run'}</button>}</td>
    </tr>
  );
}

function AskForm({ hcps }) {
  const router = useRouter();
  async function submit(ev) {
    ev.preventDefault();
    try {
      const d = await api('/api/inquiries', Object.fromEntries(new FormData(ev.target)));
      router.push(`/case?id=${encodeURIComponent(d.id)}`);
    } catch (e) { toast(e.message, 'err'); }
  }
  return (
    <form className="form" id="ask" onSubmit={submit}>
      <div className="fld"><label htmlFor="hcp">From</label>
        <select id="hcp" name="hcp">{hcps.map((h) => <option key={h.id} value={h.id}>{h.name}, {h.country}</option>)}</select></div>
      <div className="fld"><label htmlFor="ch">Channel</label>
        <select id="ch" name="channel"><option value="portal">HCP portal</option><option value="email">Email</option><option value="chatbot">Chatbot</option></select></div>
      <div className="fld w"><label htmlFor="text">Question</label>
        <textarea id="text" name="text" required maxLength={2000} defaultValue="Is Veltrona safe to use in children under 12?" /></div>
      <div className="fld w"><button className="btn dark send" type="submit">Run this question</button></div>
    </form>
  );
}

export default function Inbox() {
  const inbox = useApi('/api/inquiries');
  const hcps = useApi('/api/hcps');
  const router = useRouter();
  const [running, setRunning] = useState(null);
  const [all, setAll] = useState(null);

  async function run(id) {
    setRunning(id);
    try {
      await api(`/api/inquiries/${id}/run`, {});
      router.push(`/case?id=${encodeURIComponent(id)}`);
    } catch (e) { toast(e.message, 'err'); setRunning(null); }
  }

  async function runAll() {
    const todo = inbox.data.filter((r) => !r.eval_only);
    for (const [i, r] of todo.entries()) {
      setAll(`Running ${i + 1} of ${todo.length}`);
      try { await api(`/api/inquiries/${r.id}/run`, {}); } catch (e) { toast(`${r.id}: ${e.message}`, 'err'); }
    }
    setAll(null);
    inbox.reload();
  }

  return (
    <>
      <Section>
        <PageHead title="Inbox" actions={<button className="btn dark" id="all" disabled={!inbox.data || all !== null} onClick={runAll}>{all || 'Run every inquiry'}</button>}>
          Unsolicited questions from doctors, as they arrive from the portal, email, the chatbot, the contact centre and field reps. Run one to watch the agents decide where it goes, then open the case to see why.
        </PageHead>
        <div id="list"><Await state={inbox}>{(rows) => (
          <table className="tbl"><thead><tr><th>Received</th><th>From</th><th>Message</th><th>Where it went</th><th /></tr></thead>
            <tbody>{rows.map((r) => <Row key={r.id} r={r} run={run} running={running} />)}</tbody></table>
        )}</Await></div>
      </Section>
      <Section>
        <h2 className="sec">Ask a new question</h2>
        <p className="sub">A typed question has no recorded run, so it calls the model. The server refuses unless it was started with LIVE=1, and every live run is capped at one cent.</p>
        {hcps.data && <AskForm hcps={hcps.data} />}
      </Section>
    </>
  );
}
