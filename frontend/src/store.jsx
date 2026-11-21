import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import { api, tokenStore } from './api'

const Ctx = createContext(null)
export const useApp = () => useContext(Ctx)

// notice.kind -> toast colour
const NOTICE_TONE = {
  low_battery: 'warn', reservation_expiring: 'warn', reservation_expired: 'err', charger_taken: 'err',
  fault: 'err', session_complete: 'ok', payment_done: 'ok'
}

export function AppProvider({ children }) {
  const [authed, setAuthed] = useState(!!tokenStore.get())
  const [booting, setBooting] = useState(!!tokenStore.get())
  const [me, setMe] = useState(null)
  const [journey, setJourney] = useState(null)
  const [toasts, setToasts] = useState([])
  const activeRef = useRef(false)
  const fastRef = useRef(false)
  // Notices: lastNotice = highest id already handled (sent as ?after=). firstPoll = skip toasts for old notices after a reload/login.
  const lastNotice = useRef(0)
  const firstPoll = useRef(true)
  const seq = useRef(0)
  const applied = useRef(0)

  const push = useCallback((text, kind = 'info', action = null) => {
    const id = Math.random().toString(36).slice(2)
    setToasts((t) => [...t, { id, text, kind, action }])
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), action ? 9000 : 5500)
  }, [])

  const refresh = useCallback(async () => {
    const n = ++seq.current
    try {
      const [m, j] = await Promise.all([api.me(), api.journey(lastNotice.current)])
      // Notices: handled once each, in id order, even if two refreshes overlap (JS is single threaded, so this block is atomic).
      const fresh = (j.notices || []).filter((x) => x.id > lastNotice.current)
      if (fresh.length) lastNotice.current = Math.max(...fresh.map((x) => x.id))
      if (!firstPoll.current) fresh.forEach((x) => push(x.text, NOTICE_TONE[x.kind] || 'info'))
      firstPoll.current = false
      if (n >= applied.current) { applied.current = n; setMe(m); setJourney(j) } // ignore a slower, older response
    } catch { /* offline or 401 handled elsewhere */ }
    finally { setBooting(false) }
  }, [push])

  activeRef.current = !!(journey && journey.state && journey.state !== 'IDLE')
  fastRef.current = journey?.state === 'PLUGGED_IN' && !journey?.handshake?.ready

  useEffect(() => {
    if (!authed) return
    let stop = false, timer
    const loop = async () => {
      await refresh()
      if (!stop) timer = setTimeout(loop, fastRef.current ? 500 : activeRef.current ? 1000 : 3000)
    }
    loop()
    return () => { stop = true; clearTimeout(timer) }
  }, [authed, refresh])

  const reset = useCallback(() => {
    setMe(null); setJourney(null); lastNotice.current = 0; firstPoll.current = true; applied.current = seq.current
  }, [])

  useEffect(() => {
    const onExpired = () => { setAuthed(false); reset() }
    window.addEventListener('cg-auth-expired', onExpired)
    return () => window.removeEventListener('cg-auth-expired', onExpired)
  }, [reset])

  // Runs an API call, refreshes, toasts errors. A 402 error gets a button: wallet (action "topup") or the unpaid invoice (action "pay").
  const run = useCallback(async (fn, okMsg) => {
    try {
      const r = await fn()
      await refresh()
      if (okMsg) push(okMsg, 'ok')
      return r ?? true
    } catch (e) {
      let action = null
      if (e.status === 402 && e.action === 'topup') action = { label: 'Add money', to: '/wallet' }
      else if (e.status === 402 && e.action === 'pay') action = { label: 'Open invoice', to: e.invoiceId ? '/invoice/' + e.invoiceId : '/wallet' }
      push(e.message, 'err', action)
      refresh() // some errors (charger taken, reservation lost) change the journey
      return null
    }
  }, [refresh, push])

  const signOut = useCallback(() => { tokenStore.clear(); setAuthed(false); reset() }, [reset])

  const value = { authed, setAuthed, booting, me, journey, refresh, run, push, toasts, signOut }
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}
