import collections
import json
import logging
import threading
import time

log = logging.getLogger("chargegrid.bus")


def topic_match(pattern, topic):
    p, t = pattern.split("/"), topic.split("/")
    for i, seg in enumerate(p):
        if seg == "#":
            return True
        if i >= len(t) or (seg != "+" and seg != t[i]):
            return False
    return len(p) == len(t)


class Bus:
    """In-process pub/sub with MQTT-style topics. One RLock guards simulator + cloud."""

    def __init__(self, mqtt_host="", mqtt_port=1883, username="", password=""):
        self.lock = threading.RLock()
        self.strict = False  # tests: re-raise handler errors
        self.log = collections.deque(maxlen=300)
        self._subs = []
        self._mqtt = None
        if mqtt_host:
            try:
                import paho.mqtt.client as mqtt
                try:
                    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
                except AttributeError:
                    c = mqtt.Client()
                if username:
                    c.username_pw_set(username, password)
                c.connect_async(mqtt_host, int(mqtt_port))
                c.loop_start()
                self._mqtt = c
            except Exception as ex:  # never crash the app
                log.warning("MQTT mirror disabled: %s", ex)

    def subscribe(self, pattern, fn):
        self._subs.append((pattern, fn))

    def publish(self, topic, payload):
        with self.lock:
            self.log.append({"t": time.time(), "topic": topic, "payload": payload})
            if self._mqtt:
                try:
                    self._mqtt.publish("chargegrid/" + topic, json.dumps(payload, default=str))
                except Exception as ex:
                    log.debug("MQTT publish failed: %s", ex)
            for pat, fn in list(self._subs):
                if topic_match(pat, topic):
                    try:
                        fn(topic, payload)
                    except Exception:
                        if self.strict:
                            raise
                        log.exception("handler failed for %s", topic)

    def recent(self, n=50):
        return list(self.log)[-n:]
