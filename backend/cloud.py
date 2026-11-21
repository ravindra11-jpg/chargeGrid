"""The services: auth, catalog, availability, reservations, journey, billing, wallet.
Learns about chargers only from bus status/telemetry; controls them only with bus commands."""
import datetime as dt
import functools
import math
import re
import time
import uuid

from itsdangerous import BadSignature, URLSafeTimedSerializer
from werkzeug.security import check_password_hash, generate_password_hash

from errors import ApiError
from seed import CENTRE

FRIENDLY = {"AVAILABLE": "available", "RESERVED": "reserved by someone else", "PREPARING": "in use",
            "CHARGING": "in use", "FINISHING": "in use", "FAULTED": "out of order", "OFFLINE": "offline"}


def tariff(ts):
    h = dt.datetime.fromtimestamp(ts).hour
    if 18 <= h < 22:
        return 1.3, "Peak"
    if h >= 23 or h < 6:
        return 0.85, "Off-peak"
    return 1.0, "Standard"


def haversine(a, b, c, d):
    p1, p2 = math.radians(a), math.radians(c)
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(d - b) / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(h))


def now_iso():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def sim_iso(ts):
    return dt.datetime.fromtimestamp(ts).isoformat(timespec="seconds")


def locked(fn):
    @functools.wraps(fn)
    def w(self, *a, **k):
        with self.bus.lock:
            return fn(self, *a, **k)
    return w


def num(v, lo, hi, label):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not (lo <= v <= hi):
        raise ApiError(400, f"{label} must be a number between {lo} and {hi}.")
    return float(v)


SESSION_COLS = ("id user_id charger_id station_id vehicle_model_id start_soc end_soc target_soc spending_cap energy_kwh "
                "energy_cost idle_minutes idle_fee status end_reason sim_started sim_ended started_at ended_at").split()
INVOICE_COLS = ("id number session_id user_id energy_kwh energy_amount idle_fee tax_percent tax_amount total status "
                "created_at paid_at lines").split()
RES_COLS = "id user_id charger_id status created_at expires_at".split()


class Cloud:
    def __init__(self, bus, repo, cfg, catalog, now_fn=time.time):
        self.bus, self.repo, self.cfg, self.now_fn = bus, repo, cfg, now_fn
        self.vehicles, self.stations, self.chargers = catalog["vehicles"], catalog["stations"], catalog["chargers"]
        self.cs = {cid: dict(status="OFFLINE", reason="unknown", owner=None, session_id=None, power_kw=0.0,
                             demand_kw=0.0, share_kw=0.0, energy_kwh=0.0, soc=None, eta_min=None, free_at_sim=None)
                   for cid in self.chargers}
        self.sim_now, self.sim_speed = None, cfg.DEFAULT_SIM_SPEED
        self.users, self.by_name, self.journeys, self.conn = {}, {}, {}, {}
        self.reservations, self.sessions, self.invoices, self.txs = {}, {}, {}, {}
        self.notices, self._nid, self._tx_id, self._inv_seq = {}, 0, 0, 0
        self.low_warned, self._last_snap = set(), time.time()
        self.ser = URLSafeTimedSerializer(cfg.APP_SECRET_KEY, salt="chargegrid-auth")
        bus.subscribe("ev/+/+/status", self._on_status)
        bus.subscribe("ev/+/+/telemetry", self._on_tele)
        bus.subscribe("ev/sim/tick", self._on_tick)
        self._load()

    # ================= startup / recovery =================
    def _load(self):
        f = float
        for r in self.repo.load("users"):
            for k in ("soc", "lat", "lng", "wallet_balance"):
                r[k] = f(r[k])
            self.users[r["id"]] = r
            self.by_name[r["name"].lower()] = r["id"]
        for r in sorted(self.repo.load("wallet_transactions"), key=lambda x: x["id"]):
            r["amount"], r["balance_after"] = f(r["amount"]), f(r["balance_after"])
            self.txs.setdefault(r["user_id"], []).append(r)
            self._tx_id = max(self._tx_id, int(r["id"]))
        for r in self.repo.load("invoices"):
            for k in ("energy_kwh", "energy_amount", "idle_fee", "tax_percent", "tax_amount", "total"):
                r[k] = f(r[k])
            self.invoices[r["id"]] = r
            m = re.search(r"(\d+)$", r["number"])
            self._inv_seq = max(self._inv_seq, int(m.group(1)) if m else 0)
        for r in self.repo.load("charging_sessions"):
            for k in ("start_soc", "end_soc", "target_soc", "spending_cap", "energy_kwh", "energy_cost", "idle_minutes", "idle_fee"):
                r[k] = None if r.get(k) is None else f(r[k])
            r.update(last_energy=r["energy_kwh"] or 0.0, segments={}, stopped_at_sim=None, idle_exempt=True)
            self.sessions[r["id"]] = r
        for r in self.repo.load("reservations"):
            self.reservations[r["id"]] = r
            if r["status"] == "active":
                r["status"] = "expired"
                self.repo.upsert("reservations", self._res_row(r))
        for s in list(self.sessions.values()):
            if s["status"] == "active":
                self._recover(s)

    def _recover(self, s):
        """A previous run died mid-session: close it as aborted and bill the energy delivered."""
        u = self.users.get(s["user_id"])
        if not u:
            return
        veh = self.vehicles[s["vehicle_model_id"]]
        kwh = s["energy_kwh"] or 0.0
        end = min(100.0, s["start_soc"] + kwh / veh["battery_kwh"] * 100)
        s.update(status="aborted", end_reason="server_restart", end_soc=end, ended_at=now_iso(), idle_fee=0.0, idle_minutes=0.0)
        amt = round(s["energy_cost"] or 0.0, 2)
        lines = [{"label": "Energy delivered before the server restarted", "kwh": round(kwh, 3),
                  "rate": round(amt / kwh, 2) if kwh else 0.0, "amount": amt}]
        self.repo.upsert("charging_sessions", self._srow(s))
        u["soc"] = end
        self._invoice(u, s, lines, kwh, amt)

    # ================= helpers =================
    def _srow(self, s):
        return {k: s.get(k) for k in SESSION_COLS}

    def _res_row(self, r):
        return {k: r.get(k) for k in RES_COLS}

    def _save_user(self, u):
        self.repo.upsert("users", {k: u[k] for k in ("id", "name", "pin_hash", "vehicle_model_id", "soc", "lat", "lng", "wallet_balance", "created_at")})

    def _j(self, uid):
        return self.journeys.setdefault(uid, {"state": "IDLE"})

    def _veh(self, u):
        return self.vehicles[u["vehicle_model_id"]]

    def _now(self):
        return self.sim_now if self.sim_now is not None else time.time()

    def _notify(self, uid, kind, text):
        self._nid += 1
        lst = self.notices.setdefault(uid, [])
        lst.append({"id": self._nid, "kind": kind, "text": text})
        del lst[:-20]

    def _compat(self, veh, ch):
        want = veh["ac_connector"] if ch["kind"] == "AC" else veh["dc_connector"]
        if want == ch["connector"]:
            return True, None
        return False, (f"Your {veh['label']} charges on {veh['dc_connector']} at DC chargers, "
                       f"so it can't use this {ch['connector']} charger.")

    def _unpaid(self, uid):
        return next((i for i in self.invoices.values() if i["user_id"] == uid and i["status"] == "unpaid"), None)

    def _need_paid(self, uid):
        inv = self._unpaid(uid)
        if inv:
            raise ApiError(402, f"You have an unpaid invoice of ₹{inv['total']:,.2f}. Pay it before starting another trip.",
                           action="pay", invoice_id=inv["id"])

    def _active_res(self, uid):
        return next((r for r in self.reservations.values() if r["user_id"] == uid and r["status"] == "active"), None)

    def _trip(self, u, veh, lat, lng):
        d = round(haversine(u["lat"], u["lng"], lat, lng) * self.cfg.ROAD_FACTOR, 2)
        use = d * veh["wh_per_km"] / (veh["battery_kwh"] * 1000) * 100
        return d, d / self.cfg.AVG_KMH * 60, use, u["soc"] - use

    def _range(self, u):
        v = self._veh(u)
        return round(u["soc"] / 100 * v["battery_kwh"] * 1000 / v["wh_per_km"], 1)

    def _ch(self, cid):
        if not isinstance(cid, str) or cid not in self.chargers:
            raise ApiError(404, "That charger doesn't exist.")
        return self.chargers[cid]

    def _alternatives(self, u, lat, lng, max_km=None, exclude=None, n=3):
        veh, out = self._veh(u), []
        for st in self.stations.values():
            if st["id"] == exclude:
                continue
            d = round(haversine(lat, lng, st["lat"], st["lng"]) * self.cfg.ROAD_FACTOR, 2)
            arrive = u["soc"] - d * veh["wh_per_km"] / (veh["battery_kwh"] * 1000) * 100
            free = [c for c in self.chargers.values() if c["station_id"] == st["id"]
                    and self.cs[c["id"]]["status"] == "AVAILABLE" and self._compat(veh, c)[0]]
            if free and arrive >= self.cfg.MIN_ARRIVAL_SOC and (max_km is None or d < max_km):
                out.append({"station_id": st["id"], "name": st["name"], "distance_km": d,
                            "free_count": len(free), "arrive_soc": round(arrive, 1), "charger_id": free[0]["id"]})
        return sorted(out, key=lambda x: x["distance_km"])[:n]

    def _reset(self, uid, message=None, suggestions=None):
        self.journeys[uid] = {"state": "IDLE", "message": message, "suggestions": suggestions or []}

    def _check_low(self, uid):
        u = self.users[uid]
        if u["soc"] < 20 and uid not in self.low_warned:
            self.low_warned.add(uid)
            self._notify(uid, "low_battery", f"Battery is at {u['soc']:.0f}%. Find a charger soon.")
        elif u["soc"] >= 20:
            self.low_warned.discard(uid)

    def _idle(self, s, now):
        if s.get("idle_exempt") or s.get("stopped_at_sim") is None:
            return 0.0, 0.0
        mins = max(0.0, (now - s["stopped_at_sim"]) / 60 - self.cfg.IDLE_GRACE_MIN)
        return mins, min(self.cfg.IDLE_CAP, round(mins * self.cfg.IDLE_RATE, 2))

    # ================= auth =================
    def _token(self, uid):
        return self.ser.dumps({"uid": uid})

    @locked
    def auth(self, token):
        try:
            uid = self.ser.loads(token, max_age=30 * 86400)["uid"]
        except BadSignature:
            raise ApiError(401, "Your session has expired. Sign in again.")
        if uid not in self.users:
            raise ApiError(401, "Your session has expired. Sign in again.")
        return uid

    @locked
    def signup(self, name, pin, vehicle_model_id, soc, lat=None, lng=None):
        name = name.strip() if isinstance(name, str) else ""
        if not 2 <= len(name) <= 30:
            raise ApiError(400, "Enter a name between 2 and 30 characters.")
        if not (isinstance(pin, str) and re.fullmatch(r"\d{4}", pin)):
            raise ApiError(400, "The PIN must be exactly 4 digits.")
        if vehicle_model_id not in self.vehicles:
            raise ApiError(400, "Pick one of the listed vehicle models.")
        soc = num(soc, 0, 100, "Starting battery")
        lat = CENTRE[0] if lat is None else num(lat, -90, 90, "Latitude")
        lng = CENTRE[1] if lng is None else num(lng, -180, 180, "Longitude")
        if name.lower() in self.by_name:
            raise ApiError(409, "That name is taken. Pick another or sign in.")
        u = {"id": str(uuid.uuid4()), "name": name, "pin_hash": generate_password_hash(pin),
             "vehicle_model_id": vehicle_model_id, "soc": soc, "lat": lat, "lng": lng,
             "wallet_balance": 0.0, "created_at": now_iso()}
        self.users[u["id"]] = u
        self.by_name[name.lower()] = u["id"]
        self._save_user(u)  # row must exist before its transactions (foreign key)
        self._tx(u, "topup", 1000.0)  # welcome balance
        self._save_user(u)
        return self._token(u["id"]), self.me_view(u["id"])

    @locked
    def login(self, name, pin):
        uid = self.by_name.get(name.strip().lower()) if isinstance(name, str) else None
        if not uid or not isinstance(pin, str) or not check_password_hash(self.users[uid]["pin_hash"], pin):
            raise ApiError(401, "Name or PIN is incorrect.")
        return self._token(uid), self.me_view(uid)

    # ================= profile / wallet =================
    @locked
    def me_view(self, uid):
        u = self.users[uid]
        v = self._veh(u)
        inv = self._unpaid(uid)
        return {"id": uid, "name": u["name"], "vehicle": v, "soc": round(u["soc"], 1), "range_km": self._range(u),
                "lat": u["lat"], "lng": u["lng"], "wallet_balance": round(u["wallet_balance"], 2),
                "unpaid_invoice_id": inv["id"] if inv else None}

    @locked
    def update_me(self, uid, data):
        u, j = self.users[uid], self._j(uid)
        if j["state"] not in ("IDLE", "INVOICE"):
            raise ApiError(409, "Finish your current journey before changing your vehicle or battery.")
        if "vehicle_model_id" in data:
            if data["vehicle_model_id"] not in self.vehicles:
                raise ApiError(400, "Pick one of the listed vehicle models.")
            u["vehicle_model_id"] = data["vehicle_model_id"]
        if "soc" in data:
            u["soc"] = num(data["soc"], 0, 100, "Battery")
            self._check_low(uid)
        self._save_user(u)
        return self.me_view(uid)

    def _tx(self, u, kind, amount, invoice_id=None):
        u["wallet_balance"] = round(u["wallet_balance"] + (amount if kind == "topup" else -amount), 2)
        self._tx_id += 1
        row = {"id": self._tx_id, "user_id": u["id"], "kind": kind, "amount": round(amount, 2),
               "balance_after": u["wallet_balance"], "invoice_id": invoice_id, "created_at": now_iso()}
        self.txs.setdefault(u["id"], []).append(row)
        self.repo.insert("wallet_transactions", {k: v for k, v in row.items() if k != "id"})

    @locked
    def topup(self, uid, amount):
        amount = num(amount, 1, 10000, "Amount")
        u = self.users[uid]
        self._tx(u, "topup", amount)
        self._save_user(u)
        return self.wallet_view(uid)

    @locked
    def wallet_view(self, uid):
        u = self.users[uid]
        return {"balance": round(u["wallet_balance"], 2),
                "transactions": list(reversed(self.txs.get(uid, [])))[:50],
                "unpaid_invoices": [self._inv_pub(i) for i in self.invoices.values() if i["user_id"] == uid and i["status"] == "unpaid"]}

    # ================= availability =================
    def _free_in(self, cid, now):
        cs = self.cs[cid]
        s = cs["status"]
        if s == "AVAILABLE":
            return 0
        if s == "CHARGING":
            return None if cs["eta_min"] is None else int(math.ceil(cs["eta_min"]))
        if s in ("FINISHING", "FAULTED", "OFFLINE"):
            fa = cs["free_at_sim"]
            return int(math.ceil(max(0.0, (fa - now) / 60))) if fa else (5 if s == "FINISHING" else None)
        if s == "RESERVED":
            r = next((r for r in self.reservations.values() if r["charger_id"] == cid and r["status"] == "active"), None)
            return int(math.ceil(max(0.0, r["expires_ts"] - self.now_fn()) / 60)) if r else 5
        return 15

    def _ch_pub(self, uid, veh, ch):
        now = self._now()
        cs, (mult, label) = self.cs[ch["id"]], tariff(now)
        ok, why = self._compat(veh, ch)
        return {"id": ch["id"], "station_id": ch["station_id"], "number": ch["number"], "kind": ch["kind"],
                "connector": ch["connector"], "max_kw": ch["max_kw"], "status": cs["status"],
                "power_kw": round(cs["power_kw"], 1), "price_base": ch["price_per_kwh"],
                "price_now": round(ch["price_per_kwh"] * mult, 2), "tariff": label, "multiplier": mult,
                "compatible": ok, "incompatible_reason": why, "free_in_minutes": self._free_in(ch["id"], now),
                "mine": cs["owner"] == uid and cs["status"] in ("RESERVED", "PREPARING", "CHARGING", "FINISHING")}

    def _station_pub(self, u, st, lat, lng):
        veh = self._veh(u)
        d, mins, use, arrive = self._trip({"lat": lat, "lng": lng, "soc": u["soc"]}, veh, st["lat"], st["lng"])
        chs = [self._ch_pub(u["id"], veh, c) for c in self.chargers.values() if c["station_id"] == st["id"]]
        free = [c for c in chs if c["status"] == "AVAILABLE"]
        out = {"id": st["id"], "name": st["name"], "lat": st["lat"], "lng": st["lng"], "power_cap_kw": st["power_cap_kw"],
               "distance_km": d, "eta_min": round(mins), "arrive_soc": round(arrive, 1),
               "reachable": arrive >= self.cfg.MIN_ARRIVAL_SOC, "free_count": len(free),
               "free_compatible": sum(1 for c in free if c["compatible"]), "chargers": chs, "wait_estimate": None}
        if not free:
            pool = [c["free_in_minutes"] for c in chs if c["compatible"] and c["free_in_minutes"] is not None] or \
                   [c["free_in_minutes"] for c in chs if c["free_in_minutes"] is not None]
            out["wait_estimate"] = min(pool) if pool else None
        return out

    @locked
    def stations_view(self, uid, lat=None, lng=None):
        u = self.users[uid]
        lat = u["lat"] if lat is None else num(lat, -90, 90, "Latitude")
        lng = u["lng"] if lng is None else num(lng, -180, 180, "Longitude")
        return {"stations": sorted((self._station_pub(u, s, lat, lng) for s in self.stations.values()),
                                   key=lambda s: s["distance_km"]), "sim_time": self.sim_now, "sim_speed": self.sim_speed}

    @locked
    def station_view(self, uid, sid):
        if sid not in self.stations:
            raise ApiError(404, "That station doesn't exist.")
        u = self.users[uid]
        return self._station_pub(u, self.stations[sid], u["lat"], u["lng"])

    # ================= bus handlers =================
    def _on_status(self, topic, p):
        cid = topic.split("/")[2]
        if cid not in self.cs:
            return
        cs = self.cs[cid]
        if p.get("at_sim"):
            self.sim_now = p["at_sim"]
        cs.update(status=p["status"], reason=p.get("reason"), owner=p.get("owner"), session_id=p.get("session_id"),
                  free_at_sim=p.get("free_at_sim"), eta_min=p.get("eta_min"), energy_kwh=p.get("energy_kwh", 0.0), soc=p.get("soc"))
        if p["status"] != "CHARGING":
            cs.update(power_kw=0.0, demand_kw=0.0, share_kw=0.0)
        if p["status"] in ("FAULTED", "OFFLINE"):
            self._cancel_res_for_charger(cid, p["status"])
        uid = self.conn.get(cid)
        if not uid:
            return
        j = self._j(uid)
        s = self.sessions.get(j.get("session_id"))
        if s and s["status"] == "active" and p.get("session_id") == s["id"]:
            self._bill_to(s, p["energy_kwh"], p["at_sim"])
            if p.get("soc") is not None:
                self.users[uid]["soc"] = p["soc"]
        if p["status"] == "FINISHING" and j["state"] == "CHARGING":
            self._on_stopped(uid, j, s, p)
        elif p["status"] in ("FAULTED", "OFFLINE"):
            self._on_lost(uid, j, s, p, cid)

    def _on_tele(self, topic, p):
        cid = topic.split("/")[2]
        cs = self.cs.get(cid)
        if cs is None:
            return
        self.sim_now = p["at_sim"]
        cs.update(power_kw=p["power_kw"], demand_kw=p["demand_kw"], share_kw=p["share_kw"],
                  energy_kwh=p["energy_kwh"], soc=p["soc"], eta_min=p["eta_min"])
        uid = self.conn.get(cid)
        j = self.journeys.get(uid) if uid else None
        s = self.sessions.get(j.get("session_id")) if j else None
        if not s or j["state"] != "CHARGING" or s["status"] != "active":
            return
        self._bill_to(s, p["energy_kwh"], p["at_sim"])
        self.users[uid]["soc"] = p["soc"]
        cap = s["spending_cap"]
        if cap and s["energy_cost"] * (1 + self.cfg.TAX_PERCENT / 100) >= cap:
            self._cmd(cid, "stop", reason="spending_cap")

    def _on_tick(self, topic, p):
        self.sim_now, self.sim_speed = p["at_sim"], p["speed"]
        self._expire_reservations()
        for uid, j in list(self.journeys.items()):
            if j["state"] == "DRIVING":
                self._drive(uid, j, p["dt"])
        if time.time() - self._last_snap >= self.cfg.SNAPSHOT_SECONDS:
            self.snapshot()

    def _cmd(self, cid, cmd, **kw):
        self.bus.publish(f"ev/{self.chargers[cid]['station_id']}/{cid}/cmd", {"cmd": cmd, **kw})

    # ================= billing =================
    def _bill_to(self, s, total_kwh, at_sim):
        delta = total_kwh - s["last_energy"]
        if delta <= 0:
            return
        mult, _ = tariff(at_sim)
        price = self.chargers[s["charger_id"]]["price_per_kwh"]
        key = round(mult, 2)
        s["segments"][key] = s["segments"].get(key, 0.0) + delta
        s["energy_cost"] += delta * price * mult
        s["energy_kwh"], s["last_energy"] = total_kwh, total_kwh

    def _on_stopped(self, uid, j, s, p):
        s["stopped_at_sim"], s["end_reason"], s["end_soc"] = p["at_sim"], p["reason"], p["soc"]
        j["state"] = "STOPPED"
        if p["reason"] != "unplugged":
            text = {"spending_cap": "Spending cap reached. Charging stopped.", "user_stop": "Charging stopped."}.get(
                p["reason"], "Charging complete.")
            self._notify(uid, "session_complete", text + " Unplug your cable when you're ready.")

    def _on_lost(self, uid, j, s, p, cid):
        ch = self.chargers[cid]
        st = self.stations[ch["station_id"]]
        reason = "fault" if p["status"] == "FAULTED" else "station_offline"
        what = f"Charger {ch['number']} at {st['name']} " + ("reported a fault." if reason == "fault" else "went offline.")
        alts = self._alternatives(self.users[uid], st["lat"], st["lng"], exclude=st["id"])
        if s:
            s["end_reason"], s["idle_exempt"] = reason, True
            if p.get("soc") is not None:
                s["end_soc"] = p["soc"]
            note = what + " Charging stopped and your cable was released. You're only billed for the energy delivered."
        else:
            note = what + " Your cable was released."
        self._notify(uid, "fault", what)
        self._finish(uid, aborted=True, note=note, alts=alts)

    def _cancel_res_for_charger(self, cid, status):
        for r in list(self.reservations.values()):
            if r["charger_id"] == cid and r["status"] == "active":
                r["status"] = "cancelled"
                self.repo.upsert("reservations", self._res_row(r))
                uid = r["user_id"]
                ch = self.chargers[cid]
                msg = f"Charger {ch['number']} at {self.stations[ch['station_id']]['name']} went out of service, so your reservation was cancelled."
                self._notify(uid, "fault", msg)
                if self._j(uid)["state"] == "RESERVED":
                    st = self.stations[ch["station_id"]]
                    self._reset(uid, msg, self._alternatives(self.users[uid], self.users[uid]["lat"], self.users[uid]["lng"], exclude=st["id"]))

    # ================= reservations =================
    def _expire_reservations(self):
        now = self.now_fn()
        for r in list(self.reservations.values()):
            if r["status"] != "active":
                continue
            left = r["expires_ts"] - now
            uid = r["user_id"]
            if left <= 0:
                r["status"] = "expired"
                self.repo.upsert("reservations", self._res_row(r))
                cs = self.cs[r["charger_id"]]
                if cs["status"] == "RESERVED" and cs["owner"] == uid:
                    self._cmd(r["charger_id"], "cancel_reserve")
                msg = "Your reservation expired and the charger was released."
                self._notify(uid, "reservation_expired", msg)
                if self._j(uid)["state"] == "RESERVED":
                    self._reset(uid, msg)
            elif left < 60 and not r.get("warned"):
                r["warned"] = True
                self._notify(uid, "reservation_expiring", "Your reservation expires in under a minute.")

    @locked
    def reserve(self, uid, charger_id):
        self._expire_reservations()
        u, j = self.users[uid], self._j(uid)
        if j["state"] != "IDLE":
            raise ApiError(409, "Finish your current journey before reserving a charger.")
        self._need_paid(uid)
        ch = self._ch(charger_id)
        ok, why = self._compat(self._veh(u), ch)
        if not ok:
            raise ApiError(409, why)
        cs = self.cs[charger_id]
        if cs["status"] != "AVAILABLE":
            raise ApiError(409, f"That charger is {FRIENDLY[cs['status']]}. Pick another one.")
        self._cmd(charger_id, "reserve", owner=uid)
        if self.cs[charger_id]["status"] != "RESERVED" or self.cs[charger_id]["owner"] != uid:
            raise ApiError(409, "Someone else got that charger first. Pick another one.")
        r = {"id": str(uuid.uuid4()), "user_id": uid, "charger_id": charger_id, "status": "active", "created_at": now_iso(),
             "expires_at": (dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=self.cfg.RESERVATION_HOLD_SECONDS)).isoformat(),
             "expires_ts": self.now_fn() + self.cfg.RESERVATION_HOLD_SECONDS}
        self.reservations[r["id"]] = r
        self.repo.upsert("reservations", self._res_row(r))
        self.journeys[uid] = {"state": "RESERVED", "charger_id": charger_id, "reservation_id": r["id"]}
        return self.journey_view(uid)

    @locked
    def cancel_reservation(self, uid, rid):
        r = self.reservations.get(rid)
        if not r or r["user_id"] != uid:
            raise ApiError(404, "Reservation not found.")
        if r["status"] != "active":
            raise ApiError(409, "That reservation has already ended.")
        r["status"] = "cancelled"
        self.repo.upsert("reservations", self._res_row(r))
        if self.cs[r["charger_id"]]["status"] == "RESERVED":
            self._cmd(r["charger_id"], "cancel_reserve")
        if self._j(uid)["state"] == "RESERVED":
            self._reset(uid, "Reservation cancelled.")
        return self.journey_view(uid)

    # ================= journey =================
    @locked
    def go(self, uid, charger_id):
        self._expire_reservations()
        u, j = self.users[uid], self._j(uid)
        if j["state"] not in ("IDLE", "RESERVED"):
            raise ApiError(409, "Finish your current journey first.")
        self._need_paid(uid)
        ch = self._ch(charger_id)
        veh = self._veh(u)
        ok, why = self._compat(veh, ch)
        if not ok:
            raise ApiError(409, why)
        res, cs = self._active_res(uid), self.cs[charger_id]
        if res and res["charger_id"] != charger_id:
            raise ApiError(409, "You have a reservation on another charger. Go there or cancel it first.")
        if not res and cs["status"] != "AVAILABLE":
            raise ApiError(409, f"That charger is {FRIENDLY[cs['status']]}. Pick another one.")
        st = self.stations[ch["station_id"]]
        d, mins, use, arrive = self._trip(u, veh, st["lat"], st["lng"])
        if arrive < self.cfg.MIN_ARRIVAL_SOC:
            raise ApiError(409, f"You'd arrive with {max(arrive, 0):.1f}% battery, which is too low. Try a closer charger.",
                           suggestions=self._alternatives(u, u["lat"], u["lng"], max_km=d))
        self.journeys[uid] = {"state": "DRIVING", "charger_id": charger_id, "reservation_id": res["id"] if res else None,
                              "drive": {"elapsed": 0.0, "duration_s": max(1.0, d / self.cfg.AVG_KMH * 3600),  # >= 1 s: 0 km (already at the station) must not divide by zero
                                        "dist_km": d, "use_pct": use,
                                        "start_soc": u["soc"], "from": (u["lat"], u["lng"]), "to": (st["lat"], st["lng"])}}
        return self.journey_view(uid)

    def _drive(self, uid, j, dt_s):
        u, d = self.users[uid], j["drive"]
        d["elapsed"] += dt_s
        f = min(1.0, d["elapsed"] / d["duration_s"])
        u["soc"] = d["start_soc"] - d["use_pct"] * f
        u["lat"] = d["from"][0] + (d["to"][0] - d["from"][0]) * f
        u["lng"] = d["from"][1] + (d["to"][1] - d["from"][1]) * f
        self._check_low(uid)
        if f >= 1.0:
            self._arrive(uid, j)

    def _arrive(self, uid, j):
        u, cid = self.users[uid], j["charger_id"]
        ch = self.chargers[cid]
        st = self.stations[ch["station_id"]]
        u["lat"], u["lng"] = st["lat"], st["lng"]
        self._save_user(u)
        cs = self.cs[cid]
        if cs["status"] == "AVAILABLE" or (cs["status"] == "RESERVED" and cs["owner"] == uid):
            j["state"] = "ARRIVED"
            return
        msg = (f"Charger {ch['number']} at {st['name']} is no longer free: it's {FRIENDLY[cs['status']]}. "
               f"You're at the station. Here are other chargers nearby.")
        self._notify(uid, "charger_taken", msg)
        self._reset(uid, msg, self._alternatives(u, u["lat"], u["lng"]))

    @locked
    def plug_in(self, uid):
        self._expire_reservations()
        u, j = self.users[uid], self._j(uid)
        if j["state"] != "ARRIVED":
            raise ApiError(409, "You need to arrive at a charger before plugging in.")
        cid = j["charger_id"]
        ch, veh, cs = self.chargers[cid], self._veh(u), self.cs[cid]
        st = self.stations[ch["station_id"]]
        ok, why = self._compat(veh, ch)
        if not ok:
            raise ApiError(409, why)
        if cs["status"] != "AVAILABLE" and not (cs["status"] == "RESERVED" and cs["owner"] == uid):
            msg = f"Charger {ch['number']} is {FRIENDLY[cs['status']]} now. Here are other chargers nearby."
            self._reset(uid, msg, self._alternatives(u, u["lat"], u["lng"], exclude=None))
            raise ApiError(409, msg)
        inv = self._unpaid(uid)
        if inv:
            raise ApiError(402, f"You have an unpaid invoice of ₹{inv['total']:,.2f}. Pay it to start charging.", action="pay", invoice_id=inv["id"])
        if u["wallet_balance"] < self.cfg.MIN_WALLET_TO_START:
            raise ApiError(402, f"Your wallet needs at least ₹{self.cfg.MIN_WALLET_TO_START:,.0f} to start charging. Add money first.", action="topup")
        self._cmd(cid, "connect", owner=uid, soc=u["soc"],
                  vehicle={k: veh[k] for k in ("battery_kwh", "max_ac_kw", "max_dc_kw")})
        if self.cs[cid]["status"] != "PREPARING" or self.cs[cid]["owner"] != uid:
            raise ApiError(409, "The charger didn't accept the connection. Try again or pick another charger.")
        self.conn[cid] = uid
        res = self._active_res(uid)
        if res:
            res["status"] = "used"
            self.repo.upsert("reservations", self._res_row(res))
        j.update(state="PLUGGED_IN", hs_start=self.now_fn(), message=None)
        return self.journey_view(uid)

    def _hs_ready(self, j):
        return self.now_fn() - j.get("hs_start", 0) >= self.cfg.HANDSHAKE_SECONDS

    @locked
    def start(self, uid, target=80, cap=None):
        u, j = self.users[uid], self._j(uid)
        if j["state"] != "PLUGGED_IN":
            raise ApiError(409, "Plug in the vehicle first.")
        if not self._hs_ready(j):
            raise ApiError(409, "The charger is still recognising your vehicle. Wait a moment.")
        if u["soc"] > 95:
            raise ApiError(409, "Your battery is already almost full. Unplug when you're ready.")
        target = num(target, 0, 100, "Target")
        if not (u["soc"] + 5 - 1e-9 <= target <= 100):
            raise ApiError(400, f"Pick a target between {math.ceil(u['soc'] + 5)}% and 100%.")
        if cap is not None:
            cap = num(cap, 1, 100000, "Spending cap")
        cid, veh = j["charger_id"], self._veh(u)
        s = {"id": str(uuid.uuid4()), "user_id": uid, "charger_id": cid, "station_id": self.chargers[cid]["station_id"],
             "vehicle_model_id": u["vehicle_model_id"], "start_soc": u["soc"], "end_soc": None, "target_soc": target,
             "spending_cap": cap, "energy_kwh": 0.0, "energy_cost": 0.0, "idle_minutes": 0.0, "idle_fee": 0.0,
             "status": "active", "end_reason": None, "sim_started": sim_iso(self._now()), "sim_ended": None,
             "started_at": now_iso(), "ended_at": None, "last_energy": 0.0, "segments": {}, "stopped_at_sim": None,
             "idle_exempt": False, "started_sim_ts": self._now()}
        self.sessions[s["id"]] = s
        j["session_id"] = s["id"]
        self._cmd(cid, "start", session_id=s["id"], target=target)
        if self.cs[cid]["status"] != "CHARGING":
            del self.sessions[s["id"]]
            j.pop("session_id")
            raise ApiError(409, "The charger couldn't start. Try again or pick another charger.")
        j["state"] = "CHARGING"
        self.repo.upsert("charging_sessions", self._srow(s))
        return self.journey_view(uid)

    @locked
    def stop(self, uid):
        j = self._j(uid)
        if j["state"] != "CHARGING":
            raise ApiError(409, "You're not charging right now.")
        self._cmd(j["charger_id"], "stop", reason="user_stop")
        return self.journey_view(uid)

    @locked
    def unplug(self, uid):
        j = self._j(uid)
        if j["state"] not in ("PLUGGED_IN", "CHARGING", "STOPPED"):
            raise ApiError(409, "There's no cable to unplug.")
        self._finish(uid)
        return self.journey_view(uid)

    @locked
    def dismiss(self, uid):
        j = self._j(uid)
        if j["state"] != "INVOICE":
            raise ApiError(409, "There's no invoice to dismiss.")
        self._reset(uid)
        return self.journey_view(uid)

    def _finish(self, uid, aborted=False, note=None, alts=None):
        u, j = self.users[uid], self._j(uid)
        cid = j["charger_id"]
        cs = self.cs[cid]
        if cs["status"] == "CHARGING":
            self._cmd(cid, "stop", reason="unplugged")  # status handler moves the journey to STOPPED
        if self.conn.get(cid) == uid and self.cs[cid]["status"] in ("PREPARING", "CHARGING", "FINISHING"):
            self._cmd(cid, "disconnect")
        self.conn.pop(cid, None)
        s = self.sessions.get(j.get("session_id"))
        if not s:
            return self._reset(uid, note or "Unplugged. Nothing was charged, so there's nothing to pay.", alts)
        idle_min, idle_fee = (0.0, 0.0) if aborted else self._idle(s, self._now())
        s.update(status="aborted" if aborted else "completed", end_reason=s["end_reason"] or "unplugged",
                 idle_minutes=round(idle_min, 2), idle_fee=idle_fee, sim_ended=sim_iso(self._now()), ended_at=now_iso())
        if s["end_soc"] is None:
            s["end_soc"] = u["soc"]
        u["soc"] = s["end_soc"]
        lines, amt = [], 0.0
        price = self.chargers[cid]["price_per_kwh"]
        for mult, kwh in sorted(s["segments"].items()):
            a = round(kwh * price * mult, 2)
            amt += a
            label = {1.3: "Peak", 0.85: "Off-peak"}.get(mult, "Standard")
            lines.append({"label": f"Energy ({label} rate)", "kwh": round(kwh, 3), "rate": round(price * mult, 2), "amount": a})
        s["energy_kwh"], s["energy_cost"] = round(s["energy_kwh"], 3), round(amt, 2)
        self.repo.upsert("charging_sessions", self._srow(s))
        inv = self._invoice(u, s, lines, s["energy_kwh"], round(amt, 2))
        self._check_low(uid)
        self.journeys[uid] = {"state": "INVOICE", "invoice_id": inv["id"], "message": note, "suggestions": alts or [],
                              "charger_id": cid, "session_id": s["id"]}

    def _invoice(self, u, s, lines, kwh, energy_amount):
        self._inv_seq += 1
        tax = round((energy_amount + s["idle_fee"]) * self.cfg.TAX_PERCENT / 100, 2)
        inv = {"id": str(uuid.uuid4()), "number": f"CG-{self._inv_seq:06d}", "session_id": s["id"], "user_id": u["id"],
               "energy_kwh": round(kwh, 3), "energy_amount": energy_amount, "idle_fee": s["idle_fee"],
               "tax_percent": self.cfg.TAX_PERCENT, "tax_amount": tax, "total": round(energy_amount + s["idle_fee"] + tax, 2),
               "status": "unpaid", "created_at": now_iso(), "paid_at": None, "lines": lines}
        self.invoices[inv["id"]] = inv
        self.repo.upsert("invoices", {k: inv[k] for k in INVOICE_COLS})  # row must exist before the payment (foreign key)
        self._pay(u, inv)
        self.repo.upsert("invoices", {k: inv[k] for k in INVOICE_COLS})
        self._save_user(u)
        return inv

    def _pay(self, u, inv):
        if inv["status"] == "paid":
            return True
        if u["wallet_balance"] + 1e-9 < inv["total"]:
            return False
        if inv["total"] > 0:
            self._tx(u, "payment", inv["total"], inv["id"])
        inv.update(status="paid", paid_at=now_iso())
        self._notify(u["id"], "payment_done", f"Paid ₹{inv['total']:,.2f} from your wallet.")
        return True

    @locked
    def pay_invoice(self, uid, iid):
        inv = self.invoices.get(iid)
        if not inv or inv["user_id"] != uid:
            raise ApiError(404, "Invoice not found.")
        u = self.users[uid]
        if inv["status"] == "paid":
            raise ApiError(409, "That invoice is already paid.")
        if not self._pay(u, inv):
            raise ApiError(402, f"Your wallet has ₹{u['wallet_balance']:,.2f} but the invoice is ₹{inv['total']:,.2f}. Add money, then pay.", action="topup")
        self.repo.upsert("invoices", {k: inv[k] for k in INVOICE_COLS})
        self._save_user(u)
        return self._inv_pub(inv)

    @locked
    def trip(self, uid, km):
        u, j = self.users[uid], self._j(uid)
        km = num(km, 1, 1000, "Distance")
        if j["state"] not in ("IDLE", "INVOICE"):
            raise ApiError(409, "Finish your current journey before taking a trip.")
        self._need_paid(uid)
        v = self._veh(u)
        use = km * v["wh_per_km"] / (v["battery_kwh"] * 1000) * 100
        if u["soc"] - use < self.cfg.MIN_ARRIVAL_SOC:
            raise ApiError(409, f"A {km:g} km round trip needs {use:.1f}% battery and you have {u['soc']:.1f}%. Charge first or pick a shorter trip.")
        u["soc"] -= use
        self._check_low(uid)
        self._save_user(u)
        return {"used_pct": round(use, 1), "me": self.me_view(uid)}

    @locked
    def break_charger(self, uid):
        j = self._j(uid)
        if j["state"] not in ("RESERVED", "ARRIVED", "PLUGGED_IN", "CHARGING", "STOPPED"):
            raise ApiError(409, "You're not at a charger, so there's nothing to break.")
        self._cmd(j["charger_id"], "fault", minutes=40)
        return self.journey_view(uid)

    # ================= views =================
    def _inv_pub(self, inv):
        s = self.sessions.get(inv["session_id"], {})
        ch = self.chargers.get(s.get("charger_id"), {})
        st = self.stations.get(s.get("station_id"), {})
        return {**inv, "station": st.get("name"), "charger_number": ch.get("number"),
                "vehicle": self.vehicles.get(s.get("vehicle_model_id"), {}).get("label"),
                "sim_started": s.get("sim_started"), "sim_ended": s.get("sim_ended"), "end_reason": s.get("end_reason"),
                "idle_minutes": s.get("idle_minutes"), "session_status": s.get("status")}

    @locked
    def invoice_view(self, uid, iid):
        inv = self.invoices.get(iid)
        if not inv or inv["user_id"] != uid:
            raise ApiError(404, "Invoice not found.")
        return self._inv_pub(inv)

    @locked
    def sessions_view(self, uid):
        by_s = {i["session_id"]: i for i in self.invoices.values() if i["user_id"] == uid}
        rows = sorted((s for s in self.sessions.values() if s["user_id"] == uid and s["status"] != "active"),
                      key=lambda s: s["started_at"], reverse=True)
        items, daily = [], {}
        for s in rows:
            inv = by_s.get(s["id"])
            ch = self.chargers[s["charger_id"]]
            items.append({"id": s["id"], "station": self.stations[s["station_id"]]["name"], "charger_number": ch["number"],
                          "started_at": s["started_at"], "sim_started": s["sim_started"], "sim_ended": s["sim_ended"],
                          "energy_kwh": s["energy_kwh"], "status": s["status"], "end_reason": s["end_reason"],
                          "total": inv["total"] if inv else 0, "invoice_id": inv["id"] if inv else None,
                          "invoice_status": inv["status"] if inv else None})
            d = daily.setdefault(s["started_at"][:10], {"date": s["started_at"][:10], "kwh": 0.0, "spend": 0.0})
            d["kwh"] += s["energy_kwh"] or 0
            d["spend"] += inv["total"] if inv else 0
        return {"sessions": items,
                "summary": {"total_kwh": round(sum(i["energy_kwh"] or 0 for i in items), 3),
                            "total_spend": round(sum(i["total"] for i in items), 2), "sessions": len(items)},
                "daily": [{**d, "kwh": round(d["kwh"], 3), "spend": round(d["spend"], 2)} for d in sorted(daily.values(), key=lambda d: d["date"])]}

    def _allowed(self, uid):
        j = self._j(uid)
        st = j["state"]
        if st == "IDLE":
            return [] if self._unpaid(uid) else ["reserve", "go", "trip"]
        if st == "RESERVED":
            return ["go", "cancel"]
        if st == "ARRIVED":
            return ["plug_in"]
        if st == "PLUGGED_IN":
            return ["start", "unplug"] if self._hs_ready(j) else ["unplug"]
        if st == "CHARGING":
            return ["stop", "unplug"]
        if st == "STOPPED":
            return ["unplug"]
        if st == "INVOICE":
            return ["dismiss"] + (["pay"] if self._unpaid(uid) else [])
        return []

    @locked
    def journey_view(self, uid, after=0):
        self._expire_reservations()
        u, j = self.users[uid], self._j(uid)
        st, now = j["state"], self._now()
        mult, label = tariff(now)
        out = {"state": st, "allowed_actions": self._allowed(uid), "soc": round(u["soc"], 1), "range_km": self._range(u),
               "message": j.get("message"), "suggestions": j.get("suggestions", []), "sim_time": now,
               "sim_speed": self.sim_speed, "lat": u["lat"], "lng": u["lng"],
               "tariff": {"label": label, "multiplier": mult},
               "unpaid_invoice_id": (self._unpaid(uid) or {}).get("id"),
               "notices": [n for n in self.notices.get(uid, []) if n["id"] > after]}
        cid = j.get("charger_id")
        if cid and st != "IDLE":
            ch = self.chargers[cid]
            out["charger"] = self._ch_pub(uid, self._veh(u), ch)
            out["station"] = {"id": ch["station_id"], "name": self.stations[ch["station_id"]]["name"]}
        if st in ("RESERVED", "DRIVING", "ARRIVED") and self._active_res(uid):
            r = self._active_res(uid)
            out["reservation"] = {"id": r["id"], "expires_in_s": max(0, round(r["expires_ts"] - self.now_fn()))}
        if st == "DRIVING":
            d = j["drive"]
            f = min(1.0, d["elapsed"] / d["duration_s"])
            out["drive"] = {"progress": round(f, 3), "dist_km": d["dist_km"], "eta_min": round((1 - f) * d["duration_s"] / 60, 1),
                            "arrival_soc": round(d["start_soc"] - d["use_pct"], 1)}
        if st in ("ARRIVED", "PLUGGED_IN"):
            el = self.now_fn() - j.get("hs_start", self.now_fn())
            T = self.cfg.HANDSHAKE_SECONDS
            labels = ["Cable connected", "Vehicle recognised", "Payment ready"]
            started = st == "PLUGGED_IN"
            out["handshake"] = {"ready": started and self._hs_ready(j), "steps": [
                {"label": l, "done": started and (T <= 0 or el >= T * (i + 1) / 3)} for i, l in enumerate(labels)]}
        if st == "PLUGGED_IN":
            v, ch = self._veh(u), self.chargers[cid]
            out["plugged"] = {"max_power_kw": min(ch["max_kw"], v["max_ac_kw"] if ch["kind"] == "AC" else v["max_dc_kw"]),
                              "battery_kwh": v["battery_kwh"], "price_now": round(ch["price_per_kwh"] * mult, 2),
                              "min_target": math.ceil(u["soc"] + 5), "tax_percent": self.cfg.TAX_PERCENT}
        s = self.sessions.get(j.get("session_id"))
        if st in ("CHARGING", "STOPPED") and s:
            cs = self.cs[cid]
            others = sum(1 for c in self.chargers.values() if c["station_id"] == self.chargers[cid]["station_id"]
                         and c["id"] != cid and self.cs[c["id"]]["status"] == "CHARGING")
            note = f"You're getting {cs['power_kw']:.0f} kW."
            if st == "CHARGING" and others and cs["share_kw"] < cs["demand_kw"] - 0.01:
                note += f" The station limit is shared with {others} other car{'s' if others > 1 else ''}."
            tax = 1 + self.cfg.TAX_PERCENT / 100
            out["charging"] = {"power_kw": round(cs["power_kw"], 1), "energy_kwh": round(s["energy_kwh"], 3), "soc": round(u["soc"], 1),
                               "target_soc": s["target_soc"], "elapsed_min": round((now - s["started_sim_ts"]) / 60, 1),
                               "time_left_min": None if cs["eta_min"] is None or st != "CHARGING" else round(cs["eta_min"], 1),
                               "running_cost": round(s["energy_cost"] * tax, 2), "spending_cap": s["spending_cap"],
                               "rate": round(self.chargers[cid]["price_per_kwh"] * mult, 2), "tariff": label,
                               "sharing_note": note, "end_reason": s["end_reason"]}
        if st == "STOPPED" and s:
            mins = (now - s["stopped_at_sim"]) / 60
            _, fee = self._idle(s, now)
            out["stopped"] = {"reason": s["end_reason"], "idle_minutes": round(max(0, mins), 1),
                              "grace_left_min": round(max(0.0, self.cfg.IDLE_GRACE_MIN - mins), 1),
                              "idle_fee_now": fee, "idle_fee_cap": self.cfg.IDLE_CAP}
        if st == "INVOICE":
            out["invoice"] = self._inv_pub(self.invoices[j["invoice_id"]])
        return out

    # ================= persistence =================
    @locked
    def snapshot(self):
        """Periodic snapshot of active sessions and of users on the move (never per tick)."""
        self._last_snap = time.time()
        for s in self.sessions.values():
            if s["status"] == "active":
                s["energy_kwh"] = round(s["last_energy"], 5)
                if self.cs[s["charger_id"]]["soc"] is not None:
                    s["end_soc"] = self.cs[s["charger_id"]]["soc"]
                self.repo.upsert("charging_sessions", self._srow(s))
        for uid, j in self.journeys.items():
            if j["state"] in ("DRIVING", "CHARGING", "STOPPED"):
                self._save_user(self.users[uid])
