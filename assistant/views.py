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
from .context import build_form_reference, build_general_reference, build_list_reference
from .ratelimit import allow_request

logger = logging.getLogger(__name__)

MAX_BODY_BYTES = 12 * 1024
MAX_HISTORY_TURNS = 3
MAX_ANSWER_CHARS = 1500
# Control characters other than tab and newline have no place in a question.
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def _clean_text(value):
    return _CONTROL_CHARS.sub("", value).strip()


class QuestionForm(forms.Form):
    page = forms.ChoiceField(
        choices=[("form", "form"), ("list", "list"), ("general", "general")], required=False
    )
    model = forms.CharField(max_length=100, required=False)
    object_id = forms.CharField(max_length=20, required=False)
    field = forms.CharField(max_length=100, required=False)
    question = forms.CharField(min_length=3, max_length=500)

    def clean_page(self):
        return self.cleaned_data["page"] or "form"

    def clean_question(self):
        return _clean_text(self.cleaned_data["question"])

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("page") in ("form", "list") and not cleaned.get("model"):
            raise forms.ValidationError("A form or list question needs its model.")
        return cleaned


def _history(payload):
    """
    The last few exchanges, so a follow-up like "and then?" makes sense.
    They come from the browser, so they're length-checked and treated as
    plain conversation, never as instructions.
    """
    turns = payload.get("history")
    if not isinstance(turns, list):
        return []
    cleaned = []
    for turn in turns:
        if not isinstance(turn, dict):
            continue
        question, answer = turn.get("question"), turn.get("answer")
        if not (isinstance(question, str) and isinstance(answer, str)):
            continue
        question, answer = _clean_text(question)[:500], _clean_text(answer)[:MAX_ANSWER_CHARS]
        if question and answer:
            cleaned.append((question, answer))
    return cleaned[-MAX_HISTORY_TURNS:]


def _error(message, status):
    return JsonResponse({"error": message}, status=status)


@require_POST
def ask(request):
    """
    Answer a question about the admin page the user has open: a form, a list
    or the desk in general. CSRF is enforced by the middleware; only active
    staff can use it, and only for pages they can see.
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
    if not isinstance(payload, dict):
        return _error("Invalid request.", 400)
    form = QuestionForm(payload)
    if not form.is_valid():
        if "question" in form.errors:
            return _error("Please ask a question between 3 and 500 characters.", 400)
        return _error("Invalid request.", 400)
    data = form.cleaned_data
    page = data["page"]

    model_admin = obj = None
    if page in ("form", "list"):
        try:
            model_admin = admin.site.get_model_admin(apps.get_model(data["model"]))
        except (LookupError, ValueError, NotRegistered):
            return _error("Unknown page.", 400)
    if page == "form" and data["object_id"]:
        obj = model_admin.get_object(request, data["object_id"])
        if obj is None:
            return _error("That record doesn't exist.", 404)
    if model_admin is not None and not model_admin.has_view_or_change_permission(request, obj):
        return _error("You don't have access to this page.", 403)

    if not allow_request(user.pk):
        return _error("You've asked a lot of questions in a short time. Please wait a minute.", 429)

    field_label = None
    if page == "form":
        reference, labels = build_form_reference(model_admin, request, obj)
        field_label = labels.get(data["field"])
    elif page == "list":
        reference = build_list_reference(model_admin, request)
    else:
        reference = build_general_reference(request)

    messages = client.build_messages(reference, data["question"], field_label, _history(payload))
    try:
        answer = client.ask(messages)
    except client.AssistantError as exc:
        return _error(exc.user_message, exc.status)

    # Question text isn't logged: staff may paste customer details into it.
    logger.info(
        "Assistant answered user=%s page=%s model=%s question_chars=%d",
        user.pk,
        page,
        data["model"] or "-",
        len(data["question"]),
    )
    return JsonResponse({"answer": answer})
