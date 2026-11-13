import { useState } from 'react'
import { api } from '../api'
import { useAuth } from '../auth'
import { MOVEMENT, fdatetime, toOptions } from '../labels'
import { ErrorBox, Form, Modal, Table, useLoad, useRefOptions } from '../components/ui'

const WH = { endpoint: '/warehouses', label: (w) => w.name }
const PROD = { endpoint: '/products', label: (p) => `${p.name} (${p.sku})` }
export const movementFields = [
  { name: 'product_id', label: 'מוצר', type: 'ref', ref: PROD, required: true },
  { name: 'type', label: 'סוג תנועה', type: 'select', options: toOptions(MOVEMENT), required: true, default: 'receive' },
  { name: 'warehouse_id', label: 'מחסן', type: 'ref', ref: WH, required: true },
  { name: 'quantity', label: 'כמות', type: 'number', min: -10000000, required: true, help: 'בתיקון ספירה: מספר שלילי מפחית מהמלאי' },
  { name: 'to_warehouse_id', label: 'מחסן יעד (להעברה)', type: 'ref', ref: WH, omitIfEmpty: true },
  { name: 'unit_cost', label: 'עלות ליחידה (₪)', type: 'money', omitIfEmpty: true },
  { name: 'reference', label: 'אסמכתא (מס\' תעודה/הזמנה)', max: 100 },
  { name: 'note', label: 'הערה', max: 300 },
]

export default function Stock() {
  const { can } = useAuth()
  const [adding, setAdding] = useState(false)
  const moves = useLoad(() => api('/stock/movements', { params: { limit: 300 } }))
  const products = useRefOptions(PROD)
  const whs = useRefOptions(WH)
  const name = (opts, id) => opts.find((o) => o.value === id)?.label || id
  const add = async (v) => { await api('/stock/movements', { method: 'POST', body: v }); setAdding(false); moves.reload() }
  return (
    <section>
      <div className="page-head"><h1>תנועות מלאי</h1>
        <div className="toolbar">{can('stock', 'write') ? <button className="btn primary" onClick={() => setAdding(true)}>+ תנועה חדשה</button> : null}</div>
      </div>
      <ErrorBox error={moves.error} />
      <Table rows={moves.data?.items} columns={[
        { key: 'ts', label: 'תאריך', render: (r) => fdatetime(r.ts) },
        { key: 'product_id', label: 'מוצר', render: (r) => name(products, r.product_id) },
        { key: 'warehouse_id', label: 'מחסן', render: (r) => name(whs, r.warehouse_id) },
        { key: 'type', label: 'סוג', render: (r) => MOVEMENT[r.type] },
        { key: 'quantity', label: 'כמות', num: true, render: (r) => <span className={r.quantity < 0 ? 'bad-text' : 'good-text'}>{r.quantity > 0 ? '+' : ''}{r.quantity}</span> },
        { key: 'reference', label: 'אסמכתא' }, { key: 'note', label: 'הערה' }]} />
      {adding ? <Modal title="תנועת מלאי חדשה" onClose={() => setAdding(false)} wide><Form fields={movementFields} onSubmit={add} onCancel={() => setAdding(false)} submitLabel="רישום" /></Modal> : null}
    </section>
  )
}
