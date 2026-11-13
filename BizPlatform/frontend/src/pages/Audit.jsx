import { useState } from 'react'
import { api } from '../api'
import { fdatetime } from '../labels'
import { ErrorBox, Table, useLoad } from '../components/ui'

const ACTIONS = { create: 'יצירה', update: 'עדכון', delete: 'מחיקה', login: 'כניסה', logout: 'יציאה', login_failed: 'כניסה נכשלה',
  login_failed_otp: 'קוד 2FA שגוי', login_locked: 'ניסיון לחשבון נעול', password_changed: 'שינוי סיסמה', '2fa_enabled': 'הפעלת 2FA',
  '2fa_disabled': 'ביטול 2FA', export: 'ייצוא נתונים', secret_view: 'צפייה במפתח רישיון', asset_assign: 'מסירת ציוד',
  asset_return: 'החזרת ציוד', offboard_start: 'תחילת עזיבה', payment_add: 'רישום תשלום', payment_delete: 'מחיקת תשלום' }

export default function Audit() {
  const [entity, setEntity] = useState('')
  const list = useLoad(() => api('/audit', { params: { entity, limit: 500 } }), [entity])
  const verify = useLoad(() => api('/audit/verify'))
  return (
    <section>
      <div className="page-head"><h1>יומן ביקורת</h1>
        <div className="toolbar">
          <select value={entity} onChange={(e) => setEntity(e.target.value)} aria-label="סינון">
            <option value="">הכול</option>
            {['auth', 'users', 'products', 'stock', 'invoices', 'customers', 'suppliers', 'employees', 'assets'].map((x) => <option key={x}>{x}</option>)}
          </select>
          <button className="btn" onClick={verify.reload}>בדיקת שלמות</button>
        </div>
      </div>
      {verify.data ? (verify.data.valid
        ? <div className="alert ok">🛡 שרשרת היומן תקינה. נבדקו {verify.data.checked} רשומות ולא זוהו שינויים או מחיקות</div>
        : <div className="alert error">⚠ זוהתה פגיעה ביומן ברשומה #{verify.data.broken_at_id}. ייתכן ניסיון טשטוש</div>) : null}
      <ErrorBox error={list.error} />
      <Table rows={list.data?.items} columns={[
        { key: 'ts', label: 'זמן', render: (r) => fdatetime(r.ts) }, { key: 'user_email', label: 'משתמש' },
        { key: 'action', label: 'פעולה', render: (r) => ACTIONS[r.action] || r.action }, { key: 'entity', label: 'ישות' },
        { key: 'entity_id', label: 'מזהה' }, { key: 'ip', label: 'IP' },
        { key: 'details', label: 'פרטים', render: (r) => (r.details ? <code className="details">{JSON.stringify(r.details)}</code> : '—') }]} />
    </section>
  )
}
