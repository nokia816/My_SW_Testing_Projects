import { useState } from 'react'
import { api } from '../api'
import { useAuth } from '../auth'
import { ASSET_TYPE, EMP_STATUS, fdate, fdatetime, toOptions } from '../labels'
import ResourcePage from '../components/ResourcePage'
import { Badge, ErrorBox, Form, Modal, Table, useLoad, useRefOptions } from '../components/ui'

const DEPT = { endpoint: '/departments', label: (d) => d.name }
const TONE = { active: 'good', offboarding: 'warn', left: 'neutral' }

function fields(canPii) {
  return [
    { name: 'employee_number', label: 'מספר עובד', required: true, max: 30 },
    { name: 'first_name', label: 'שם פרטי', required: true, max: 100 },
    { name: 'last_name', label: 'שם משפחה', required: true, max: 100 },
    ...(canPii ? [{ name: 'national_id', label: 'ת.ז (מוצפן)', max: 9, help: 'נשמר מוצפן. גלוי רק למשאבי אנוש ולמנהל מערכת' }] : []),
    { name: 'email', label: 'אימייל', type: 'email' },
    { name: 'phone', label: 'טלפון', type: 'tel', max: 40 },
    { name: 'department_id', label: 'מחלקה', type: 'ref', ref: DEPT },
    { name: 'position', label: 'תפקיד', max: 120 },
    { name: 'start_date', label: 'תחילת עבודה', type: 'date' },
    { name: 'end_date', label: 'סיום עבודה', type: 'date' },
    { name: 'status', label: 'סטטוס', type: 'select', options: toOptions(EMP_STATUS), required: true, default: 'active' },
    { name: 'notes', label: 'הערות', type: 'textarea' },
  ]
}

function EmployeeCard({ emp, onClose, onChanged }) {
  const { can } = useAuth()
  const [edit, setEdit] = useState(false)
  const [error, setError] = useState(null)
  const assets = useLoad(() => (can('assets') ? api(`/employees/${emp.id}/assets`) : Promise.resolve(null)), [emp.id])
  const offboard = async () => {
    if (!window.confirm('להתחיל תהליך עזיבה? כל הציוד שבידי העובד יסומן להחזרה')) return
    try { await api(`/employees/${emp.id}/offboard`, { method: 'POST' }); onChanged(); onClose() } catch (e) { setError(e) }
  }
  return (
    <Modal title={`${emp.first_name} ${emp.last_name}`} onClose={onClose} wide>
      <p>#{emp.employee_number} · {emp.position || '—'} · <Badge tone={TONE[emp.status]}>{EMP_STATUS[emp.status]}</Badge></p>
      <ErrorBox error={error} />
      {edit ? <Form fields={fields(can('employees_pii'))} initial={emp} onCancel={() => setEdit(false)}
        onSubmit={async (v) => { await api(`/employees/${emp.id}`, { method: 'PATCH', body: v }); onChanged(); onClose() }} />
        : can('employees', 'write') ? <div className="form-actions"><button className="btn" onClick={() => setEdit(true)}>עריכת פרטים</button>
          {emp.status === 'active' ? <button className="btn danger" onClick={offboard}>התחלת תהליך עזיבה</button> : null}</div> : null}
      {assets.data ? <>
        <h3>ציוד שבידי העובד ({assets.data.current.length})</h3>
        {emp.status === 'offboarding' && assets.data.current.length ? <div className="alert warn">יש להחזיר את הפריטים הבאים לפני סיום העסקה</div> : null}
        <Table rows={assets.data.current} empty="אין ציוד" columns={[{ key: 'asset_tag', label: 'תג' }, { key: 'type', label: 'סוג', render: (r) => ASSET_TYPE[r.type] },
          { key: 'model', label: 'דגם', render: (r) => `${r.brand || ''} ${r.model || ''}` }, { key: 'serial_number', label: 'מס\' סידורי' }]} />
        <h3>היסטוריית ציוד</h3>
        <Table rows={assets.data.history} empty="אין היסטוריה" columns={[{ key: 'asset_tag', label: 'תג' },
          { key: 'assigned_at', label: 'נמסר', render: (r) => fdatetime(r.assigned_at) }, { key: 'returned_at', label: 'הוחזר', render: (r) => (r.returned_at ? fdatetime(r.returned_at) : <Badge tone="info">עדיין אצלו</Badge>) },
          { key: 'condition_in', label: 'מצב בהחזרה' }]} />
      </> : null}
    </Modal>
  )
}

export default function Employees() {
  const { can } = useAuth()
  const [card, setCard] = useState(null)
  const [key, setKey] = useState(0)
  const depts = useRefOptions(DEPT)
  return (
    <>
      <ResourcePage key={key} title="עובדים" endpoint="/employees" resource="employees" exportName="employees" createLabel="עובד חדש"
        fields={fields(can('employees_pii'))} canDelete={false} onRowClick={setCard}
        filters={[{ name: 'status', label: 'סטטוס', options: toOptions(EMP_STATUS) }, { name: 'department_id', label: 'מחלקה', options: depts }]}
        columns={[
          { key: 'employee_number', label: 'מס\'' }, { key: 'name', label: 'שם', render: (r) => `${r.first_name} ${r.last_name}` },
          { key: 'department_id', label: 'מחלקה', render: (r) => depts.find((d) => d.value === r.department_id)?.label || '—' },
          { key: 'position', label: 'תפקיד' }, { key: 'start_date', label: 'תחילת עבודה', render: (r) => fdate(r.start_date) },
          { key: 'assets_count', label: 'ציוד', num: true },
          { key: 'status', label: 'סטטוס', render: (r) => <Badge tone={TONE[r.status]}>{EMP_STATUS[r.status]}</Badge> },
        ]} />
      {card ? <EmployeeCard emp={card} onClose={() => setCard(null)} onChanged={() => setKey((k) => k + 1)} /> : null}
    </>
  )
}
