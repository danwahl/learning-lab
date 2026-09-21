"""A throwaway Open WebUI instance (compose project learning-lab-test, port
3001) seeded from .env.example with an in-container OpenAI stub in place of
OpenRouter. KEEP=1 leaves it running after the tests."""

import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
from seed import Api, load_env  # noqa: E402

PROJECT = "learning-lab-test"
PORT = "3001"
URL = f"http://127.0.0.1:{PORT}"
ENV = REPO / "tests" / ".env"
MODEL = "stub-model"
ADMIN = ("admin@example.com", "admin-password-for-tests")
STUDENT = ("student@example.com", "student-password-for-tests")
SEED_KEYS = ("ADMIN_", "STUDENT_", "TUTOR_", "TTS_", "OPENAI_")  # seed.py reads these from the environment too
CLEAN_ENV = {k: v for k, v in os.environ.items() if not k.startswith(SEED_KEYS)}
OVERRIDES = {
    "WEBUI_SECRET_KEY": "not-a-secret",
    "OPENAI_API_KEY": "stub",
    "OPENAI_API_BASE_URL": "http://127.0.0.1:8081/v1",
    "TTS_MODEL": "hexgrad/kokoro-82m",
    "WEBUI_URL": URL, "CORS_ALLOW_ORIGIN": URL,
    "WEBUI_SESSION_COOKIE_SECURE": "False", "WEBUI_AUTH_COOKIE_SECURE": "False",
    "TUTOR_MODEL": MODEL,
    "ADMIN_NAME": "Admin", "ADMIN_EMAIL": ADMIN[0], "ADMIN_PASSWORD": ADMIN[1],
    "STUDENT_NAME": "Student", "STUDENT_EMAIL": STUDENT[0], "STUDENT_PASSWORD": STUDENT[1],
}


def sh(*cmd, **kw):
    r = subprocess.run(cmd, cwd=REPO, text=True, capture_output=True, **kw)
    if r.returncode:
        pytest.fail(f"{' '.join(cmd[:3])} exited {r.returncode}:\n{r.stderr}", pytrace=False)
    return r.stdout


def compose(*args):
    env = {**os.environ, "COMPOSE_PROJECT_NAME": PROJECT, "PORT": PORT, "ENV_FILE": str(ENV)}
    return sh("docker", "compose", *args, env=env)


def in_container(*cmd, **kw):
    return sh("docker", "exec", "-i", PROJECT, *cmd, **kw)


def seed():
    return sh(sys.executable, "scripts/seed.py", "--url", URL, "--env", str(ENV), env=CLEAN_ENV)


def signin(email, password):
    api = Api(URL)
    api.token = api.post("/api/v1/auths/signin", {"email": email, "password": password})["token"]
    return api


@pytest.fixture(scope="session")
def instance():
    env = {k: v for k, v in load_env(REPO / ".env.example").items() if not k.startswith(SEED_KEYS)}
    ENV.write_text("".join(f"{k}={v}\n" for k, v in {**env, **OVERRIDES}.items()))
    try:
        compose("up", "-d")
        sh("docker", "cp", str(REPO / "tests" / "stub.py"), f"{PROJECT}:/tmp/stub.py")
        sh("docker", "exec", "-d", PROJECT, "python3", "/tmp/stub.py", MODEL)  # up before the first model-list fetch
        for _ in range(300):
            try:
                urllib.request.urlopen(URL + "/health", timeout=5)
                break
            except OSError:  # URLError and HTTPError included
                time.sleep(1)
        else:
            pytest.fail("open-webui did not come up:\n" + compose("logs", "--tail", "30"), pytrace=False)
        sh(str(REPO / "scripts" / "render.sh"))
        seed()
        yield
    finally:
        if not os.environ.get("KEEP"):
            compose("down", "-v")


@pytest.fixture(scope="session")
def admin(instance):
    return signin(*ADMIN)


@pytest.fixture(scope="session")
def student(instance):
    return signin(*STUDENT)


@pytest.fixture(scope="session")
def approved_user(admin):
    """A factory: sign a new person up and approve them, as an admin would."""
    def make(name):
        email = f"{name}@example.com"
        r = Api(URL).post("/api/v1/auths/signup", {"name": name, "email": email, "password": "a-long-test-password"})
        admin.post(f"/api/v1/users/{r['id']}/update", {"role": "user"})
        return signin(email, "a-long-test-password")
    return make
