"""Drives the Flask test client and ticks the simulator by hand. Run: pytest -q"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app  # noqa: E402
from repo import MemoryBackend  # noqa: E402

NEAR_ADYAR = (13.0112, 80.2565)  # ~1 km from Adyar station


def make_app(backend=None, **over):
    o = dict(HANDSHAKE_SECONDS=0, SUPABASE_URL="", SUPABASE_SERVICE_KEY="", APP_SECRET_KEY="test-secret")
    o.update(over)
    app = create_app(start_sim=False, overrides=o, backend=backend or MemoryBackend(), sim_seed=1)
    app.sim.traffic, app.sim.random_faults, app.bus.strict = "off", False, True
    return app


@pytest.fixture
def app():
    return make_app()


def advance(app, seconds, step=30):
    for _ in range(int(seconds / step)):
        app.sim.step(step)


class User:
    def __init__(self, app, name, vehicle="compact_suv", soc=25, loc=NEAR_ADYAR, pin="1234"):
        self.app, self.c = app, app.test_client()
        r = self.c.post("/api/auth/signup", json=dict(name=name, pin=pin, vehicle_model_id=vehicle, soc=soc, lat=loc[0], lng=loc[1]))
        assert r.status_code == 201, r.json
        self.id, self.h = r.json["me"]["id"], {"Authorization": "Bearer " + r.json["token"]}

    def get(self, path):
        return self.c.get(path, headers=self.h)

    def post(self, path, **body):
        return self.c.post(path, json=body, headers=self.h)

    def journey(self):
        return self.get("/api/journey").json

    def wallet(self):
        return self.get("/api/wallet").json["balance"]

    def until(self, state, max_s=3600):
        for _ in range(int(max_s / 30)):
            j = self.journey()
            if j["state"] == state:
                return j
            self.app.sim.step(30)
        raise AssertionError(f"never reached {state}, stuck at {self.journey()['state']}")

    def drive_and_plug(self, charger):
        assert self.post("/api/journey/go", charger_id=charger).status_code == 200
        self.until("ARRIVED")
        r = self.post("/api/journey/plug-in")
        assert r.status_code == 200, r.json
        assert r.json["state"] == "PLUGGED_IN"


def test_signup_login(app):
    u = User(app, "Asha")
    c = app.test_client()
    assert c.post("/api/auth/signup", json=dict(name="asha", pin="1234", vehicle_model_id="hatchback", soc=50)).status_code == 409
    assert c.post("/api/auth/signup", json=dict(name="Ravi", pin="12", vehicle_model_id="hatchback", soc=50)).status_code == 400
    assert c.post("/api/auth/login", json=dict(name="Asha", pin="0000")).status_code == 401
    r = c.post("/api/auth/login", json=dict(name="ASHA", pin="1234"))
    assert r.status_code == 200 and r.json["me"]["id"] == u.id
    assert c.get("/api/me").status_code == 401
    assert u.get("/api/me").json["wallet_balance"] == 1000
    assert c.get("/api/health").json["ok"] and c.get("/api/vehicles").json["vehicles"]


def test_incompatible_charger_refused(app):
    sedan = User(app, "Old Sedan", vehicle="sedan_chademo")
    r = sedan.post("/api/reservations", charger_id="adyar-3")  # CCS2
    assert r.status_code == 409 and "CCS2" in r.json["error"]
    assert sedan.post("/api/journey/go", charger_id="adyar-3").status_code == 409
    chs = {c["id"]: c for c in sedan.get("/api/stations/adyar").json["chargers"]}
    assert not chs["adyar-3"]["compatible"] and chs["adyar-3"]["incompatible_reason"]
    assert chs["adyar-4"]["compatible"] and chs["adyar-1"]["compatible"]


def test_reservation_blocks_others_and_race(app):
    a, b = User(app, "Aarav"), User(app, "Bela")
    assert a.post("/api/reservations", charger_id="adyar-3").status_code == 201
    r = b.post("/api/reservations", charger_id="adyar-3")
    assert r.status_code == 409
    st = {c["id"]: c for c in b.get("/api/stations/adyar").json["chargers"]}
    assert st["adyar-3"]["status"] == "RESERVED"
    assert a.post("/api/reservations", charger_id="adyar-2").status_code == 409  # one reservation per user
    rid = a.journey()["reservation"]["id"]
    assert a.c.delete(f"/api/reservations/{rid}", headers=a.h).status_code == 200
    assert b.post("/api/reservations", charger_id="adyar-3").status_code == 201


def test_reservation_expiry(app):
    a, b = User(app, "Aarav"), User(app, "Bela")
    a.post("/api/reservations", charger_id="adyar-3")
    app.cloud.reservations[a.journey()["reservation"]["id"]]["expires_ts"] = 0
    app.sim.step(10)
    j = a.journey()
    assert j["state"] == "IDLE" and "expired" in j["message"]
    assert any(n["kind"] == "reservation_expired" for n in j["notices"])
    assert b.post("/api/reservations", charger_id="adyar-3").status_code == 201


def test_charger_taken_during_drive(app):
    a, b = User(app, "Aarav"), User(app, "Bela")
    assert a.post("/api/journey/go", charger_id="adyar-3").status_code == 200
    assert b.post("/api/reservations", charger_id="adyar-3").status_code == 201
    j = a.until("IDLE")
    assert "no longer free" in j["message"] and j["suggestions"]
    assert (a.get("/api/me").json["lat"], a.get("/api/me").json["lng"]) == (13.0012, 80.2565)  # now at the station


def test_low_battery_trip_refusal(app):
    a = User(app, "Aarav", soc=3)
    r = a.post("/api/journey/go", charger_id="tambaram-1")
    assert r.status_code == 409 and "too low" in r.json["error"]
    assert a.post("/api/trips", km=100).status_code == 409
    b = User(app, "Bela", soc=60)
    r = b.post("/api/trips", km=15)
    assert r.status_code == 200 and abs(r.json["used_pct"] - 15 * 150 / 40000 * 100) < 0.1


def test_full_journey_power_sharing_idle_fee_invoice(app):
    a, b = User(app, "Aarav", "compact_suv", 25), User(app, "Bela", "sedan_chademo", 30)
    assert a.post("/api/reservations", charger_id="adyar-3").status_code == 201
    a.drive_and_plug("adyar-3")
    assert a.post("/api/journey/start", target_soc=3).status_code == 400
    j = a.post("/api/journey/start", target_soc=80, spending_cap=None).json
    assert j["state"] == "CHARGING"
    advance(app, 120)
    alone = a.journey()["charging"]
    assert 49 < alone["power_kw"] <= 50 and "shared" not in alone["sharing_note"]
    # Bela joins the same station on the CHAdeMO charger: the 80 kW cap is now shared
    b.drive_and_plug("adyar-4")
    assert b.post("/api/journey/start", target_soc=80).json["state"] == "CHARGING"
    advance(app, 60)
    shared = a.journey()["charging"]
    assert shared["power_kw"] < alone["power_kw"] - 5
    assert "shared with 1 other car" in shared["sharing_note"]
    assert abs(shared["power_kw"] + b.journey()["charging"]["power_kw"] - 80) < 0.5
    # Aarav reaches the target; cable stays connected
    j = a.until("STOPPED")
    assert j["charging"]["soc"] == pytest.approx(80, abs=0.01) and j["stopped"]["idle_fee_now"] == 0
    advance(app, 300)  # grace period (5 sim minutes): still free
    assert a.journey()["stopped"]["idle_fee_now"] == 0
    advance(app, 600)  # 10 billable minutes -> Rs 20
    assert a.journey()["stopped"]["idle_fee_now"] == pytest.approx(20.0, abs=0.01)
    before = a.wallet()
    j = a.post("/api/journey/unplug").json
    assert j["state"] == "INVOICE"
    inv = j["invoice"]
    assert inv["status"] == "paid" and inv["idle_fee"] == pytest.approx(20.0, abs=0.01)
    start = app.cloud.sessions[inv["session_id"]]["start_soc"]  # slightly below 25: the drive used battery
    assert start < 25 and inv["energy_kwh"] == pytest.approx((80 - start) / 100 * 40, abs=0.01)
    assert inv["energy_amount"] == pytest.approx(sum(l["amount"] for l in inv["lines"]), abs=0.001)
    assert inv["energy_amount"] == pytest.approx(inv["energy_kwh"] * 16, abs=0.02)  # 08:00 standard tariff, DC CCS2 Rs 16
    assert inv["tax_amount"] == pytest.approx((inv["energy_amount"] + inv["idle_fee"]) * 0.18, abs=0.01)
    assert inv["total"] == pytest.approx(inv["energy_amount"] + inv["idle_fee"] + inv["tax_amount"], abs=0.01)
    assert a.wallet() == pytest.approx(before - inv["total"], abs=0.01)
    assert app.cloud.cs["adyar-3"]["status"] == "AVAILABLE"
    assert a.get("/api/me").json["soc"] == pytest.approx(80, abs=0.1)
    assert a.post("/api/journey/dismiss").json["state"] == "IDLE"
    s = a.get("/api/sessions").json
    assert s["summary"]["sessions"] == 1 and s["sessions"][0]["invoice_id"] == inv["id"]
    assert a.get(f"/api/invoices/{inv['id']}").json["total"] == inv["total"]
    assert b.get(f"/api/invoices/{inv['id']}").status_code == 404


def test_spending_cap_and_manual_stop(app):
    a = User(app, "Aarav", "compact_suv", 20)
    a.drive_and_plug("adyar-3")
    a.post("/api/journey/start", target_soc=100, spending_cap=100)
    j = a.until("STOPPED")
    assert j["charging"]["end_reason"] == "spending_cap"
    inv = a.post("/api/journey/unplug").json["invoice"]
    assert 100 <= inv["total"] < 110
    b = User(app, "Bela", "compact_suv", 20)
    b.drive_and_plug("adyar-3")
    b.post("/api/journey/start", target_soc=100)
    advance(app, 60)
    assert b.post("/api/journey/stop").json["state"] == "STOPPED"


def test_fault_mid_session_bills_delivered_only(app):
    a = User(app, "Aarav", "compact_suv", 25)
    a.drive_and_plug("adyar-3")
    a.post("/api/journey/start", target_soc=90)
    advance(app, 300)
    delivered = app.cloud.cs["adyar-3"]["energy_kwh"]
    assert delivered > 1
    before = a.wallet()
    j = a.post("/api/sim/break-my-charger").json
    assert j["state"] == "INVOICE" and "fault" in j["message"] and j["suggestions"]
    inv = j["invoice"]
    assert inv["idle_fee"] == 0 and inv["session_status"] == "aborted" and inv["end_reason"] == "fault"
    assert inv["energy_kwh"] == pytest.approx(delivered, abs=0.01)
    assert a.wallet() == pytest.approx(before - inv["total"], abs=0.01)
    assert app.cloud.cs["adyar-3"]["status"] == "FAULTED"
    assert a.post("/api/journey/dismiss").json["state"] == "IDLE"
    advance(app, 3600)  # self-repairs after 40 sim minutes
    assert app.cloud.cs["adyar-3"]["status"] == "AVAILABLE"


def test_low_wallet_blocks_start_then_topup(app):
    a = User(app, "Aarav")
    app.cloud.users[a.id]["wallet_balance"] = 50
    assert a.post("/api/journey/go", charger_id="adyar-3").status_code == 200
    a.until("ARRIVED")
    r = a.post("/api/journey/plug-in")
    assert r.status_code == 402 and r.json["action"] == "topup"
    assert a.post("/api/wallet/topup", amount=500).json["balance"] == 550
    assert a.post("/api/journey/plug-in").json["state"] == "PLUGGED_IN"


def test_unpaid_invoice_blocks_new_journeys(app):
    a = User(app, "Aarav", "compact_suv", 25)
    a.drive_and_plug("adyar-3")
    a.post("/api/journey/start", target_soc=90)
    advance(app, 600)
    app.cloud.users[a.id]["wallet_balance"] = 1.0  # can't cover the bill
    j = a.post("/api/journey/unplug").json
    assert j["invoice"]["status"] == "unpaid" and "pay" in j["allowed_actions"]
    a.post("/api/journey/dismiss")
    r = a.post("/api/reservations", charger_id="adyar-3")
    assert r.status_code == 402 and r.json["action"] == "pay"
    inv_id = r.json["invoice_id"]
    assert a.post(f"/api/invoices/{inv_id}/pay").status_code == 402
    a.post("/api/wallet/topup", amount=1000)
    assert a.post(f"/api/invoices/{inv_id}/pay").json["status"] == "paid"
    assert a.post("/api/reservations", charger_id="adyar-3").status_code == 201


def test_peak_tariff_split_lines(app):
    app.sim.now += 9.9 * 3600  # jump to 17:54
    a = User(app, "Aarav", "compact_suv", 20)
    a.drive_and_plug("adyar-3")
    a.post("/api/journey/start", target_soc=60)
    j = a.until("STOPPED")
    inv = a.post("/api/journey/unplug").json["invoice"]
    labels = [l["label"] for l in inv["lines"]]
    assert len(inv["lines"]) == 2 and "Peak" in labels[1]
    assert inv["lines"][1]["rate"] == pytest.approx(16 * 1.3, abs=0.01)


def test_restart_recovery():
    be = MemoryBackend()
    app1 = make_app(be)
    a = User(app1, "Aarav", "compact_suv", 25)
    a.drive_and_plug("adyar-3")
    a.post("/api/journey/start", target_soc=90)
    advance(app1, 300)
    app1.cloud.snapshot()
    delivered = app1.cloud.sessions[next(iter(app1.cloud.sessions))]["energy_kwh"]
    before = a.wallet()
    app2 = make_app(be)  # "restart": same database, fresh process
    c = app2.test_client()
    r = c.post("/api/auth/login", json=dict(name="Aarav", pin="1234"))
    assert r.status_code == 200
    h = {"Authorization": "Bearer " + r.json["token"]}
    s = c.get("/api/sessions", headers=h).json["sessions"][0]
    assert s["status"] == "aborted" and s["end_reason"] == "server_restart"
    assert s["energy_kwh"] == pytest.approx(delivered, abs=0.01) and delivered > 1
    w = c.get("/api/wallet", headers=h).json
    assert w["balance"] < before and w["balance"] == pytest.approx(before - s["total"], abs=0.01)
    assert c.get("/api/journey", headers=h).json["state"] == "IDLE"
    assert all(v["status"] == "AVAILABLE" for v in app2.cloud.cs.values())
    assert c.get("/api/me", headers=h).json["soc"] > 25


def test_second_session_at_the_station_you_are_already_at(app):
    """Regression: 'go' to a charger at the station you already stand at (0 km) crashed with ZeroDivisionError (HTTP 500)
    and left the journey stuck in DRIVING, so GET /api/journey kept returning 500."""
    u = User(app, "Meera", loc=(13.0012, 80.2565))  # exactly at the Adyar station
    cid = next(c["id"] for c in app.cloud.chargers.values() if c["station_id"] == "adyar" and c["kind"] == "AC")
    r = u.post("/api/journey/go", charger_id=cid)
    assert r.status_code == 200, r.json
    assert u.get("/api/journey").status_code == 200
    u.until("ARRIVED", max_s=120)
