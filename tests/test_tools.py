"""The consent and leak checks in web/tools, exercised as the deployed tool
code inside the container, against chats created through the API."""

import json

from conftest import in_container

CASES = r'''
import asyncio, json, os
from open_webui.models.tools import Tools as ToolsTable
from open_webui.models.users import Users

async def main():
    p = json.loads(os.environ["CASES"])
    async def load(tid):
        ns = {}
        exec((await ToolsTable.get_tool_by_id(tid)).content, ns)
        return ns["Tools"]()
    mentors, review = await load("mentors"), await load("review")
    S, M, O = [(await Users.get_user_by_email(p[k])).model_dump() for k in ("student", "mentor", "other")]

    # before consent
    assert "has not added you" in await review.list_student_chats(S["email"], 7, M)
    assert "not reviewable" in await review.view_student_chat(p["tutor_chat"], M)
    assert "own address" in await mentors.add_mentor(S["email"], S)
    assert "No account" in await mentors.add_mentor("nobody@example.com", S)

    # consent, stored lowercase whatever the learner typed
    assert await mentors.add_mentor(M["email"].upper(), S) == "Mentors: " + M["email"]
    assert await mentors.list_mentors(S) == "Mentors: " + M["email"]
    listing = await review.list_student_chats(S["email"], 7, M)
    assert p["tutor_chat"] in listing
    assert p["reviewer_chat"] not in listing and p["mixed_chat"] not in listing
    assert "user: what is 2+2" in await review.view_student_chat(p["tutor_chat"], M)
    assert "not reviewable" in await review.view_student_chat(p["reviewer_chat"], M)
    assert "not reviewable" in await review.view_student_chat(p["mixed_chat"], M)
    assert "has not added you" in await review.list_student_chats(S["email"], 7, O)

    # revocation
    assert await mentors.remove_mentor(M["email"], S) == "Mentors: none"
    assert "has not added you" in await review.list_student_chats(S["email"], 7, M)
    assert "not reviewable" in await review.view_student_chat(p["tutor_chat"], M)
    print("ok")

asyncio.run(main())
'''


def chat(api, title, models):
    """A two-message chat in Open WebUI's shape: `models[0]` is the chat's model, `models[-1]` the one that answered."""
    msgs = {
        "u": {"id": "u", "parentId": None, "childrenIds": ["a"], "role": "user", "content": "what is 2+2"},
        "a": {"id": "a", "parentId": "u", "childrenIds": [], "role": "assistant", "content": "what do you think?", "model": models[-1]},
    }
    form = {"chat": {"title": title, "models": models[:1], "history": {"currentId": "a", "messages": msgs}, "messages": list(msgs.values())}}
    return api.post("/api/v1/chats/new", form)["id"]


def test_consent_and_leak_checks(approved_user):
    s, m, o = approved_user("student1"), approved_user("mentor1"), approved_user("other1")
    cases = {
        "student": "student1@example.com", "mentor": "mentor1@example.com", "other": "other1@example.com",
        "tutor_chat": chat(s, "Quadratics", ["tutor"]),
        "reviewer_chat": chat(s, "About someone else", ["reviewer"]),
        "mixed_chat": chat(s, "Switched models", ["tutor", "reviewer"]),
    }
    out = in_container("env", "CASES=" + json.dumps(cases), "python3", "-", input=CASES)
    assert out.strip() == "ok"
