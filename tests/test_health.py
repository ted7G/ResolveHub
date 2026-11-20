import pytest
from django.db import connection

pytestmark = pytest.mark.django_db


@pytest.fixture
def production_like(settings):
    """Strict hosts and the HTTPS redirect, as they are behind the real proxy."""
    settings.ALLOWED_HOSTS = ["resolvehub.example"]
    settings.SECURE_SSL_REDIRECT = True


def test_healthz_reports_ok_when_database_is_reachable(client):
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert "no-cache" in response["Cache-Control"]


def test_healthz_reports_503_when_database_is_down(client, monkeypatch):
    def broken_cursor():
        raise ConnectionError("database is gone")

    monkeypatch.setattr(connection, "cursor", broken_cursor)

    response = client.get("/healthz")

    assert response.status_code == 503
    assert response.json()["database"] == "unreachable"


def test_container_probe_on_internal_address_is_answered(client, production_like):
    # Docker's HEALTHCHECK calls plain http://127.0.0.1:8000/healthz.
    response = client.get("/healthz", HTTP_HOST="127.0.0.1:8000")

    assert response.status_code == 200


def test_other_pages_still_reject_unknown_hosts(client, production_like):
    response = client.get("/admin/login/", HTTP_HOST="127.0.0.1:8000")

    assert response.status_code == 400


def test_other_pages_still_redirect_to_https(client, production_like):
    response = client.get("/admin/login/", HTTP_HOST="resolvehub.example")

    assert response.status_code == 301
    assert response["Location"] == "https://resolvehub.example/admin/login/"


def test_https_requests_through_the_proxy_are_served(client, production_like):
    response = client.get(
        "/admin/login/", HTTP_HOST="resolvehub.example", HTTP_X_FORWARDED_PROTO="https"
    )

    assert response.status_code == 200


def test_root_redirects_to_admin(client):
    response = client.get("/")

    assert response.status_code == 302
    assert response["Location"] == "/admin/"


def test_database_queries_have_a_time_limit():
    with connection.cursor() as cursor:
        cursor.execute("SHOW statement_timeout")
        assert cursor.fetchone()[0] == "30s"
