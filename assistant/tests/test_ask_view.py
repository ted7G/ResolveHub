import json

import httpx2
import openai
import pytest
from django.core.cache import cache
from django.test import Client
from django.urls import reverse

from accounts.roles import AGENT, VIEWER
from tickets.rules import Status

pytestmark = pytest.mark.django_db

URL = reverse("assistant:ask")


class FakeOpenAI:
    """Stands in for openai.OpenAI; records the call and returns or raises `outcome`."""

    calls = []
    outcome = "Pick Resolved once the fix is confirmed."

    def __init__(self, **kwargs):
        self.client_kwargs = kwargs
        self.chat = self
        self.completions = self

    def create(self, **kwargs):
        FakeOpenAI.calls.append({**kwargs, "client": self.client_kwargs})
        if isinstance(FakeOpenAI.outcome, Exception):
            raise FakeOpenAI.outcome
        message = type("Message", (), {"content": FakeOpenAI.outcome})
        choice = type("Choice", (), {"message": message})
        return type("Response", (), {"choices": [choice]})


@pytest.fixture(autouse=True)
def fake_provider(monkeypatch, settings):
    settings.OPENAI_API_KEY = "test-key"
    monkeypatch.setattr(openai, "OpenAI", FakeOpenAI)
    FakeOpenAI.calls = []
    FakeOpenAI.outcome = "Pick Resolved once the fix is confirmed."
    cache.clear()
    return FakeOpenAI


def ask(client, **payload):
    payload.setdefault("model", "tickets.ticket")
    payload.setdefault("question", "What does priority change?")
    return client.post(URL, json.dumps(payload), content_type="application/json")


# --- Happy path ---------------------------------------------------------------


def test_answers_using_the_form_reference(login_as, make_ticket, fake_provider):
    client = login_as(AGENT)
    ticket = make_ticket(status=Status.OPEN, assignee=client.user.agent_profile)

    response = ask(client, object_id=str(ticket.pk), field="status", question="Can I close it?")

    assert response.status_code == 200
    assert response.json() == {"answer": "Pick Resolved once the fix is confirmed."}
    call = fake_provider.calls[0]
    system, user = call["messages"]
    assert "currently Open, options: Open, Waiting on customer, Resolved" in system["content"]
    assert user["content"] == '(I\'m on the "Status" field.) Can I close it?'
    assert call["client"]["timeout"] == 20.0
    assert call["max_completion_tokens"] == 400


def test_control_characters_are_stripped_from_the_question(login_as, fake_provider):
    ask(login_as(AGENT), question="What is\x07 a tag?\x1b[31m")

    assert fake_provider.calls[0]["messages"][1]["content"] == "What is a tag?[31m"


def test_null_bytes_are_rejected(login_as, fake_provider):
    response = ask(login_as(AGENT), question="What is\x00 a tag?")

    assert response.status_code == 400
    assert not fake_provider.calls


# --- Access control and input validation -------------------------------------------


def test_requires_a_logged_in_staff_user(client, make_user):
    assert ask(client).status_code == 403

    client.force_login(make_user(is_staff=False))
    assert ask(client).status_code == 403


def test_only_post_is_allowed(login_as):
    assert login_as(AGENT).get(URL).status_code == 405


def test_csrf_token_is_required(login_as):
    user = login_as(AGENT).user
    strict = Client(enforce_csrf_checks=True)
    strict.force_login(user)

    assert ask(strict).status_code == 403


@pytest.mark.parametrize(
    "payload",
    [
        {"question": "x"},
        {"question": "x" * 501},
        {"model": "not-a-model"},
        {"model": "sessions.session"},  # a real model, but not in the admin
    ],
)
def test_rejects_invalid_input(login_as, payload, fake_provider):
    response = ask(login_as(AGENT), **payload)

    assert response.status_code == 400
    assert not fake_provider.calls


def test_rejects_malformed_json(login_as):
    response = login_as(AGENT).post(URL, "{not json", content_type="application/json")

    assert response.status_code == 400


def test_rejects_oversized_bodies(login_as):
    response = ask(login_as(AGENT), question="ok?", padding="x" * 13000)

    assert response.status_code == 413


def test_forms_the_user_cannot_open_are_refused(login_as, fake_provider):
    response = ask(login_as(AGENT), model="auth.user")

    assert response.status_code == 403
    assert not fake_provider.calls


def test_unknown_record(login_as):
    assert ask(login_as(VIEWER), object_id="999999").status_code == 404


def test_rate_limit_per_user(login_as, settings, fake_provider, monkeypatch):
    settings.ASSISTANT_REQUESTS_PER_MINUTE = 2
    # Pin the clock so the three requests can't straddle a minute boundary.
    monkeypatch.setattr("assistant.ratelimit.time.time", lambda: 1_800_000_000.0)
    client = login_as(AGENT)

    statuses = [ask(client).status_code for _ in range(3)]

    assert statuses == [200, 200, 429]
    assert len(fake_provider.calls) == 2


# --- Provider failures never break the admin --------------------------------------

_REQUEST = httpx2.Request("POST", "https://api.example/v1/chat/completions")


@pytest.mark.parametrize(
    ("error", "status", "message"),
    [
        (openai.APITimeoutError(request=_REQUEST), 503, "took too long"),
        (openai.APIConnectionError(request=_REQUEST), 503, "unavailable right now"),
        (
            openai.RateLimitError(
                "quota", response=httpx2.Response(429, request=_REQUEST), body=None
            ),
            429,
            "busy right now",
        ),
        (
            openai.AuthenticationError(
                "bad key", response=httpx2.Response(401, request=_REQUEST), body=None
            ),
            503,
            "misconfigured",
        ),
        (
            openai.InternalServerError(
                "boom", response=httpx2.Response(500, request=_REQUEST), body=None
            ),
            503,
            "unavailable right now",
        ),
    ],
)
def test_provider_errors_become_friendly_messages(login_as, fake_provider, error, status, message):
    fake_provider.outcome = error

    response = ask(login_as(AGENT))

    assert response.status_code == status
    assert message in response.json()["error"]


def test_empty_answer_is_reported(login_as, fake_provider):
    fake_provider.outcome = "   "

    response = ask(login_as(AGENT))

    assert response.status_code == 503
    assert "didn't return an answer" in response.json()["error"]


def test_missing_api_key_is_explained(login_as, settings, fake_provider):
    settings.OPENAI_API_KEY = ""

    response = ask(login_as(AGENT))

    assert response.status_code == 503
    assert "isn't set up" in response.json()["error"]
    assert not fake_provider.calls


# --- Pages other than forms, and follow-up questions ---------------------------


def test_list_questions_get_the_list_reference(login_as, fake_provider):
    response = ask(login_as(AGENT), page="list")

    assert response.status_code == 200
    system = fake_provider.calls[0]["messages"][0]["content"]
    assert "Page: the tickets list" in system
    assert "Move selected tickets to Resolved" in system
    assert "- Deadline: Overdue" in system


def test_general_questions_need_no_model(login_as, fake_provider):
    response = ask(login_as(VIEWER), page="general", model="")

    assert response.status_code == 200
    system = fake_provider.calls[0]["messages"][0]["content"]
    assert "Dashboard, top to bottom" in system
    assert "They can read tickets, customers, agents and tags but not change anything." in system


def test_form_and_list_questions_still_need_a_model(login_as):
    response = ask(login_as(AGENT), page="list", model="")

    assert response.status_code == 400


def test_recent_turns_are_sent_as_conversation(login_as, fake_provider):
    history = [{"question": f"Question {n}?", "answer": f"Answer {n}."} for n in range(5)]
    history.append({"question": 42, "answer": ["not text"]})

    ask(login_as(AGENT), page="general", model="", question="And then?", history=history)

    messages = fake_provider.calls[0]["messages"]
    # The last three well-formed turns, as user/assistant pairs, then the question.
    assert [m["role"] for m in messages] == ["system"] + ["user", "assistant"] * 2 + ["user"]
    assert messages[1]["content"] == "Question 3?"
    assert messages[-1]["content"] == "And then?"
