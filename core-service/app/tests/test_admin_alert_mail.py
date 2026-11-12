from app.services import notifications as n


def _setup(monkeypatch, config, admins):
    sent = []
    monkeypatch.setattr(n, "settings", lambda db: config)
    monkeypatch.setattr(n, "_admin_emails", lambda db: admins)
    monkeypatch.setattr(n, "queue", lambda key, rec, subject, body, html=None: sent.append((key, rec, subject, body, html)))
    return sent


def test_a_breakdown_reaches_the_administrators_in_html_and_text(monkeypatch):
    sent = _setup(monkeypatch, {"enabled": True, "appUrl": "https://b2s"}, ["admin@corp.local"])
    n.admin_alert(None, "server_unreachable:dfs01:1", "Serveur dfs01 injoignable", ["3 échecs <de suite>"], "/observability", intro="i")
    key, rec, subject, body, html = sent[0]
    assert rec == ["admin@corp.local"] and subject == "[BornToShare] Serveur dfs01 injoignable"
    assert "3 échecs <de suite>" in body and "&lt;de suite&gt;" in html and "https://b2s/observability" in html


def test_nothing_is_sent_when_disabled_or_without_address(monkeypatch):
    sent = _setup(monkeypatch, {"enabled": True, "adminAlerts": False}, ["admin@corp.local"])
    n.admin_alert(None, "k", "t", ["l"], "/", intro="i")
    sent += _setup(monkeypatch, {"enabled": True}, [])
    n.admin_alert(None, "k", "t", ["l"], "/", intro="i")
    assert sent == []
