import json
import logging
import re

from django import forms
from django.apps import apps
from django.contrib import admin
from django.contrib.admin.exceptions import NotRegistered
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from . import client
from .context import build_form_reference
from .ratelimit import allow_request

logger = logging.getLogger(__name__)

MAX_BODY_BYTES = 4096
# Control characters other than tab and newline have no place in a question.
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


class QuestionForm(forms.Form):
    model = forms.CharField(max_length=100)
    object_id = forms.CharField(max_length=20, required=False)
    field = forms.CharField(max_length=100, required=False)
    question = forms.CharField(min_length=3, max_length=500)

    def clean_question(self):
        return _CONTROL_CHARS.sub("", self.cleaned_data["question"]).strip()


def _error(message, status):
    return JsonResponse({"error": message}, status=status)


@require_POST
def ask(request):
    """
    Answer a question about the admin form the user has open. CSRF is
    enforced by the middleware; only active staff can use it.
    """
    user = request.user
    if not (user.is_authenticated and user.is_active and user.is_staff):
        return _error("Sign in to the admin to use the assistant.", 403)
    if len(request.body) > MAX_BODY_BYTES:
        return _error("That request is too large.", 413)

    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return _error("Invalid request.", 400)
    form = QuestionForm(payload if isinstance(payload, dict) else {})
    if not form.is_valid():
        if "question" in form.errors:
            return _error("Please ask a question between 3 and 500 characters.", 400)
        return _error("Invalid request.", 400)
    data = form.cleaned_data

    try:
        model_admin = admin.site.get_model_admin(apps.get_model(data["model"]))
    except (LookupError, ValueError, NotRegistered):
        return _error("Unknown form.", 400)

    obj = None
    if data["object_id"]:
        obj = model_admin.get_object(request, data["object_id"])
        if obj is None:
            return _error("That record doesn't exist.", 404)
    if not model_admin.has_view_or_change_permission(request, obj):
        return _error("You don't have access to this form.", 403)

    if not allow_request(user.pk):
        return _error("You've asked a lot of questions in a short time. Please wait a minute.", 429)

    reference, labels = build_form_reference(model_admin, request, obj)
    messages = client.build_messages(reference, data["question"], labels.get(data["field"]))
    try:
        answer = client.ask(messages)
    except client.AssistantError as exc:
        return _error(exc.user_message, exc.status)

    # Question text isn't logged: staff may paste customer details into it.
    logger.info(
        "Assistant answered user=%s form=%s question_chars=%d",
        user.pk,
        data["model"],
        len(data["question"]),
    )
    return JsonResponse({"answer": answer})
