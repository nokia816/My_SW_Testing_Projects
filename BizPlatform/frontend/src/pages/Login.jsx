import { useState } from 'react'
import { useAuth } from '../auth'

export default function Login() {
  const { login } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [otp, setOtp] = useState('')
  const [needOtp, setNeedOtp] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true); setError('')
    try { await login(email, password, needOtp ? otp : null) } catch (err) {
      if (err.detail === 'otp_required') { setNeedOtp(true); setError('') } else setError(err.message)
    } finally { setBusy(false) }
  }
  return (
    <div className="login-wrap">
      <form className="login-card" onSubmit={submit}>
        <div className="brand big"><span className="logo">B</span>BizPlatform</div>
        <p className="muted">מלאי · חשבוניות · הכנסות · עובדים · ציוד</p>
        {!needOtp ? (
          <>
            <label className="field"><span>אימייל</span><input type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} /></label>
            <label className="field"><span>סיסמה</span><input type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} /></label>
          </>
        ) : (
          <label className="field"><span>קוד מאפליקציית האימות (6 ספרות)</span>
            <input inputMode="numeric" autoComplete="one-time-code" pattern="[0-9 ]{6,7}" autoFocus required value={otp} onChange={(e) => setOtp(e.target.value)} />
          </label>
        )}
        {error ? <div className="alert error" role="alert">{error}</div> : null}
        <button className="btn primary block" disabled={busy}>{busy ? 'מתחבר…' : needOtp ? 'אימות' : 'כניסה'}</button>
        <p className="muted small">🔒 חיבור מוצפן · נעילה אוטומטית אחרי 5 ניסיונות כושלים</p>
      </form>
    </div>
  )
}
