import { Battery, Plug } from 'lucide-react'
import { rangeKm } from '../format'

export default function VehicleCards({ vehicles, value, onChange }) {
  return (
    <div className="grid gap-2" role="radiogroup" aria-label="Vehicle model">
      {vehicles.map((v) => (
        <button key={v.id} type="button" role="radio" aria-checked={value === v.id} onClick={() => onChange(v.id)}
          className={`rounded-xl border p-3 text-left ${value === v.id ? 'border-brand bg-white ring-2 ring-brand' : 'border-line bg-white'}`}>
          <div className="font-display font-bold">{v.label}</div>
          <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted">
            <span className="inline-flex items-center gap-1"><Battery size={14} aria-hidden="true" />{v.battery_kwh} kWh</span>
            <span className="inline-flex items-center gap-1"><Plug size={14} aria-hidden="true" />{v.ac_connector} · {v.dc_connector}</span>
            <span>{rangeKm(100, v)} km range</span>
          </div>
        </button>
      ))}
    </div>
  )
}
