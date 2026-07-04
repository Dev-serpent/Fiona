#!/usr/bin/env python3
"""Fiona Flask frontend — server-rendered pages replacing the JS SPA.

Usage:
    python fionaLocalPages/server/flask_app.py [--port 5000] [--host 0.0.0.0]
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

import flask

# ---------------------------------------------------------------------------
# Ensure the project root is on sys.path so all Fiona modules are importable.
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_PACKAGE_ROOT = Path(__file__).resolve().parent  # fionaLocalPages/server/
_PACKAGE_PARENT = _PACKAGE_ROOT.parent  # fionaLocalPages/
if str(_PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(_PACKAGE_PARENT))

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("fiona.flask")

# ---------------------------------------------------------------------------
# Flask Application
# ---------------------------------------------------------------------------

app = flask.Flask(
    __name__,
    static_folder=str(_PACKAGE_PARENT),        # serves from fionaLocalPages/
    static_url_path="",                          # /css/... → fionaLocalPages/css/...
    template_folder=str(_PACKAGE_PARENT / "templates_jinja"),
)

app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0  # dev only

# ---------------------------------------------------------------------------
# ── Templates ───────────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------

# Ensure templates_jinja directory exists
_jinja_dir = _PACKAGE_PARENT / "templates_jinja"
_jinja_dir.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# ── Import page route modules ──────────────────────────────────────────────
# ---------------------------------------------------------------------------

# Each route module registers its routes with the app
from fionaLocalPages.server.flask_routes import register_routes

register_routes(app)

# ---------------------------------------------------------------------------
# ── Health endpoint (for connection indicator) ──────────────────────────────
# ---------------------------------------------------------------------------

@app.route("/api/v1/health")
def health():
    return flask.jsonify({"ok": True, "version": "0.1.0", "server": "flask"})

# ---------------------------------------------------------------------------
# ── Main ────────────────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Fiona Flask Frontend")
    parser.add_argument("--port", type=int, default=5000, help="Port to bind")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host to bind")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    args = parser.parse_args()

    logger.info(
        "Starting Fiona Flask frontend on http://%s:%d",
        args.host,
        args.port,
    )
    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
