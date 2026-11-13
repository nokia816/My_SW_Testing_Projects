import { useState } from 'react'
import { api, download } from '../api'
import { useAuth } from '../auth'
import { DOC_TYPE, INVOICE_STATUS, PAY_METHOD, fdate, money, toOptions, today } from '../labels'
import { Badge, ConfirmButton, ErrorBox, Form, Modal, Stat, Table, useDebounced, useLoad } from '../components/ui'

const TONE = { open: 'info', partial: 'warn', paid: 'good', cancelled: 'neutral' }
const invoiceFields = (vat) => [
  { name: 'number', label: 'מספר חשבונית', required: true, max: 50 },
  { name: 'doc_type', label: 'סוג מסמך', type: 'select', options: toOptions(DOC_TYPE), required: true, default: 'tax_invoice' },
  { name: 'customer_id', label: 'לקוח', type: 'ref', ref: { endpoint: '/customers', label: (c) => c.name }, required: true },
  { name: 'issue_date', label: 'תאריך הנפקה', type: 'date', required: true, default: today() },
  { name: 'due_date', label: 'תאריך לתשלום', type: 'date', omitIfEmpty: true, help: 'ריק = לפי תנאי התשלום של הלקוח' },
  { name: 'amount_before_vat', label: 'סכום לפני מע"מ (₪)', type: 'money', required: true },
  { name: 'vat_rate', label: `שיעור מע"מ (%)`, type: 'money', default: String(vat), omitIfEmpty: true },
  { name: 'allocation_number', label: 'מספר הקצאה (רשות המסים)', max: 20, help: 'חובה בחשבונית מס מעל 5,000 ₪ לפני מע"מ' },
  { name: 'cancelled', label: 'חשבונית מבוטלת', type: 'checkbox' },
  { name: 'notes', label: 'הערות', type: 'textarea' },
]
const payFields = (balance) => [
  { name: 'paid_on', label: 'תאריך תשלום', type: 'date', required: true, default: today() },
  { name: 'amount', label: 'סכום (₪)', type: 'money', required: true, default: String(balance) },
  { name: 'method', label: 'אמצעי תשלום', type: 'select', options: toOptions(PAY_METHOD), required: true, default: 'bank_transfer' },
  { name: 'reference', label: 'אסמכתא', max: 100 },
]

function InvoiceDetail({ inv, onClose, onChanged, vat }) {
  const { can } = useAuth()
  const writable = can('invoices', 'write')
  const [cur, setCur] = useState(inv)
  const [mode, setMode] = useState(null)
  const [error, setError] = useState(null)
  const done = (x) => { setCur(x); setMode(null); onChanged() }
  const run = async (fn) => { setError(null); try { await fn() } catch (e) { setError(e) } }
  return (
    <Modal title={`חשבונית #${cur.number}`} onClose={onClose} wide>
      <div className="stats">
        <Stat label="סה&quot;כ כולל מע&quot;מ" value={money(cur.total)} sub={`${money(cur.amount_before_vat)} + מע"מ ${money(cur.vat_amount)}`} />
        <Stat label="שולם" value={money(cur.paid)} tone="good" />
        <Stat label="יתרה" value={money(cur.balance)} tone={cur.overdue ? 'bad' : ''} sub={cur.overdue ? 'באיחור!' : `לתשלום עד ${fdate(cur.due_date)}`} />
      </div>
      <p>{cur.customer_name} · {DOC_TYPE[cur.doc_type]} · הונפקה {fdate(cur.issue_date)} · <Badge tone={TONE[cur.status]}>{INVOICE_STATUS[cur.status]}</Badge></p>
      {cur.allocation_required ? <div className="alert warn">⚠ חסר מספר הקצאה. בלי מספר הקצאה הלקוח לא יוכל לקזז מע"מ</div> : cur.allocation_number ? <p className="muted">מספר הקצאה: {cur.allocation_number}</p> : null}
      <ErrorBox error={error} />
      {mode === 'edit' ? <Form fields={invoiceFields(vat)} initial={{ ...cur, cancelled: cur.status === 'cancelled' }} onCancel={() => setMode(null)}
        onSubmit={async (v) => done(await api(`/invoices/${cur.id}`, { method: 'PATCH', body: v }))} /> : null}
      {mode === 'pay' ? <Form fields={payFields(cur.balance)} onCancel={() => setMode(null)} submitLabel="רישום תשלום"
        onSubmit={async (v) => done(await api(`/invoices/${cur.id}/payments`, { method: 'POST', body: v }))} /> : null}
      {!mode && writable ? (
        <div className="form-actions">
          {cur.status !== 'cancelled' && Number(cur.balance) > 0 ? <button className="btn primary" onClick={() => setMode('pay')}>+ רישום תשלום</button> : null}
          <button className="btn" onClick={() => setMode('edit')}>עריכה</button>
          {!cur.payments.length ? <ConfirmButton onConfirm={() => run(async () => { await api(`/invoices/${cur.id}`, { method: 'DELETE' }); onChanged(); onClose() })}>מחיקה</ConfirmButton> : null}
        </div>
      ) : null}
      <h3>תשלומים</h3>
      <Table rows={cur.payments} empty="טרם התקבלו תשלומים" columns={[
        { key: 'paid_on', label: 'תאריך', render: (r) => fdate(r.paid_on) }, { key: 'amount', label: 'סכום', num: true, render: (r) => money(r.amount) },
        { key: 'method', label: 'אמצעי', render: (r) => PAY_METHOD[r.method] }, { key: 'reference', label: 'אסמכתא' },
        ...(writable ? [{ key: 'x', label: '', render: (r) => <ConfirmButton className="btn small" message="למחוק את התשלום?" onConfirm={() => run(async () => done(await api(`/invoices/${cur.id}/payments/${r.id}`, { method: 'DELETE' })))}>מחיקה</ConfirmButton> }] : [])]} />
    </Modal>
  )
}

export default function Invoices() {
  const { can, me } = useAuth()
  const [q, setQ] = useState('')
  const [status, setStatus] = useState('')
  const [overdue, setOverdue] = useState(false)
  const [open, setOpen] = useState(null)
  const [creating, setCreating] = useState(false)
  const dq = useDebounced(q)
  const list = useLoad(() => api('/invoices', { params: { q: dq, status, overdue, limit: 500 } }), [dq, status, overdue])
  const items = list.data?.items || []
  const sum = (fn) => items.reduce((s, i) => s + Number(fn(i)), 0)
  return (
    <section>
      <div className="page-head"><h1>מעקב חשבוניות</h1>
        <div className="toolbar">
          <input type="search" placeholder="מספר / לקוח / הקצאה…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="חיפוש" />
          <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="סטטוס"><option value="">כל הסטטוסים</option>{toOptions(INVOICE_STATUS).map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</select>
          <label className="check-inline"><input type="checkbox" checked={overdue} onChange={(e) => setOverdue(e.target.checked)} /> באיחור בלבד</label>
          <button className="btn" onClick={() => download('/export/invoices')}>ייצוא ל-Excel</button>
          {can('invoices', 'write') ? <button className="btn primary" onClick={() => setCreating(true)}>+ רישום חשבונית</button> : null}
        </div>
      </div>
      <p className="muted small">החשבוניות מופקות במחלקת הנהלת החשבונות. כאן עוקבים אחרי סטטוס, גבייה וחובות.</p>
      <div className="stats">
        <Stat label="סה&quot;כ חויב (בסינון)" value={money(sum((i) => (i.status === 'cancelled' ? 0 : i.total)))} />
        <Stat label="נגבה" value={money(sum((i) => i.paid))} tone="good" />
        <Stat label="יתרה פתוחה" value={money(sum((i) => (i.status === 'cancelled' ? 0 : i.balance)))} tone="warn" />
      </div>
      <ErrorBox error={list.error} />
      <Table rows={items} onRowClick={setOpen} columns={[
        { key: 'number', label: 'מספר' }, { key: 'customer_name', label: 'לקוח' },
        { key: 'issue_date', label: 'הונפקה', render: (r) => fdate(r.issue_date) },
        { key: 'due_date', label: 'לתשלום עד', render: (r) => <span className={r.overdue ? 'bad-text' : ''}>{fdate(r.due_date)}</span> },
        { key: 'total', label: 'סה"כ', num: true, render: (r) => money(r.total) },
        { key: 'balance', label: 'יתרה', num: true, render: (r) => money(r.balance) },
        { key: 'status', label: 'סטטוס', render: (r) => <>{<Badge tone={r.overdue ? 'bad' : TONE[r.status]}>{r.overdue ? 'באיחור' : INVOICE_STATUS[r.status]}</Badge>}{r.allocation_required ? <Badge tone="warn">חסר הקצאה</Badge> : null}</> },
      ]} />
      {creating ? <Modal title="רישום חשבונית למעקב" onClose={() => setCreating(false)} wide>
        <Form fields={invoiceFields(me.vat_rate).filter((f) => f.name !== 'cancelled')} onCancel={() => setCreating(false)}
          onSubmit={async (v) => { await api('/invoices', { method: 'POST', body: v }); setCreating(false); list.reload() }} />
      </Modal> : null}
      {open ? <InvoiceDetail inv={open} vat={me.vat_rate} onClose={() => setOpen(null)} onChanged={list.reload} /> : null}
    </section>
  )
}
