"""
django-allauth adapters. GitHub is only a second way into an account that
already exists and that its owner linked while signed in.
"""

from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter


class ClosedSignupAccountAdapter(DefaultAccountAdapter):
    def is_open_for_signup(self, request):
        return False


class LinkedAccountsOnlyAdapter(DefaultSocialAccountAdapter):
    """
    An unknown GitHub account is refused instead of becoming a new user.
    Staff accounts and their roles are created in the admin, so OAuth can
    never hand out access on its own.
    """

    def is_open_for_signup(self, request, sociallogin):
        return False
