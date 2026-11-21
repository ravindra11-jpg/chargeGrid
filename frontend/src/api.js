// The single place that talks to the backend. Shapes are documented in ../CONTRACT.md and match backend/cloud.py + app.py.
const BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5000'

export class ApiError extends Error {
  // data = the full JSON error body. 402 errors carry data.action ('topup' | 'pay') and sometimes data.invoice_id.
  constructor(message, status, data) {
    super(message)
    this.status = status
    this.data = data || {}
    this.action = this.data.action || null
    this.invoiceId = this.data.invoice_id || null
  }
}
export const tokenStore = {
  get: () => localStorage.getItem('cg_token'),
  set: (t) => localStorage.setItem('cg_token', t),
  clear: () => localStorage.removeItem('cg_token')
}

async function req(path, { method = 'GET', body, auth = true } = {}) {
  const headers = {}
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  const t = auth ? tokenStore.get() : null
  if (t) headers.Authorization = 'Bearer ' + t
  let res
  try {
    res = await fetch(BASE + path, { method, headers, body: body !== undefined ? JSON.stringify(body) : undefined })
  } catch {
    throw new ApiError('Cannot reach the server. Check that the backend is running on ' + BASE + '.', 0)
  }
  let data = null
  try { data = await res.json() } catch { /* empty body */ }
  if (!res.ok) {
    if (res.status === 401 && t) {
      tokenStore.clear()
      window.dispatchEvent(new Event('cg-auth-expired'))
    }
    throw new ApiError((data && data.error) || 'Something went wrong. Try again.', res.status, data)
  }
  return data
}

const post = (path, body = {}) => req(path, { method: 'POST', body })

export const api = {
  health: () => req('/api/health', { auth: false }),
  // -> [vehicle]
  vehicles: async () => (await req('/api/vehicles', { auth: false })).vehicles,
  // signup/login -> { token, me }; the token is stored here and `me` is returned
  signup: async (b) => { const d = await req('/api/auth/signup', { method: 'POST', body: b, auth: false }); tokenStore.set(d.token); return d.me },
  login: async (b) => { const d = await req('/api/auth/login', { method: 'POST', body: b, auth: false }); tokenStore.set(d.token); return d.me },
  // -> me (bare object)
  me: () => req('/api/me'),
  // body {vehicle_model_id} and/or {soc}; only while the journey is IDLE or INVOICE (else 409) -> me
  patchMe: (b) => req('/api/me', { method: 'PATCH', body: b }),
  // -> [station] (the response is {stations, sim_time, sim_speed})
  stations: async (lat, lng) => (await req(`/api/stations?lat=${lat}&lng=${lng}`)).stations,
  // reserve -> 201 journey; cancel -> journey
  reserve: (charger_id) => post('/api/reservations', { charger_id }),
  cancelReservation: (id) => req('/api/reservations/' + id, { method: 'DELETE' }),
  // -> journey (includes notices newer than `after`)
  journey: (after = 0) => req('/api/journey?after=' + Number(after || 0)),
  go: (charger_id) => post('/api/journey/go', { charger_id }),
  plugIn: () => post('/api/journey/plug-in'),
  start: (target_soc, spending_cap) => post('/api/journey/start', { target_soc, spending_cap: spending_cap || null }),
  stop: () => post('/api/journey/stop'),
  unplug: () => post('/api/journey/unplug'),
  dismiss: () => post('/api/journey/dismiss'),
  // body {km} -> { used_pct, me }
  trip: (km) => post('/api/trips', { km }),
  // -> { sessions:[...], summary:{total_kwh,total_spend,sessions}, daily:[{date,kwh,spend}] }
  sessions: () => req('/api/sessions'),
  // -> invoice
  invoice: (id) => req('/api/invoices/' + id),
  payInvoice: (id) => post(`/api/invoices/${id}/pay`),
  // -> { balance, transactions, unpaid_invoices }
  wallet: () => req('/api/wallet'),
  topup: (amount) => post('/api/wallet/topup', { amount }),
  // -> { speed, traffic, speeds, levels, sim_time }
  simGet: () => req('/api/sim/settings'),
  simSet: (b) => post('/api/sim/settings', b),
  breakMyCharger: () => post('/api/sim/break-my-charger')
}
