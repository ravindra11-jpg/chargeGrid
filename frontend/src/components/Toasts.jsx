import { Link } from 'react-router-dom'
import { useApp } from '../store'

const tone = { ok: 'bg-st-available', err: 'bg-st-faulted', warn: 'bg-st-plugged', info: 'bg-brand' }
export default function Toasts() {
  const { toasts } = useApp()
  return (
    <div className="pointer-events-none fixed inset-x-0 top-3 z-[2000] flex flex-col items-center gap-2 px-3" role="status" aria-live="polite">
      {toasts.map((t) => (
        <div key={t.id} className={`${tone[t.kind] || tone.info} pointer-events-auto flex max-w-md items-center gap-3 rounded-xl px-4 py-3 text-sm font-semibold text-white shadow-lg`}>
          <span>{t.text}</span>
          {t.action && <Link to={t.action.to} className="shrink-0 rounded-lg bg-white px-3 py-1.5 text-ink">{t.action.label}</Link>}
        </div>
      ))}
    </div>
  )
}
