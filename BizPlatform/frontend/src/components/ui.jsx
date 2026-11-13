import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api'

export function useLoad(fn, deps = []) {
  const [state, setState] = useState({ data: null, error: null, loading: true })
  const load = useCallback(() => {
    setState((s) => ({ ...s, loading: true }))
    return fn().then((data) => setState({ data, error: null, loading: false }))
      .catch((error) => setState({ data: null, error, loading: false }))
  }, deps) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { load() }, [load])
  return { ...state, reload: load }
}

export function useDebounced(value, ms = 300) {
  const [v, setV] = useState(value)
  useEffect(() => { const t = setTimeout(() => setV(value), ms); return () => clearTimeout(t) }, [value, ms])
  return v
}

export const ErrorBox = ({ error }) => error ? <div className="alert error" role="alert">{error.message || String(error)}</div> : null

export const Badge = ({ tone = 'neutral', children }) => <span className={`badge ${tone}`}>{children}</span>

export function Modal({ title, onClose, children, wide }) {
  const ref = useRef()
  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose()
    document.addEventListener('keydown', onKey)
    ref.current?.querySelector('input,select,textarea,button')?.focus()
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])
  return (
    <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className={`modal ${wide ? 'wide' : ''}`} role="dialog" aria-modal="true" aria-label={title} ref={ref}>
        <header><h2>{title}</h2><button className="icon-btn" onClick={onClose} aria-label="סגור">✕</button></header>
        <div className="modal-body">{children}</div>
      </div>
    </div>
  )
}

const refCache = {}
export function useRefOptions(ref) {
  const [opts, setOpts] = useState(refCache[ref?.endpoint] || [])
  useEffect(() => {
    if (!ref) return
    api(ref.endpoint, { params: { limit: 500, ...(ref.params || {}) } }).then((r) => {
      const list = (r.items || r).map((x) => ({ value: x.id, label: ref.label(x) }))
      refCache[ref.endpoint] = list
      setOpts(list)
    }).catch(() => {})
  }, [ref?.endpoint]) // eslint-disable-line react-hooks/exhaustive-deps
  return opts
}

function Input({ field, value, onChange }) {
  const refOpts = useRefOptions(field.ref)
  const common = { id: field.name, name: field.name, required: field.required, disabled: field.disabled,
    value: value ?? '', onChange: (e) => onChange(field.type === 'checkbox' ? e.target.checked : e.target.value) }
  switch (field.type) {
    case 'textarea': return <textarea rows={3} maxLength={field.max || 5000} {...common} />
    case 'select':
    case 'ref': {
      const options = field.type === 'ref' ? refOpts : field.options
      return (
        <select {...common}>
          {!field.required || field.type === 'ref' ? <option value="">— בחר —</option> : null}
          {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      )
    }
    case 'checkbox': return <input type="checkbox" {...common} checked={!!value} value={undefined} />
    case 'money': return <input type="number" step="0.01" min="0" inputMode="decimal" {...common} />
    case 'number': return <input type="number" step="1" min={field.min ?? 0} {...common} />
    default: return <input type={field.type || 'text'} maxLength={field.max || 200} autoComplete="off" {...common} />
  }
}

/** Generic form. Empty strings become null; numbers are converted. */
export function Form({ fields, initial = {}, onSubmit, submitLabel = 'שמירה', onCancel }) {
  const [values, setValues] = useState(() => Object.fromEntries(fields.map((f) => [f.name, initial[f.name] ?? f.default ?? (f.type === 'checkbox' ? false : '')])))
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const submit = async (e) => {
    e.preventDefault()
    setBusy(true); setError(null)
    const out = {}
    for (const f of fields) {
      if (f.readOnly) continue
      let v = values[f.name]
      if (v === '' || v === undefined) v = null
      else if (f.type === 'number' || f.type === 'ref') v = Number(v)
      else if (f.type === 'money') v = String(v)
      if (v === null && f.omitIfEmpty) continue
      out[f.name] = v
    }
    try { await onSubmit(out) } catch (err) { setError(err) } finally { setBusy(false) }
  }
  return (
    <form onSubmit={submit} className="form">
      <div className="form-grid">
        {fields.filter((f) => !f.hidden).map((f) => (
          <label key={f.name} className={`field ${f.type === 'textarea' || f.full ? 'full' : ''} ${f.type === 'checkbox' ? 'check' : ''}`}>
            <span>{f.label}{f.required ? ' *' : ''}</span>
            <Input field={f} value={values[f.name]} onChange={(v) => setValues((s) => ({ ...s, [f.name]: v }))} />
            {f.help ? <small>{f.help}</small> : null}
          </label>
        ))}
      </div>
      <ErrorBox error={error} />
      <div className="form-actions">
        <button type="submit" className="btn primary" disabled={busy}>{busy ? 'שומר…' : submitLabel}</button>
        {onCancel ? <button type="button" className="btn" onClick={onCancel}>ביטול</button> : null}
      </div>
    </form>
  )
}

export function Table({ columns, rows, onRowClick, empty = 'אין נתונים להצגה' }) {
  if (!rows?.length) return <div className="empty">{empty}</div>
  return (
    <div className="table-wrap">
      <table>
        <thead><tr>{columns.map((c) => <th key={c.key} className={c.num ? 'num' : ''}>{c.label}</th>)}</tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id} onClick={onRowClick ? () => onRowClick(r) : undefined} className={onRowClick ? 'clickable' : ''}>
              {columns.map((c) => <td key={c.key} className={c.num ? 'num' : ''} data-label={c.label}>{c.render ? c.render(r) : (r[c.key] ?? '—')}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function Stat({ label, value, tone, sub }) {
  return <div className={`stat ${tone || ''}`}><div className="stat-label">{label}</div><div className="stat-value">{value}</div>{sub ? <div className="stat-sub">{sub}</div> : null}</div>
}

/** Minimal dependency-free bar chart (two series). */
export function BarChart({ data, series, format }) {
  const max = Math.max(1, ...data.flatMap((d) => series.map((s) => Number(d[s.key]) || 0)))
  return (
    <div className="chart">
      <div className="legend">{series.map((s) => <span key={s.key}><i style={{ background: s.color }} />{s.label}</span>)}</div>
      <div className="bars">
        {data.map((d) => (
          <div className="bar-group" key={d.label} title={series.map((s) => `${s.label}: ${format(d[s.key])}`).join('\n')}>
            <div className="bar-stack">
              {series.map((s) => <div key={s.key} className="bar" style={{ height: `${(Number(d[s.key]) / max) * 100}%`, background: s.color }} />)}
            </div>
            <span className="bar-label">{d.label}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

export function ConfirmButton({ onConfirm, children, message = 'האם אתה בטוח?', className = 'btn danger' }) {
  return <button type="button" className={className} onClick={() => window.confirm(message) && onConfirm()}>{children}</button>
}
