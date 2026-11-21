import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Check, Plug, Zap, Clock } from 'lucide-react'
import UnpaidBanner from '../components/UnpaidBanner'
import { useApp } from '../store'
import { api } from '../api'
import { inr, num, mins, clockMs } from '../format'
import LightRing from '../components/LightRing'
import { InvoiceView } from './Invoice'

const STEPS = ['Reserve', 'Drive', 'Plug in', 'Charge', 'Unplug', 'Pay']
const STEP_AT = { RESERVED: 0, DRIVING: 1, ARRIVED: 2, PLUGGED_IN: 2, CHARGING: 3, STOPPED: 4, INVOICE: 5 }

function Steps({ state }) {
  const at = STEP_AT[state] ?? 0
  return (
    <ol className="mb-4 flex items-center justify-between" aria-label="Journey steps">
      {STEPS.map((s, i) => (
        <li key={s} className="flex flex-1 flex-col items-center gap-1 text-[11px] font-semibold" aria-current={i === at ? 'step' : undefined}>
          <span className={`flex h-6 w-6 items-center justify-center rounded-full text-xs ${i < at ? 'bg-st-available text-white' : i === at ? 'bg-brand text-white' : 'bg-line text-muted'}`}>
            {i < at ? <Check size={14} aria-hidden="true" /> : i + 1}
          </span>
          <span className={i === at ? 'text-ink' : 'text-muted'}>{s}</span>
        </li>
      ))}
    </ol>
  )
}

function Suggestions({ items }) {
  if (!items?.length) return null
  return (
    <div className="mt-3 text-sm"><div className="mb-1 font-semibold">Nearby alternatives</div>
      <ul className="grid gap-1">{items.map((s) => <li key={s.station_id} className="rounded-lg bg-page p-2">{s.name} <span className="text-muted num">· {num(s.distance_km)} km · {s.free_count} free · arrive with {Math.round(s.arrive_soc)}%</span></li>)}</ul>
      <Link to="/find" className="btn-primary mt-3 w-full">Find chargers</Link>
    </div>
  )
}

const TARIFF_BADGE = {
  Peak: <span className="badge bg-st-plugged/15 text-st-plugged">Peak</span>,
  'Off-peak': <span className="badge bg-st-available/15 text-st-available">Off-peak</span>
}
const STOP_TEXT = {
  target_reached: 'Your target was reached.', battery_full: 'Your battery is full.',
  spending_cap: 'Your spending cap was reached.', user_stop: 'You stopped charging.'
}

function Hold({ res }) {
  if (!res) return null
  return <p className="mt-2 text-sm text-muted num" role="timer">Reservation hold: {clockMs(res.expires_in_s)} left</p>
}

export default function Charge() {
  const { me, journey: j, run } = useApp()
  const [target, setTarget] = useState(80)
  const [cap, setCap] = useState('')
  const [busy, setBusy] = useState(false)

  const pl = j?.plugged
  useEffect(() => { if (pl) setTarget((t) => Math.max(Math.min(t, 100), pl.min_target)) }, [j?.state, pl?.min_target]) // eslint-disable-line
  useEffect(() => { if (j?.state !== 'ARRIVED') setBusy(false) }, [j?.state])

  if (!j) return <main className="px-4 pt-6 text-muted">Loading…</main>
  const c = j.charging || {}
  const ch = j.charger
  const soc = Math.round(c.soc ?? j.soc ?? me.soc)
  const allowed = j.allowed_actions || []

  const body = (() => {
    switch (j.state) {
      case 'RESERVED': return (
        <section className="card">
          <h2 className="text-xl font-bold">Charger reserved</h2>
          <p className="text-sm text-muted">{j.station?.name} · charger {ch?.number}</p>
          <div className="my-4 text-center font-display text-5xl font-bold num" role="timer">{clockMs(j.reservation?.expires_in_s)}</div>
          <p className="mb-3 text-center text-sm text-muted">Left on your hold. After this the charger is released.</p>
          <div className="flex gap-2">
            <button className="btn-ghost flex-1" disabled={!j.reservation} onClick={() => run(() => api.cancelReservation(j.reservation.id), 'Reservation cancelled.')}>Cancel</button>
            <button className="btn-primary flex-1" disabled={!allowed.includes('go')} onClick={() => run(() => api.go(ch.id), 'On your way.')}>Go now</button>
          </div>
        </section>)
      case 'DRIVING': {
        const d = j.drive || {}
        const p = Math.round((d.progress ?? 0) * 100)
        return (
          <section className="card text-center">
            <h2 className="text-xl font-bold">Driving to {j.station?.name}</h2>
            <div className="my-4 flex justify-center"><LightRing size={170} stroke={14} pct={soc} status="reserved" label={`Battery ${soc} percent while driving`}><span className="font-display text-4xl font-bold num">{soc}%</span></LightRing></div>
            <div className="h-2 overflow-hidden rounded-full bg-line" role="progressbar" aria-valuenow={p} aria-valuemin="0" aria-valuemax="100"><div className="h-full bg-brand" style={{ width: p + '%' }} /></div>
            <p className="mt-2 text-sm text-muted num">{p}% of the way · {num(d.dist_km)} km trip · about {mins(d.eta_min)} left · arriving with {Math.round(d.arrival_soc ?? 0)}%</p>
            <Hold res={j.reservation} />
          </section>)
      }
      case 'ARRIVED': return (
        <section className="card text-center">
          <h2 className="text-xl font-bold">You have arrived</h2>
          <p className="text-sm text-muted">Charger {ch?.number} · {ch?.connector} · {ch?.max_kw} kW</p>
          <div className="my-5 flex items-center justify-center gap-0" aria-hidden="true">
            <Zap size={44} className="text-brand" />
            <div className={`h-2 w-16 rounded bg-ink ${busy ? 'cable-move' : ''}`} />
            <Plug size={40} className={busy ? 'text-st-available' : 'text-muted'} />
          </div>
          <button className="btn-primary w-full" disabled={busy || !allowed.includes('plug_in')} onClick={async () => { setBusy(true); const r = await run(() => api.plugIn()); if (!r) setBusy(false) }}>{busy ? 'Connecting…' : 'Plug in'}</button>
          <Hold res={j.reservation} />
        </section>)
      case 'PLUGGED_IN': {
        const hs = j.handshake || { ready: false, steps: [] }
        const full = pl && pl.min_target > 100 // battery above 95%: the backend refuses to start
        const soc0 = me.soc
        // Rough estimate only: energy = (target - soc) / 100 x battery kWh, at today's price, plus tax. Taper and sharing are ignored.
        const kwh = pl ? Math.max(0, (target - soc0) / 100 * pl.battery_kwh) : 0
        const estimate = pl ? kwh * pl.price_now * (1 + pl.tax_percent / 100) : 0
        const estMin = pl && pl.max_power_kw ? (kwh / pl.max_power_kw) * 60 : 0
        return (
          <section className="card">
            <h2 className="text-xl font-bold">{hs.ready ? 'Ready to charge' : 'Connecting…'}</h2>
            <ul className="mt-3 grid gap-1 text-left text-sm" aria-label="Connection steps">
              {hs.steps.map((h) => <li key={h.label} className={`flex items-center gap-2 ${h.done ? 'font-semibold text-st-available' : 'text-muted'}`}>{h.done ? <Check size={16} aria-hidden="true" /> : <Clock size={16} aria-hidden="true" />}{h.label}</li>)}
            </ul>
            {hs.ready && pl && !full && (<>
              <label className="mt-4 grid gap-1 text-sm font-semibold">Charge to: <span className="font-display text-3xl num">{target}%</span>
                <input type="range" min={pl.min_target} max="100" value={target} onChange={(e) => setTarget(Number(e.target.value))} />
              </label>
              <label className="mt-3 grid gap-1 text-sm font-semibold">Spending cap in rupees (optional, including tax)
                <input className="input font-normal" type="number" min="1" inputMode="numeric" value={cap} onChange={(e) => setCap(e.target.value)} placeholder="No cap" />
              </label>
              <p className="my-3 rounded-lg bg-page p-2 text-sm text-muted num">Estimate only, not your bill: about {num(kwh, 1)} kWh, roughly {inr(estimate)} including {pl.tax_percent}% tax, at today's {inr(pl.price_now)}/kWh. Charging slows near full and when the station is shared, so time and cost will differ{estMin > 0 && <> (at full power it would take about {mins(estMin)})</>}.</p>
            </>)}
            {hs.ready && full && <p className="my-3 text-sm">Your battery is already almost full. Unplug when you are ready.</p>}
            <div className="mt-3 grid gap-2">
              <button className="btn-primary w-full" disabled={!allowed.includes('start') || full} onClick={() => run(() => api.start(target, cap ? Number(cap) : null), 'Charging started.')}>Start charging</button>
              <button className="btn-ghost w-full" disabled={!allowed.includes('unplug')} onClick={() => run(() => api.unplug())}>Unplug without charging</button>
            </div>
          </section>)
      }
      case 'CHARGING': return (
        <section className="card text-center">
          <h2 className="text-xl font-bold">Charging</h2>
          <div className="my-3 flex justify-center"><LightRing size={200} stroke={16} pct={soc} status="charging" label={`Battery ${soc} percent, charging at ${num(c.power_kw)} kilowatts`}><span className="font-display text-5xl font-bold num">{soc}%</span><span className="text-sm text-muted num">to {c.target_soc}%</span></LightRing></div>
          <dl className="grid grid-cols-2 gap-2 text-left text-sm">
            {[['Power', `${num(c.power_kw)} kW`], ['Energy', `${num(c.energy_kwh, 2)} kWh`], ['Elapsed', mins(c.elapsed_min)], ['Time left', c.time_left_min == null ? 'Working it out…' : mins(c.time_left_min)]].map(([k, v]) => <div key={k} className="rounded-lg bg-page p-2"><dt className="text-muted">{k}</dt><dd className="font-display text-lg font-bold num">{v}</dd></div>)}
          </dl>
          <div className="mt-3 rounded-lg bg-page p-3 text-left text-sm">
            <div className="flex items-center justify-between"><span className="text-muted">Cost so far (with tax)</span><span className="font-display text-2xl font-bold num">{inr(c.running_cost)}</span></div>
            <div className="text-muted num">{inr(c.rate)}/kWh now {TARIFF_BADGE[c.tariff]}</div>
            {c.spending_cap != null && <div className="text-muted num">Spending cap: {inr(c.spending_cap)}</div>}
          </div>
          {c.sharing_note && <p className="mt-3 text-left text-sm">{c.sharing_note}</p>}
          <button className="btn-danger mt-4 w-full" disabled={!allowed.includes('stop')} onClick={() => run(() => api.stop())}>Stop charging</button>
        </section>)
      case 'STOPPED': {
        const st = j.stopped || {}
        return (
          <section className="card text-center">
            <h2 className="text-xl font-bold">Charging complete</h2>
            <p className="text-sm">{STOP_TEXT[st.reason] || 'Charging stopped.'} Unplug your cable.</p>
            <div className="my-4 flex justify-center"><LightRing size={150} stroke={13} pct={soc} status="finishing" label={`Battery ${soc} percent, charging finished`}><span className="font-display text-4xl font-bold num">{soc}%</span></LightRing></div>
            {st.grace_left_min > 0
              ? <p className="mb-3 text-sm text-muted num">Free wait left: {mins(st.grace_left_min)}. After that an idle fee applies, up to {inr(st.idle_fee_cap)}.</p>
              : <p className="mb-3 text-sm font-semibold text-st-faulted num">Idle fee ticking: {inr(st.idle_fee_now)} so far ({mins(st.idle_minutes)} since you stopped, up to {inr(st.idle_fee_cap)}). Unplug to stop it.</p>}
            <button className="btn-primary w-full" disabled={!allowed.includes('unplug')} onClick={() => run(() => api.unplug())}>Unplug</button>
          </section>)
      }
      case 'INVOICE': return j.invoice ? (<>
        <InvoiceView id={j.invoice.id} invoice={j.invoice} onDone={() => run(() => api.dismiss())} />
        <Suggestions items={j.suggestions} />
      </>) : null
      default: return (
        <section className="card text-center">
          <h2 className="text-xl font-bold">No journey right now</h2>
          {j.message && <p className="mt-1 text-sm">{j.message}</p>}
          <p className="my-2 text-sm text-muted">Pick a charger to get started.</p>
          <Suggestions items={j.suggestions} />
          {!j.suggestions?.length && <Link to="/find" className="btn-primary mt-3 w-full">Find chargers</Link>}
        </section>)
    }
  })()

  return (
    <main className="mx-auto max-w-md px-4 pb-28 pt-6">
      <h1 className="mb-3 text-2xl font-bold">Charge</h1>
      <UnpaidBanner />
      {j.state !== 'IDLE' && <div className="mt-3"><Steps state={j.state} /></div>}
      {j.message && j.state !== 'IDLE' && j.state !== 'STOPPED' && <p className="mb-3 rounded-lg bg-white p-3 text-sm border border-line">{j.message}</p>}
      <div className="mt-3">{body}</div>
    </main>
  )
}
