"""Client IP address behind the hosting platform's proxy, used for login lockouts."""

import ipaddress

from django.conf import settings


def client_ip(request):
    """
    Each proxy appends the address it received the connection from to
    X-Forwarded-For, so with N trusted proxies in front of the app the
    client is the Nth entry from the right. Entries further left come from
    the client itself and could be forged, so they are ignored.
    """
    hops = settings.TRUSTED_PROXY_COUNT
    forwarded = [
        part.strip()
        for part in request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")
        if part.strip()
    ]
    if hops and len(forwarded) >= hops:
        candidate = forwarded[-hops]
        try:
            return str(ipaddress.ip_address(candidate))
        except ValueError:
            pass
    return request.META.get("REMOTE_ADDR")
