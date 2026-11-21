import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { useApp } from '../store'
import VehicleCards from '../components/VehicleCards'
import Sheet from '../components/Sheet'

const DEFAULT_SPEEDS = [1, 10, 20, 60, 120]
const DEFAULT_TRAFFIC = ['quiet', 'normal', 'busy']

function Demo({ onClose }) {
  const { run, push } = useApp()
  const [sim, setSim] = useState({ speed: 20, traffic: 'normal', speeds: DEFAULT_SPEEDS, levels: DEFAULT_TRAFFIC })
  useEffect(() => { api.simGet().then(setSim).catch((e) => push(e.message, 'err')) }, []) // eslint-disable-line
  const set = async (patch) => { const r = await run(() => api.simSet(patch)); if (r && r !== true) setSim(r) }
  return (
    <Sheet title="Simulation" onClose={onClose}>
      <p className="mb-3 text-sm text-muted">Demo tools for the simulated grid. These do not exist in a real app.</p>
      <div className="mb-3"><div className="mb-1 text-sm font-semibold">Sim speed</div>
        <div className="flex flex-wrap gap-2">{sim.speeds.map((s) => <button key={s} aria-pressed={sim.speed === s} onClick={() => set({ speed: s })} className={sim.speed === s ? 'btn-primary !py-2' : 'btn-ghost !py-2'}>{s}x</button>)}</div></div>
      <div className="mb-3"><div className="mb-1 text-sm font-semibold">Background traffic</div>
        <div className="flex gap-2">{sim.levels.map((t) => <button key={t} aria-pressed={sim.traffic === t} onClick={() => set({ traffic: t })} className={`${sim.traffic === t ? 'btn-primary' : 'btn-ghost'} !py-2 capitalize`}>{t}</button>)}</div></div>
      <div className="grid gap-2">
        <button className="btn-danger" onClick={() => run(() => api.breakMyCharger())}>Break my charger</button>
        <button className="btn-ghost" onClick={() => run(() => api.patchMe({ soc: 15 }), 'Battery set to 15%.')}>Set battery to 15%</button>
      </div>
    </Sheet>
  )
}

export default function Profile() {
  const { me, run, signOut } = useApp()
  const [vehicles, setVehicles] = useState([])
  const [pick, setPick] = useState(me.vehicle?.id)
  const [demo, setDemo] = useState(false)
  useEffect(() => { api.vehicles().then(setVehicles).catch(() => {}) }, [])
  return (
    <main className="mx-auto max-w-md px-4 pb-28 pt-6">
      <h1 className="text-2xl font-bold">Profile</h1>
      <p className="text-sm text-muted">Signed in as {me.name}</p>
      <section className="mt-4"><h2 className="mb-2 font-bold">Vehicle</h2>
        <VehicleCards vehicles={vehicles} value={pick} onChange={setPick} />
        <button className="btn-primary mt-3 w-full" disabled={pick === me.vehicle?.id} onClick={() => run(() => api.patchMe({ vehicle_model_id: pick }), 'Vehicle changed. Battery level kept.')}>Change vehicle</button>
      </section>
      <div className="mt-4 grid gap-2">
        <Link to="/history" className="btn-ghost">Charging history</Link>
        <button className="btn-ghost" onClick={() => setDemo(true)}>Simulation</button>
        <button className="btn-ghost" onClick={signOut}>Sign out</button>
      </div>
      {demo && <Demo onClose={() => setDemo(false)} />}
    </main>
  )
}
