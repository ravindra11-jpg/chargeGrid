import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '../api'
import { useApp } from '../store'
import { inr, num, dayKey } from '../format'

// Stats and the chart come straight from the server's `summary` and `daily`; nothing is recomputed here.
export default function History() {
  const { push } = useApp()
  const nav = useNavigate()
  const [data, setData] = useState(null)
  const [metric, setMetric] = useState('spend')
  useEffect(() => { api.sessions().then(setData).catch((e) => push(e.message, 'err')) }, []) // eslint-disable-line

  const rows = data?.sessions || []
  const sum = data?.summary || { total_kwh: 0, total_spend: 0, sessions: 0 }
  const chart = useMemo(() => (data?.daily || []).map((d) => ({ day: dayKey(d.date), value: metric === 'spend' ? d.spend : d.kwh })), [data, metric])

  return (
    <main className="mx-auto max-w-md px-4 pb-28 pt-6">
      <h1 className="text-2xl font-bold">Charging history</h1>
      <div className="mt-3 grid grid-cols-3 gap-2 text-center">
        {[['Energy', `${num(sum.total_kwh)} kWh`], ['Spent', inr(sum.total_spend)], ['Sessions', sum.sessions]].map(([k, v]) => <div key={k} className="card !p-3"><div className="text-xs text-muted">{k}</div><div className="font-display font-bold num">{v}</div></div>)}
      </div>
      {chart.length > 0 && (
        <section className="card mt-3">
          <div className="mb-2 flex gap-2" role="group" aria-label="Chart metric">
            {[['spend', 'Spend'], ['energy', 'Energy']].map(([k, l]) => <button key={k} aria-pressed={metric === k} onClick={() => setMetric(k)} className={`rounded-full border px-3 py-1 text-sm font-semibold ${metric === k ? 'border-brand bg-brand text-white' : 'border-line'}`}>{l}</button>)}
          </div>
          <div className="h-44" role="img" aria-label={`Chart of ${metric} per day`}>
            <ResponsiveContainer><BarChart data={chart}><CartesianGrid stroke="#d6dfe3" vertical={false} /><XAxis dataKey="day" fontSize={12} /><YAxis fontSize={12} width={40} /><Tooltip formatter={(v) => (metric === 'spend' ? inr(v) : num(v, 2) + ' kWh')} /><Bar dataKey="value" fill="#0d5c63" radius={[4, 4, 0, 0]} /></BarChart></ResponsiveContainer>
          </div>
        </section>)}
      <ul className="mt-3 grid gap-2">
        {rows.map((s) => (
          <li key={s.id}><button className="card flex w-full items-center justify-between text-left" disabled={!s.invoice_id} onClick={() => nav('/invoice/' + s.invoice_id)}>
            <span>
              <span className="block font-semibold">{s.station}<span className="font-normal text-muted"> · charger {s.charger_number}</span></span>
              <span className="text-sm text-muted num">{new Date(s.started_at).toLocaleString('en-IN')} · {num(s.energy_kwh, 2)} kWh</span>
              {s.status === 'aborted' && <span className="block text-sm font-semibold text-st-faulted">Stopped early by the charger</span>}
              {s.invoice_status === 'unpaid' && <span className="block text-sm font-semibold text-st-faulted">Unpaid</span>}
            </span>
            <span className="font-bold num">{inr(s.total)}</span>
          </button></li>))}
        {data && !rows.length && <li className="card text-sm text-muted">No sessions yet. Your first charge will show up here.</li>}
      </ul>
    </main>
  )
}
