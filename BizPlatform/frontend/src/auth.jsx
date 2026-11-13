import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { api, setCsrf, setUnauthorizedHandler } from './api'

const AuthCtx = createContext(null)

export function AuthProvider({ children }) {
  const [state, setState] = useState({ loading: true, me: null })

  const apply = useCallback((me) => { setCsrf(me?.csrf_token || null); setState({ loading: false, me }) }, [])
  const refresh = useCallback(() => api('/auth/me').then(apply).catch(() => apply(null)), [apply])

  useEffect(() => { setUnauthorizedHandler(() => apply(null)); refresh() }, [apply, refresh])

  const value = {
    ...state,
    refresh,
    login: async (email, password, otp) => apply(await api('/auth/login', { method: 'POST', body: { email, password, otp: otp || null } })),
    logout: async () => { try { await api('/auth/logout', { method: 'POST' }) } finally { apply(null) } },
    can: (resource, action = 'read') => !!state.me?.permissions?.[resource]?.includes(action),
  }
  return <AuthCtx.Provider value={value}>{children}</AuthCtx.Provider>
}

export const useAuth = () => useContext(AuthCtx)
