'use client';
import { api } from '@/lib/api';
import { when } from '@/lib/format';
import { toast, useApi } from '@/lib/hooks';
import { Await, BlockChip, Chip, PageHead, Section } from '@/components/ui';

export default function Content() {
  const blocks = useApi('/api/content');

  async function withdraw(id) {
    try {
      const r = await api(`/api/content/${encodeURIComponent(id)}/withdraw`, { note: 'Label update pending, withdrawn from use' });
      toast(r.cases.length ? `Withdrawn. Drafts now failing their check: ${r.cases.join(', ')}` : 'Withdrawn. No open draft used it.');
      blocks.reload();
    } catch (e) { toast(e.message, 'err'); }
  }

  return (
    <Section>
      <PageHead title="Approved content">
        The only text the platform may send. Each block passed Medical, Legal and Regulatory review for one product and one country, and is current only between its approval and expiry dates. Withdraw one as the content owner and the content steward pulls every open draft that used it back to review.
      </PageHead>
      <div id="blocks"><Await state={blocks}>{(bs) => (
        <table className="tbl"><thead><tr><th>Block</th><th>For</th><th>Text</th><th>Approval</th><th>Now</th><th /></tr></thead>
          <tbody>{bs.map((b) => (
            <tr key={b.id} className={b.current ? '' : 'off'}>
              <td><BlockChip id={b.id} version={b.version} /><br /><span className="muted">{b.topic || b.kind || ''}</span></td>
              <td>{b.product}, {b.country}</td>
              <td className="q">{b.text}</td>
              <td className="num">{b.mlr_ref}<br /><span className="muted">{b.approved_on || ''} to {b.expires_on || ''}</span></td>
              <td>{b.current ? <Chip tone="green">Current</Chip> : <><Chip tone="red">Not current</Chip><br /><span className="muted">{b.why_not}</span></>}
                {b.withdrawn && <><br /><span className="muted">By {b.withdrawn.by} {when(b.withdrawn.at)}</span></>}</td>
              <td className="act">{b.current && <button className="btn sm" data-w={b.id} onClick={() => withdraw(b.id)}>Withdraw</button>}</td>
            </tr>
          ))}</tbody></table>
      )}</Await></div>
    </Section>
  );
}
