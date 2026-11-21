import { statusInfo } from '../format'

// The "charger light ring": fills with battery %, dashed when faulted/offline, breathes while charging.
export default function LightRing({ pct = 100, status = 'available', size = 96, stroke = 9, label, children }) {
  const key = String(status).toLowerCase()
  const { color } = statusInfo(key)
  const r = (size - stroke) / 2
  const c = 2 * Math.PI * r
  const fill = Math.min(100, Math.max(0, pct))
  const dashed = key === 'faulted' || key === 'offline'
  return (
    <div className="relative inline-flex shrink-0 items-center justify-center" style={{ width: size, height: size }} role="img" aria-label={label}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className={key === 'charging' ? 'ring-breathe' : ''} aria-hidden="true">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#d6dfe3" strokeWidth={stroke} />
        <circle
          cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={stroke}
          strokeLinecap={dashed ? 'butt' : 'round'}
          strokeDasharray={dashed ? '5 7' : `${(c * fill) / 100} ${c}`}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
          style={{ transition: 'stroke-dasharray .6s ease' }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center text-center">{children}</div>
    </div>
  )
}
