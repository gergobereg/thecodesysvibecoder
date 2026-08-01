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
POLL_INTERVAL_MS = 500
_AGENT_REGISTRY_ATTRIBUTE = "_thecodesysvibecoder_active_agents"

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


def _process_request(path, agent_id=None, outbox_dir=None, processed_dir=None):
    agent_id = agent_id or AGENT_ID
    outbox_dir = outbox_dir or OUTBOX_DIR
    processed_dir = processed_dir or PROCESSED_DIR
    base = os.path.basename(path)
    result_path = os.path.join(outbox_dir, base + ".result.json")
    try:
        _reload_module(codesys_agent)
        request = _read_json(path)
        request["result_path"] = result_path
        request["agent_id"] = agent_id
        result = codesys_agent.handle_request(request)
        _write_json(result_path, result)
    except Exception as exc:
        _write_json(result_path, {
            "ok": False,
            "error": str(exc),
            "traceback": traceback.format_exc(),
        })

    processed_path = os.path.join(processed_dir, base)
    if os.path.exists(processed_path):
        os.remove(processed_path)
    os.rename(path, processed_path)


def _agent_registry():
    # Keep the registry on sys so it survives Execute Script File returning and
    # also survives a later reload of this module in the same CODESYS process.
    registry = getattr(sys, _AGENT_REGISTRY_ATTRIBUTE, None)
    if registry is None:
        registry = {}
        setattr(sys, _AGENT_REGISTRY_ATTRIBUTE, registry)
    return registry


def _create_dispatcher_timer(interval_ms, tick_handler):
    try:
        import clr
        clr.AddReference("WindowsBase")
        from System import TimeSpan
        from System.Windows.Threading import DispatcherTimer
    except Exception:
        raise Exception(
            "Unable to load the .NET UI DispatcherTimer required by the "
            "non-blocking CODESYS agent.\n%s" % traceback.format_exc()
        )

    timer = DispatcherTimer()
    timer.Interval = TimeSpan.FromMilliseconds(float(interval_ms))
    timer.Tick += tick_handler
    return timer


class _MailboxAgent(object):
    def __init__(
        self,
        agent_id,
        state_dir,
        inbox_dir,
        outbox_dir,
        processed_dir,
        stop_file,
    ):
        self.agent_id = agent_id
        self.state_dir = state_dir
        self.inbox_dir = inbox_dir
        self.outbox_dir = outbox_dir
        self.processed_dir = processed_dir
        self.stop_file = stop_file
        self.registry_key = os.path.normcase(os.path.abspath(state_dir))
        self.busy = False
        self.stopped = False
        self.tick_handler = self._on_tick
        self.timer = _create_dispatcher_timer(POLL_INTERVAL_MS, self.tick_handler)

    def start(self):
        self.timer.Start()

    def stop(self):
        if self.stopped:
            return
        self.stopped = True
        self.timer.Stop()
        try:
            self.timer.Tick -= self.tick_handler
        except Exception:
            pass

        registry = _agent_registry()
        if registry.get(self.registry_key) is self:
            del registry[self.registry_key]
        print("CODESYS in-IDE agent stopped: " + self.agent_id)

    def _next_request_path(self):
        try:
            names = sorted(os.listdir(self.inbox_dir))
        except Exception:
            names = []

        for name in names:
            if name.lower().endswith(".json"):
                return os.path.join(self.inbox_dir, name)
        return None

    def _on_tick(self, sender, event_args):
        # DispatcherTimer invokes this callback on the CODESYS UI dispatcher.
        # Process only one request per tick so a mailbox backlog cannot keep the
        # UI thread occupied indefinitely.
        if self.stopped or self.busy:
            return

        self.busy = True
        try:
            if os.path.exists(self.stop_file):
                self.stop()
                return

            request_path = self._next_request_path()
            if request_path is not None:
                _process_request(
                    request_path,
                    agent_id=self.agent_id,
                    outbox_dir=self.outbox_dir,
                    processed_dir=self.processed_dir,
                )
        except Exception:
            print("CODESYS in-IDE agent polling error: " + self.agent_id)
            print(traceback.format_exc())
        finally:
            self.busy = False


def main(agent_id=None):
    _configure_paths(agent_id)
    _ensure_dirs()
    if os.path.exists(STOP_FILE):
        os.remove(STOP_FILE)

    registry_key = os.path.normcase(os.path.abspath(STATE_DIR))
    registry = _agent_registry()
    existing = registry.get(registry_key)
    if existing is not None:
        existing.stop()

    agent = _MailboxAgent(
        AGENT_ID,
        STATE_DIR,
        INBOX_DIR,
        OUTBOX_DIR,
        PROCESSED_DIR,
        STOP_FILE,
    )
    registry[registry_key] = agent
    try:
        agent.start()
    except Exception:
        if registry.get(registry_key) is agent:
            del registry[registry_key]
        raise

    print("CODESYS in-IDE agent started (non-blocking).")
    print("Agent: " + AGENT_ID)
    print("State: " + STATE_DIR)
    print("Inbox: " + INBOX_DIR)
    print("Stop file: " + STOP_FILE)
    print("Startup complete; control has returned to the CODESYS user interface.")


if __name__ == "__main__":
    main()
