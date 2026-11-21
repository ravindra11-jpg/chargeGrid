import { useEffect, useMemo, useState } from 'react'
import { MapContainer, TileLayer, CircleMarker, Tooltip, useMap } from 'react-leaflet'
import { api } from '../api'
import { useApp } from '../store'
import { num, mins, STATUS } from '../format'
import StationSheet from '../components/StationSheet'
import UnpaidBanner from '../components/UnpaidBanner'

function Recenter({ pos }) { const m = useMap(); useEffect(() => { m.setView(pos) }, []) ; return null }

const stationColor = (s) => {
  if (s.free_count > 0) return STATUS.available.color
  if (s.chargers.every((c) => ['OFFLINE', 'FAULTED'].includes(String(c.status).toUpperCase()))) return STATUS.offline.color
  return STATUS.charging.color
}

export default function Find() {
  const { me, push } = useApp()
  const [stations, setStations] = useState([])
  const [selId, setSelId] = useState(null)
  const [filters, setFilters] = useState({ compat: false, fast: false, avail: false })

  useEffect(() => {
    let stop = false, t
    const load = async () => {
      try { const s = await api.stations(me.lat, me.lng); if (!stop) setStations(s) } catch (e) { if (!stop) push(e.message, 'err') }
      if (!stop) t = setTimeout(load, 3000)
    }
    load()
    return () => { stop = true; clearTimeout(t) }
  }, [me.lat, me.lng]) // eslint-disable-line

  const shown = useMemo(() => stations
    .filter((s) => (!filters.compat || s.chargers.some((c) => c.compatible))
      && (!filters.fast || s.chargers.some((c) => c.kind === 'DC'))
      && (!filters.avail || s.free_count > 0))
    .sort((a, b) => a.distance_km - b.distance_km), [stations, filters])
  const sel = stations.find((s) => s.id === selId)
  const pos = [me.lat, me.lng]

  return (
    <main className="mx-auto max-w-6xl px-4 pb-28 pt-4 lg:grid lg:grid-cols-[1fr_400px] lg:gap-4">
      <div className="mb-3 h-[40vh] overflow-hidden rounded-2xl border border-line lg:sticky lg:top-4 lg:mb-0 lg:h-[calc(100vh-7rem)]">
        <MapContainer center={pos} zoom={11} style={{ height: '100%' }}>
          <TileLayer attribution="&copy; OpenStreetMap contributors" url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
          <Recenter pos={pos} />
          <CircleMarker center={pos} radius={8} pathOptions={{ color: '#fff', weight: 3, fillColor: '#0e2433', fillOpacity: 1 }}><Tooltip>You are here</Tooltip></CircleMarker>
          {shown.map((s) => (
            <CircleMarker key={s.id} center={[s.lat, s.lng]} radius={12}
              pathOptions={{ color: '#fff', weight: 2, fillColor: stationColor(s), fillOpacity: 0.95 }}
              eventHandlers={{ click: () => setSelId(s.id) }}>
              <Tooltip>{s.name}: {s.free_count} free</Tooltip>
            </CircleMarker>
          ))}
        </MapContainer>
      </div>
      <section>
        <UnpaidBanner />
        <div className="mb-3 mt-3 flex flex-wrap gap-2" role="group" aria-label="Filters">
          {[['compat', 'Compatible with my car'], ['fast', 'Fast (DC)'], ['avail', 'Available now']].map(([k, l]) => (
            <button key={k} aria-pressed={filters[k]} onClick={() => setFilters({ ...filters, [k]: !filters[k] })}
              className={`rounded-full border px-3 py-1.5 text-sm font-semibold ${filters[k] ? 'border-brand bg-brand text-white' : 'border-line bg-white'}`}>{l}</button>
          ))}
        </div>
        <ul className="grid gap-2">
          {shown.map((s) => (
            <li key={s.id}>
              <button onClick={() => setSelId(s.id)} className="card flex w-full items-center gap-3 text-left">
                <span className="h-3 w-3 shrink-0 rounded-full" style={{ background: stationColor(s) }} aria-hidden="true" />
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-semibold">{s.name}</span>
                  <span className="text-sm text-muted num">{num(s.distance_km)} km · {mins(s.eta_min)} · {s.free_count} of {s.chargers.length} free
                    {s.free_count === 0 && s.wait_estimate != null && ` · wait about ${mins(s.wait_estimate)}`}</span>
                </span>
              </button>
            </li>
          ))}
          {shown.length === 0 && <li className="card text-sm text-muted">No stations match these filters.</li>}
        </ul>
      </section>
      {sel && <StationSheet station={sel} onClose={() => setSelId(null)} onDone={() => setSelId(null)} />}
    </main>
  )
}
