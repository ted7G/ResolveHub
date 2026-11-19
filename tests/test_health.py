import pytest


@pytest.mark.django_db
def test_healthz_reports_ok_when_database_is_reachable(client):
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_root_redirects_to_admin(client):
    response = client.get("/")

    assert response.status_code == 302
    assert response["Location"] == "/admin/"
