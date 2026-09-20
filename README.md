# learning-lab (web)

Deployment glue for running the **learning-lab** tutor as a login-gated,
ChatGPT-like web app, so a student can learn with AI instead of getting answers
from it. The tutor is **Cord** carrying the learning-lab skills.

The skills and the identity are canonical elsewhere; this repo only renders
them into an [Open WebUI](https://github.com/open-webui/open-webui) deployment:

- [`claude-plugins/plugins/learning-lab`](claude-plugins/plugins/learning-lab)
  (submodule): the tutor and technique skills, written for Claude Code.
- [`cordell/identity/current.txt`](cordell/identity/current.txt) (submodule):
  the Cord identity spec.

## Architecture

```
scandium (always-on Docker host)
├─ open-webui container  (compose.yaml, SQLite + uploads in a named volume)
│  ├─ model    = OpenRouter, one pinned model (~z-ai/glm-flash-latest)
│  ├─ presets  = Workspace Models "Tutor" (identity + tutor skill) and "Review"
│  ├─ skills   = Workspace Skills, one per learning-lab technique
│  ├─ tools    = Workspace Tools: mentor consent, chat review (web/tools)
│  └─ memory   = Open WebUI per-user Memory (the learning plan lives here)
└─ tailscale funnel :10000 -> 127.0.0.1:3000   (public HTTPS, no open ports)
```

Open WebUI supplies login, roles, chat history, memory, KaTeX, and image upload.
The only application code is two small tool modules.

## Layout

```
learning-lab/
├─ cordell/            # submodule: identity spec (danwahl/cordell)
├─ claude-plugins/     # submodule: skill sources (danwahl/claude-plugins)
├─ web/adaptations.md  # what changes when the skills run in a web chat
├─ web/review.md       # system prompt for the mentor's Review model
├─ web/tools/          # Open WebUI tools: mentors.py (consent), review.py (reading)
├─ scripts/render.sh   # submodules + adaptations -> dist/ (system prompt, skills)
├─ scripts/seed.py     # configures a running instance from dist/ and .env
├─ compose.yaml        # the open-webui service
├─ .env.example        # settings by name; real secrets live in .env (gitignored)
└─ README.md
```

Clone with `--recurse-submodules` (or `git submodule update --init`).

## How the prompt is built

`scripts/render.sh` writes two things to `dist/` (gitignored):

- `system-prompt.md`: the identity spec, the `tutor` skill body, the
  learning-science reference, then `web/adaptations.md`, which overrides the
  parts of the skill text that assume a filesystem and a calendar. Persistence
  becomes Open WebUI's memory tools: the learning plan is one memory in the
  plugin's own `plans/<topic>.md` format, searched for at the start of every
  chat and ticked as steps complete.
- `review-prompt.md`: the identity spec, then `web/review.md`.
- `skills/<name>.md`: the five technique skills, frontmatter trimmed to
  `name` and `description`, bodies with the same substitutions. They attach to
  the Tutor model and load on demand; the student can also pick one with `$`.

A few harness-specific phrases are substituted in the script; anything else
is overridden in prose in `adaptations.md`. Re-run after bumping either
submodule, then `scripts/seed.py` to push the result.

## Setup

```bash
cp .env.example .env
sed -i "s/^WEBUI_SECRET_KEY=.*/WEBUI_SECRET_KEY=$(openssl rand -hex 32)/" .env
# fill in OPENAI_API_KEY, ADMIN_*, STUDENT_*
# local run: set WEBUI_URL and CORS_ALLOW_ORIGIN to http://localhost:3000
#            and both *_COOKIE_SECURE to False
docker compose up -d
./scripts/render.sh
./scripts/seed.py
```

`seed.py` registers the admin (first account), points the OpenRouter
connection at `TUTOR_MODEL` only, hides the base model from the picker while
keeping it readable by the `students` group, creates the skills, the tools,
and the "Tutor" and "Review" models, makes Tutor the default, creates the
student in the group, and turns signup off. Every step creates or
updates, so re-run it after a render. `--help` lists the flags (`--url`,
`--env`, `--keep-signup-open`).

The student sees a login form (no signup), two models, no chat controls,
no system-prompt or parameter editing, no code interpreter, notes, arena, web
search or image generation. The admin can read all chats
(`ENABLE_ADMIN_CHAT_ACCESS`, default true); tell the student.

## Mentors

Anyone with an account can be a mentor to anyone who lets them. A student
tells Tutor "let dan@example.com review my chats"; Tutor confirms, then the
`mentors` tool stores that email on her user record. The mentor picks the
Review model and asks about her by email; the `review` tool returns her
chats only if her record lists the mentor, and only chats made with Tutor,
so a mentor's own Review chats stay hidden from whoever mentors them.
"Remove dan@example.com" revokes it. Both checks are in
`web/tools/review.py`, not in the prompt. Chats made with the old "cord"
model are not reviewable. More accounts: Admin > Users, then add them to
`students`.

## Exposure (scandium)

`tailscale serve` already holds 443 and 8443 on scandium, tailnet-only. Funnel
allows 443, 8443 and 10000, so the tutor gets 10000:

```bash
tailscale funnel --bg --https=10000 http://127.0.0.1:3000
tailscale funnel status
```

Public URL: `https://scandium.dinosaur-cloud.ts.net:10000` (matches `WEBUI_URL`
and `CORS_ALLOW_ORIGIN` in `.env`). Funnel must be allowed for this node in
the tailnet policy.

Security on that URL is: the login form, signup off, a long student password
(Open WebUI has no login rate limiting), and a spend limit on the OpenRouter key.

## Operations

```bash
docker compose pull && docker compose up -d       # after bumping the image tag in compose.yaml
docker compose logs -f
docker run --rm -v learning-lab_data:/data -v "$PWD":/backup alpine \
  tar czf /backup/learning-lab-data-$(date +%F).tgz -C /data .   # backup
```

Model swap: change `TUTOR_MODEL` in `.env`, re-run `seed.py`. Another
student: change `STUDENT_*` in `.env` and re-run, or Admin > Users, then add
to `students`. Another skill: add it to the plugin, render, seed. Another
tool: a file in `web/tools/` and its id in the right model's `toolIds` in
`seed.py`.

## Open WebUI settings that matter

Env values are copied into the database on first boot and read from there
afterwards (`ENABLE_PERSISTENT_CONFIG`); after that, change them in the admin UI
or wipe the volume. `seed.py` sets its part through the API, so it applies any
time. Two settings that are not obvious:

- `ENABLE_FOLLOW_UP_GENERATION=False`: follow-up chips are generated from the
  whole exchange and spell out the answer the tutor is withholding.
- `MEMORIES_CONTEXT_CHAR_LIMIT` / `MEMORIES_USER_CHAR_LIMIT=8000`: the plan
  does not fit the 2000-character default.
