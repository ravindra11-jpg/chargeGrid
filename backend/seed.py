CENTRE = (13.0827, 80.2707)  # Chennai Central

VEHICLES = [
    dict(id="hatchback", label="Compact hatchback", battery_kwh=24, max_ac_kw=7.2, max_dc_kw=25,
         ac_connector="Type 2", dc_connector="CCS2", wh_per_km=110),
    dict(id="compact_suv", label="Compact SUV", battery_kwh=40, max_ac_kw=7.2, max_dc_kw=50,
         ac_connector="Type 2", dc_connector="CCS2", wh_per_km=150),
    dict(id="midsize_suv", label="Midsize SUV", battery_kwh=50, max_ac_kw=11, max_dc_kw=75,
         ac_connector="Type 2", dc_connector="CCS2", wh_per_km=165),
    dict(id="premium_suv", label="Premium SUV", battery_kwh=60, max_ac_kw=11, max_dc_kw=90,
         ac_connector="Type 2", dc_connector="CCS2", wh_per_km=180),
    dict(id="sedan_chademo", label="Older sedan (CHAdeMO)", battery_kwh=30, max_ac_kw=6.6, max_dc_kw=40,
         ac_connector="Type 2", dc_connector="CHAdeMO", wh_per_km=140),
]

# code -> (kind, connector, kW)
CH = {"A": ("AC", "Type 2", 7.4), "C30": ("DC", "CCS2", 30), "C60": ("DC", "CCS2", 60), "H50": ("DC", "CHAdeMO", 50)}

# id, name, lat, lng, power cap kW, chargers
STATIONS = [
    ("tnagar", "T. Nagar Charge Hub", 13.0418, 80.2341, 70, ["A", "A", "C60"]),
    ("adyar", "Adyar Riverside Charging", 13.0012, 80.2565, 80, ["A", "C30", "C60", "H50"]),
    ("annanagar", "Anna Nagar Tower Chargers", 13.0850, 80.2101, 40, ["A", "A", "C30"]),
    ("velachery", "Velachery Phoenix Plaza", 12.9815, 80.2180, 90, ["C60", "C60", "A"]),
    ("guindy", "Guindy Industrial Estate EV", 13.0067, 80.2206, 80, ["C30", "C30", "H50"]),
    ("mylapore", "Mylapore Tank Street Charge", 13.0368, 80.2676, 40, ["A", "A", "A", "C30"]),
    ("omr", "OMR Tech Park Chargers", 12.9010, 80.2279, 100, ["C60", "C30", "H50", "A"]),
    ("porur", "Porur Junction Chargers", 13.0382, 80.1565, 55, ["A", "A", "C60"]),
    ("tambaram", "Tambaram Station Road EV", 12.9249, 80.1000, 30, ["C30", "A"]),
]

_NUM = {
    "vehicle_models": ("battery_kwh", "max_ac_kw", "max_dc_kw", "wh_per_km"),
    "stations": ("lat", "lng", "power_cap_kw"),
    "chargers": ("max_kw", "price_per_kwh"),
}


def _norm(table, rows):
    for r in rows:
        for k in _NUM[table]:
            r[k] = float(r[k])
    return rows


def ensure_seed(repo):
    """Write seed data on first start; afterwards read the catalog back from the database."""
    if not repo.load("vehicle_models"):
        for v in VEHICLES:
            repo.upsert("vehicle_models", dict(v))
    if not repo.load("stations"):
        for sid, name, lat, lng, cap, chs in STATIONS:
            repo.upsert("stations", dict(id=sid, name=name, lat=lat, lng=lng, power_cap_kw=cap))
        for sid, *_rest, chs in STATIONS:
            for n, code in enumerate(chs, 1):
                kind, conn, kw = CH[code]
                repo.upsert("chargers", dict(id=f"{sid}-{n}", station_id=sid, number=n, kind=kind,
                                             connector=conn, max_kw=kw, price_per_kwh=12 if kind == "AC" else 16))
    repo.flush()
    chargers = sorted(repo.load("chargers"), key=lambda c: (c["station_id"], c["number"]))
    return {
        "vehicles": {r["id"]: r for r in _norm("vehicle_models", repo.load("vehicle_models"))},
        "stations": {r["id"]: r for r in _norm("stations", repo.load("stations"))},
        "chargers": {r["id"]: r for r in _norm("chargers", chargers)},
    }
