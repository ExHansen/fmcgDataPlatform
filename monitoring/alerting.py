"""Kirim alert: selalu ke ops.alert_log + logs/alerts.log; ke webhook Discord/Slack bila ALERT_WEBHOOK_URL di-set."""
from __future__ import annotations

import json
import logging
import urllib.request
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import urlparse

from ingestion.common.connections import dwh_connect
from ingestion.common.settings import ROOT, env

log = logging.getLogger(__name__)
LOG_FILE = ROOT / "logs" / "alerts.log"
ICON = {"info": "ℹ️", "warn": "⚠️", "error": "🚨"}


@dataclass
class Alert:
    severity: str            # info / warn / error
    source: str              # dq / recon / freshness / pipeline / airflow
    title: str
    lines: list[str] = field(default_factory=list)
    alert_keys: list[str] = field(default_factory=list)
    run_id: str | None = None

    def text(self) -> str:
        body = "\n".join(f"• {line}" for line in self.lines[:25])
        more = f"\n… dan {len(self.lines) - 25} lainnya" if len(self.lines) > 25 else ""
        return f"{ICON.get(self.severity, '')} [{self.severity.upper()}] {self.title}\n{body}{more}".strip()


def _post_webhook(url: str, text: str) -> None:
    host = urlparse(url).hostname or ""
    payload = {"content": text[:1900]} if "discord" in host else {"text": text}
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": "fmcg-data-platform"})
    with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310 - URL dari konfigurasi operator
        resp.read()


def send(alert: Alert) -> bool:
    """Return True bila terkirim ke webhook (atau tidak ada webhook dan hanya dicatat)."""
    text = alert.text()
    url = env("ALERT_WEBHOOK_URL", "")
    channel, delivered, error = ("webhook", True, None) if url else ("log", True, None)
    if url:
        try:
            _post_webhook(url, text)
        except Exception as exc:  # noqa: BLE001 - kegagalan kirim tetap dicatat, tidak boleh menggagalkan pipeline
            delivered, error = False, f"{type(exc).__name__}: {exc}"[:500]
            log.error("Gagal kirim webhook: %s", error)

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(f"{datetime.now(timezone.utc).isoformat()} {text}\n\n")
    log.warning("%s", text)

    keys = alert.alert_keys or [f"{alert.source}:{alert.title}"]
    with dwh_connect() as conn:
        for key in keys:
            conn.execute(
                "insert into ops.alert_log (alert_id, severity, source, alert_key, title, message, run_id, channel, "
                "delivered, delivery_error) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (str(uuid.uuid4()), alert.severity, alert.source, key, alert.title, text, alert.run_id, channel,
                 delivered, error))
        conn.commit()
    return delivered
