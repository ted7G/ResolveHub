import pytest
from django.test import RequestFactory

from accounts.client_ip import client_ip


def request_with(forwarded=None, remote="10.0.0.1"):
    extra = {"REMOTE_ADDR": remote}
    if forwarded is not None:
        extra["HTTP_X_FORWARDED_FOR"] = forwarded
    return RequestFactory().get("/", **extra)


def test_uses_the_address_added_by_the_trusted_proxy(settings):
    settings.TRUSTED_PROXY_COUNT = 1

    assert client_ip(request_with("81.2.69.160")) == "81.2.69.160"


def test_ignores_entries_the_client_could_have_forged(settings):
    settings.TRUSTED_PROXY_COUNT = 1

    assert client_ip(request_with("1.1.1.1, 81.2.69.160")) == "81.2.69.160"


def test_two_proxies(settings):
    settings.TRUSTED_PROXY_COUNT = 2

    assert client_ip(request_with("1.1.1.1, 81.2.69.160, 172.71.1.1")) == "81.2.69.160"


@pytest.mark.parametrize("forwarded", [None, "", "not-an-ip"])
def test_falls_back_to_the_connection_address(settings, forwarded):
    settings.TRUSTED_PROXY_COUNT = 1

    assert client_ip(request_with(forwarded)) == "10.0.0.1"


def test_proxy_count_zero_trusts_only_the_connection(settings):
    settings.TRUSTED_PROXY_COUNT = 0

    assert client_ip(request_with("81.2.69.160")) == "10.0.0.1"
