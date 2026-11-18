'use client';
import { useState } from 'react';
import { api } from '@/lib/api';
import { useApi } from '@/lib/hooks';
import { Await, Chip, PageHead, Section } from '@/components/ui';

const LABEL = {
  approved: ['Approved', 'green'],
  unapproved: ['Not approved', 'red'],
  withdrawn: ['Withdrawn', 'red'],
  wrong_country: ['Wrong country', 'red'],
};

function Form({ blocks }) {
  const products = [...new Set(blocks.map((b) => b.product))].sort();
  const countries = [...new Set(blocks.map((b) => b.country))].sort();
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  async function submit(ev) {
    ev.preventDefault();
    const form = new FormData(ev.target);
    setBusy(true);
    setError(null);
    try {
      setResult(await api('/api/content/check', { text: form.get('text'), product: form.get('product'), country: form.get('country') }));
    } catch (e) { setError(e); setResult(null); }
    setBusy(false);
  }

  const bad = result ? result.sentences.filter((s) => s.status !== 'approved').length : 0;
  return (
    <>
      <form className="form" id="check" onSubmit={submit}>
        <div className="fld"><label htmlFor="product">Product</label>
          <select id="product" name="product">{products.map((p) => <option key={p} value={p}>{p}</option>)}</select></div>
        <div className="fld"><label htmlFor="country">Country</label>
          <select id="country" name="country">{countries.map((c) => <option key={c} value={c}>{c}</option>)}</select></div>
        <div className="fld w"><label htmlFor="text">Email copy</label>
          <textarea id="text" name="text" required placeholder="Paste the email text here" /></div>
        <div className="fld w"><button className="btn dark" type="submit" disabled={busy}>Check</button></div>
      </form>
      {error && <p className="empty err">{error.message}</p>}
      {result && (
        <div id="result">
          <h2 className="sec gap">{result.ok ? 'Every sentence is approved.' : `${bad} of ${result.sentences.length} sentences cannot go out.`}</h2>
          {result.sentences.map((s, i) => {
            const [label, tone] = LABEL[s.status] || [s.status, 'grey'];
            return <p key={i}><Chip tone={tone}>{label}</Chip> {s.text}{s.block_id && <span className="muted"> ({s.block_id})</span>}</p>;
          })}
        </div>
      )}
    </>
  );
}

export default function Check() {
  const blocks = useApi('/api/content');
  return (
    <Section>
      <PageHead title="Fact check">
        Paste the copy for an email and pick the product and country. Each sentence is matched to approved text that is current today. A sentence with no match, a withdrawn block or a block for another country cannot go out.
      </PageHead>
      <Await state={blocks}>{(bs) => <Form blocks={bs} />}</Await>
    </Section>
  );
}
