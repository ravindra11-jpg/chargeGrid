import { useState } from 'react'
import { Link } from 'react-router-dom'
import { AlertTriangle, MapPin, Route, Plus, ArrowRight } from 'lucide-react'
import { useApp } from '../store'
import { api } from '../api'
import { inr } from '../format'
import LightRing from '../components/LightRing'
import Sheet from '../components/Sheet'
import UnpaidBanner from '../components/UnpaidBanner'

export default function Home() {
  const { me, journey, run, push } = useApp()
  const [trip, setTrip] = useState(false)
  const [km, setKm] = useState(15)
  const v = me.vehicle
  const soc = Math.round(me.soc)
  const active = journey && journey.state && journey.state !== 'IDLE'
  const canTrip = !!journey?.allowed_actions?.includes('trip')
  const use = v ? ((km * v.wh_per_km) / 1000 / v.battery_kwh) * 100 : 0

  const doTrip = async () => {
    const r = await run(() => api.trip(Number(km)))
    if (r) { setTrip(false); push(`Trip done. It used ${r.used_pct}% of your battery.`, 'ok') }
  }

  return (
    <main className="mx-auto max-w-md px-4 pb-28 pt-6">
      <h1 className="text-2xl font-bold">Hi, {me.name}</h1>
      {active && (
        <Link to="/charge" className="mt-3 flex items-center justify-between rounded-xl bg-st-charging px-4 py-3 font-semibold text-white">
          {journey.state === 'CHARGING' ? 'Continue charging' : 'Continue your journey'} <ArrowRight size={18} aria-hidden="true" />
        </Link>
      )}
      <UnpaidBanner />
      {soc < 20 && (
        <div className="mt-3 flex items-start gap-2 rounded-xl bg-st-faulted/10 p-3 text-sm font-semibold text-st-faulted" role="alert">
          <AlertTriangle size={18} aria-hidden="true" /> Battery is low. Find a charger soon.
        </div>
      )}
      <section className="card mt-4 flex flex-col items-center py-6">
        <LightRing size={200} stroke={16} pct={soc} status={journey?.state === 'CHARGING' ? 'charging' : 'available'} label={`Battery ${soc} percent, about ${Math.round(me.range_km)} kilometres of range`}>
          <span className="font-display text-5xl font-bold num">{soc}%</span>
          <span className="text-sm text-muted num">{Math.round(me.range_km)} km range</span>
        </LightRing>
        <div className="mt-3 font-display text-lg font-bold">{v?.label}</div>
        <div className="text-sm text-muted">{v?.ac_connector} (AC) · {v?.dc_connector} (DC)</div>
      </section>
      <Link to="/wallet" className="card mt-3 flex items-center justify-between">
        <span className="text-sm text-muted">Wallet balance</span><span className="font-display text-xl font-bold num">{inr(me.wallet_balance)}</span>
      </Link>
      <div className="mt-3 grid grid-cols-3 gap-2">
        <Link to="/find" className="btn-ghost flex-col !gap-1 text-sm"><MapPin size={20} aria-hidden="true" />Find chargers</Link>
        <button className="btn-ghost flex-col !gap-1 text-sm" disabled={!canTrip} onClick={() => setTrip(true)}><Route size={20} aria-hidden="true" />Take a trip</button>
        <Link to="/wallet" className="btn-ghost flex-col !gap-1 text-sm"><Plus size={20} aria-hidden="true" />Add money</Link>
      </div>
      {trip && (
        <Sheet title="Take a trip" onClose={() => setTrip(false)}>
          <p className="mb-3 text-sm text-muted">A round trip. Enter the total distance there and back. You end up back where you started with less battery.</p>
          <div className="mb-3 flex flex-wrap gap-2">
            {[5, 15, 40, 100].map((k) => <button key={k} className={km === k ? 'btn-primary !py-2' : 'btn-ghost !py-2'} onClick={() => setKm(k)}>{k} km</button>)}
          </div>
          <label className="grid gap-1 text-sm font-semibold">Total round-trip distance (km)
            <input className="input font-normal" type="number" min="1" max="1000" value={km} onChange={(e) => setKm(e.target.value)} />
          </label>
          <p className="my-3 text-sm">This uses about <b className="num">{use.toFixed(1)}%</b> of your battery. {use > me.soc - 2 && <span className="font-semibold text-st-faulted">That is more than you have left.</span>}</p>
          <button className="btn-primary w-full" disabled={!(km > 0)} onClick={doTrip}>Start trip</button>
        </Sheet>
      )}
    </main>
  )
}
