"""OpenAI-compatible stub for tests: one model, a canned reply, and a log of
every chat request. Runs inside the Open WebUI container."""

import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

MODEL = sys.argv[1]
LOG = "/tmp/stub-requests.jsonl"
REPLY = "stub reply"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, body, content_type="application/json"):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # /models
        self.send(json.dumps({"object": "list", "data": [{"id": MODEL, "object": "model"}]}).encode())

    def do_POST(self):  # /chat/completions
        req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        with open(LOG, "a") as f:
            f.write(json.dumps(req) + "\n")
        if req.get("stream"):
            chunks = [
                {"id": "stub", "object": "chat.completion.chunk", "model": MODEL, "choices": [{"index": 0, "delta": {"role": "assistant", "content": REPLY}, "finish_reason": None}]},
                {"id": "stub", "object": "chat.completion.chunk", "model": MODEL, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
            ]
            body = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"
            self.send(body.encode(), "text/event-stream")
        else:
            self.send(json.dumps({
                "id": "stub", "object": "chat.completion", "model": MODEL,
                "choices": [{"index": 0, "message": {"role": "assistant", "content": REPLY}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            }).encode())


HTTPServer(("127.0.0.1", 8081), Handler).serve_forever()
