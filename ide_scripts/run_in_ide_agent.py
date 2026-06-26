from __future__ import print_function

import json
import os
import re
import sys
import traceback

try:
    from scriptengine import *  # noqa: F401,F403 - injected by the CODESYS ScriptEngine
except Exception:
    pass


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPT_DIR)
AGENT_ID = "default"
STATE_DIR = None
INBOX_DIR = None
OUTBOX_DIR = None
PROCESSED_DIR = None
STOP_FILE = None

if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import codesys_agent


def _reload_module(module):
    try:
        import importlib
        reload_func = getattr(importlib, "reload", None)
        if reload_func is not None:
            return reload_func(module)
    except Exception:
        pass

    try:
        import imp
        reload_func = getattr(imp, "reload", None)
        if reload_func is not None:
            return reload_func(module)
    except Exception:
        pass

    return module


def _safe_agent_id(value):
    if value is None:
        return ""
    text = str(value).strip()
    if not text or text.lower() == "default":
        return ""
    text = re.sub(r"[^A-Za-z0-9_.-]", "_", text)
    text = text.strip(" .")
    if not text or text in [".", ".."]:
        raise Exception("Invalid CODESYS agent id '%s'." % value)
    return text


def _agent_id_from_args():
    if len(sys.argv) > 1:
        return sys.argv[1]
    return os.environ.get("CODESYS_AGENT_ID")


def _configure_paths(agent_id=None):
    global AGENT_ID, STATE_DIR, INBOX_DIR, OUTBOX_DIR, PROCESSED_DIR, STOP_FILE

    safe_agent_id = _safe_agent_id(agent_id if agent_id is not None else _agent_id_from_args())
    AGENT_ID = safe_agent_id or "default"
    if safe_agent_id:
        STATE_DIR = os.path.join(ROOT_DIR, ".codesys_agent", safe_agent_id)
    else:
        STATE_DIR = os.path.join(ROOT_DIR, ".codesys_agent")
    INBOX_DIR = os.path.join(STATE_DIR, "inbox")
    OUTBOX_DIR = os.path.join(STATE_DIR, "outbox")
    PROCESSED_DIR = os.path.join(STATE_DIR, "processed")
    STOP_FILE = os.path.join(STATE_DIR, "stop-agent")


def _ensure_dirs():
    for path in [STATE_DIR, INBOX_DIR, OUTBOX_DIR, PROCESSED_DIR]:
        if not os.path.isdir(path):
            os.makedirs(path)


def _read_json(path):
    with open(path, "r") as handle:
        text = handle.read()
    if text.startswith("\xef\xbb\xbf"):
        text = text[3:]
    return json.loads(text)


def _write_json(path, payload):
    text = json.dumps(codesys_agent._plain(payload), indent=2, sort_keys=True)
    with open(path, "w") as handle:
        handle.write(text)
        handle.write("\n")


def _process_request(path):
    base = os.path.basename(path)
    result_path = os.path.join(OUTBOX_DIR, base + ".result.json")
    try:
        _reload_module(codesys_agent)
        request = _read_json(path)
        request["result_path"] = result_path
        request["agent_id"] = AGENT_ID
        result = codesys_agent.handle_request(request)
        _write_json(result_path, result)
    except Exception as exc:
        _write_json(result_path, {
            "ok": False,
            "error": str(exc),
            "traceback": traceback.format_exc(),
        })

    processed_path = os.path.join(PROCESSED_DIR, base)
    if os.path.exists(processed_path):
        os.remove(processed_path)
    os.rename(path, processed_path)


def main(agent_id=None):
    _configure_paths(agent_id)
    _ensure_dirs()
    if os.path.exists(STOP_FILE):
        os.remove(STOP_FILE)

    print("CODESYS in-IDE agent started.")
    print("Agent: " + AGENT_ID)
    print("State: " + STATE_DIR)
    print("Inbox: " + INBOX_DIR)
    print("Stop file: " + STOP_FILE)

    while not os.path.exists(STOP_FILE):
        names = []
        try:
            names = sorted(os.listdir(INBOX_DIR))
        except Exception:
            names = []

        for name in names:
            if not name.lower().endswith(".json"):
                continue
            _process_request(os.path.join(INBOX_DIR, name))

        system.delay(500)

    print("CODESYS in-IDE agent stopped.")


if __name__ == "__main__":
    main()
