import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Printer } from 'lucide-react'
import { api } from '../api'
import { useApp } from '../store'
import { inr, num } from '../format'

// `invoice` (optional) is the live object from journey.invoice; without it the invoice is fetched by id.
export function InvoiceView({ id, invoice, onDone }) {
  const { run } = useApp()
  const [fetched, setFetched] = useState(null)
  const [err, setErr] = useState('')
  const load = () => api.invoice(id).then(setFetched).catch((e) => setErr(e.message))
  useEffect(() => { if (!invoice) load() }, [id]) // eslint-disable-line
  const inv = invoice || fetched
  if (err) return <p className="card text-st-faulted" role="alert">{err}</p>
  if (!inv) return <p className="card text-muted">Loading invoice…</p>
  const lines = inv.lines?.length ? inv.lines : [{ label: 'Energy', kwh: inv.energy_kwh, rate: inv.energy_kwh ? inv.energy_amount / inv.energy_kwh : 0, amount: inv.energy_amount }]
  const paid = String(inv.status).toLowerCase() === 'paid'
  const lost = ['fault', 'station_offline'].includes(inv.end_reason)
  const pay = async () => { const r = await run(() => api.payInvoice(id)); if (r && r !== true) setFetched(r) }

  return (
    <section className="card">
      <div className="flex items-start justify-between">
        <div><h2 className="text-xl font-bold">Invoice</h2><p className="text-sm text-muted num">{inv.number}</p></div>
        <span className={`badge ${paid ? 'bg-st-available/15 text-st-available' : 'bg-st-faulted/15 text-st-faulted'}`}>{paid ? 'Paid' : 'Unpaid'}</span>
      </div>
      {inv.station && <p className="mt-2 text-sm text-muted">{inv.station}{inv.charger_number ? ` · charger ${inv.charger_number}` : ''}{inv.vehicle ? ` · ${inv.vehicle}` : ''}</p>}
      {lost && <p className="mt-3 rounded-lg bg-st-faulted/10 p-3 text-sm font-semibold text-st-faulted">Charging stopped early because of a charger problem. You are billed only for the energy delivered, with no idle fee.</p>}
      <table className="mt-4 w-full text-sm">
        <tbody>
          {lines.map((l, i) => (
            <tr key={i} className="border-t border-line">
              <td className="py-2">{l.label || 'Energy'}<div className="text-muted num">{num(l.kwh, 2)} kWh × {inr(l.rate)}</div></td>
              <td className="py-2 text-right num">{inr(l.amount)}</td>
            </tr>
          ))}
          {Number(inv.idle_fee) > 0 && <tr className="border-t border-line"><td className="py-2">Idle fee<div className="text-muted num">{num(inv.idle_minutes, 1)} min after the free wait</div></td><td className="py-2 text-right num">{inr(inv.idle_fee)}</td></tr>}
          <tr className="border-t border-line"><td className="py-2">Tax ({inv.tax_percent}%)</td><td className="py-2 text-right num">{inr(inv.tax_amount)}</td></tr>
          <tr className="border-t-2 border-ink"><td className="py-2 font-bold">Total</td><td className="py-2 text-right font-display text-xl font-bold num">{inr(inv.total)}</td></tr>
        </tbody>
      </table>
      <p className="mt-2 text-sm text-muted">{paid ? 'Paid from your wallet.' : 'Not paid yet. Top up your wallet, then pay this invoice.'} Tax rate is illustrative.</p>
      <div className="no-print mt-4 flex gap-2">
        <button className="btn-ghost" onClick={() => window.print()}><Printer size={16} aria-hidden="true" />Print</button>
        {!paid && <button className="btn-primary flex-1" onClick={pay}>Pay now</button>}
        {onDone && <button className="btn-primary flex-1" onClick={onDone}>Done</button>}
      </div>
    </section>
  )
}

export default function InvoicePage() {
  const { id } = useParams(); const nav = useNavigate()
  return <main className="mx-auto max-w-md px-4 pb-28 pt-6"><button className="no-print mb-3 text-sm font-semibold text-brand" onClick={() => nav(-1)}>← Back</button><InvoiceView id={id} /></main>
}
