// Same-origin API client. Session lives in an HttpOnly cookie (not readable by JS);
// the CSRF token is kept in memory only.
let csrfToken = null
let onUnauthorized = () => {}

export const setCsrf = (t) => { csrfToken = t }
export const setUnauthorizedHandler = (fn) => { onUnauthorized = fn }

export class ApiError extends Error {
  constructor(status, detail, errors) {
    super(Array.isArray(detail) ? detail.join(' · ') : (detail || 'שגיאה'))
    this.status = status
    this.detail = detail
    this.errors = errors
  }
}

export async function api(path, { method = 'GET', body, params } = {}) {
  let url = '/api' + path
  if (params) {
    const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== '' && v != null && v !== false))
    if ([...qs].length) url += '?' + qs
  }
  const headers = { Accept: 'application/json' }
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (method !== 'GET' && csrfToken) headers['X-CSRF-Token'] = csrfToken
  const res = await fetch(url, {
    method, headers, credentials: 'same-origin',
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  if (res.status === 204) return null
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    if (res.status === 401 && !path.startsWith('/auth/login')) onUnauthorized()
    const errs = data.errors?.map((e) => `${e.field}: ${e.msg}`)
    throw new ApiError(res.status, errs?.length ? errs : data.detail, data.errors)
  }
  return data
}

export function download(path) {
  const a = document.createElement('a')
  a.href = '/api' + path
  a.rel = 'noopener'
  document.body.appendChild(a)
  a.click()
  a.remove()
}
