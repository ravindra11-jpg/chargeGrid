import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    def __init__(self, **overrides):
        e = os.environ.get
        self.SUPABASE_URL = e("SUPABASE_URL", "")
        self.SUPABASE_SERVICE_KEY = e("SUPABASE_SERVICE_KEY", "")
        self.APP_SECRET_KEY = e("APP_SECRET_KEY", "dev-secret-change-me")
        self.PORT = int(e("PORT", "5000"))
        self.CORS_ORIGINS = [o.strip() for o in e("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()]
        self.RESERVATION_HOLD_SECONDS = float(e("RESERVATION_HOLD_SECONDS", "300"))
        self.TAX_PERCENT = float(e("TAX_PERCENT", "18"))
        self.MIN_WALLET_TO_START = float(e("MIN_WALLET_TO_START", "100"))
        self.DEFAULT_SIM_SPEED = int(e("DEFAULT_SIM_SPEED", "20"))
        self.MQTT_HOST = e("MQTT_HOST", "")
        self.MQTT_PORT = int(e("MQTT_PORT", "1883") or 1883)
        self.MQTT_USERNAME = e("MQTT_USERNAME", "")
        self.MQTT_PASSWORD = e("MQTT_PASSWORD", "")
        # fixed model constants
        self.HANDSHAKE_SECONDS = 2.5
        self.IDLE_GRACE_MIN = 5
        self.IDLE_RATE = 2.0
        self.IDLE_CAP = 200.0
        self.ROAD_FACTOR = 1.3
        self.AVG_KMH = 30.0
        self.MIN_ARRIVAL_SOC = 2.0
        self.SNAPSHOT_SECONDS = 10
        for k, v in overrides.items():
            setattr(self, k, v)

    @property
    def supabase_configured(self):
        u, k = self.SUPABASE_URL, self.SUPABASE_SERVICE_KEY
        return bool(u and k) and "YOUR-" not in u and not k.startswith("YOUR-")
