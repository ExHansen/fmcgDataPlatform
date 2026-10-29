"""Provision Metabase dari spec.py (idempotent): setup admin, koneksi warehouse (bi_reader), dashboard.

    python -m dashboards.metabase.provision [--url http://127.0.0.1:3000] [--public-links]

Dashboard di koleksi "FMCG Commercial Platform" diarsipkan lalu dibuat ulang setiap run,
jadi perubahan di spec.py selalu menjadi sumber kebenaran.
"""
from __future__ import annotations

import argparse
import json
import logging
import time
import urllib.error
import urllib.request

from dashboards.metabase.spec import DASHBOARDS
from ingestion.common.settings import env

log = logging.getLogger(__name__)
COLLECTION = "FMCG Commercial Platform"
DB_NAME = "FMCG Warehouse"


class Metabase:
    def __init__(self, url: str):
        self.url = url.rstrip("/")
        self.session: str | None = None

    def call(self, method: str, path: str, body: dict | None = None):
        req = urllib.request.Request(self.url + path, method=method,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "application/json",
                                              **({"X-Metabase-Session": self.session} if self.session else {})})
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 - URL lokal dari argumen
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"{method} {path} -> {exc.code}: {exc.read()[:500]!r}") from None
        return json.loads(raw) if raw else None

    def wait_healthy(self, timeout_s: int = 600) -> None:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            try:
                if self.call("GET", "/api/health").get("status") == "ok":
                    return
            except Exception:  # noqa: BLE001 - Metabase belum siap
                pass
            time.sleep(5)
        raise TimeoutError("Metabase tidak sehat dalam batas waktu")

    def login(self) -> None:
        email, password = env("METABASE_ADMIN_EMAIL"), env("METABASE_ADMIN_PASSWORD")
        props = self.call("GET", "/api/session/properties")
        if not props.get("has-user-setup"):
            log.info("Setup awal Metabase (admin %s)", email)
            self.call("POST", "/api/setup", {
                "token": props["setup-token"],
                "user": {"email": email, "password": password, "first_name": "Admin", "last_name": "FMCG"},
                "prefs": {"site_name": "FMCG Commercial Data Platform", "site_locale": "id", "allow_tracking": False},
            })
        self.session = self.call("POST", "/api/session", {"username": email, "password": password})["id"]


def _list(payload):
    return payload["data"] if isinstance(payload, dict) and "data" in payload else payload


def ensure_database(mb: Metabase) -> int:
    details = {"host": env("MB_WAREHOUSE_HOST", "dwh"), "port": int(env("MB_WAREHOUSE_PORT", "5432")),
               "dbname": env("DWH_DB_NAME"), "user": "bi_reader", "password": env("BI_READER_PASSWORD"),
               "ssl": False, "schema-filters-type": "inclusion", "schema-filters-patterns": "marts,ops,forecast"}
    existing = [d for d in _list(mb.call("GET", "/api/database")) if d["name"] == DB_NAME]
    if existing:
        db_id = existing[0]["id"]
        mb.call("PUT", f"/api/database/{db_id}", {"details": details})
    else:
        db_id = mb.call("POST", "/api/database", {"engine": "postgres", "name": DB_NAME, "details": details})["id"]
    mb.call("POST", f"/api/database/{db_id}/sync_schema")
    return db_id


def ensure_collection(mb: Metabase) -> int:
    for c in _list(mb.call("GET", "/api/collection")):
        if c.get("name") == COLLECTION and not c.get("archived"):
            items = _list(mb.call("GET", f"/api/collection/{c['id']}/items?models=card&models=dashboard"))
            for it in items:   # arsipkan versi lama; spec.py adalah sumber kebenaran
                kind = "dashboard" if it["model"] == "dashboard" else "card"
                mb.call("PUT", f"/api/{kind}/{it['id']}", {"archived": True})
            return c["id"]
    return mb.call("POST", "/api/collection", {"name": COLLECTION,
                                               "description": "Dashboard dibuat oleh dashboards/metabase/provision.py"})["id"]


def create_dashboard(mb: Metabase, db_id: int, coll_id: int, spec: dict) -> dict:
    dash = mb.call("POST", "/api/dashboard", {"name": spec["name"], "description": spec["description"],
                                              "collection_id": coll_id})
    dashcards = []
    for i, c in enumerate(spec["cards"]):
        created = mb.call("POST", "/api/card", {
            "name": c["name"], "collection_id": coll_id, "display": c["display"],
            "visualization_settings": c["viz"],
            "dataset_query": {"type": "native", "database": db_id, "native": {"query": c["sql"], "template-tags": {}}},
        })
        # Jalankan sekali untuk memastikan SQL valid di warehouse
        result = mb.call("POST", f"/api/card/{created['id']}/query")
        if result.get("status") != "completed":
            raise RuntimeError(f"Kartu '{c['name']}' gagal: {result.get('error')}")
        dashcards.append({"id": -(i + 1), "card_id": created["id"], "row": c["row"], "col": c["col"],
                          "size_x": c["w"], "size_y": c["h"], "parameter_mappings": [], "visualization_settings": {}})
    mb.call("PUT", f"/api/dashboard/{dash['id']}", {"dashcards": dashcards})
    return dash


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("--url", default=env("METABASE_URL", "http://127.0.0.1:3000"))
    p.add_argument("--public-links", action="store_true", help="buat link publik (untuk screenshot; lokal saja)")
    args = p.parse_args()

    mb = Metabase(args.url)
    mb.wait_healthy()
    mb.login()
    db_id = ensure_database(mb)
    coll_id = ensure_collection(mb)
    out = {}
    if args.public_links:
        mb.call("PUT", "/api/setting/enable-public-sharing", {"value": True})
    for spec in DASHBOARDS:
        dash = create_dashboard(mb, db_id, coll_id, spec)
        entry = {"id": dash["id"], "url": f"{args.url}/dashboard/{dash['id']}"}
        if args.public_links:
            uuid = mb.call("POST", f"/api/dashboard/{dash['id']}/public_link")["uuid"]
            entry["public_url"] = f"{args.url}/public/dashboard/{uuid}"
        out[spec["name"]] = entry
        log.info("Dashboard '%s' -> %s (%d kartu)", spec["name"], entry["url"], len(spec["cards"]))
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
