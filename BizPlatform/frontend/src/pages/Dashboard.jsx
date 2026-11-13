import { Link } from 'react-router-dom'
import { api } from '../api'
import { ASSET_STATUS, ASSET_TYPE, fdate, money, num } from '../labels'
import { BarChart, ErrorBox, Stat, useLoad } from '../components/ui'

const MONTHS = ['ינו', 'פבר', 'מרץ', 'אפר', 'מאי', 'יונ', 'יול', 'אוג', 'ספט', 'אוק', 'נוב', 'דצמ']

export default function Dashboard() {
  const { data, error } = useLoad(() => api('/dashboard'))
  if (error) return <ErrorBox error={error} />
  if (!data) return <div className="empty">טוען…</div>
  const { finance: f, inventory: inv, assets: a, people: p } = data
  return (
    <section>
      <div className="page-head"><h1>לוח בקרה</h1></div>
      <div className="stats">
        {f ? <>
          <Stat label="הכנסות החודש" value={money(f.income_this_month)} tone="good" />
          <Stat label="הכנסות מתחילת השנה" value={money(f.income_ytd)} />
          <Stat label="יתרת חובות לקוחות" value={money(f.receivables)} />
          <Stat label="באיחור" value={money(f.overdue_amount)} tone={f.overdue_count ? 'bad' : ''} sub={`${f.overdue_count} חשבוניות`} />
        </> : null}
        {inv ? <>
          <Stat label="שווי מלאי (עלות)" value={money(inv.stock_value_cost)} sub={`${num(inv.products)} מוצרים פעילים`} />
          <Stat label="מוצרים במלאי נמוך" value={num(inv.low_stock_count)} tone={inv.low_stock_count ? 'warn' : ''} />
        </> : null}
        {a ? <Stat label="פריטי ציוד" value={num(a.total)} sub={`${num(a.by_status.assigned || 0)} אצל עובדים`} /> : null}
        {p ? <Stat label="עובדים פעילים" value={num(p.active || 0)} sub={p.offboarding ? `${p.offboarding} בתהליך עזיבה` : null} /> : null}
      </div>

      <div className="grid-2">
        {f ? (
          <div className="card span-2">
            <h3>הכנסות מול חשבוניות שהונפקו – 12 חודשים</h3>
            <BarChart format={money} data={f.income_by_month.map((m) => ({ label: MONTHS[Number(m.month.slice(5)) - 1], income: m.income, invoiced: m.invoiced }))}
              series={[{ key: 'invoiced', label: 'חויב', color: 'var(--chart-2)' }, { key: 'income', label: 'נגבה', color: 'var(--chart-1)' }]} />
          </div>
        ) : null}
        {f ? (
          <div className="card">
            <h3>חשבוניות באיחור</h3>
            {f.missing_allocation ? <div className="alert warn">⚠ {f.missing_allocation} חשבוניות פתוחות מעל 5,000 ₪ ללא מספר הקצאה</div> : null}
            {f.top_overdue.length ? <ul className="list">{f.top_overdue.map((i) => <li key={i.id}><Link to="/invoices">#{i.number} · {i.customer_name}</Link><span>{money(i.balance)} · {fdate(i.due_date)}</span></li>)}</ul> : <div className="empty">אין חשבוניות באיחור 🎉</div>}
          </div>
        ) : null}
        {inv ? (
          <div className="card">
            <h3>מלאי נמוך – להזמנה</h3>
            {inv.low_stock.length ? <ul className="list">{inv.low_stock.map((x) => <li key={x.id}><Link to="/products">{x.name} <span className="muted">({x.sku})</span></Link><span className={x.stock <= 0 ? 'bad-text' : 'warn-text'}>{x.stock} / מינ' {x.min_stock}</span></li>)}</ul> : <div className="empty">כל המוצרים מעל המינימום</div>}
          </div>
        ) : null}
        {a ? (
          <div className="card">
            <h3>ציוד – תשומת לב</h3>
            {a.offboarding.filter((e) => e.assets_to_return).map((e) => <div key={e.id} className="alert warn">🔁 {e.name} בתהליך עזיבה – {e.assets_to_return} פריטים להחזרה</div>)}
            <ul className="list">
              {a.licenses_expiring.map((x) => <li key={'l' + x.id}><Link to="/assets">🔑 {x.model || x.asset_tag}</Link><span className={x.expired ? 'bad-text' : 'warn-text'}>{x.expired ? 'פג ב-' : 'יפוג'} {fdate(x.date)}</span></li>)}
              {a.warranty_expiring.map((x) => <li key={'w' + x.id}><Link to="/assets">🛠 אחריות {x.asset_tag} {x.model || ''}</Link><span className="warn-text">{fdate(x.date)}</span></li>)}
            </ul>
            {!a.licenses_expiring.length && !a.warranty_expiring.length && !a.offboarding.length ? <div className="empty">אין התראות</div> : null}
          </div>
        ) : null}
        {a ? (
          <div className="card">
            <h3>פילוח ציוד</h3>
            <ul className="list">{Object.entries(a.by_type).map(([k, v]) => <li key={k}><span>{ASSET_TYPE[k]}</span><span>{v}</span></li>)}</ul>
            <div className="chips">{Object.entries(a.by_status).map(([k, v]) => <span key={k} className="badge neutral">{ASSET_STATUS[k]}: {v}</span>)}</div>
          </div>
        ) : null}
      </div>
    </section>
  )
}
