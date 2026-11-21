import { Navigate, Route, Routes } from 'react-router-dom'
import { useApp } from './store'
import TabBar from './components/TabBar'
import Toasts from './components/Toasts'
import Welcome from './pages/Welcome'
import Home from './pages/Home'
import Find from './pages/Find'
import Charge from './pages/Charge'
import Wallet from './pages/Wallet'
import History from './pages/History'
import Profile from './pages/Profile'
import InvoicePage from './pages/Invoice'

export default function App() {
  const { authed, booting, me } = useApp()
  let body
  if (!authed) body = <Welcome />
  else if (booting || !me) body = <main className="px-4 pt-10 text-center text-muted">Loading your app…</main>
  else body = (
    <>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/find" element={<Find />} />
        <Route path="/charge" element={<Charge />} />
        <Route path="/wallet" element={<Wallet />} />
        <Route path="/history" element={<History />} />
        <Route path="/profile" element={<Profile />} />
        <Route path="/invoice/:id" element={<InvoicePage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      <TabBar />
    </>
  )
  return <><Toasts />{body}</>
}
