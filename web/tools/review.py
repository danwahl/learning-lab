"""
title: Review
description: Lets a mentor read the tutoring chats of students who added them.
"""

import time

from open_webui.models.chats import Chats
from open_webui.models.users import Users

TUTOR_MODEL = "tutor"
DAY = 86400


def _consented(student, mentor_email):
    return mentor_email.lower() in (student.info or {}).get("mentors", [])


def _tutor_only(chat):
    """True when every model that spoke in this chat is the tutor.

    Chats made with the reviewer model hold other students' transcripts and must
    never be reviewable, whoever owns them."""
    data = chat.chat or {}
    models = set(data.get("models") or [])
    for m in (data.get("history", {}).get("messages") or {}).values():
        if m.get("model"):
            models.add(m["model"])
    return models == {TUTOR_MODEL}


def _messages(chat):
    history = chat.chat.get("history", {})
    msgs, cur, seen = [], history.get("currentId"), set()
    while cur and cur not in seen:
        seen.add(cur)
        m = history.get("messages", {}).get(cur)
        if not m:
            break
        msgs.append(f"{m.get('role', '')}: {m.get('content', '')}")
        cur = m.get("parentId")
    return "\n\n".join(reversed(msgs))


class Tools:
    async def list_students(self, __user__: dict = None) -> str:
        """
        List the students who added you as a mentor, as `Name <email>`.
        """
        users = (await Users.get_users())["users"]
        students = sorted(f"{u.name} <{u.email}>" for u in users if _consented(u, __user__["email"]))
        return "\n".join(students) or "No student has added you as a mentor yet."

    async def list_student_chats(self, student_email: str, since_days: int = 7, __user__: dict = None) -> str:
        """
        List a student's recent tutoring chats. Works only for students who
        added you as a mentor.

        :param student_email: The student's login email.
        :param since_days: How many days back to look.
        """
        student = await Users.get_user_by_email(student_email.strip())
        if not student or not _consented(student, __user__["email"]):
            return f"{student_email} has not added you as a mentor."
        since = int(time.time()) - since_days * DAY
        chats = await Chats.get_chats_by_user_id(student.id, filter={"updated_at": since}, limit=100)
        lines = [
            f"{c.id}  {time.strftime('%Y-%m-%d', time.localtime(c.updated_at))}  {c.title}"
            for c in chats.items
            if _tutor_only(c)
        ]
        return "\n".join(lines) or f"No tutoring chats in the last {since_days} days."

    async def view_student_chat(self, chat_id: str, __user__: dict = None) -> str:
        """
        Read one of a student's tutoring chats, from an id returned by
        list_student_chats.

        :param chat_id: The chat id.
        """
        chat = await Chats.get_chat_by_id(chat_id.strip())
        student = chat and await Users.get_user_by_id(chat.user_id)
        if not student or not _consented(student, __user__["email"]) or not _tutor_only(chat):
            return "Chat not found or not reviewable."
        return f"# {chat.title}\n\n{_messages(chat)}"
