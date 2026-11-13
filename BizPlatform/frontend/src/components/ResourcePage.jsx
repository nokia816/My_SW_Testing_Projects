import { useState } from 'react'
import { api, download } from '../api'
import { useAuth } from '../auth'
import { ConfirmButton, ErrorBox, Form, Modal, Table, useDebounced, useLoad } from './ui'

/** Generic list + search + create/edit/delete page driven by a config object. */
export default function ResourcePage({ title, endpoint, resource, columns, fields, exportName, filters = [],
  rowActions, onRowClick, createLabel = 'הוספה', extraToolbar, canDelete = true, editFields }) {
  const { can } = useAuth()
  const [q, setQ] = useState('')
  const [filterVals, setFilterVals] = useState({})
  const [editing, setEditing] = useState(null) // null | {} (new) | row
  const [error, setError] = useState(null)
  const dq = useDebounced(q)
  const list = useLoad(() => api(endpoint, { params: { q: dq, limit: 500, ...filterVals } }), [endpoint, dq, JSON.stringify(filterVals)])
  const writable = can(resource, 'write')

  const save = async (values) => {
    if (editing.id) await api(`${endpoint}/${editing.id}`, { method: 'PATCH', body: values })
    else await api(endpoint, { method: 'POST', body: values })
    setEditing(null); list.reload()
  }
  const remove = async (row) => {
    setError(null)
    try { await api(`${endpoint}/${row.id}`, { method: 'DELETE' }); setEditing(null); list.reload() } catch (e) { setError(e) }
  }

  return (
    <section>
      <div className="page-head">
        <h1>{title}</h1>
        <div className="toolbar">
          <input type="search" placeholder="חיפוש…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="חיפוש" />
          {filters.map((f) => (
            <select key={f.name} value={filterVals[f.name] || ''} aria-label={f.label}
              onChange={(e) => setFilterVals((s) => ({ ...s, [f.name]: e.target.value }))}>
              <option value="">{f.label}: הכול</option>
              {f.options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          ))}
          {extraToolbar}
          {exportName ? <button className="btn" onClick={() => download(`/export/${exportName}`)}>ייצוא ל-Excel</button> : null}
          {writable ? <button className="btn primary" onClick={() => setEditing({})}>+ {createLabel}</button> : null}
        </div>
      </div>
      <ErrorBox error={list.error || error} />
      {list.loading && !list.data ? <div className="empty">טוען…</div> : (
        <>
          <Table columns={[...columns, ...(rowActions ? [{ key: '_a', label: '', render: rowActions }] : [])]}
            rows={list.data?.items}
            onRowClick={onRowClick || (writable ? (r) => setEditing(r) : undefined)} />
          <div className="muted small">סה"כ {list.data?.total ?? 0} רשומות</div>
        </>
      )}
      {editing ? (
        <Modal title={editing.id ? `עריכה` : createLabel} onClose={() => setEditing(null)} wide>
          <Form fields={editing.id && editFields ? editFields : fields} initial={editing} onSubmit={save} onCancel={() => setEditing(null)} />
          {editing.id && canDelete ? (
            <div className="danger-zone"><ConfirmButton onConfirm={() => remove(editing)} message="למחוק את הרשומה? הפעולה תתועד ביומן הביקורת">מחיקה</ConfirmButton></div>
          ) : null}
        </Modal>
      ) : null}
    </section>
  )
}

export { useLoad }
