"""
GitHub sign-in through the real django-allauth views. Only the two calls
that would reach GitHub (exchanging the code, fetching the profile) are
replaced.
"""

from urllib.parse import parse_qs, urlparse

import pytest
from allauth.socialaccount.models import SocialAccount
from allauth.socialaccount.providers.github.views import GitHubOAuth2Adapter
from allauth.socialaccount.providers.oauth2.client import OAuth2Client
from django.contrib.auth import get_user_model
from django.urls import reverse

pytestmark = pytest.mark.django_db

PROFILE = {"id": 4242, "login": "dana-gh", "name": "Dana Reyes", "email": "dana@example.com"}


@pytest.fixture(autouse=True)
def fake_github(monkeypatch):
    monkeypatch.setattr(
        OAuth2Client,
        "get_access_token",
        lambda self, code, **kwargs: {"access_token": "token", "token_type": "bearer"},
    )
    monkeypatch.setattr(
        GitHubOAuth2Adapter,
        "complete_login",
        lambda self, request, app, token, **kwargs: self.get_provider().sociallogin_from_response(
            request, dict(PROFILE)
        ),
    )


def github_round_trip(client, process="login"):
    """Start the flow, then come back from "GitHub" with a code and the issued state."""
    start = client.post(
        reverse("github_login") + "?next=/admin/", {"process": process} if process else {}
    )
    assert start.status_code == 302
    assert start["Location"].startswith("https://github.com/login/oauth/authorize")
    state = parse_qs(urlparse(start["Location"]).query)["state"][0]
    return client.get(reverse("github_callback"), {"code": "abc", "state": state})


def logged_in_user(client):
    return client.get(reverse("admin:index")).wsgi_request.user


def test_login_page_offers_github_when_configured(client):
    page = client.get(reverse("admin:login")).content.decode()

    assert "Sign in with GitHub" in page


def test_login_page_hides_github_when_not_configured(client, settings):
    settings.GITHUB_LOGIN_ENABLED = False

    page = client.get(reverse("admin:login")).content.decode()

    assert "Sign in with GitHub" not in page


def test_unknown_github_account_cannot_sign_in_or_create_a_user(client):
    users_before = get_user_model().objects.count()

    github_round_trip(client)

    assert not logged_in_user(client).is_authenticated
    assert get_user_model().objects.count() == users_before
    assert not SocialAccount.objects.exists()


def test_matching_email_alone_does_not_grant_access(client, make_user):
    staff = make_user(email=PROFILE["email"])
    password_hash = staff.password

    github_round_trip(client)

    assert not logged_in_user(client).is_authenticated
    staff.refresh_from_db()
    assert staff.password == password_hash  # password login still works


def test_linked_staff_account_can_sign_in_with_github(client, make_user):
    staff = make_user()
    client.force_login(staff)

    # Link while signed in, from the "GitHub sign-in" page.
    github_round_trip(client, process="connect")
    assert SocialAccount.objects.get(provider="github").user == staff

    client.logout()
    response = github_round_trip(client)

    assert response.status_code == 302
    assert response["Location"] == "/admin/"
    assert logged_in_user(client) == staff


def test_a_github_account_linked_to_someone_else_cannot_be_linked_again(client, make_user):
    owner, other = make_user(), make_user()
    client.force_login(owner)
    github_round_trip(client, process="connect")

    client.force_login(other)
    github_round_trip(client, process="connect")

    assert SocialAccount.objects.get(provider="github").user == owner


def test_linking_page_uses_the_admin_layout(client, make_user):
    client.force_login(make_user())

    page = client.get(reverse("socialaccount_connections")).content.decode()

    assert "ResolveHub" in page
    assert "Back to the admin" in page


def test_unlinked_github_account_is_told_how_to_link_it(client):
    page = github_round_trip(client).content.decode()

    assert "isn't linked to a login yet" in page
    assert reverse("admin:login") in page
    assert "Sign Up Closed" not in page


def test_cancelling_at_github_explains_and_links_back(client):
    start = client.post(reverse("github_login"), {"process": "login"})
    state = parse_qs(urlparse(start["Location"]).query)["state"][0]

    page = client.get(
        reverse("github_callback"), {"error": "access_denied", "state": state}, follow=True
    ).content.decode()

    assert "GitHub sign-in cancelled" in page
    assert reverse("admin:login") in page


def test_there_is_only_one_login_page(client):
    response = client.get("/accounts/login/?next=/admin/")

    assert response.status_code == 302
    assert response["Location"] == reverse("admin:login") + "?next=/admin/"


def test_linked_github_account_can_be_unlinked(client, make_user):
    staff = make_user()
    client.force_login(staff)
    github_round_trip(client, process="connect")
    account = SocialAccount.objects.get(user=staff)
    page = client.get(reverse("socialaccount_connections")).content.decode()
    assert PROFILE["login"] in page

    response = client.post(reverse("socialaccount_connections"), {"account": account.pk})

    assert response.status_code == 302
    assert not SocialAccount.objects.filter(pk=account.pk).exists()


def test_unlinking_is_refused_with_a_reason_when_there_is_no_password(client, make_user):
    staff = make_user()
    staff.set_unusable_password()
    staff.save()
    client.force_login(staff)
    github_round_trip(client, process="connect")
    account = SocialAccount.objects.get(user=staff)

    response = client.post(reverse("socialaccount_connections"), {"account": account.pk})

    assert SocialAccount.objects.filter(pk=account.pk).exists()
    assert "has no password" in response.content.decode()
