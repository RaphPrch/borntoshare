from __future__ import annotations

import logging

from app.core import logging as auth_logging


def _capture(caplog, **fields) -> str:
    logger = logging.getLogger("auth.test")
    with caplog.at_level(logging.INFO, logger="auth.test"):
        auth_logging.log_event(logger, logging.INFO, "AUTH_TEST", **fields)
    return caplog.records[-1].getMessage()


def test_log_event_includes_first_forwarded_ip(caplog) -> None:
    auth_logging.set_client_ip_context("203.0.113.7, 10.89.0.51", "10.89.0.51")
    try:
        assert "client_ip=203.0.113.7" in _capture(caplog)
    finally:
        auth_logging.clear_request_id_context()


def test_log_event_falls_back_to_peer_then_nothing(caplog) -> None:
    auth_logging.set_client_ip_context(None, "10.89.0.51")
    assert "client_ip=10.89.0.51" in _capture(caplog)
    auth_logging.clear_request_id_context()
    assert "client_ip=" not in _capture(caplog)
