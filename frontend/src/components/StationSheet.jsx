import Sheet from './Sheet'
import LightRing from './LightRing'
import { inr, num, mins, statusInfo } from '../format'
import { useApp } from '../store'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import UnpaidBanner from './UnpaidBanner'

export default function StationSheet({ station, onClose, onDone }) {
  const { journey, run } = useApp()
  const nav = useNavigate()
  const allowed = journey?.allowed_actions || []
  const canReserve = allowed.includes('reserve')
  const canGo = allowed.includes('go')

  // After a successful reserve or go, close the sheet and open the Charge tab, where the journey continues.
  const reserve = async (c) => { if (await run(() => api.reserve(c.id), 'Charger reserved. Head there within the hold time.')) { onDone?.(); nav('/charge') } }
  const go = async (c) => { if (await run(() => api.go(c.id), 'On your way.')) { onDone?.(); nav('/charge') } }

  return (
    <Sheet title={station.name} onClose={onClose}>
      <p className="mb-3 text-sm text-muted">
        {num(station.distance_km)} km away · about {mins(station.eta_min)} drive · you would arrive with {Math.round(station.arrive_soc ?? 0)}%
        {station.free_count === 0 && station.wait_estimate != null && <> · all busy, next free in about {mins(station.wait_estimate)}</>}
      </p>
      <ul className="grid gap-3">
        {station.chargers.map((c) => {
          const st = statusInfo(c.status)
          const free = String(c.status).toUpperCase() === 'AVAILABLE'
          const myHold = c.mine && String(c.status).toUpperCase() === 'RESERVED'
          return (
            <li key={c.id} className="card">
              <div className="flex items-center gap-3">
                <LightRing size={56} stroke={7} status={c.status} label={`Charger ${c.number}: ${st.label}`}>
                  <span className="font-display text-sm font-bold">{c.number}</span>
                </LightRing>
                <div className="min-w-0 flex-1">
                  <div className="font-semibold">{c.connector} · {c.max_kw} kW <span className="font-normal text-muted">({c.kind})</span></div>
                  <div className="text-sm">
                    <span style={{ color: st.color }} className="font-semibold">{st.label}</span>
                    {!free && c.free_in_minutes != null && <span className="text-muted"> · free in about {mins(c.free_in_minutes)}</span>}
                  </div>
                  <div className="text-sm text-muted">
                    {inr(c.price_now)}/kWh now{' '}
                    {c.tariff === 'Peak' && <span className="badge bg-st-plugged/15 text-st-plugged">Peak</span>}
                    {c.tariff === 'Off-peak' && <span className="badge bg-st-available/15 text-st-available">Off-peak</span>}
                    {myHold && <span className="badge ml-1 bg-brand/15 text-brand">Reserved by you</span>}
                  </div>
                </div>
              </div>
              {!c.compatible ? (
                <p className="mt-2 rounded-lg bg-page p-2 text-sm text-muted">{c.incompatible_reason || 'This charger does not fit your car.'}</p>
              ) : (
                <div className="mt-3 flex gap-2">
                  <button className="btn-ghost flex-1" disabled={!free || !canReserve} onClick={() => reserve(c)}>Reserve</button>
                  <button className="btn-primary flex-1" disabled={!(free || myHold) || !canGo || station.reachable === false} onClick={() => go(c)}>Go now</button>
                </div>
              )}
            </li>
          )
        })}
      </ul>
      {station.reachable === false && <p className="mt-3 text-sm text-muted">You would arrive with too little battery to drive here. Charge nearer to you first.</p>}
      <UnpaidBanner />
      {!canGo && journey?.state !== 'IDLE' && <p className="mt-3 text-sm text-muted">You already have a journey in progress. Finish it from the Charge tab first.</p>}
    </Sheet>
  )
}
