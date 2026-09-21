#!/usr/bin/env python3
"""Configure a fresh (or existing) Open WebUI instance for the tutor.

Idempotent: every step creates or updates. Run after `scripts/render.sh`.
Reads OPENAI_API_BASE_URL / OPENAI_API_KEY / TUTOR_MODEL / TTS_* / ADMIN_* / STUDENT_*
from .env (or the environment); passwords are prompted for when unset.

Steps, in order: admin account (signup on first boot, else signin) ->
OpenRouter connection restricted to TUTOR_MODEL -> base model hidden from the
picker but readable by every user -> skills from dist/skills -> tools from
web/tools -> workspace models "tutor" (rendered system prompt, memory, skills,
mentors tool; the default) and "reviewer" (reviewer prompt, review tool) ->
optional STUDENT_* test account -> read-aloud voice (TTS_MODEL on OpenRouter) ->
signup open, new accounts pending until an admin approves them.
"""

import argparse
import base64
import getpass
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DIST = REPO / "dist"
MODEL_ID = "tutor"
REVIEWER_ID = "reviewer"
# Model params for both presets; at the default effort the model thinks for about a minute per turn.
PARAMS = {"function_calling": "native", "reasoning_effort": "medium"}
TOOLS = REPO / "web" / "tools"
SUGGESTIONS = [
    "I want to learn how to factor quadratics",
    "Quiz me on what we did last time",
    "Here's my homework, can you check where I went wrong?",
    "Let me explain the chain rule back to you",
]


def load_env(path):
    """KEY=value lines from `path`; the process environment wins."""
    env = {}
    if path.exists():
        for line in path.read_text().splitlines():
            line = re.sub(r"(^|\s)#.*", "", line).strip()  # compose-style inline comments
            if "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    env.update({k: v for k, v in os.environ.items() if k.startswith(("ADMIN_", "STUDENT_", "TUTOR_", "TTS_", "OPENAI_"))})
    return env


class Api:
    def __init__(self, url):
        self.url = url.rstrip("/")
        self.token = None

    def call(self, method, path, body=None, missing=()):
        """JSON in, JSON out. Error codes in `missing` return None; others exit."""
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.url + path, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        if self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        try:
            with urllib.request.urlopen(req) as r:
                raw = r.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            if e.code in missing:
                return None
            sys.exit(f"{method} {path} -> {e.code}: {e.read().decode()[:300]}")

    def get(self, path, missing=()):
        return self.call("GET", path, missing=missing)

    def post(self, path, body):
        return self.call("POST", path, body)


def frontmatter(text):
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S) or sys.exit(f"no frontmatter in {text[:40]!r}")
    meta = {}
    key = None
    for line in m.group(1).splitlines():
        if re.match(r"^[a-z_-]+:", line):
            key, _, val = line.partition(":")
            meta[key] = val.strip().lstrip("|").strip()
        elif key:
            meta[key] += ("" if not meta[key] or meta[key].endswith("-") else " ") + line.strip()
    return meta, m.group(2)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--url", default="http://127.0.0.1:3000")
    p.add_argument("--env", default=REPO / ".env", type=Path)
    args = p.parse_args()
    env = load_env(args.env)

    model = env.get("TUTOR_MODEL") or sys.exit("TUTOR_MODEL not set")
    base_url = env.get("OPENAI_API_BASE_URL") or sys.exit("OPENAI_API_BASE_URL not set")
    api_key = env.get("OPENAI_API_KEY") or sys.exit("OPENAI_API_KEY not set")
    admin_email = env.get("ADMIN_EMAIL") or sys.exit("ADMIN_EMAIL not set")
    admin_pw = env.get("ADMIN_PASSWORD") or getpass.getpass(f"password for {admin_email}: ")
    system_prompt = (DIST / "system-prompt.md").read_text()

    api = Api(args.url)

    # 1. admin
    if api.get("/api/config").get("onboarding"):
        r = api.post("/api/v1/auths/signup", {"name": env.get("ADMIN_NAME") or "Admin", "email": admin_email, "password": admin_pw})
        print(f"registered admin {admin_email}")
    else:
        r = api.post("/api/v1/auths/signin", {"email": admin_email, "password": admin_pw})
    api.token = r["token"]
    if r.get("role") != "admin":
        sys.exit(f"{admin_email} is not an admin")

    # 2. provider connection, allowlisted to one model
    api.post("/openai/config/update", {
        "ENABLE_OPENAI_API": True,
        "OPENAI_API_BASE_URLS": [base_url],
        "OPENAI_API_KEYS": [api_key],
        "OPENAI_API_CONFIGS": {"0": {"enable": True, "connection_type": "external", "model_ids": [model]}},
    })
    print(f"connection {base_url} -> {model}")

    # 3. everything below is readable by every signed-in user
    grants = [{"principal_type": "user", "principal_id": "*", "permission": "read"}]
    for g in api.get("/api/v1/groups/"):
        if g["name"] == "students":  # earlier deployments scoped access to this group
            api.call("DELETE", f"/api/v1/groups/id/{g['id']}/delete")
            print("deleted the old students group")

    # 4. base model: readable (a preset needs its base), hidden from the picker
    def upsert_model(form):
        if api.get("/api/v1/models/model?id=" + urllib.parse.quote(form["id"]), missing=(404,)):
            api.post("/api/v1/models/model/update", form)
        else:
            api.post("/api/v1/models/create", form)
        api.post("/api/v1/models/model/access/update", {"id": form["id"], "access_grants": grants})

    upsert_model({"id": model, "base_model_id": None, "name": model, "meta": {"hidden": True}, "params": {}, "access_grants": grants})
    print(f"base model {model} hidden")

    # 5. skills
    skill_ids = []
    have = {s["id"] for s in api.get("/api/v1/skills/")}
    for path in sorted(DIST.glob("skills/*.md")):
        meta, body = frontmatter(path.read_text())
        sid = path.stem
        form = {"id": sid, "name": meta["name"], "description": meta.get("description"), "content": body.strip() + "\n", "access_grants": grants}
        if sid in have:
            api.post(f"/api/v1/skills/id/{sid}/update", form)
        else:
            api.post("/api/v1/skills/create", form)
        api.post(f"/api/v1/skills/id/{sid}/access/update", {"access_grants": grants})
        skill_ids.append(sid)
    print(f"skills: {', '.join(skill_ids)}")

    # 6. tools: the python in web/tools, one workspace tool per file
    tool_ids = []
    have = {t["id"] for t in api.get("/api/v1/tools/")}
    for path in sorted(TOOLS.glob("*.py")):
        tid = path.stem
        content = path.read_text()
        desc = re.search(r"^description: (.*)$", content, re.M)
        form = {"id": tid, "name": tid.capitalize(), "content": content, "meta": {"description": desc and desc.group(1)}, "access_grants": grants}
        api.post(f"/api/v1/tools/id/{tid}/update" if tid in have else "/api/v1/tools/create", form)
        api.post(f"/api/v1/tools/id/{tid}/access/update", {"access_grants": grants})
        tool_ids.append(tid)
    print(f"tools: {', '.join(tool_ids)}")

    # 7. the two presets
    capabilities = {"vision": True, "file_upload": True, "builtin_tools": True, "web_search": False, "image_generation": False, "code_interpreter": False}
    upsert_model({
        "id": MODEL_ID,
        "base_model_id": model,
        "name": "Tutor",
        "meta": {
            "description": "For students: learn a topic by working it out yourself, one hint at a time.",
            "capabilities": capabilities,
            "builtinTools": {"memory": True},
            "skillIds": skill_ids,
            "toolIds": ["mentors"],
            "suggestion_prompts": [{"content": s} for s in SUGGESTIONS],
        },
        "params": {"system": system_prompt, **PARAMS},
        "access_grants": grants,
    })
    upsert_model({
        "id": REVIEWER_ID,
        "base_model_id": model,
        "name": "Reviewer",
        "meta": {
            "description": "For mentors: read and analyze the tutoring chats of your students.",
            "profile_image_url": "data:image/png;base64," + base64.b64encode((REPO / "web" / "icons" / "reviewer.png").read_bytes()).decode(),
            "capabilities": {**capabilities, "builtin_tools": False},
            "toolIds": ["review"],
            "suggestion_prompts": [{"content": "What did my student work on this week?"}],
        },
        "params": {"system": (DIST / "reviewer-prompt.md").read_text(), **PARAMS},
        "access_grants": grants,
    })
    for old in ("cord", "review"):  # earlier names of the two presets
        if api.get(f"/api/v1/models/model?id={old}", missing=(404,)):
            api.post("/api/v1/models/model/delete", {"id": old})
            print(f"deleted the old {old} preset")
    cfg = api.get("/api/v1/configs/models")
    cfg["DEFAULT_MODELS"] = MODEL_ID
    api.post("/api/v1/configs/models", cfg)
    print(f"models {MODEL_ID} (default, {len(system_prompt.split())} words of system prompt) and {REVIEWER_ID}, base {model}")

    # 8. optional test student, already approved
    student_email = env.get("STUDENT_EMAIL")
    if student_email:
        users = api.get("/api/v1/users/search?query=" + urllib.parse.quote(student_email))["users"]
        if not any(u["email"] == student_email.lower() for u in users):
            pw = env.get("STUDENT_PASSWORD") or getpass.getpass(f"password for {student_email}: ")
            api.post("/api/v1/auths/add", {"name": env.get("STUDENT_NAME") or "Student", "email": student_email, "password": pw, "role": "user"})
            print(f"created user {student_email}")

    # 9. read-aloud voice through the same OpenRouter key; TTS_MODEL empty means the browser's own voices
    tts_model = env.get("TTS_MODEL")
    audio = api.get("/api/v1/audio/config")
    if tts_model:
        audio["tts"].update({"ENGINE": "openai", "OPENAI_API_BASE_URL": base_url, "OPENAI_API_KEY": api_key, "MODEL": tts_model,
                             "VOICE": env.get("TTS_VOICE", ""), "OPENAI_PARAMS": {"response_format": "mp3"}})  # OpenRouter defaults to pcm, which the browser cannot play
    else:
        audio["tts"]["ENGINE"] = ""
    api.post("/api/v1/audio/config/update", audio)
    print(f"tts {tts_model or 'browser'}")

    # 10. the door: anyone can sign up, nobody gets in until an admin approves
    admin = api.get("/api/v1/auths/admin/config")
    admin.update({"ENABLE_SIGNUP": True, "DEFAULT_USER_ROLE": "pending"})
    api.post("/api/v1/auths/admin/config", admin)
    print("signup open, new accounts pending")


if __name__ == "__main__":
    main()
