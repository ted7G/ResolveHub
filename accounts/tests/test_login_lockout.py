import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db

LOGIN = reverse("admin:login")
PASSWORD = "correct-horse-battery"


@pytest.fixture(autouse=True)
def axes_on(settings):
    settings.AXES_ENABLED = True


@pytest.fixture
def staff(django_user_model):
    return django_user_model.objects.create_user("dana", password=PASSWORD, is_staff=True)


def attempt(client, password, ip="203.0.113.7"):
    return client.post(
        LOGIN,
        {"username": "dana", "password": password, "next": "/admin/"},
        HTTP_X_FORWARDED_FOR=ip,
    )


def test_correct_password_logs_in(client, staff):
    response = attempt(client, PASSWORD)

    assert response.status_code == 302
    assert response["Location"] == "/admin/"


def test_five_failures_lock_the_account_even_for_the_right_password(client, staff):
    for _ in range(5):
        attempt(client, "wrong-guess")

    response = attempt(client, PASSWORD)

    assert response.status_code == 429
    assert b"Too many failed sign-in attempts" in response.content


def test_lockout_is_per_ip_so_the_real_user_can_still_sign_in(client, staff):
    for _ in range(5):
        attempt(client, "wrong-guess", ip="198.51.100.20")

    response = attempt(client, PASSWORD, ip="203.0.113.7")

    assert response.status_code == 302


def test_successful_login_resets_the_failure_count(client, staff):
    for _ in range(4):
        attempt(client, "wrong-guess")
    attempt(client, PASSWORD)
    client.logout()

    for _ in range(4):
        attempt(client, "wrong-guess")
    response = attempt(client, PASSWORD)

    assert response.status_code == 302
