import { useState } from 'react'
import { NavLink, Navigate, Route, Routes } from 'react-router-dom'
import { useAuth } from './auth'
import { ROLE } from './labels'
import Account from './pages/Account'
import Assets from './pages/Assets'
import Audit from './pages/Audit'
import Dashboard from './pages/Dashboard'
import Employees from './pages/Employees'
import Invoices from './pages/Invoices'
import Login from './pages/Login'
import Products from './pages/Products'
import { Customers, Departments, Suppliers, Warehouses } from './pages/Simple'
import Stock from './pages/Stock'
import Users from './pages/Users'

const NAV = [
  { group: 'ראשי', items: [{ to: '/', label: 'לוח בקרה', icon: '◧', res: 'dashboard', el: <Dashboard /> }] },
  { group: 'מלאי ומוצרים', items: [
    { to: '/products', label: 'מוצרים', icon: '▦', res: 'products', el: <Products /> },
    { to: '/stock', label: 'תנועות מלאי', icon: '⇄', res: 'stock', el: <Stock /> },
    { to: '/warehouses', label: 'מחסנים', icon: '⌂', res: 'warehouses', el: <Warehouses /> },
    { to: '/suppliers', label: 'ספקים', icon: '⛟', res: 'suppliers', el: <Suppliers /> },
  ] },
  { group: 'כספים', items: [
    { to: '/invoices', label: 'מעקב חשבוניות', icon: '₪', res: 'invoices', el: <Invoices /> },
    { to: '/customers', label: 'לקוחות', icon: '☺', res: 'customers', el: <Customers /> },
  ] },
  { group: 'עובדים וציוד', items: [
    { to: '/employees', label: 'עובדים', icon: '👤', res: 'employees', el: <Employees /> },
    { to: '/assets', label: 'מחשבים וציוד', icon: '💻', res: 'assets', el: <Assets /> },
    { to: '/departments', label: 'מחלקות', icon: '▤', res: 'departments', el: <Departments /> },
  ] },
  { group: 'ניהול', items: [
    { to: '/users', label: 'משתמשים והרשאות', icon: '🔑', res: 'users', el: <Users /> },
    { to: '/audit', label: 'יומן ביקורת', icon: '🛡', res: 'audit', el: <Audit /> },
  ] },
]

export default function App() {
  const { loading, me, can, logout } = useAuth()
  const [menuOpen, setMenuOpen] = useState(false)
  if (loading) return <div className="center-screen">טוען…</div>
  if (!me) return <Login />
  const u = me.user
  const blocked = u.must_change_password || (me.require_2fa && !u.totp_enabled)
  if (blocked) return <div className="blocked-wrap"><Account forced /></div>

  const allowed = NAV.map((g) => ({ ...g, items: g.items.filter((i) => can(i.res)) })).filter((g) => g.items.length)
  return (
    <div className={`layout ${menuOpen ? 'menu-open' : ''}`}>
      <aside className="sidebar">
        <div className="brand"><span className="logo">B</span>{me.org_name}</div>
        <nav onClick={() => setMenuOpen(false)}>
          {allowed.map((g) => (
            <div key={g.group} className="nav-group">
              <div className="nav-title">{g.group}</div>
              {g.items.map((i) => <NavLink key={i.to} to={i.to} end={i.to === '/'}><span className="nav-icon">{i.icon}</span>{i.label}</NavLink>)}
            </div>
          ))}
        </nav>
      </aside>
      <div className="main">
        <header className="topbar">
          <button className="icon-btn menu-btn" onClick={() => setMenuOpen((v) => !v)} aria-label="תפריט">☰</button>
          <div className="spacer" />
          {!u.totp_enabled ? <NavLink to="/account" className="badge warn">מומלץ להפעיל אימות דו-שלבי</NavLink> : null}
          <NavLink to="/account" className="user-chip">{u.full_name} · {ROLE[u.role]}</NavLink>
          <button className="btn" onClick={logout}>יציאה</button>
        </header>
        <main className="content">
          <Routes>
            {allowed.flatMap((g) => g.items).map((i) => <Route key={i.to} path={i.to} element={i.el} />)}
            <Route path="/account" element={<Account />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
    </div>
  )
}
