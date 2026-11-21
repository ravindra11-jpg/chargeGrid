import functools
import logging
from datetime import datetime

from flask import Flask, jsonify, request
from flask_cors import CORS

import seed
from bus import Bus
from cloud import Cloud
from config import Config
from errors import ApiError
from repo import MemoryBackend, Repo, SupabaseBackend
from simulator import Simulator

log = logging.getLogger("chargegrid")


def create_app(start_sim=True, overrides=None, backend=None, sim_seed=None):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    cfg = Config(**(overrides or {}))
    if backend is None:
        if cfg.supabase_configured:
            try:
                backend = SupabaseBackend(cfg.SUPABASE_URL, cfg.SUPABASE_SERVICE_KEY)
                log.info("Supabase connected. Data will persist.")
            except Exception as ex:
                log.error("Supabase connection failed (%s). If you see 'invalid API key', run: pip install -U supabase. "
                          "Running in memory instead.", ex)
        else:
            log.warning("Supabase values are still placeholders: running IN MEMORY. Nothing will persist across restarts.")
        backend = backend or MemoryBackend()
    bus = Bus(cfg.MQTT_HOST, cfg.MQTT_PORT, cfg.MQTT_USERNAME, cfg.MQTT_PASSWORD)
    repo = Repo(backend)
    catalog = seed.ensure_seed(repo)
    sim = Simulator(bus, cfg, catalog, sim_seed)
    cloud = Cloud(bus, repo, cfg, catalog)
    sim.publish_all()

    app = Flask(__name__)
    app.cfg, app.bus, app.sim, app.cloud, app.repo = cfg, bus, sim, cloud, repo
    CORS(app, origins=cfg.CORS_ORIGINS, allow_headers=["Authorization", "Content-Type"],
         methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"])

    def body():
        b = request.get_json(silent=True)
        return b if isinstance(b, dict) else {}

    def authed(fn):
        @functools.wraps(fn)
        def w(*a, **k):
            h = request.headers.get("Authorization", "")
            if not h.startswith("Bearer "):
                raise ApiError(401, "Sign in to continue.")
            return fn(cloud.auth(h[7:].strip()), *a, **k)
        return w

    def fnum(name):
        v = request.args.get(name)
        if v is None:
            return None
        try:
            return float(v)
        except ValueError:
            raise ApiError(400, f"{name} must be a number.")

    @app.errorhandler(ApiError)
    def _api(e):
        return jsonify(e.to_dict()), e.status

    @app.errorhandler(404)
    def _404(e):
        return jsonify(error="That endpoint doesn't exist."), 404

    @app.errorhandler(405)
    def _405(e):
        return jsonify(error="That method isn't allowed here."), 405

    @app.errorhandler(Exception)
    def _500(e):
        log.exception("unhandled error")
        return jsonify(error="Something went wrong on our side. Try again."), 500

    # ---- public ----
    @app.get("/api/health")
    def health():
        return jsonify(ok=True, supabase=bool(repo.backend.is_remote and repo.backend.connected), persistent=repo.persistent,
                       sim_running=sim.running, sim_time=datetime.fromtimestamp(sim.now).isoformat(timespec="seconds"))

    @app.get("/api/vehicles")
    def vehicles():
        return jsonify(vehicles=list(catalog["vehicles"].values()))

    @app.post("/api/auth/signup")
    def signup():
        b = body()
        token, me = cloud.signup(b.get("name"), b.get("pin"), b.get("vehicle_model_id"), b.get("soc", 50), b.get("lat"), b.get("lng"))
        return jsonify(token=token, me=me), 201

    @app.post("/api/auth/login")
    def login():
        b = body()
        token, me = cloud.login(b.get("name"), b.get("pin"))
        return jsonify(token=token, me=me)

    # ---- profile / wallet ----
    @app.get("/api/me")
    @authed
    def me(uid):
        return jsonify(cloud.me_view(uid))

    @app.patch("/api/me")
    @authed
    def patch_me(uid):
        return jsonify(cloud.update_me(uid, {k: v for k, v in body().items() if k in ("vehicle_model_id", "soc")}))

    @app.get("/api/wallet")
    @authed
    def wallet(uid):
        return jsonify(cloud.wallet_view(uid))

    @app.post("/api/wallet/topup")
    @authed
    def topup(uid):
        return jsonify(cloud.topup(uid, body().get("amount")))

    # ---- stations / reservations ----
    @app.get("/api/stations")
    @authed
    def stations(uid):
        return jsonify(cloud.stations_view(uid, fnum("lat"), fnum("lng")))

    @app.get("/api/stations/<sid>")
    @authed
    def station(uid, sid):
        return jsonify(cloud.station_view(uid, sid))

    @app.post("/api/reservations")
    @authed
    def reserve(uid):
        return jsonify(cloud.reserve(uid, body().get("charger_id"))), 201

    @app.delete("/api/reservations/<rid>")
    @authed
    def unreserve(uid, rid):
        return jsonify(cloud.cancel_reservation(uid, rid))

    # ---- journey ----
    @app.get("/api/journey")
    @authed
    def journey(uid):
        try:
            after = int(request.args.get("after", 0))
        except ValueError:
            after = 0
        return jsonify(cloud.journey_view(uid, after))

    @app.post("/api/journey/go")
    @authed
    def go(uid):
        return jsonify(cloud.go(uid, body().get("charger_id")))

    @app.post("/api/journey/plug-in")
    @authed
    def plug_in(uid):
        return jsonify(cloud.plug_in(uid))

    @app.post("/api/journey/start")
    @authed
    def start(uid):
        b = body()
        return jsonify(cloud.start(uid, b.get("target_soc", 80), b.get("spending_cap")))

    @app.post("/api/journey/stop")
    @authed
    def stop(uid):
        return jsonify(cloud.stop(uid))

    @app.post("/api/journey/unplug")
    @authed
    def unplug(uid):
        return jsonify(cloud.unplug(uid))

    @app.post("/api/journey/dismiss")
    @authed
    def dismiss(uid):
        return jsonify(cloud.dismiss(uid))

    @app.post("/api/trips")
    @authed
    def trips(uid):
        return jsonify(cloud.trip(uid, body().get("km")))

    # ---- history / invoices ----
    @app.get("/api/sessions")
    @authed
    def sessions(uid):
        return jsonify(cloud.sessions_view(uid))

    @app.get("/api/invoices/<iid>")
    @authed
    def invoice(uid, iid):
        return jsonify(cloud.invoice_view(uid, iid))

    @app.post("/api/invoices/<iid>/pay")
    @authed
    def pay(uid, iid):
        return jsonify(cloud.pay_invoice(uid, iid))

    # ---- demo tools ----
    def sim_settings():
        return {"speed": sim.speed, "traffic": sim.traffic, "speeds": list(sim.SPEEDS),
                "levels": ["quiet", "normal", "busy"], "sim_time": datetime.fromtimestamp(sim.now).isoformat(timespec="seconds")}

    @app.get("/api/sim/settings")
    @authed
    def get_sim(uid):
        return jsonify(sim_settings())

    @app.post("/api/sim/settings")
    @authed
    def set_sim(uid):
        b = body()
        with bus.lock:
            if "speed" in b:
                if b["speed"] not in sim.SPEEDS or isinstance(b["speed"], bool):
                    raise ApiError(400, f"Speed must be one of {', '.join(str(s) for s in sim.SPEEDS)}.")
                sim.speed = int(b["speed"])
            if "traffic" in b:
                if b["traffic"] not in ("quiet", "normal", "busy"):
                    raise ApiError(400, "Traffic must be quiet, normal or busy.")
                sim.traffic = b["traffic"]
        return jsonify(sim_settings())

    @app.post("/api/sim/break-my-charger")
    @authed
    def break_it(uid):
        return jsonify(cloud.break_charger(uid))

    if start_sim:
        sim.start()
    return app


if __name__ == "__main__":
    application = create_app()
    application.run(host="0.0.0.0", port=application.cfg.PORT, threaded=True, use_reloader=False)
