'use client';
import { api } from '@/lib/api';
import { usd, words } from '@/lib/format';
import { toast, useApi } from '@/lib/hooks';
import { Await, Chip, PageHead, Section } from '@/components/ui';

const MODEL = { haiku: 'Haiku 5.5', sonnet: 'Sonnet 5.5', none: 'No model' };

const Line = ({ label, children }) => <p><b>{label}</b> {children}</p>;

function Roster({ agents }) {
  return (
    <div className="calls" id="roster">{agents.map((a) => (
      <article className="call" key={a.id} data-agent={a.id}>
        <header><h4>{a.name}</h4>
          <span className="meta"><Chip>{MODEL[a.model] || a.model}</Chip><span className="num">{a.calls} calls</span><b className="num">{usd(a.cost_usd)}</b></span></header>
        <p>{a.goal}</p>
        <Line label="Perceives">{a.perceives}</Line>
        <Line label="Acts alone">{a.acts_alone}</Line>
        <Line label="Proposes to a person">{a.proposes}</Line>
        <Line label="Never">{a.never}</Line>
      </article>))}</div>
  );
}

function Autonomy({ autonomy, guardian }) {
  return (
    <div className="card" id="autonomy-by-country"><div className="call">{Object.entries(autonomy).map(([code, s]) => (
      <div className="switch" key={code}>
        <div><b>{code}</b> <Chip tone={s.enabled ? 'green' : 'red'}>{s.enabled ? 'On' : 'Off'}</Chip><br />
          <span className="muted">{s.topics.length ? `Cleared topics: ${s.topics.map(words).join(', ')}` : 'No topic is cleared, so every draft goes to review'}</span>
          {guardian[code]?.reviewed > 0 && <><br /><span className="muted">Reviewers rejected {Math.round(guardian[code].override_rate * 100)}% of {guardian[code].reviewed} drafts</span></>}</div>
      </div>))}</div></div>
  );
}

function Proposals({ list, refresh }) {
  return (
    <>
      <div className="btns"><button className="btn" id="refresh" onClick={refresh}>Look for proposals</button></div>
      {list.length ? list.map((p) => (
        <div className="call" key={p.id}><header><h4>{words(p.kind)}</h4><span className="meta"><Chip tone="wait">{words(p.status)}</Chip></span></header>
          <p>{p.change}</p></div>)) : <p className="empty">No proposals. The improver writes one when reviewers keep correcting the same thing.</p>}
    </>
  );
}

export default function Agents() {
  const state = useApi('/api/agents');
  async function refresh() {
    try { const r = await api('/api/proposals/refresh', {}); toast(`${r.length || 0} proposal${r.length === 1 ? '' : 's'} found`); state.reload(); } catch (e) { toast(e.message, 'err'); }
  }
  return (
    <>
      <Section>
        <PageHead title="Agents">
          The agents of this client, each with a goal, what it perceives, what it may do alone and what it may only propose. An agent acts alone only in the direction that lowers risk. Cost and calls come from the AI gateway's spend log.
        </PageHead>
        <Await state={state}>{(d) => <Roster agents={d.agents} />}</Await>
      </Section>
      <Section>
        <h2 className="sec">Autonomy by country</h2>
        <p className="sub">Which topics may be answered without a person, and how often reviewers overrode the drafts. The guardian lowers autonomy on its own; only a person raises it again.</p>
        <Await state={state}>{(d) => <Autonomy autonomy={d.autonomy} guardian={d.guardian} />}</Await>
      </Section>
      <Section>
        <h2 className="sec">Proposals</h2>
        <p className="sub">What the improver learned from corrections. It runs candidates against the eval gate and never promotes anything itself.</p>
        <Await state={state}>{(d) => <Proposals list={d.proposals} refresh={refresh} />}</Await>
      </Section>
    </>
  );
}
