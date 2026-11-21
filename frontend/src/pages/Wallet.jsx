import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { CheckCircle2 } from 'lucide-react'
import { api } from '../api'
import { useApp } from '../store'
import { inr, inr0 } from '../format'
import Sheet from '../components/Sheet'

export default function Wallet() {
  const { run, me, push } = useApp()
  const nav = useNavigate()
  const [w, setW] = useState(null)
  const [done, setDone] = useState(null)
  const load = () => api.wallet().then(setW).catch((e) => push(e.message, 'err'))
  useEffect(() => { load() }, [me?.wallet_balance]) // eslint-disable-line

  const topup = async (amt) => { if (await run(() => api.topup(amt))) { setDone(amt); load() } }
  const unpaid = w?.unpaid_invoices || []

  return (
    <main className="mx-auto max-w-md px-4 pb-28 pt-6">
      <h1 className="text-2xl font-bold">Wallet</h1>
      <section className="card mt-3 text-center">
        <div className="text-sm text-muted">Balance</div>
        <div className="font-display text-4xl font-bold num">{inr(w?.balance ?? me.wallet_balance)}</div>
        <div className="mt-3 flex justify-center gap-2">{[200, 500, 1000].map((a) => <button key={a} className="btn-ghost !py-2" onClick={() => topup(a)}>Add {inr0(a)}</button>)}</div>
        <p className="mt-2 text-xs text-muted">Payments are simulated. No real money moves.</p>
      </section>
      {unpaid.length > 0 && (
        <section className="mt-4"><h2 className="mb-2 font-bold">Unpaid invoices</h2>
          {unpaid.map((i) => (
            <div key={i.id} className="card mb-2 flex items-center justify-between">
              <button className="text-left" onClick={() => nav('/invoice/' + i.id)}><div className="font-semibold num">{i.number}</div><div className="text-sm text-muted num">{inr(i.total)}</div></button>
              <button className="btn-primary !py-2" onClick={async () => { if (await run(() => api.payInvoice(i.id), 'Payment done.')) load() }}>Pay now</button>
            </div>))}
        </section>)}
      <section className="mt-4"><div className="mb-2 flex items-center justify-between"><h2 className="font-bold">Transactions</h2><Link to="/history" className="text-sm font-semibold text-brand">Charging history</Link></div>
        <ul className="grid gap-2">
          {(w?.transactions || []).map((t) => (
            <li key={t.id} className="card flex items-center justify-between !py-3">
              <div><div className="font-semibold">{t.kind === 'topup' ? 'Added money' : 'Charging payment'}</div><div className="text-xs text-muted">{new Date(t.created_at).toLocaleString('en-IN')}</div></div>
              <div className="text-right"><div className={`font-bold num ${t.kind === 'topup' ? 'text-st-available' : ''}`}>{t.kind === 'topup' ? '+' : '-'}{inr(Math.abs(t.amount))}</div><div className="text-xs text-muted num">Balance {inr(t.balance_after)}</div></div>
            </li>))}
          {w && !w.transactions?.length && <li className="card text-sm text-muted">No transactions yet.</li>}
        </ul>
      </section>
      {done && (
        <Sheet title="Payment successful" onClose={() => setDone(null)}>
          <div className="flex flex-col items-center gap-2 py-4"><CheckCircle2 size={56} className="text-st-available" aria-hidden="true" /><p className="font-display text-2xl font-bold num">{inr(done)} added</p><p className="text-sm text-muted">This was a simulated payment.</p></div>
          <button className="btn-primary w-full" onClick={() => setDone(null)}>Done</button>
        </Sheet>)}
    </main>
  )
}
