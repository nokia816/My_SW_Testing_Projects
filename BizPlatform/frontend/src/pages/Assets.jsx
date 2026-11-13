import { useState } from 'react'
import { api } from '../api'
import { useAuth } from '../auth'
import { ASSET_STATUS, ASSET_TYPE, fdate, fdatetime, money, toOptions } from '../labels'
import ResourcePage from '../components/ResourcePage'
import { Badge, ErrorBox, Form, Modal, Table, useLoad } from '../components/ui'

const TONE = { in_stock: 'good', assigned: 'info', repair: 'warn', retired: 'neutral', lost: 'bad' }
const EMP = { endpoint: '/employees', params: { status: 'active' }, label: (e) => `${e.first_name} ${e.last_name} (${e.employee_number})` }
const editableStatus = toOptions(ASSET_STATUS).filter((o) => o.value !== 'assigned')

const assetFields = (canSecret) => [
  { name: 'asset_tag', label: 'תג נכס', required: true, max: 50, help: 'למשל LT-001' },
  { name: 'type', label: 'סוג', type: 'select', options: toOptions(ASSET_TYPE), required: true, default: 'laptop' },
  { name: 'brand', label: 'יצרן', max: 100 },
  { name: 'model', label: 'דגם', max: 150 },
  { name: 'serial_number', label: 'מספר סידורי', max: 100 },
  { name: 'specs', label: 'מפרט (מעבד/זיכרון/דיסק/מערכת הפעלה)', max: 300 },
  { name: 'purchase_date', label: 'תאריך רכישה', type: 'date' },
  { name: 'purchase_price', label: 'מחיר רכישה (₪)', type: 'money' },
  { name: 'supplier_id', label: 'ספק', type: 'ref', ref: { endpoint: '/suppliers', label: (s) => s.name } },
  { name: 'warranty_until', label: 'אחריות עד', type: 'date' },
  { name: 'license_expiry', label: 'תוקף רישיון', type: 'date' },
  ...(canSecret ? [{ name: 'license_key', label: 'מפתח רישיון (מוצפן)', max: 1000, omitIfEmpty: true, help: 'נשמר מוצפן. השאר ריק כדי לא לשנות' }] : []),
  { name: 'status', label: 'סטטוס', type: 'select', options: editableStatus, omitIfEmpty: true },
  { name: 'location', label: 'מיקום', max: 150 },
  { name: 'notes', label: 'הערות', type: 'textarea' },
]

function AssetCard({ asset, onClose, onChanged }) {
  const { can } = useAuth()
  const writable = can('assets', 'write')
  const [cur, setCur] = useState(asset)
  const [mode, setMode] = useState(null)
  const [secret, setSecret] = useState(null)
  const [error, setError] = useState(null)
  const hist = useLoad(() => api(`/assets/${asset.id}/history`), [asset.id, cur.status])
  const done = (x) => { setCur(x); setMode(null); onChanged() }
  const reveal = async () => { try { setSecret((await api(`/assets/${cur.id}/secret`)).license_key) } catch (e) { setError(e) } }
  return (
    <Modal title={`${cur.asset_tag} · ${ASSET_TYPE[cur.type]}`} onClose={onClose} wide>
      <p>{cur.brand} {cur.model} · מס' סידורי {cur.serial_number || '—'} · <Badge tone={TONE[cur.status]}>{ASSET_STATUS[cur.status]}</Badge></p>
      <div className="kv">
        <div><span>מחזיק</span>{cur.employee_name || '—'}</div><div><span>מפרט</span>{cur.specs || '—'}</div>
        <div><span>נרכש</span>{fdate(cur.purchase_date)} · {money(cur.purchase_price)}</div><div><span>אחריות עד</span>{fdate(cur.warranty_until)}</div>
        {cur.license_expiry ? <div><span>תוקף רישיון</span>{fdate(cur.license_expiry)}</div> : null}
        {cur.has_license_key && can('asset_secrets') ? <div><span>מפתח רישיון</span>{secret ? <code>{secret}</code> : <button className="btn small" onClick={reveal}>הצגה (נרשם ביומן)</button>}</div> : null}
      </div>
      <ErrorBox error={error} />
      {mode === 'assign' ? <Form submitLabel="מסירה" onCancel={() => setMode(null)} fields={[
        { name: 'employee_id', label: 'עובד', type: 'ref', ref: EMP, required: true },
        { name: 'condition', label: 'מצב הפריט במסירה', max: 200, default: 'תקין' },
        { name: 'acknowledged', label: 'העובד חתם על קבלת הציוד', type: 'checkbox' },
        { name: 'note', label: 'הערה', max: 300 }]}
        onSubmit={async (v) => done(await api(`/assets/${cur.id}/assign`, { method: 'POST', body: v }))} /> : null}
      {mode === 'return' ? <Form submitLabel="קליטת החזרה" onCancel={() => setMode(null)} fields={[
        { name: 'condition', label: 'מצב הפריט בהחזרה', max: 200 },
        { name: 'new_status', label: 'סטטוס אחרי ההחזרה', type: 'select', options: editableStatus, required: true, default: 'in_stock' },
        { name: 'note', label: 'הערה', max: 300 }]}
        onSubmit={async (v) => done(await api(`/assets/${cur.id}/return`, { method: 'POST', body: v }))} /> : null}
      {mode === 'edit' ? <Form fields={assetFields(can('asset_secrets'))} initial={{ ...cur, license_key: '', status: cur.employee_id ? '' : cur.status }}
        onCancel={() => setMode(null)} onSubmit={async (v) => {
          if (cur.employee_id) delete v.status
          done(await api(`/assets/${cur.id}`, { method: 'PATCH', body: v }))
        }} /> : null}
      {!mode && writable ? <div className="form-actions">
        {cur.employee_id ? <button className="btn primary" onClick={() => setMode('return')}>החזרה מעובד</button>
          : ['in_stock', 'repair'].includes(cur.status) ? <button className="btn primary" onClick={() => setMode('assign')}>מסירה לעובד</button> : null}
        <button className="btn" onClick={() => setMode('edit')}>עריכה</button>
      </div> : null}
      <h3>היסטוריית החזקה</h3>
      <Table rows={hist.data} empty="הפריט לא נמסר מעולם" columns={[
        { key: 'employee_name', label: 'עובד' }, { key: 'assigned_at', label: 'נמסר', render: (r) => fdatetime(r.assigned_at) },
        { key: 'condition_out', label: 'מצב במסירה' }, { key: 'acknowledged', label: 'חתם', render: (r) => (r.acknowledged ? '✔' : '—') },
        { key: 'returned_at', label: 'הוחזר', render: (r) => (r.returned_at ? fdatetime(r.returned_at) : <Badge tone="info">אצל העובד</Badge>) },
        { key: 'condition_in', label: 'מצב בהחזרה' }]} />
    </Modal>
  )
}

export default function Assets() {
  const { can } = useAuth()
  const [card, setCard] = useState(null)
  const [key, setKey] = useState(0)
  return (
    <>
      <ResourcePage key={key} title="מחשבים וציוד" endpoint="/assets" resource="assets" exportName="assets" createLabel="פריט חדש"
        fields={assetFields(can('asset_secrets'))} onRowClick={setCard} canDelete={false}
        filters={[{ name: 'type', label: 'סוג', options: toOptions(ASSET_TYPE) }, { name: 'status', label: 'סטטוס', options: toOptions(ASSET_STATUS) }]}
        columns={[
          { key: 'asset_tag', label: 'תג' }, { key: 'type', label: 'סוג', render: (r) => ASSET_TYPE[r.type] },
          { key: 'model', label: 'יצרן / דגם', render: (r) => `${r.brand || ''} ${r.model || ''}`.trim() || '—' },
          { key: 'serial_number', label: 'מס\' סידורי' }, { key: 'employee_name', label: 'מחזיק' },
          { key: 'warranty_until', label: 'אחריות', render: (r) => fdate(r.warranty_until || r.license_expiry) },
          { key: 'status', label: 'סטטוס', render: (r) => <Badge tone={TONE[r.status]}>{ASSET_STATUS[r.status]}</Badge> },
        ]} />
      {card ? <AssetCard asset={card} onClose={() => setCard(null)} onChanged={() => setKey((k) => k + 1)} /> : null}
    </>
  )
}
