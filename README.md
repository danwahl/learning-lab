# learning-lab (web)

Deployment glue for running the **learning-lab** tutor as a login-gated, ChatGPT-like web app, so a student can learn with AI instead of getting answers from it. The tutor is **Cord** carrying the learning-lab skills.

The skills and the identity are canonical elsewhere; this repo only renders them into an [Open WebUI](https://github.com/open-webui/open-webui) deployment:

- [`claude-plugins/plugins/learning-lab`](claude-plugins/plugins/learning-lab) (submodule): the tutor and technique skills, written for Claude Code.
- [`cordell/identity/current.txt`](cordell/identity/current.txt) (submodule): the Cord identity spec.

## Architecture

```
scandium (always-on Docker host)
├─ open-webui container  (compose.yaml, SQLite + uploads in a named volume)
│  ├─ model    = OpenRouter, one pinned model (~z-ai/glm-flash-latest)
│  ├─ presets  = Workspace Models "Tutor" (identity + tutor skill) and "Reviewer"
│  ├─ skills   = Workspace Skills, one per learning-lab technique
│  ├─ tools    = Workspace Tools: mentor consent, chat review (web/tools)
│  └─ memory   = Open WebUI per-user Memory (the learning plan lives here)
└─ tailscale funnel :10000 -> 127.0.0.1:3000   (public HTTPS, no open ports)
```

Open WebUI supplies login, roles, chat history, memory, KaTeX, and image upload. The only application code is two small tool modules.

## Layout

```
learning-lab/
├─ cordell/            # submodule: identity spec (danwahl/cordell)
├─ claude-plugins/     # submodule: skill sources (danwahl/claude-plugins)
├─ web/adaptations.md  # what changes when the skills run in a web chat
├─ web/reviewer.md     # system prompt for the mentor's Reviewer model
├─ web/tools/          # Open WebUI tools: mentors.py (consent), review.py (reading)
├─ web/icons/          # favicon, logo, splash, app and preset icons, mounted over the bundled ones
├─ tests/              # pytest against a throwaway instance with a stubbed model
├─ scripts/render.sh   # submodules + adaptations -> dist/ (system prompt, skills)
├─ scripts/seed.py     # configures a running instance from dist/ and .env
├─ compose.yaml        # the open-webui service
├─ .env.example        # settings by name; real secrets live in .env (gitignored)
└─ README.md
```

Clone with `--recurse-submodules` (or `git submodule update --init`).

## How the prompt is built

`scripts/render.sh` writes two things to `dist/` (gitignored):

- `system-prompt.md`: the identity spec, the `tutor` skill body, the learning-science reference, then `web/adaptations.md`, which overrides the parts of the skill text that assume a filesystem and a calendar. Persistence becomes Open WebUI's memory tools: the learning plan is one memory in the plugin's own `plans/<topic>.md` format, searched for at the start of every chat and ticked as steps complete.
- `reviewer-prompt.md`: the identity spec, then `web/reviewer.md`.
- `skills/<name>.md`: the five technique skills, frontmatter trimmed to `name` and `description`, bodies with the same substitutions. They attach to the Tutor model and load on demand; the student can also pick one with `$`.

A few harness-specific phrases are substituted in the script; anything else is overridden in prose in `adaptations.md`. Re-run after bumping either submodule, then `scripts/seed.py` to push the result.

## Setup

```bash
cp .env.example .env
sed -i "s/^WEBUI_SECRET_KEY=.*/WEBUI_SECRET_KEY=$(openssl rand -hex 32)/" .env
# fill in OPENAI_API_KEY, ADMIN_*, and STUDENT_* for a test account
# local run: set WEBUI_URL and CORS_ALLOW_ORIGIN to http://localhost:3000
#            and both *_COOKIE_SECURE to False
docker compose up -d
./scripts/render.sh
./scripts/seed.py
```

`seed.py` registers the admin (first account), points the OpenRouter connection at `TUTOR_MODEL` only, hides the base model from the picker, creates the skills, the tools, and the "Tutor" and "Reviewer" models readable by every user, makes Tutor the default, creates the `STUDENT_*` test account if set, and opens signup with new accounts pending. Every step creates or updates, so re-run it after a render. `--help` lists the flags (`--url`, `--env`).

Students sign up at the URL and wait until an admin sets them to "user" in Admin > Users. A student sees two models, no chat controls, no system-prompt or parameter editing, no code interpreter, notes, arena, web search or image generation. The admin can read all chats (`ENABLE_ADMIN_CHAT_ACCESS`, default true); tell the students.

## Mentors

Anyone with an account can be a mentor to anyone who lets them. A student tells Tutor "let dan@example.com review my chats"; Tutor confirms, then the `mentors` tool stores that email on their user record. The mentor picks the Reviewer model and asks about them by email; the `review` tool returns their chats only if their record lists the mentor, and only chats made with Tutor, so a mentor's own Reviewer chats stay hidden from whoever mentors them. "Remove dan@example.com" revokes it. Both checks are in `web/tools/review.py`, not in the prompt. Chats made with the old "cord" model are not reviewable. A mentor needs an approved account of their own.

## Tests

```bash
pip install pytest && pytest -q tests           # ~2 min; KEEP=1 leaves the instance up
docker compose -p learning-lab-test down -v     # removes it
```

The suite brings up a second compose project (`learning-lab-test`, port 3001) from `.env.example`, replaces OpenRouter with a stub inside the container (`tests/stub.py`: one model, a canned reply, a log of every request), renders and seeds it, and checks: seeding is idempotent, signup lands pending and approval unlocks the two presets, both tools and five skills, a chat turn reaches the model with the rendered prompt, the reasoning effort and the right tool specs, and the consent and leak checks in `web/tools` hold against chats created through the API. GitHub Actions runs it on every push (`.github/workflows/test.yml`). Nothing exercises a real model; that stays a manual check.

## Exposure (scandium)

`tailscale serve` already holds 443 and 8443 on scandium, tailnet-only. Funnel allows 443, 8443 and 10000, so the tutor gets 10000:

```bash
tailscale funnel --bg --https=10000 http://127.0.0.1:3000
tailscale funnel status
```

Public URL: `https://scandium.dinosaur-cloud.ts.net:10000` (matches `WEBUI_URL` and `CORS_ALLOW_ORIGIN` in `.env`). Funnel must be allowed for this node in the tailnet policy.

Security on that URL is: the login form, admin approval of new accounts, whatever passwords students pick (Open WebUI has no login rate limiting), and a spend limit on the OpenRouter key.

## Operations

```bash
docker compose pull && docker compose up -d       # after bumping the image tag in compose.yaml
docker compose logs -f
docker run --rm -v learning-lab_data:/data -v "$PWD":/backup alpine \
  tar czf /backup/learning-lab-data-$(date +%F).tgz -C /data .   # backup
```

Model swap: change `TUTOR_MODEL` in `.env`, re-run `seed.py`. New students: approve them in Admin > Users. Another skill: add it to the plugin, render, seed. Another tool: a file in `web/tools/` and its id in the right model's `toolIds` in `seed.py`.

## Branding

`WEBUI_NAME` sets the name (this version appends " (Open WebUI)"). The icons in `web/icons/` are bind-mounted read-only over the bundled ones in `compose.yaml`; the app recopies its own on every boot, so the mounts log a few harmless "Read-only file system" errors at startup. Tutor's avatar is the favicon; Reviewer's is a greyscale copy of it that `seed.py` embeds in the preset. To change the icon: `scripts/icons.py new.png` (needs Pillow), commit, deploy, then `docker compose up -d --force-recreate` so the mounts pick up the new files. Open WebUI's license allows rebranding for deployments with 50 or fewer users in a 30-day period.

## Open WebUI settings that matter

Env values are copied into the database on first boot and read from there afterwards (`ENABLE_PERSISTENT_CONFIG`); after that, change them in the admin UI or wipe the volume. `seed.py` sets its part through the API, so it applies any time. Two settings that are not obvious:

- `ENABLE_FOLLOW_UP_GENERATION=False`: follow-up chips are generated from the whole exchange and spell out the answer the tutor is withholding.
- `MEMORIES_CONTEXT_CHAR_LIMIT` / `MEMORIES_USER_CHAR_LIMIT=8000`: the plan does not fit the 2000-character default.
