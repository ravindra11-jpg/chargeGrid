export const inr = (n) =>
  new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(Number(n) || 0)
export const inr0 = (n) =>
  new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(Number(n) || 0)
export const num = (n, d = 1) =>
  Number(n || 0).toLocaleString('en-IN', { minimumFractionDigits: d, maximumFractionDigits: d })
export const mins = (m) => {
  m = Math.max(0, Math.round(Number(m) || 0))
  const h = Math.floor(m / 60)
  return h ? `${h} h ${m % 60} min` : `${m} min`
}
export const clockMs = (s) => {
  s = Math.max(0, Math.round(s || 0))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}
export const rangeKm = (soc, v) => (v ? Math.round((soc * v.battery_kwh * 10) / v.wh_per_km) : 0)
export const STATUS = {
  available: { label: 'Available', color: '#1a9f63' },
  reserved: { label: 'Reserved', color: '#7c5cdb' },
  preparing: { label: 'Plugged in', color: '#d98a00' },
  charging: { label: 'Charging', color: '#1d6fe0' },
  finishing: { label: 'Finished', color: '#0f9bb0' },
  faulted: { label: 'Faulted', color: '#d93d44' },
  offline: { label: 'Offline', color: '#7d8b96' }
}
export const statusInfo = (s) => STATUS[String(s || '').toLowerCase()] || STATUS.offline
export const dayKey = (iso) => (iso ? new Date(iso).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', timeZone: 'UTC' }) : '')
