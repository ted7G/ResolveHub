from allauth.socialaccount.adapter import get_adapter
from allauth.socialaccount.forms import DisconnectForm
from django import forms
from django.core.exceptions import ValidationError


class UnlinkGitHubForm(DisconnectForm):
    """
    allauth won't remove the last linked account when it runs without its
    own password pages, assuming GitHub is the only way in. Here every staff
    login also has the admin's password sign-in, so unlinking is safe as
    long as the account has a password to fall back on.
    """

    def clean(self):
        cleaned_data = forms.Form.clean(self)  # skips allauth's last-account rule
        account = cleaned_data.get("account")
        if account:
            if not account.user.has_usable_password():
                raise ValidationError(
                    "This login has no password, so it couldn't sign in at all without "
                    "GitHub. Ask a support admin to set a password first."
                )
            get_adapter().validate_disconnect(account, self.accounts)
        return cleaned_data
