import { NavLink } from 'react-router-dom'
import { Home, MapPin, Zap, Wallet, User } from 'lucide-react'
import { useApp } from '../store'

const tabs = [
  { to: '/', label: 'Home', Icon: Home, end: true },
  { to: '/find', label: 'Find', Icon: MapPin },
  { to: '/charge', label: 'Charge', Icon: Zap },
  { to: '/wallet', label: 'Wallet', Icon: Wallet },
  { to: '/profile', label: 'Profile', Icon: User }
]
export default function TabBar() {
  const { journey } = useApp()
  const active = journey && journey.state && journey.state !== 'IDLE'
  return (
    <nav className="fixed inset-x-0 bottom-0 z-[900] border-t border-line bg-white" aria-label="Main">
      <ul className="mx-auto flex max-w-3xl">
        {tabs.map(({ to, label, Icon, end }) => (
          <li key={to} className="flex-1">
            <NavLink to={to} end={end}
              className={({ isActive }) => `relative flex flex-col items-center gap-0.5 py-2.5 text-xs font-semibold ${isActive ? 'text-brand' : 'text-muted'}`}>
              <Icon size={22} aria-hidden="true" />
              {label}
              {label === 'Charge' && active && <span className="absolute right-[32%] top-2 h-2.5 w-2.5 rounded-full bg-st-charging" aria-label="Journey in progress" />}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  )
}
