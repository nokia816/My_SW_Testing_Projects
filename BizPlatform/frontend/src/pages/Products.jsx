import { useState } from 'react'
import { api } from '../api'
import { useAuth } from '../auth'
import { MOVEMENT, fdatetime, money } from '../labels'
import ResourcePage from '../components/ResourcePage'
import { Badge, Form, Modal, Table, useLoad } from '../components/ui'
import { movementFields } from './Stock'

export const productFields = [
  { name: 'sku', label: 'מק"ט', required: true, max: 64 },
  { name: 'name', label: 'שם המוצר', required: true },
  { name: 'category', label: 'קטגוריה', max: 100 },
  { name: 'barcode', label: 'ברקוד', max: 64 },
  { name: 'unit', label: 'יחידת מידה', default: "יח'", max: 20 },
  { name: 'supplier_id', label: 'ספק', type: 'ref', ref: { endpoint: '/suppliers', label: (s) => s.name } },
  { name: 'cost_price', label: 'מחיר עלות (₪)', type: 'money', default: '0' },
  { name: 'sale_price', label: 'מחיר מכירה (₪)', type: 'money', default: '0' },
  { name: 'min_stock', label: 'מלאי מינימום (התראה)', type: 'number', default: 0 },
  { name: 'is_active', label: 'פעיל', type: 'checkbox', default: true },
  { name: 'description', label: 'תיאור', type: 'textarea' },
]

function ProductStock({ product, onClose }) {
  const { can } = useAuth()
  const levels = useLoad(() => api('/stock/levels', { params: { product_id: product.id } }), [product.id])
  const moves = useLoad(() => api('/stock/movements', { params: { product_id: product.id, limit: 50 } }), [product.id])
  const [adding, setAdding] = useState(false)
  const add = async (v) => { await api('/stock/movements', { method: 'POST', body: { ...v, product_id: product.id } }); setAdding(false); levels.reload(); moves.reload() }
  return (
    <Modal title={`מלאי: ${product.name}`} onClose={onClose} wide>
      <div className="chips">{levels.data?.map((l) => <Badge key={l.warehouse_id}>{l.warehouse}: {l.quantity}</Badge>)}</div>
      {can('stock', 'write') ? (adding ? <Form fields={movementFields.filter((f) => f.name !== 'product_id')} onSubmit={add} onCancel={() => setAdding(false)} submitLabel="רישום תנועה" />
        : <button className="btn primary" onClick={() => setAdding(true)}>+ תנועת מלאי</button>) : null}
      <h3>תנועות אחרונות</h3>
      <Table rows={moves.data?.items} columns={[
        { key: 'ts', label: 'תאריך', render: (r) => fdatetime(r.ts) }, { key: 'type', label: 'סוג', render: (r) => MOVEMENT[r.type] },
        { key: 'quantity', label: 'כמות', num: true, render: (r) => <span className={r.quantity < 0 ? 'bad-text' : 'good-text'}>{r.quantity > 0 ? '+' : ''}{r.quantity}</span> },
        { key: 'reference', label: 'אסמכתא' }, { key: 'note', label: 'הערה' }]} />
    </Modal>
  )
}

export default function Products() {
  const [stockOf, setStockOf] = useState(null)
  return (
    <>
      <ResourcePage title="מוצרים" endpoint="/products" resource="products" exportName="products" createLabel="מוצר חדש"
        fields={productFields}
        columns={[
          { key: 'sku', label: 'מק"ט' }, { key: 'name', label: 'שם' }, { key: 'category', label: 'קטגוריה' },
          { key: 'sale_price', label: 'מחיר', num: true, render: (r) => money(r.sale_price) },
          { key: 'stock', label: 'במלאי', num: true, render: (r) => <span className={r.min_stock && r.stock <= r.min_stock ? 'bad-text' : ''}>{r.stock} {r.unit}</span> },
          { key: 'is_active', label: 'סטטוס', render: (r) => (r.is_active ? <Badge tone="good">פעיל</Badge> : <Badge>לא פעיל</Badge>) },
        ]}
        rowActions={(r) => <button className="btn small" onClick={(e) => { e.stopPropagation(); setStockOf(r) }}>מלאי</button>} />
      {stockOf ? <ProductStock product={stockOf} onClose={() => setStockOf(null)} /> : null}
    </>
  )
}
