"""Flask route registrations for all migrated pages.

Each page gets a route handler that:
1. Fetches data (via direct Python import from handler modules)
2. Renders a Jinja2 template with the data
3. Returns the rendered HTML
"""

from __future__ import annotations

import logging
from typing import Any, Callable

import flask

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Route registry — maps path → (template_name, data_fn, title)
# ---------------------------------------------------------------------------
# Each entry:
#   path: URL path
#   template: Jinja2 template filename (in templates_jinja/)
#   data_fn: function that returns dict of template variables
#   title: Display title for the page
#   breadcrumb: Breadcrumb text (defaults to title)

PageRoute = dict[str, Any]
_route_table: list[PageRoute] = []


def _page(path: str, template: str, title: str, data_fn: Callable[[], dict] | None = None, **extra) -> None:
    """Register a page route."""
    _route_table.append({
        "path": path,
        "template": template,
        "title": title,
        "data_fn": data_fn,
        "breadcrumb": extra.get("breadcrumb", title),
        "status_module": extra.get("status_module", title),
    })


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------

def register_routes(app: flask.Flask) -> None:
    """Register all page routes on the Flask app."""

    # ── Define page data-fetching functions ──────────────────────────────
    # Each function returns a dict of extra template variables.

    def _no_data() -> dict:
        return {}

    def _dashboard_data() -> dict:
        out = {"data": {}, "metrics": {}, "notifications_summary": {}}
        try:
            from fionaLocalPages.server.handlers.system import system_status, system_metrics
            status = _call_handler(system_status, {})
            if isinstance(status, dict) and status.get("ok"): out["data"] = status.get("data", {})
            metrics = _call_handler(system_metrics, {})
            if isinstance(metrics, dict) and metrics.get("ok"): out["metrics"] = metrics.get("data", {})
        except Exception as e:
            logger.warning("Dashboard data unavailable: %s", e)
        try:
            from fionaLocalPages.server.handlers.notifications_handler import list_notifications
            n = _call_handler(list_notifications, {})
            if isinstance(n, dict) and n.get("ok"): out["notifications_summary"] = n.get("data", {})
        except Exception:
            pass
        return out

    def _desktop_data() -> dict:
        data = {"active_data": {}, "resources": {}, "applications": [], "processes": []}
        try:
            from fionaLocalPages.server.handlers.desktop import desktop_active, desktop_system_resources, desktop_applications, desktop_processes
            act = _call_handler(desktop_active, {})
            if isinstance(act, dict): data["active_data"] = act
            res = _call_handler(desktop_system_resources, {})
            if isinstance(res, dict) and res.get("ok"): data["resources"] = res.get("data", {})
            apps = _call_handler(desktop_applications, {})
            if isinstance(apps, dict) and apps.get("ok"): data["applications"] = apps.get("data", [])
            procs = _call_handler(desktop_processes, {})
            if isinstance(procs, dict) and procs.get("ok"): data["processes"] = procs.get("data", [])
        except Exception as e:
            logger.warning("Desktop data unavailable: %s", e)
        return data

    def _tasks_data() -> dict:
        try:
            from fionaLocalPages.server.handlers.tasks import list_tasks
            result = _call_handler(list_tasks, {})
            if isinstance(result, dict) and result.get("ok"):
                return {"tasks": result.get("data", [])}
        except Exception as e:
            logger.warning("Tasks data unavailable: %s", e)
        return {"tasks": []}

    def _notifications_data() -> dict:
        try:
            from fionaLocalPages.server.handlers.notifications_handler import list_notifications
            result = _call_handler(list_notifications, {})
            if isinstance(result, dict) and result.get("ok"):
                nd = result.get("data", {})
                return {"notifications": nd}
        except Exception as e:
            logger.warning("Notifications data unavailable: %s", e)
        return {"notifications": {"items": [], "total": 0, "unread": 0}}

    def _actions_data() -> dict:
        try:
            from fionaLocalPages.server.handlers.actions import list_actions
            result = _call_handler(list_actions, {})
            if isinstance(result, dict) and result.get("ok"):
                return {"actions": result.get("data", [])}
        except Exception as e:
            logger.warning("Actions data unavailable: %s", e)
        return {"actions": []}

    def _agents_data() -> dict:
        try:
            from fionaLocalPages.server.handlers.agents_crud import list_agents
            result = _call_handler(list_agents, {})
            if isinstance(result, dict) and result.get("ok"):
                return {"agents": result.get("data", [])}
        except Exception as e:
            logger.warning("Agents data unavailable: %s", e)
        return {"agents": []}

    def _settings_data() -> dict:
        try:
            from fionaLocalPages.server.handlers.settings_handler import get_settings
            result = _call_handler(get_settings, {})
            if isinstance(result, dict) and result.get("ok"):
                return {"settings": result.get("data", {})}
        except Exception as e:
            logger.warning("Settings data unavailable: %s", e)
        return {"settings": {}}

    # ── Chat data — sessions + messages ─────────────────────────────────
    def _chat_data() -> dict:
        sessions = []
        messages = []
        try:
            # Try to get sessions via direct import
            from FionaCore.memory import load_session_list
            raw = load_session_list()
            if raw:
                sessions = [{"id": s.get("id", ""), "title": s.get("title", "Untitled"),
                             "created_at": s.get("created_at", ""), "message_count": len(s.get("messages", []))}
                            for s in raw[:20]]
                if sessions:
                    sid = sessions[0]["id"]
                    from FionaCore.memory import load_session
                    session = load_session(sid)
                    if session:
                        msgs = session.get("messages", [])
                        messages = [{"id": m.get("id", ""), "role": m.get("role", "user"),
                                     "content": m.get("content", ""), "created_at": m.get("created_at", "")}
                                    for m in msgs[-20:]]
        except Exception as e:
            logger.warning("Chat data unavailable: %s", e)
        return {"sessions": sessions, "messages": messages, "active_session_id": sessions[0]["id"] if sessions else None}

    def _terminal_data() -> dict:
        return {}  # Static shell, data handled by JS

    def _macros_data() -> dict:
        try:
            from fionaLocalPages.server.handlers.macros import list_macros
            result = _call_handler(list_macros, {})
            if isinstance(result, dict) and result.get("ok"):
                return {"macros": result.get("data", [])}
        except Exception as e:
            logger.warning("Macros data unavailable: %s", e)
        return {"macros": []}

    def _bindings_data() -> dict:
        try:
            from fionaLocalPages.server.handlers.bindings import list_bindings
            result = _call_handler(list_bindings, {})
            if isinstance(result, dict) and result.get("ok"):
                return {"bindings": result.get("data", [])}
        except Exception as e:
            logger.warning("Bindings data unavailable: %s", e)
        return {"bindings": []}

    def _voice_data() -> dict:
        try:
            from fionaLocalPages.server.handlers.voice import voice_transcribe
            # Just check if handler loads — voice is a POST-only feature
            return {"voice_available": True}
        except Exception as e:
            logger.warning("Voice data unavailable: %s", e)
            return {"voice_available": False}

    def _recall_data() -> dict:
        try:
            from fionaLocalPages.server.handlers.recall import recall_search
            result = _call_handler(recall_search, {"q": ""})
            items = []
            if isinstance(result, dict) and result.get("ok"):
                items = result.get("data", [])
            try:
                from RecallVault import recall_stats
                stats = recall_stats()
            except Exception:
                stats = {}
            return {"recall_items": items, "recall_stats": stats}
        except Exception as e:
            logger.warning("Recall data unavailable: %s", e)
        return {"recall_items": [], "recall_stats": {}}

    def _logs_data() -> dict:
        try:
            from fionaLocalPages.server.handlers.system import system_metrics
            result = _call_handler(system_metrics, {})
            if isinstance(result, dict) and result.get("ok"):
                return {"metrics": result.get("data", {})}
        except Exception as e:
            logger.warning("Logs data unavailable: %s", e)
        return {"metrics": {}}

    def _camcoms_data() -> dict:
        try:
            from fionaLocalPages.server.handlers.camcoms import camcoms_status
            result = _call_handler(camcoms_status, {})
            if isinstance(result, dict) and result.get("ok"):
                return {"camcoms_status": result.get("data", {})}
        except Exception as e:
            logger.warning("CamComs data unavailable: %s", e)
        return {"camcoms_status": {}}

    def _workspace_data() -> dict:
        try:
            from fionaLocalPages.server.handlers.desktop import desktop_workspaces
            result = _call_handler(desktop_workspaces, {})
            if isinstance(result, dict) and result.get("ok"):
                return {"workspaces": result.get("data", [])}
        except Exception as e:
            logger.warning("Workspace data unavailable: %s", e)
        return {"workspaces": []}

    def _plugins_data() -> dict:
        try:
            from fionaLocalPages.server.handlers.plugins import list_plugins
            result = _call_handler(list_plugins, {})
            if isinstance(result, dict) and result.get("ok"):
                return {"plugins": result.get("data", [])}
        except Exception as e:
            logger.warning("Plugins data unavailable: %s", e)
        return {"plugins": []}

    def _config_data() -> dict:
        try:
            from fionaLocalPages.server.handlers.config import list_configs
            result = _call_handler(list_configs, {})
            if isinstance(result, dict) and result.get("ok"):
                return {"configs": result.get("data", [])}
        except Exception as e:
            logger.warning("Config data unavailable: %s", e)
        return {"configs": []}

    def _performance_data() -> dict:
        try:
            from fionaLocalPages.server.handlers.desktop import desktop_system_resources
            result = _call_handler(desktop_system_resources, {})
            if isinstance(result, dict) and result.get("ok"):
                return {"resources": result.get("data", {})}
        except Exception as e:
            logger.warning("Performance data unavailable: %s", e)
        return {"resources": {}}

    def _diagnostics_data() -> dict:
        try:
            from fionaLocalPages.server.handlers.system import system_status, system_metrics
            status = _call_handler(system_status, {})
            metrics = _call_handler(system_metrics, {})
            data = {}
            if isinstance(status, dict) and status.get("ok"):
                data["status"] = status.get("data", {})
            if isinstance(metrics, dict) and metrics.get("ok"):
                data["metrics"] = metrics.get("data", {})
            return data
        except Exception as e:
            logger.warning("Diagnostics data unavailable: %s", e)
        return {"status": {}, "metrics": {}}

    def _devtools_data() -> dict:
        return {}  # Developer tools info page

    def _phiconnect_data() -> dict:
        try:
            from fionaLocalPages.server.handlers.phiconnect import phiconnect_status
            result = _call_handler(phiconnect_status, {})
            out = {}
            if isinstance(result, dict) and result.get("ok"):
                out["phiconnect_status"] = result.get("data", {})
            from fionaLocalPages.server.handlers.phiconnect import phiconnect_peers_list
            peers = _call_handler(phiconnect_peers_list, {})
            if isinstance(peers, dict) and peers.get("ok"):
                out["peers"] = peers.get("data", [])
            else:
                out["peers"] = []
            return out
        except Exception as e:
            logger.warning("PhiConnect data unavailable: %s", e)
        return {"phiconnect_status": {}, "peers": []}

    def _browser_data() -> dict:
        try:
            from fionaLocalPages.server.handlers.browser import browser_status_handler
            result = _call_handler(browser_status_handler, {})
            if isinstance(result, dict) and result.get("ok"):
                return {"browser_status": result.get("data", {})}
        except Exception as e:
            logger.warning("Browser data unavailable: %s", e)
        return {"browser_status": {"state": "unknown", "running": False}}

    def _calendar_data() -> dict:
        try:
            from fionaLocalPages.server.handlers.calendar import list_events, get_stats
            events_result = _call_handler(list_events, {"upcoming": "14"})
            events = []
            if isinstance(events_result, dict) and events_result.get("ok"):
                events = events_result["data"].get("events", [])
            stats_result = _call_handler(get_stats, {})
            stats = {}
            if isinstance(stats_result, dict) and stats_result.get("ok"):
                stats = stats_result.get("data", {})
            return {"events": events, "stats": stats}
        except Exception as e:
            logger.warning("Calendar data unavailable: %s", e)
        return {"events": [], "stats": {}}

    def _files_data() -> dict:
        try:
            from fionaLocalPages.server.handlers.files import file_list
            result = _call_handler(file_list, {"path": "."})
            if isinstance(result, dict) and result.get("ok"):
                return {"files": result.get("data", []), "current_path": "."}
        except Exception as e:
            logger.warning("Files data unavailable: %s", e)
        return {"files": [], "current_path": "."}

    def _agent_status_data() -> dict:
        return {}  # Requires agent ID from URL

    # ── Register page routes ─────────────────────────────────────────────
    # Order matters — more specific routes before catch-all fallback.

    routes = [
        ("/",                "dashboard",     "Dashboard",     _dashboard_data),
        ("/chat",            "chat",          "AI Chat",       _chat_data),
        ("/agents",          "agents",        "Agents",        _agents_data),
        ("/actions",         "actions",       "Actions",       _actions_data),
        ("/settings",        "settings",      "Settings",      _settings_data),
        ("/terminal",        "terminal",      "Terminal",      _terminal_data),
        ("/desktop",         "desktop",       "SeeOnDesk",     _desktop_data),
        ("/tasks",           "tasks",         "Task Queue",    _tasks_data),
        ("/notifications",   "notifications", "Notifications", _notifications_data),
        ("/macros",          "macros",        "Macros",         _macros_data),
        ("/bindings",        "bindings",      "Key Bindings",  _bindings_data),
        ("/voice",           "voice",         "Voice Commands", _voice_data),
        ("/recall",          "recall",        "RecallVault",   _recall_data),
        ("/logs",            "logs",          "Logs",          _logs_data),
        ("/camcoms",         "camcoms",       "CamComs",       _camcoms_data),
        ("/workspace",       "workspace",     "Workspace",     _workspace_data),
        ("/plugins",         "plugins",       "Plugins",       _plugins_data),
        ("/config",          "config",        "Configuration", _config_data),
        ("/diagnostics",     "diagnostics",   "Diagnostics",   _diagnostics_data),
        ("/devtools",        "devtools",      "Dev Tools",     _devtools_data),
        ("/phiconnect",      "phiconnect",    "PhiConnect",    _phiconnect_data),
        ("/browser",         "browser",       "Browser",       _browser_data),
        ("/files",           "file-explorer", "Files",         _files_data),
        ("/performance",     "performance",   "Performance",   _performance_data),
        ("/calendar",        "calendar",      "Calendar",      _calendar_data),
    ]

    for path, template, title, data_fn in routes:
        _create_route(app, path, template, title, data_fn)

    # ── Agent detail route (needs parameter from URL) ──────────────────
    @app.route("/agents/<agent_id>")
    def agent_detail(agent_id: str):
        return flask.render_template("fallback.html",
                                      page_title=f"Agent: {agent_id}",
                                      breadcrumb=f"Agent: {agent_id}",
                                      status_module="Agents",
                                      path=f"agents/{agent_id}")

    # ── Fallback for unmigrated / unknown paths ────────────────────────
    # Using 404 handler instead of catch-all route to avoid conflicting
    # with Flask's built-in static route (<path:filename> with static_url_path="").
    @app.errorhandler(404)
    def not_found(e):
        path = flask.request.path.lstrip("/") if flask.request else "unknown"
        return flask.render_template("fallback.html",
                                      page_title=path.title() if path else "Home",
                                      breadcrumb=path.title() if path else "Home",
                                      status_module=path.title() if path else "Home",
                                      path=path or ""), 404

    # ── Register AJAX action endpoints ─────────────────────────────────
    register_action_handlers(app)


def _create_route(app: flask.Flask, path: str, template: str, title: str, data_fn: Callable) -> None:
    """Register a single page route."""
    def handler():
        extra = data_fn()
        return flask.render_template(
            f"{template}.html",
            page_title=title,
            breadcrumb=title,
            status_module=title,
            **extra,
        )
    # Rename the function to avoid Flask naming conflicts
    handler.__name__ = f"page_{template.replace('-', '_')}"
    app.route(path)(handler)


def _call_handler(handler_fn: Callable, params: dict[str, Any]) -> Any:
    """Call an aiohttp handler function by providing a mock request-like context."""
    from unittest.mock import MagicMock
    import asyncio

    mock_request = MagicMock()
    mock_request.app = {"ws_manager": None}
    mock_request.match_info = params
    mock_request.query = params
    mock_request.headers = {}
    mock_request.method = "GET"

    loop = asyncio.new_event_loop()
    try:
        result = loop.run_until_complete(handler_fn(mock_request))
    finally:
        loop.close()

    if hasattr(result, "body"):
        import json
        return json.loads(result.body)
    return result


def _call_handler_post(handler_fn: Callable, body: dict[str, Any]) -> Any:
    """Call an aiohttp POST/PUT handler with JSON body.

    Creates a mock request whose ``await request.json()`` returns *body*.
    Handlers that read from ``request.match_info`` or ``request.query``
    will see empty values — use this only for handlers driven by body data.
    """
    from unittest.mock import MagicMock, AsyncMock
    import asyncio
    import json

    async def _body_json() -> dict[str, Any]:
        return body

    mock_request = MagicMock()
    mock_request.app = {"ws_manager": None}
    mock_request.match_info = {}
    mock_request.query = {}
    mock_request.headers = {"Content-Type": "application/json"}
    mock_request.method = "POST"
    # Make await request.json() return our body dict
    mock_request.json = AsyncMock(side_effect=_body_json)

    loop = asyncio.new_event_loop()
    try:
        result = loop.run_until_complete(handler_fn(mock_request))
    finally:
        loop.close()

    if hasattr(result, "body"):
        return json.loads(result.body)
    return result


def _json_response(data: Any, status: int = 200) -> flask.Response:
    """Return a JSON response (for AJAX endpoints)."""
    return flask.jsonify(data), status


# ---------------------------------------------------------------------------
# AJAX Action Handlers (POST endpoints called from page JS)
# ---------------------------------------------------------------------------

def register_action_handlers(app: flask.Flask) -> None:
    """Register POST endpoints for interactive page actions."""

    # ── Tasks ──────────────────────────────────────────────────────────
    @app.route("/tasks/create", methods=["POST"])
    def tasks_create():
        try:
            from fionaLocalPages.server.handlers.tasks import create_task
            body = flask.request.get_json(force=True, silent=True) or {}
            result = _call_handler_post(create_task, body)
            return _json_response(result, result.get("_status", 201) if isinstance(result, dict) else 201)
        except Exception as e:
            logger.warning("Task create failed: %s", e)
            return _json_response({"ok": False, "error": str(e)}, 400)

    @app.route("/tasks/update", methods=["POST"])
    def tasks_update():
        try:
            from fionaLocalPages.server.handlers.tasks import update_task
            body = flask.request.get_json(force=True, silent=True) or {}
            result = _call_handler_post(update_task, body)
            return _json_response(result)
        except Exception as e:
            logger.warning("Task update failed: %s", e)
            return _json_response({"ok": False, "error": str(e)}, 400)

    @app.route("/tasks/delete", methods=["POST"])
    def tasks_delete():
        try:
            from fionaLocalPages.server.handlers.tasks import delete_task
            body = flask.request.get_json(force=True, silent=True) or {}
            result = _call_handler_post(delete_task, body)
            return _json_response(result)
        except Exception as e:
            logger.warning("Task delete failed: %s", e)
            return _json_response({"ok": False, "error": str(e)}, 400)

    # ── Settings ───────────────────────────────────────────────────────
    @app.route("/settings/save", methods=["POST"])
    def settings_save():
        try:
            from fionaLocalPages.server.handlers.settings_handler import put_settings
            body = flask.request.get_json(force=True, silent=True) or {}
            result = _call_handler_post(put_settings, body)
            return _json_response(result)
        except Exception as e:
            logger.warning("Settings save failed: %s", e)
            return _json_response({"ok": False, "error": str(e)}, 400)

    # ── Chat ────────────────────────────────────────────────────────────
    @app.route("/chat/send", methods=["POST"])
    def chat_send():
        try:
            body = flask.request.get_json(force=True, silent=True) or {}
            message = (body.get("message") or "").strip()
            session_id = body.get("session_id", "")
            if not message:
                return _json_response({"ok": False, "error": "Message is required"}, 400)

            # Try to use the agent_ask handler for the AI response
            try:
                from fionaLocalPages.server.handlers.agent import agent_ask
                result = _call_handler_post(agent_ask, {"message": message, "session_id": session_id})
            except Exception:
                # Fallback: just echo back
                result = {"ok": True, "data": {"response": f"Echo: {message}"}}

            return _json_response(result)
        except Exception as e:
            logger.warning("Chat send failed: %s", e)
            return _json_response({"ok": False, "error": str(e)}, 400)

    @app.route("/chat/new", methods=["POST"])
    def chat_new():
        try:
            body = flask.request.get_json(force=True, silent=True) or {}
            title = (body.get("title") or "New Chat").strip()
            import uuid
            from datetime import datetime, timezone
            session = {
                "id": str(uuid.uuid4()),
                "title": title,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "messages": [],
            }
            # Try to persist via FionaCore.memory, but don't fail if unavailable
            try:
                from FionaCore.memory import save_session
                save_session(session)
            except ImportError:
                logger.info("FionaCore.memory not available — session created in-memory only")
            except Exception as inner_e:
                logger.warning("Failed to persist session: %s", inner_e)
            return _json_response({"ok": True, "data": session}, 201)
        except Exception as e:
            logger.warning("Chat new session failed: %s", e)
            return _json_response({"ok": False, "error": str(e)}, 400)

    # ── Actions ─────────────────────────────────────────────────────────
    @app.route("/actions/run", methods=["POST"])
    def actions_run():
        try:
            from fionaLocalPages.server.handlers.actions import run_action
            body = flask.request.get_json(force=True, silent=True) or {}
            result = _call_handler_post(run_action, body)
            return _json_response(result)
        except Exception as e:
            logger.warning("Action run failed: %s", e)
            return _json_response({"ok": False, "error": str(e)}, 400)

    # ── Notifications ──────────────────────────────────────────────────
    @app.route("/notifications/clear", methods=["POST"])
    def notifications_clear():
        try:
            from fionaLocalPages.server.handlers.notifications_handler import clear_notifications
            result = _call_handler_post(clear_notifications, {})
            return _json_response(result)
        except Exception as e:
            logger.warning("Notifications clear failed: %s", e)
            return _json_response({"ok": False, "error": str(e)}, 400)

    @app.route("/notifications/dismiss", methods=["POST"])
    def notifications_dismiss():
        try:
            from fionaLocalPages.server.handlers.notifications_handler import mark_read
            body = flask.request.get_json(force=True, silent=True) or {}
            result = _call_handler_post(mark_read, body)
            return _json_response(result)
        except Exception as e:
            logger.warning("Notification dismiss failed: %s", e)
            return _json_response({"ok": False, "error": str(e)}, 400)

    # ── Calendar ──────────────────────────────────────────────────────
    @app.route("/calendar/events/create", methods=["POST"])
    def calendar_events_create():
        try:
            from fionaLocalPages.server.handlers.calendar import create_event
            body = flask.request.get_json(force=True, silent=True) or {}
            result = _call_handler_post(create_event, body)
            return _json_response(result, result.get("_status", 201) if isinstance(result, dict) else 201)
        except Exception as e:
            logger.warning("Calendar event create failed: %s", e)
            return _json_response({"ok": False, "error": str(e)}, 400)

    @app.route("/calendar/events/update", methods=["POST"])
    def calendar_events_update():
        try:
            from fionaLocalPages.server.handlers.calendar import update_event
            body = flask.request.get_json(force=True, silent=True) or {}
            # The PUT route needs event id in match_info.  We pass it in the body.
            from unittest.mock import MagicMock, AsyncMock
            import asyncio
            import json
            async def _body_json() -> dict:
                return body
            mock_request = MagicMock()
            mock_request.app = {"ws_manager": None}
            mock_request.match_info = {"id": body.get("id", "")}
            mock_request.query = {}
            mock_request.headers = {"Content-Type": "application/json"}
            mock_request.method = "PUT"
            mock_request.json = AsyncMock(side_effect=_body_json)
            loop = asyncio.new_event_loop()
            try:
                result = loop.run_until_complete(update_event(mock_request))
            finally:
                loop.close()
            if hasattr(result, "body"):
                result = json.loads(result.body)
            return _json_response(result)
        except Exception as e:
            logger.warning("Calendar event update failed: %s", e)
            return _json_response({"ok": False, "error": str(e)}, 400)

    @app.route("/calendar/events/delete", methods=["POST"])
    def calendar_events_delete():
        try:
            from fionaLocalPages.server.handlers.calendar import delete_event
            body = flask.request.get_json(force=True, silent=True) or {}
            from unittest.mock import MagicMock
            import asyncio
            import json
            mock_request = MagicMock()
            mock_request.app = {"ws_manager": None}
            mock_request.match_info = {"id": body.get("id", "")}
            mock_request.query = {}
            mock_request.headers = {}
            mock_request.method = "DELETE"
            loop = asyncio.new_event_loop()
            try:
                result = loop.run_until_complete(delete_event(mock_request))
            finally:
                loop.close()
            if hasattr(result, "body"):
                result = json.loads(result.body)
            return _json_response(result)
        except Exception as e:
            logger.warning("Calendar event delete failed: %s", e)
            return _json_response({"ok": False, "error": str(e)}, 400)
