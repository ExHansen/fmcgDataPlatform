import json

import pytest

from monitoring import alerting, report
from monitoring.alerting import Alert


class FakeConn:
    def __init__(self):
        self.rows = []

    def execute(self, sql, params=None):
        self.rows.append(params)

    def commit(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def fake_db(monkeypatch, tmp_path):
    conn = FakeConn()
    monkeypatch.setattr(alerting, "dwh_connect", lambda: conn)
    monkeypatch.setattr(alerting, "LOG_FILE", tmp_path / "alerts.log")
    return conn


def test_alert_text_truncates_long_lists():
    a = Alert("warn", "dq", "judul", lines=[f"baris {i}" for i in range(30)])
    text = a.text()
    assert text.startswith("⚠️ [WARN] judul")
    assert "baris 24" in text and "baris 25" not in text
    assert "dan 5 lainnya" in text


def test_build_alert_uses_highest_severity_and_counts():
    issues = [report.Issue("dq:a", "warn", "a"), report.Issue("recon:b", "error", "b"),
              report.Issue("dq:c", "warn", "c")]
    alert = report.build_alert(issues, "run-1")
    assert alert.severity == "error"
    assert alert.title.endswith("1 error, 2 warning")
    assert alert.lines[0] == "b"                       # error di urutan pertama
    assert alert.alert_keys[0] == "recon:b"
    assert report.build_alert([], None) is None


def test_recon_messages_are_readable():
    text = report.RECON_TEXT["dms_file_received"].format(dim="DIST_B", start="2026-10-20", src=1, tgt=0, diff=0)
    assert text == "Distributor DIST_B tidak mengirim file tanggal 2026-10-20"


@pytest.mark.parametrize("url, key", [("https://discord.com/api/webhooks/1/x", "content"),
                                      ("https://hooks.slack.com/services/T/B/x", "text")])
def test_webhook_payload_per_platform(monkeypatch, fake_db, url, key):
    sent = {}

    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return b""

    def fake_urlopen(req, timeout):
        sent["body"] = json.loads(req.data)
        return Resp()

    monkeypatch.setenv("ALERT_WEBHOOK_URL", url)
    monkeypatch.setattr(alerting.urllib.request, "urlopen", fake_urlopen)
    assert alerting.send(Alert("error", "dq", "uji", lines=["x"]))
    assert key in sent["body"] and "uji" in sent["body"][key]
    assert fake_db.rows[0][-3:] == ("webhook", True, None)


def test_webhook_failure_is_logged_not_raised(monkeypatch, fake_db):
    def boom(req, timeout):
        raise OSError("jaringan putus")

    monkeypatch.setenv("ALERT_WEBHOOK_URL", "https://discord.com/api/webhooks/1/x")
    monkeypatch.setattr(alerting.urllib.request, "urlopen", boom)
    assert alerting.send(Alert("error", "dq", "uji")) is False
    channel, delivered, error = fake_db.rows[0][-3:]
    assert (channel, delivered) == ("webhook", False) and "jaringan putus" in error
    assert alerting.LOG_FILE.read_text(encoding="utf-8").count("uji") == 1


def test_without_webhook_alert_is_only_logged(monkeypatch, fake_db):
    monkeypatch.setenv("ALERT_WEBHOOK_URL", "")
    assert alerting.send(Alert("warn", "freshness", "telat", alert_keys=["freshness:DMS_A:WARN"]))
    assert fake_db.rows[0][3] == "freshness:DMS_A:WARN"
    assert fake_db.rows[0][-3:] == ("log", True, None)
