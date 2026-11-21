import { useEffect, useState } from 'react'
import { MapContainer, TileLayer, CircleMarker, useMapEvents } from 'react-leaflet'
import { api } from '../api'
import { useApp } from '../store'
import VehicleCards from '../components/VehicleCards'
import LightRing from '../components/LightRing'

const CITY = [13.0827, 80.2707]
function Picker({ onPick }) { useMapEvents({ click: (e) => onPick([e.latlng.lat, e.latlng.lng]) }); return null }

export default function Welcome() {
  const { setAuthed, refresh, push } = useApp()
  const [tab, setTab] = useState('create')
  const [vehicles, setVehicles] = useState([])
  const [f, setF] = useState({ name: '', pin: '', vehicle: '', soc: 40 })
  const [loc, setLoc] = useState(CITY)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  useEffect(() => { api.vehicles().then((v) => { setVehicles(v); if (v[0]) setF((x) => ({ ...x, vehicle: x.vehicle || v[0].id })) }).catch((e) => setErr(e.message)) }, [])

  const submit = async (e) => {
    e.preventDefault(); setErr('')
    if (f.name.trim().length < 2) return setErr('Enter a name between 2 and 30 characters.')
    if (!/^\d{4}$/.test(f.pin)) return setErr('Your PIN must be exactly 4 digits.')
    setBusy(true)
    try {
      if (tab === 'create') await api.signup({ name: f.name.trim(), pin: f.pin, vehicle_model_id: f.vehicle, soc: Number(f.soc), lat: loc[0], lng: loc[1] })
      else await api.login({ name: f.name.trim(), pin: f.pin })
      setAuthed(true); await refresh()
    } catch (x) { setErr(x.message); push(x.message, 'err') } finally { setBusy(false) }
  }

  return (
    <main className="mx-auto max-w-md px-4 pb-10 pt-8">
      <div className="mb-6 flex items-center gap-3">
        <LightRing size={56} stroke={7} status="charging" pct={72} label="ChargeGrid logo" />
        <div><h1 className="text-3xl font-bold">ChargeGrid</h1><p className="text-sm text-muted">Find a charger, plug in, pay. All simulated.</p></div>
      </div>
      <div className="mb-4 grid grid-cols-2 rounded-xl border border-line bg-white p-1" role="tablist">
        {[['create', 'Create account'], ['login', 'Sign in']].map(([k, l]) => (
          <button key={k} role="tab" aria-selected={tab === k} onClick={() => { setTab(k); setErr('') }}
            className={`rounded-lg py-2 text-sm font-semibold ${tab === k ? 'bg-brand text-white' : 'text-muted'}`}>{l}</button>
        ))}
      </div>
      <form onSubmit={submit} className="grid gap-4">
        <label className="grid gap-1 text-sm font-semibold">Name
          <input className="input font-normal" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} autoComplete="username" maxLength={30} />
        </label>
        <label className="grid gap-1 text-sm font-semibold">4-digit PIN
          <input className="input font-normal" type="password" inputMode="numeric" maxLength={4} value={f.pin}
            onChange={(e) => setF({ ...f, pin: e.target.value.replace(/\D/g, '') })} autoComplete="current-password" />
        </label>
        {tab === 'create' && (
          <>
            <div><div className="mb-1 text-sm font-semibold">Vehicle</div><VehicleCards vehicles={vehicles} value={f.vehicle} onChange={(v) => setF({ ...f, vehicle: v })} /></div>
            <label className="grid gap-1 text-sm font-semibold">Starting battery: {f.soc}%
              <input type="range" min="5" max="100" value={f.soc} onChange={(e) => setF({ ...f, soc: e.target.value })} />
            </label>
            <div>
              <div className="mb-1 text-sm font-semibold">Starting location <span className="font-normal text-muted">(tap the map to change; default is the city centre)</span></div>
              <div className="h-44 overflow-hidden rounded-xl border border-line">
                <MapContainer center={CITY} zoom={11} style={{ height: '100%' }}>
                  <TileLayer attribution="&copy; OpenStreetMap contributors" url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
                  <Picker onPick={setLoc} />
                  <CircleMarker center={loc} radius={9} pathOptions={{ color: '#0d5c63', fillColor: '#0d5c63', fillOpacity: 0.8 }} />
                </MapContainer>
              </div>
            </div>
          </>
        )}
        {err && <p className="rounded-lg bg-st-faulted/10 p-3 text-sm font-semibold text-st-faulted" role="alert">{err}</p>}
        <button className="btn-primary" disabled={busy}>{busy ? 'Please wait…' : tab === 'create' ? 'Create account' : 'Sign in'}</button>
      </form>
    </main>
  )
}
