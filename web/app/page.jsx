'use client';
import Link from 'next/link';
import { Await, PageHead, RouteChip, Section } from '@/components/ui';
import { useApi } from '@/lib/hooks';
import { words } from '@/lib/format';

// What each node is and whether a model is involved. The facts each node sets come from the API, so
// this page cannot drift from hcpagents.graph.
const NODES = {
  intake: ['Intake', 'Matches the sender to the HCP registry', false],
  safety_screen: ['Safety screen', 'Keyword rules and the safety agent, either one is enough to stop.', true],
  classify: ['Classify', 'Triage agent splits the questions; injection rules run beside it.', true],
  scope_check: ['Scope check', 'Each question against the label for that country', false],
  assemble: ['Assemble', 'Assembler agent picks block ids through two read-only tools.', true],
  verify: ['Verify', 'Every sentence matched to a current approved block', false],
  autonomy: ['Autonomy', 'Is this topic cleared for automatic replies here? Policy read from SSM.', false],
};

const PLANES = [
  ['Agent plane', 'Long-lived Temporal workflows: the inquiry agent, the safety sentinel, the outreach coordinator, the content steward and the insight agent each have a goal and wait for events.'],
  ['Control plane', 'The policy kernel, Cedar, the autonomy ladder, budgets, the model router, the eval gate, the guardian and the ledger. No agent can change these.'],
  ['Data plane', 'Postgres with row-level security per tenant and pgvector, Valkey, the event bus, S3 Object Lock and a KMS key per tenant.'],
  ['Interface plane', 'This console, the versioned /v1 API with server-sent events, the MCP server, the hcp command line and signed channel webhooks.'],
];

const AWS = [
  ['Cases, content, HCP 360, touches', 'Aurora Postgres Serverless v2 with row-level security'],
  ['Audit ledger archive', 'S3 Object Lock in compliance mode, one KMS key per tenant'],
  ['Who may do what', 'Verified Permissions with the Cedar policies in this repo'],
  ['People and roles', 'Cognito user pool with MFA, tenant and role as claims'],
  ['Long-running agents', 'Temporal workers on ECS Fargate'],
  ['Cache, rate limits, idempotency', 'ElastiCache for Valkey, serverless'],
  ['Models', 'Claude Haiku 5.5 and Sonnet 5.5 on Bedrock, granted by model ARN'],
  ['Everything above', 'One CDK stack, checked by cdk-nag before any deploy'],
];

const Agents = ({ agents }) => Object.entries(agents).map(([k, v]) => (
  <article className="call" key={k}>
    <header>
      <h4>{k[0].toUpperCase() + k.slice(1)} agent</h4>
      <span className="row">
        <span className="chip grey">{v.tools ? 'Two read-only MCP tools' : 'No tools'}</span>
        <span className="chip grey">{v.max_turns} turn{v.max_turns > 1 ? 's' : ''} at most</span>
      </span>
    </header>
    <details><summary className="muted">System prompt</summary><pre>{v.system}</pre></details>
  </article>
));

export default function Architecture() {
  const state = useApi('/api/architecture');
  return (
    <>
      <Section>
        <PageHead
          title="Every reply traced to approved content, or no reply at all."
          actions={<><Link className="btn dark" href="/inbox">Open the inbox</Link><Link className="btn" href="/proof">See the proof</Link></>}
        >
          Medical information inquiries from doctors arrive on many channels. A set of agents with their own goals reads each one and
          answers automatically only when every sentence comes from content that Medical, Legal and Regulatory approved and that is
          still current today. Everything else goes to a human in the loop with the reason written down.
        </PageHead>
      </Section>

      <Section>
        <h2 className="sec">Four planes</h2>
        <p className="sub">Agents live in the agent plane and can only act through the control plane, which holds the limits no plan may break.</p>
        <div className="tri">
          {PLANES.map(([t, d]) => <div className="card" key={t}><h3>{t}</h3><p>{d}</p></div>)}
        </div>
      </Section>

      <Await state={state}>{(a) => (
        <>
          <Section>
            <h2 className="sec">The graph</h2>
            <p className="sub">Seven steps run in order. After each one the policy kernel checks the routing table below, and the first rule that matches decides where the case goes. Three steps use a model, outlined in purple; none of them can choose a route or write a sentence.</p>
            <div className="lanes" id="lanes">
              {a.nodes.map((n) => {
                const [title, desc, model] = NODES[n.node];
                return (
                  <div className={model ? 'node model' : 'node'} data-node={n.node} key={n.node}>
                    <b>{title}</b>{desc}
                    <span className="by">{model ? 'Uses the model' : 'Plain code'}</span>
                    <span className="by">Sets {n.facts.map(words).join(', ')}</span>
                  </div>
                );
              })}
            </div>
          </Section>

          <Section>
            <h2 className="sec">The routing table</h2>
            <p className="sub">Order is the policy: safety first, then identity, then intent, then content. It is the policy kernel's table, so no plan an agent makes can reorder it.</p>
            <ol className="rules" id="rules">
              {a.routing.map((r) => (
                <li key={r.fact + r.value}>
                  <code>{words(r.fact)} is {typeof r.value === 'boolean' ? (r.value ? 'yes' : 'no') : words(r.value)}</code>
                  <span><RouteChip route={r.route} /></span><span className="muted">{r.why}</span>
                </li>
              ))}
              <li className="send"><code>Every rule passed</code><span><RouteChip route="send" /></span><span className="muted">{a.send.why}</span></li>
            </ol>
          </Section>

          <Section>
            <h2 className="sec">The agents</h2>
            <p className="sub">Single-purpose model agents on the Claude Agent SDK, each limited to <code>{a.model}</code> or Sonnet 5.5 by the router, with no built-in tools, no settings files and no slash commands. Their output is structured; code checks it before it becomes a fact.</p>
            <div className="calls" id="agents"><Agents agents={a.agents} /></div>
          </Section>

          <Section>
            <h2 className="sec">Who may do what</h2>
            <p className="sub">Cedar policies in Verified Permissions. Every approve, reject, withdraw, autonomy change and agent tool call asks the policy store first, and the answer is written to the ledger with the policy file that decided it.</p>
            <div id="cedar">
              {Object.entries(a.cedar).map(([f, t]) => <details className="code" key={f}><summary>{f}</summary><pre>{t}</pre></details>)}
            </div>
          </Section>
        </>
      )}</Await>

      <Section>
        <h2 className="sec">On AWS</h2>
        <p className="sub">Locally everything runs in containers with Floci standing in for AWS. The CDK stack in <code>deploy/</code> is the production shape and is synthesised and checked on every change.</p>
        <table className="tbl"><thead><tr><th>Job</th><th>Service</th></tr></thead>
          <tbody>{AWS.map(([j, s]) => <tr key={j}><td>{j}</td><td>{s}</td></tr>)}</tbody></table>
      </Section>
    </>
  );
}
