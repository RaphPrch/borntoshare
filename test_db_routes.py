from fastapi.testclient import TestClient
import socket
import pytest
from unittest.mock import patch, MagicMock

from app.main import app # Assuming your FastAPI app instance is named 'app' in app.main

client = TestClient(app)

@patch("app.routes.db.socket.gethostbyname")
@patch("app.routes.db.socket.create_connection")
def test_network_diagnostic_success(mock_create_connection, mock_gethostbyname):
    mock_gethostbyname.return_value = "127.0.0.1"
    mock_create_connection.return_value = MagicMock() # Mock the socket object

    response = client.post(
        "/api/db/diagnostic",
        json={"host": "localhost", "port": 3306}
    )

    assert response.status_code == 200
    assert response.json()["dns_ok"] is True
    assert response.json()["tcp_ok"] is True
    assert isinstance(response.json()["latency_ms"], int)
    mock_gethostbyname.assert_called_once_with("localhost")
    mock_create_connection.assert_called_once_with(("127.0.0.1", 3306), timeout=3)

@patch("app.routes.db.socket.gethostbyname")
@patch("app.routes.db.socket.create_connection")
def test_network_diagnostic_dns_failure(mock_create_connection, mock_gethostbyname):
    mock_gethostbyname.side_effect = socket.gaierror("DNS lookup failed")

    response = client.post(
        "/api/db/diagnostic",
        json={"host": "nonexistent.host", "port": 3306}
    )

    assert response.status_code == 200 # Diagnostic endpoint returns 200 even on failure
    assert response.json()["dns_ok"] is False
    assert response.json()["tcp_ok"] is False
    assert response.json()["latency_ms"] is None
    mock_gethostbyname.assert_called_once_with("nonexistent.host")
    mock_create_connection.assert_not_called()

@patch("app.routes.db.get_connection")
def test_test_db_success(mock_get_connection):
    mock_conn = MagicMock()
    mock_get_connection.return_value = mock_conn

    response = client.post(
        "/api/db/test",
        json={
            "host": "localhost",
            "port": 3306,
            "user": "testuser",
            "password": "testpassword"
        }
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    mock_get_connection.assert_called_once()
    mock_conn.close.assert_called_once()

@patch("app.routes.db.get_connection")
def test_test_db_failure(mock_get_connection):
    mock_get_connection.side_effect = Exception("DB connection error")

    response = client.post(
        "/api/db/test",
        json={
            "host": "badhost",
            "port": 3306,
            "user": "baduser",
            "password": "badpassword"
        }
    )

    assert response.status_code == 400
    assert "Unable to connect to database" in response.json()["detail"]
    mock_get_connection.assert_called_once()

@patch("app.routes.db.get_connection")
def test_privileges_test_success(mock_get_connection):
    mock_conn = MagicMock()
    mock_cur = mock_conn.cursor.return_value
    # Simule les retours de SHOW DATABASES, SHOW GRANTS et les exécutions CREATE/DROP
    mock_cur.fetchall.side_effect = [
        [("db1",)], # SHOW DATABASES
        [("GRANT ALL PRIVILEGES ON *.* TO 'root'@'%'",)] # SHOW GRANTS
    ]
    mock_get_connection.return_value = mock_conn

    response = client.post(
        "/api/db/privileges-test",
        json={
            "host": "localhost", 
            "port": 3306, 
            "user": "root", 
            "password": "password"
        }
    )

    assert response.status_code == 200
    data = response.json()
    assert data["privileges"]["create_table"] is True
    assert data["all_required_ok"] is True

@patch("app.routes.db.os")
def test_save_logging_db_connection_success(mock_os):
    payload = {
        "host": "loghost",
        "port": 3306,
        "user": "loguser",
        "password": "logpassword",
        "database": "logging_db"
    }
    response = client.post("/api/db/logging/save", json=payload)
    assert response.status_code == 200
    assert response.json()["ok"] is True
    mock_os.environ.__setitem__.assert_any_call("WIZARD_LOG_DB_HOST", "loghost")
    mock_os.environ.__setitem__.assert_any_call("WIZARD_LOG_DB_NAME", "logging_db")
    # ... assert other environment variables