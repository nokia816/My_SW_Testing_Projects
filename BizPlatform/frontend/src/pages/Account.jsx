import { useState } from 'react'
import { api } from '../api'
import { useAuth } from '../auth'
import { ROLE } from '../labels'
import { ErrorBox, Form } from '../components/ui'

const PW_FIELDS = [
  { name: 'current_password', label: 'סיסמה נוכחית', type: 'password', required: true },
  { name: 'new_password', label: 'סיסמה חדשה', type: 'password', required: true, help: 'לפחות 12 תווים, שילוב של אותיות גדולות/קטנות, ספרות וסימנים' },
]

export default function Account({ forced }) {
  const { me, refresh, logout } = useAuth()
  const u = me.user
  const [msg, setMsg] = useState('')
  const [setup, setSetup] = useState(null)
  const [code, setCode] = useState('')
  const [error, setError] = useState(null)

  const changePw = async (v) => { await api('/auth/change-password', { method: 'POST', body: v }); setMsg('הסיסמה עודכנה'); refresh() }
  const startSetup = async () => { setError(null); try { setSetup(await api('/auth/2fa/setup', { method: 'POST' })) } catch (e) { setError(e) } }
  const enable = async (e) => {
    e.preventDefault(); setError(null)
    try { await api('/auth/2fa/enable', { method: 'POST', body: { code } }); setSetup(null); setCode(''); setMsg('אימות דו-שלבי הופעל'); refresh() } catch (err) { setError(err) }
  }
  const disable = async () => {
    const c = window.prompt('הזן קוד נוכחי מאפליקציית האימות כדי לבטל')
    if (!c) return
    try { await api('/auth/2fa/disable', { method: 'POST', body: { code: c } }); refresh() } catch (err) { setError(err) }
  }
  const showPw = !forced || u.must_change_password
  const show2fa = !forced || (!u.must_change_password && me.require_2fa && !u.totp_enabled)

  return (
    <section className="account">
      <div className="page-head"><h1>{forced ? 'נדרשת פעולה לפני הכניסה' : 'החשבון שלי'}</h1>{forced ? <button className="btn" onClick={logout}>יציאה</button> : null}</div>
      {msg ? <div className="alert ok">{msg}</div> : null}
      <div className="cards">
        <div className="card"><h3>פרטים</h3><p>{u.full_name}</p><p className="muted">{u.email} · {ROLE[u.role]}</p></div>
        {showPw ? <div className="card"><h3>{u.must_change_password ? 'יש להחליף את הסיסמה הזמנית' : 'החלפת סיסמה'}</h3><Form fields={PW_FIELDS} onSubmit={changePw} submitLabel="עדכון סיסמה" /></div> : null}
        {show2fa ? (
          <div className="card">
            <h3>אימות דו-שלבי (2FA)</h3>
            {u.totp_enabled ? (<><p>✅ פעיל</p>{!me.require_2fa ? <button className="btn" onClick={disable}>ביטול</button> : null}</>) : setup ? (
              <form onSubmit={enable} className="form">
                <p>סרוק באפליקציית אימות (Google Authenticator, Microsoft Authenticator, Authy…)</p>
                <img className="qr" alt="QR לאימות דו-שלבי" src={`data:image/svg+xml;utf8,${encodeURIComponent(setup.qr_svg)}`} />
                <p className="muted small">או הזן ידנית: <code>{setup.secret}</code></p>
                <label className="field"><span>קוד בן 6 ספרות</span><input inputMode="numeric" required value={code} onChange={(e) => setCode(e.target.value)} /></label>
                <button className="btn primary">הפעלה</button>
              </form>
            ) : <><p className="muted">מגן על החשבון גם אם הסיסמה דלפה.</p><button className="btn primary" onClick={startSetup}>הפעלת אימות דו-שלבי</button></>}
            <ErrorBox error={error} />
          </div>
        ) : null}
      </div>
    </section>
  )
}
