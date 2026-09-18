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
│  ├─ preset   = Workspace Model "Cord": identity + tutor skill as system prompt
│  ├─ skills   = Workspace Skills, one per learning-lab technique
│  └─ memory   = Open WebUI per-user Memory (the learning plan lives here)
└─ tailscale funnel :10000 -> 127.0.0.1:3000   (public HTTPS, no open ports)
```

Open WebUI supplies login, roles, chat history, memory, KaTeX, and image upload.
There is no application code here.

## Layout

```
learning-lab/
├─ cordell/            # submodule: identity spec (danwahl/cordell)
├─ claude-plugins/     # submodule: skill sources (danwahl/claude-plugins)
├─ compose.yaml        # the open-webui service
├─ .env.example        # settings by name; real secrets live in .env (gitignored)
└─ README.md
```

Clone with `--recurse-submodules` (or `git submodule update --init`).

## Quick start (local)

```bash
cp .env.example .env
sed -i "s/^WEBUI_SECRET_KEY=.*/WEBUI_SECRET_KEY=$(openssl rand -hex 32)/" .env
# fill in OPENAI_API_KEY; set WEBUI_URL and CORS_ALLOW_ORIGIN to http://localhost:3000
docker compose up -d
```

Then http://localhost:3000 shows the login page. The first account registered is the admin.
