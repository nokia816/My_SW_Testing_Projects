import { useState } from 'react'
import { api } from '../api'
import { ROLE, fdatetime, toOptions } from '../labels'
import { Badge, ErrorBox, Form, Modal, Table, useLoad } from '../components/ui'

export default function Users() {
  const list = useLoad(() => api('/users'))
  const [edit, setEdit] = useState(null)
  const save = async (v) => {
    if (edit.id) {
      if (!v.reset_password) delete v.reset_password
      await api(`/users/${edit.id}`, { method: 'PATCH', body: v })
    } else await api('/users', { method: 'POST', body: v })
    setEdit(null); list.reload()
  }
  const roles = toOptions(ROLE)
  return (
    <section>
      <div className="page-head"><h1>משתמשים והרשאות</h1><div className="toolbar"><button className="btn primary" onClick={() => setEdit({})}>+ משתמש חדש</button></div></div>
      <p className="muted small">כל משתמש מקבל רק את ההרשאות שהתפקיד שלו צריך. משתמש חדש מחויב להחליף סיסמה בכניסה הראשונה.</p>
      <ErrorBox error={list.error} />
      <Table rows={list.data?.items} onRowClick={setEdit} columns={[
        { key: 'full_name', label: 'שם' }, { key: 'email', label: 'אימייל' }, { key: 'role', label: 'תפקיד', render: (r) => ROLE[r.role] },
        { key: 'totp_enabled', label: '2FA', render: (r) => (r.totp_enabled ? <Badge tone="good">פעיל</Badge> : <Badge tone="warn">לא פעיל</Badge>) },
        { key: 'is_active', label: 'סטטוס', render: (r) => (r.is_active ? <Badge tone="good">פעיל</Badge> : <Badge>מושבת</Badge>) },
        { key: 'last_login_at', label: 'כניסה אחרונה', render: (r) => fdatetime(r.last_login_at) }]} />
      {edit ? <Modal title={edit.id ? `עריכת ${edit.full_name}` : 'משתמש חדש'} onClose={() => setEdit(null)} wide>
        <Form initial={edit} onSubmit={save} onCancel={() => setEdit(null)} fields={edit.id ? [
          { name: 'full_name', label: 'שם מלא', required: true }, { name: 'role', label: 'תפקיד', type: 'select', options: roles, required: true },
          { name: 'is_active', label: 'פעיל', type: 'checkbox' },
          { name: 'reset_password', label: 'איפוס סיסמה (סיסמה זמנית)', type: 'password', omitIfEmpty: true, help: 'ריק = ללא שינוי. המשתמש יחויב להחליף' },
          { name: 'reset_2fa', label: 'איפוס אימות דו-שלבי (טלפון אבד)', type: 'checkbox' },
        ] : [
          { name: 'full_name', label: 'שם מלא', required: true }, { name: 'email', label: 'אימייל', type: 'email', required: true },
          { name: 'role', label: 'תפקיד', type: 'select', options: roles, required: true, default: 'viewer' },
          { name: 'password', label: 'סיסמה זמנית', type: 'password', required: true, help: 'לפחות 12 תווים' },
        ]} />
      </Modal> : null}
    </section>
  )
}
