import { Link } from 'react-router-dom'
import { Receipt } from 'lucide-react'
import { useApp } from '../store'

// Shown when the journey is IDLE but an invoice is unpaid (the backend then returns allowed_actions: []).
export default function UnpaidBanner() {
  const { journey } = useApp()
  const id = journey?.unpaid_invoice_id
  if (!id || journey.state !== 'IDLE') return null
  return (
    <Link to={'/invoice/' + id} className="mt-3 flex items-center gap-2 rounded-xl bg-st-faulted/10 p-3 text-sm font-semibold text-st-faulted" role="alert">
      <Receipt size={18} aria-hidden="true" /> Pay your invoice first. You cannot start a new trip until it is paid. <span className="ml-auto underline">Open invoice</span>
    </Link>
  )
}
