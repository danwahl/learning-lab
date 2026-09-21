"""Seeding, signup, and what an approved user can reach."""

import json
import urllib.request

from conftest import MODEL, REPO, URL, Api, in_container, seed


def test_seed_is_idempotent(instance):
    out = seed()
    assert "models tutor (default" in out and "signup open" in out


def test_branding(instance):
    assert Api(URL).get("/api/config")["name"].startswith("Learning Lab")


def test_signup_is_pending_until_approved(admin):
    r = Api(URL).post("/api/v1/auths/signup", {"name": "Newcomer", "email": "newcomer@example.com", "password": "a-long-test-password"})
    assert r["role"] == "pending"
    pending = Api(URL)
    pending.token = r["token"]
    assert pending.get("/api/models", missing=(401, 403)) is None
    admin.post(f"/api/v1/users/{r['id']}/update", {"role": "user"})
    assert {m["id"] for m in pending.get("/api/models")["data"]} >= {"tutor", "reviewer"}


def test_approved_user_sees_presets_tools_skills(student):
    models = {m["id"]: m for m in student.get("/api/models")["data"]}
    assert set(models) == {MODEL, "tutor", "reviewer"}
    assert models["tutor"]["name"] == "Tutor" and models["reviewer"]["name"] == "Reviewer"
    assert models["tutor"]["info"]["meta"]["toolIds"] == ["mentors"]
    assert models["reviewer"]["info"]["meta"]["toolIds"] == ["review"]
    avatar = urllib.request.urlopen(urllib.request.Request(f"{URL}/api/v1/models/model/profile/image?id=reviewer", headers={"Authorization": f"Bearer {student.token}"}))
    assert avatar.headers["Content-Type"] == "image/png" and avatar.read() == (REPO / "web" / "icons" / "reviewer.png").read_bytes()
    assert {t["id"] for t in student.get("/api/v1/tools/")} == {"mentors", "review"}
    assert len(student.get("/api/v1/skills/")) == 5


def last_request():
    return json.loads(in_container("tail", "-n", "1", "/tmp/stub-requests.jsonl"))


def chat(api, model):
    """One API turn; the UI sends a preset's tool ids itself, so pass them here."""
    tools = {"tutor": ["mentors"], "reviewer": ["review"]}[model]
    r = api.post("/api/chat/completions", {"model": model, "messages": [{"role": "user", "content": "hi"}], "stream": False, "tool_ids": tools})
    assert r["choices"][0]["message"]["content"] == "stub reply"
    req = last_request()
    assert req["model"] == MODEL
    assert req["reasoning_effort"] == "medium"
    return next(m["content"] for m in req["messages"] if m["role"] == "system"), {t["function"]["name"] for t in req["tools"]}


def test_tutor_chat_carries_prompt_and_tools(student):
    system, tools = chat(student, "tutor")
    assert "Cordell" in system and "Persistence" in system and "{{" not in system
    assert "age None" in system  # no birth date on the profile
    assert tools == {"list_mentors", "add_mentor", "remove_mentor"}


def test_reviewer_chat_carries_review_tools(student):
    system, tools = chat(student, "reviewer")
    assert "Cordell" in system and "mentor" in system and "Persistence" not in system
    assert tools == {"list_students", "list_student_chats", "view_student_chat"}
