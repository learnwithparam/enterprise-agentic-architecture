'use client';
import { Suspense } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { useApi } from '@/lib/hooks';
import { when, words } from '@/lib/format';
import { Await, BlockChip, CaseLink, ChannelChip, Chip, PageHead, Section } from '@/components/ui';

function People({ selected }) {
  const state = useApi('/api/hcps');
  return (
    <div className="people" id="people"><Await state={state}>{(hs) => hs.map((h) => (
      <Link className="person" key={h.id} href={`/hcp?id=${encodeURIComponent(h.id)}`} aria-current={h.id === selected ? 'true' : undefined}>
        <b>{h.name}</b><small>{h.specialty}, {h.country}</small>
        <span className="row">
          <Chip className="num">{h.touches} touch{h.touches === 1 ? '' : 'es'}</Chip>
          {h.open_cases > 0 && <Chip tone="wait">{h.open_cases} open case{h.open_cases > 1 ? 's' : ''}</Chip>}
          {h.held > 0 && <Chip tone="red">{h.held} held</Chip>}
        </span>
      </Link>))}</Await></div>
  );
}

function Plan({ id }) {
  const plan = useApi(`/api/hcps/${encodeURIComponent(id)}/outreach`);
  return (
    <div id="outreach"><h2 className="sec gap">Outreach coordinator</h2>
      <p className="sub">The agent that decides the next contact. It proposes a touch for a person to send or holds it, and writes the reason with its source.</p>
      <Await state={plan}>{(ds) => ds.length ? ds.map((d) => (
        <p key={d.id}><b className="num">{d.on}</b> <Chip tone={d.action === 'hold' ? 'red' : 'green'}>{d.action === 'hold' ? 'Hold' : 'Propose'}</Chip>
          {d.reasons.map((r) => <span key={r.rule} className="muted"> {r.why}{r.source ? ` (${r.source})` : ''}.</span>)}</p>
      )) : <p className="empty">Nothing to coordinate.</p>}</Await></div>
  );
}

function Detail({ id }) {
  const state = useApi(`/api/hcps/${encodeURIComponent(id)}`);
  return (
    <Await state={state}>{(v) => {
      const h = v.hcp;
      return (
        <>
          <div className="head"><div><h2 className="sec">{h.name}</h2><p>{h.specialty}, {h.city}. Registry id <span className="num">{h.registry_id}</span>.</p></div>
            <div className="row">{Object.entries(h.consent).map(([k, ok]) => <Chip key={k} tone={ok ? 'green' : 'red'}>{words(k)} {ok ? 'yes' : 'no'}</Chip>)}</div></div>
          <div className="meta">{Object.entries(h.records).map(([k, r]) => <span key={k}>{words(k)} <b className="num">{r}</b></span>)}</div><br />
          <div className="two">
            <div>
              <h2 className="sec">Planned touches</h2><p className="sub">What other teams want to send next, and whether the platform lets it go.</p>
              {v.planned.length ? v.planned.map((p) => (
                <div key={p.id} className={`go ${p.decision.go ? 'yes' : 'no'}`}>
                  <div className="row"><b className="num">{p.on}</b><ChannelChip channel={p.channel} />{p.content && <BlockChip id={p.content} />}
                    <Chip tone={p.decision.go ? 'green' : 'red'}>{p.decision.go ? 'Goes out' : 'Held'}</Chip></div>
                  <p>{p.summary}</p>
                  {p.decision.reasons.length > 0 && <ul>{p.decision.reasons.map((r) => <li key={r}>{r}</li>)}</ul>}
                </div>)) : <p className="empty">Nothing planned.</p>}
              <h2 className="sec gap">Open medical cases</h2>
              {v.open_cases.length ? v.open_cases.map((c) => <p key={c.id}><CaseLink id={c.id} /> <span className="muted">{c.product}, {words(c.status)}</span></p>) : <p className="empty">None.</p>}
              <Plan id={id} />
            </div>
            <div>
              <h2 className="sec">Timeline</h2><p className="sub">Every touch from every channel, newest first. Promotional touches count toward the cap.</p>
              <ol className="tl">{v.timeline.length ? v.timeline.map((t, i) => (
                <li key={i}><time>{when(t.on)}</time>
                  <span><span className="row"><ChannelChip channel={t.channel} />{t.promotional && <Chip>Promotional</Chip>}{t.content && <BlockChip id={t.content} />}</span>
                    {t.summary}{t.case && <> <Link href={`/case?id=${encodeURIComponent(t.case)}`}>Open case</Link></>}</span></li>))
                : <li><span /><span className="muted">No touches yet.</span></li>}</ol>
            </div>
          </div>
        </>
      );
    }}</Await>
  );
}

function Inner() {
  const id = useSearchParams().get('id') || 'hcp-kaya';
  return (
    <>
      <Section>
        <PageHead title="HCP 360">
          One record per doctor, joined across the CRM, marketing automation, the contact centre and the portal. It is the shared memory of the agents. Every planned touch is checked against consent, the country's promotional cap, open medical cases and content currency before it goes out.
        </PageHead>
        <People selected={id} />
      </Section>
      <Section id="detail"><Detail key={id} id={id} /></Section>
    </>
  );
}

export default function Hcp() {
  return <Suspense fallback={<Section><p className="empty">Loading</p></Section>}><Inner /></Suspense>;
}
