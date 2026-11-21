"""The devices: chargers, virtual drivers, faults and the clock. Knows nothing about the cloud."""
import random
import threading
import time
from datetime import datetime

AVAILABLE, RESERVED, PREPARING, CHARGING, FINISHING, FAULTED, OFFLINE = (
    "AVAILABLE", "RESERVED", "PREPARING", "CHARGING", "FINISHING", "FAULTED", "OFFLINE")


def taper(soc):
    return 1.0 if soc < 80 else max(0.12, 1 - (soc - 80) / 20 * 0.88)


def max_min_share(caps, total):
    """Max-min fair split of `total` kW: nobody gets more than their cap, leftovers go to the rest."""
    out, left = [0.0] * len(caps), total
    order = sorted(range(len(caps)), key=lambda i: caps[i])
    for k, i in enumerate(order):
        out[i] = min(caps[i], left / (len(order) - k))
        left -= out[i]
    return out


class Charger:
    def __init__(self, row):
        self.id, self.station = row["id"], row["station_id"]
        self.kind, self.connector, self.max_kw = row["kind"], row["connector"], float(row["max_kw"])
        self.limit_kw = None
        self.status = AVAILABLE
        self.fault_until = None
        self.reset()

    def reset(self):
        self.owner = self.session_id = self.vehicle = self.leave_at = None
        self.soc = self.energy = self.power = 0.0
        self.target = 100.0
        self.virtual = False


class Simulator:
    SPEEDS = (1, 10, 20, 60, 120)
    TRAFFIC = {"off": 0, "quiet": 6, "normal": 15, "busy": 30}

    def __init__(self, bus, cfg, catalog, seed=None):
        self.bus, self.cfg, self.rng = bus, cfg, random.Random(seed)
        self.vehicles = list(catalog["vehicles"].values())
        self.stations = {s["id"]: {"cap": float(s["power_cap_kw"]), "offline_until": None} for s in catalog["stations"].values()}
        self.chargers = {c["id"]: Charger(c) for c in catalog["chargers"].values()}
        self.now = datetime.now().replace(hour=8, minute=0, second=0, microsecond=0).timestamp()
        self.speed, self.traffic = cfg.DEFAULT_SIM_SPEED, "normal"
        self.random_faults, self.running = True, False
        bus.subscribe("ev/+/+/cmd", self._on_cmd)

    # ---- publishing ----
    def _cap(self, c):
        v = c.vehicle
        return min(c.limit_kw or c.max_kw, v["max_ac_kw"] if c.kind == "AC" else v["max_dc_kw"])

    def _eta(self, c):
        if c.status != CHARGING:
            return None
        p = c.power if c.power > 0.1 else self._cap(c) * taper(c.soc)
        return max(0.0, c.target - c.soc) / 100 * c.vehicle["battery_kwh"] / p * 60 if p > 0 else None

    def _pub(self, c, reason):
        free_at = None
        if c.status == FINISHING and c.virtual:
            free_at = c.leave_at
        elif c.status == FAULTED:
            free_at = c.fault_until
        elif c.status == OFFLINE:
            free_at = self.stations[c.station]["offline_until"]
        self.bus.publish(f"ev/{c.station}/{c.id}/status", {
            "status": c.status, "reason": reason, "owner": c.owner, "session_id": c.session_id,
            "at_sim": self.now, "soc": round(c.soc, 4) if c.vehicle else None,
            "energy_kwh": c.energy, "free_at_sim": free_at, "eta_min": self._eta(c)})

    def _set(self, c, status, reason, clear=False):
        c.status = status
        self._pub(c, reason)
        if clear:
            c.reset()

    def publish_all(self):
        for c in self.chargers.values():
            self._pub(c, "init")

    # ---- commands ----
    def _on_cmd(self, topic, p):
        _, st, cid, _ = topic.split("/")
        c, cmd = self.chargers.get(cid), p.get("cmd")
        if cmd == "offline":
            return self._offline(st, float(p.get("minutes", 60)) * 60)
        if c is None:
            return
        s = c.status
        if cmd == "reserve" and s == AVAILABLE:
            c.owner = p["owner"]
            self._set(c, RESERVED, "reserved")
        elif cmd == "cancel_reserve" and s == RESERVED:
            self._set(c, AVAILABLE, "reservation_ended", clear=True)
        elif cmd == "connect" and (s == AVAILABLE or (s == RESERVED and c.owner == p["owner"])):
            c.owner, c.vehicle, c.soc, c.energy = p["owner"], dict(p["vehicle"]), float(p["soc"]), 0.0
            self._set(c, PREPARING, "connected")
        elif cmd == "start" and s == PREPARING:
            c.session_id, c.target, c.energy = p["session_id"], float(p["target"]), 0.0
            self._set(c, CHARGING, "started")
        elif cmd == "stop" and s == CHARGING:
            c.power = 0.0
            self._set(c, FINISHING, p.get("reason", "user_stop"))
        elif cmd == "disconnect" and s in (PREPARING, CHARGING, FINISHING):
            self._set(c, AVAILABLE, "unplugged", clear=True)
        elif cmd == "set_limit":
            c.limit_kw = p.get("kw")
        elif cmd == "fault":
            self._fault(c, float(p.get("minutes", 30)) * 60)
        else:
            self._pub(c, "rejected")

    # ---- faults ----
    def _fault(self, c, secs):
        if c.status in (FAULTED, OFFLINE):
            return
        c.fault_until = self.now + secs
        self._set(c, FAULTED, "fault", clear=True)

    def _offline(self, station_id, secs):
        st = self.stations[station_id]
        if st["offline_until"]:
            return
        st["offline_until"] = self.now + secs
        for c in self.chargers.values():
            if c.station == station_id:
                c.fault_until = None
                self._set(c, OFFLINE, "station_offline", clear=True)

    def _faults(self, dt):
        if self.random_faults:
            for c in self.chargers.values():
                if self.rng.random() < dt / 3600 / 40:
                    self._fault(c, self.rng.uniform(20, 60) * 60)
            for sid, st in self.stations.items():
                if not st["offline_until"] and self.rng.random() < dt / 3600 / 400:
                    self._offline(sid, self.rng.uniform(30, 90) * 60)
        for sid, st in self.stations.items():
            if st["offline_until"] and self.now >= st["offline_until"]:
                st["offline_until"] = None
                for c in self.chargers.values():
                    if c.station == sid and c.status == OFFLINE:
                        self._set(c, AVAILABLE, "station_online")
        for c in self.chargers.values():
            if c.status == FAULTED and self.now >= c.fault_until:
                c.fault_until = None
                self._set(c, AVAILABLE, "repaired")

    # ---- virtual drivers ----
    def _virtual(self, dt):
        for c in self.chargers.values():
            if c.virtual and c.status == FINISHING and self.now >= c.leave_at:
                self._set(c, AVAILABLE, "virtual_left", clear=True)
        n = self.TRAFFIC[self.traffic] * dt / 3600
        k = int(n) + (1 if self.rng.random() < n - int(n) else 0)
        for _ in range(k):
            v = self.rng.choice(self.vehicles)
            ok = [c for c in self.chargers.values() if c.status == AVAILABLE and
                  c.connector == (v["ac_connector"] if c.kind == "AC" else v["dc_connector"])]
            if not ok:
                continue
            c = self.rng.choice(ok)
            c.virtual, c.owner, c.vehicle = True, "virtual", dict(v)
            c.soc, c.target, c.energy = self.rng.uniform(10, 60), self.rng.uniform(70, 100), 0.0
            c.session_id = None
            self._set(c, CHARGING, "virtual_driver")

    # ---- charging physics ----
    def _charge(self, dt):
        groups = {}
        for c in self.chargers.values():
            if c.status == CHARGING:
                groups.setdefault(c.station, []).append(c)
        for sid, cs in groups.items():
            caps = [self._cap(c) for c in cs]
            shares = max_min_share(caps, self.stations[sid]["cap"])
            for c, cap, share in zip(cs, caps, shares):
                kwh = c.vehicle["battery_kwh"]
                p = min(cap, share) * taper(c.soc)
                e = max(0.0, min(p * dt / 3600, (c.target - c.soc) / 100 * kwh))
                c.energy += e
                c.soc = min(100.0, c.soc + e / kwh * 100)
                c.power = p
                self.bus.publish(f"ev/{sid}/{c.id}/telemetry", {
                    "power_kw": round(p, 3), "demand_kw": round(cap, 3), "share_kw": round(share, 3),
                    "energy_kwh": c.energy, "soc": c.soc, "eta_min": self._eta(c),
                    "session_id": c.session_id, "at_sim": self.now})
                if c.status == CHARGING and c.soc >= c.target - 1e-9:
                    c.power = 0.0
                    if c.virtual:
                        c.leave_at = self.now + self.rng.uniform(0, 10) * 60
                    self._set(c, FINISHING, "battery_full" if c.target >= 100 - 1e-9 else "target_reached")

    def step(self, dt):
        """Advance the simulation by dt simulated seconds."""
        with self.bus.lock:
            self.now += dt
            self._faults(dt)
            self._virtual(dt)
            self._charge(dt)
            self.bus.publish("ev/sim/tick", {"at_sim": self.now, "dt": dt, "speed": self.speed})

    # ---- thread ----
    def start(self):
        self.running = True
        threading.Thread(target=self._loop, daemon=True, name="sim").start()

    def stop(self):
        self.running = False

    def _loop(self):
        while self.running:
            t0 = time.time()
            try:
                self.step(float(self.speed))
            except Exception:
                import logging
                logging.getLogger("chargegrid.sim").exception("tick failed")
            time.sleep(max(0.0, 1.0 - (time.time() - t0)))
