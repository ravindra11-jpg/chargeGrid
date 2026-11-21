import collections
import copy
import logging
import queue
import threading

log = logging.getLogger("chargegrid.repo")


class MemoryBackend:
    is_remote = False
    connected = False

    def __init__(self):
        self.tables = collections.defaultdict(dict)
        self._seq = 0

    def upsert(self, table, row, key="id"):
        self.tables[table][row[key]] = copy.deepcopy(row)

    def insert(self, table, row):
        self._seq += 1
        r = copy.deepcopy(row)
        r.setdefault("id", self._seq)
        self.tables[table][r["id"]] = r

    def select_all(self, table):
        return [copy.deepcopy(r) for r in self.tables[table].values()]


class SupabaseBackend:
    is_remote = True

    def __init__(self, url, key):
        from supabase import create_client
        self.c = create_client(url, key)
        self.c.table("vehicle_models").select("id").limit(1).execute()  # fails fast on bad URL/key/schema
        self.connected = True

    def upsert(self, table, row, key="id"):
        self.c.table(table).upsert(row, on_conflict=key).execute()

    def insert(self, table, row):
        self.c.table(table).insert(row).execute()

    def select_all(self, table):
        out, a = [], 0
        while True:
            rows = self.c.table(table).select("*").range(a, a + 999).execute().data or []
            out += rows
            if len(rows) < 1000:
                return out
            a += 1000


class Repo:
    """Writes go through a background queue (remote) so the simulation never waits on the network."""

    def __init__(self, backend):
        self.backend = backend
        self.q = queue.Queue()
        if backend.is_remote:
            threading.Thread(target=self._worker, daemon=True, name="repo-writer").start()

    @property
    def persistent(self):
        return self.backend.is_remote

    def _worker(self):
        while True:
            op, table, row, key = self.q.get()
            try:
                for attempt in (1, 2):
                    try:
                        (self.backend.upsert(table, row, key) if op == "upsert" else self.backend.insert(table, row))
                        break
                    except Exception as ex:
                        if attempt == 2:
                            log.error("write to %s failed: %s", table, ex)
            finally:
                self.q.task_done()

    def _do(self, op, table, row, key="id"):
        if self.backend.is_remote:
            self.q.put((op, table, copy.deepcopy(row), key))
        else:
            self.backend.upsert(table, row, key) if op == "upsert" else self.backend.insert(table, row)

    def upsert(self, table, row, key="id"):
        self._do("upsert", table, row, key)

    def insert(self, table, row):
        self._do("insert", table, row)

    def load(self, table):
        self.flush()
        return self.backend.select_all(table)

    def flush(self):
        if self.backend.is_remote:
            self.q.join()
