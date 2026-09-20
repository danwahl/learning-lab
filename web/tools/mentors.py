"""
title: Mentors
description: Lets a student choose who may review their tutoring chats.
"""

from open_webui.models.users import Users


async def _mentors(user_id):
    user = await Users.get_user_by_id(user_id)
    return list((user.info or {}).get("mentors", []))


async def _save(user_id, mentors):
    user = await Users.get_user_by_id(user_id)
    await Users.update_user_by_id(user_id, {"info": {**(user.info or {}), "mentors": mentors}})
    return "Mentors: " + (", ".join(mentors) or "none")


class Tools:
    async def list_mentors(self, __user__: dict) -> str:
        """
        List the people allowed to review this learner's tutoring chats.
        """
        return "Mentors: " + (", ".join(await _mentors(__user__["id"])) or "none")

    async def add_mentor(self, email: str, __user__: dict) -> str:
        """
        Allow a person to review all of this learner's tutoring chats. Confirm
        with the learner before calling: the mentor will be able to read every
        chat they have with the tutor, past and future, until removed.

        :param email: The mentor's login email on this site.
        """
        email = email.strip().lower()
        if email == __user__["email"].lower():
            return "That is your own address."
        if not await Users.get_user_by_email(email):
            return f"No account for {email}; the mentor needs an account here first."
        mentors = await _mentors(__user__["id"])
        if email not in mentors:
            mentors.append(email)
        return await _save(__user__["id"], mentors)

    async def remove_mentor(self, email: str, __user__: dict) -> str:
        """
        Stop a person from reviewing this learner's tutoring chats.

        :param email: The mentor's login email.
        """
        email = email.strip().lower()
        mentors = [m for m in await _mentors(__user__["id"]) if m != email]
        return await _save(__user__["id"], mentors)
