#!/usr/bin/env python3
"""Generate web/icons from one square PNG: `scripts/icons.py path/to/icon.png`.
compose.yaml mounts the results over Open WebUI's bundled icons; after
changing them, `docker compose up -d --force-recreate`."""

import sys
from pathlib import Path

from PIL import Image

OUT = Path(__file__).resolve().parent.parent / "web" / "icons"
SIZES = {
    "favicon.png": 512, "favicon-96x96.png": 96, "logo.png": 500, "splash.png": 500, "splash-dark.png": 500,
    "apple-touch-icon.png": 180, "web-app-manifest-192x192.png": 192, "web-app-manifest-512x512.png": 512,
}

src = Image.open(sys.argv[1]).convert("RGBA")
for name, px in SIZES.items():
    src.resize((px, px), Image.LANCZOS).save(OUT / name, optimize=True)
src.resize((256, 256), Image.LANCZOS).save(OUT / "favicon.ico", sizes=[(s, s) for s in (16, 32, 48, 64, 128, 256)])
print(f"wrote {len(SIZES) + 1} icons to {OUT}")
