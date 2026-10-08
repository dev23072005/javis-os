"""Regression: a background job running on Codex must reach the MCP hub at ITS OWN permission level.

Canary 2026-10-08 (VPS reminder migration, finding F2): reminders created with
muc_quyen=suggest ran on Codex, and the hub audit logged every one of their calls with
mode=full. The shared Codex profile (~/.codex/javis.config.toml) always carries
X-Javis-Mode = "full" because every chat turn reads it, and `_build_codex` never told Codex
otherwise. The hub was left with only each connection's own permission cap.

The fix sends the level per process with the same `-c` override that already carries
X-Javis-Vault. Codex applies `-c` after the profile layer; checked by hand with codex-cli
0.160.1: `codex -p javis -c 'mcp_servers.javis.http_headers.X-Javis-Mode="suggest"' mcp get
javis --json` prints "suggest" in either flag order, and a header override WITHOUT a
`mcp_servers.javis` entry makes Codex refuse to start ("invalid transport"). This test replays
that layering on the real argv instead of only checking that an override string is present.

    python tests/run.py codex_mode_header      (no network, does not spawn codex)
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import json
import os
import re
import sys
import tempfile
import tomllib
from pathlib import Path

# Hard-set, not setdefault: inside the production container JAVIS_STATE_DIR, BRAINS_DIR and
# HOME already point at live data, and this test writes a Codex profile under HOME.
_TMP = Path(tempfile.mkdtemp(prefix="javis-codex-mode-"))
os.environ["JAVIS_STATE_DIR"] = str(_TMP / "state")
os.environ["JAVIS_SESSIONS_DB"] = str(_TMP / "conversations.db")
os.environ["BRAINS_DIR"] = str(_TMP / "brains")
os.environ["HOME"] = str(_TMP / "home")
os.environ.pop("JAVIS_CODEX_SANDBOX", None)
for _d in ("state", "brains/Brain Default", "home"):
    (_TMP / _d).mkdir(parents=True, exist_ok=True)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import claude_cli  # noqa: E402
import config as cfgmod  # noqa: E402
import mcp_catalog  # noqa: E402
import mcp_hub  # noqa: E402
import aux_engine  # noqa: E402

# Behave as on a machine where Codex is installed (CI has no codex binary).
claude_cli.find_codex_cli = lambda: "codex"

fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  [{detail}]" if detail and not cond else ""))
    if not cond:
        fails.append(name)


# Valid HTTP header name (RFC 9110 token), what rmcp-client's HeaderName::from_bytes requires.
_TOKEN = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")
BRAIN = _TMP / "brains" / "Brain Default"
MODE_KEY = mcp_hub.CODEX_MODE_KEY


def effective_hub_headers(argv):
    """Replay Codex: load the profile picked by -p, then apply every -c in argv order."""
    cfg = {}
    if "-p" in argv:
        name = argv[argv.index("-p") + 1]
        cfg = tomllib.loads((Path.home() / ".codex" / f"{name}.config.toml").read_text(encoding="utf-8"))
    for i, a in enumerate(argv):
        if a != "-c":
            continue
        key, raw = argv[i + 1].split("=", 1)
        try:
            val = tomllib.loads(f"v = {raw}")["v"]
        except tomllib.TOMLDecodeError:
            val = raw
        cur, path = cfg, key.strip().split(".")
        for part in path[:-1]:
            if not isinstance(cur.get(part), dict):
                cur[part] = {}
            cur = cur[part]
        cur[path[-1]] = val
    return ((cfg.get("mcp_servers") or {}).get("javis") or {}).get("http_headers") or {}


def hub_mode(engine):
    return effective_hub_headers(engine._build_args()).get("X-Javis-Mode")


def mode_overrides(argv):
    return [a for a in argv if str(a).startswith(MODE_KEY + "=")]


def shared_profile():
    """What main._write_codex_profile does when the hub is on: one shared file, always full."""
    return mcp_hub.codex_profile("full")


class _Engine:
    """Stand-in for the Claude engine a background lane builds before the router swaps it."""

    def __init__(self, mode=None, vault=BRAIN):
        self.cwd = str(BRAIN)
        self.tag = "reminder"
        self.system_prompt = None
        self.javis_vault = str(vault) if vault else None
        self.javis_mode = mode
        self.model = None

    def is_available(self):
        return True


def set_hub(on):
    cfgmod.SETTINGS_PATH.write_text(json.dumps({"mcp": {"hub": bool(on)}}), encoding="utf-8")


set_hub(True)
CODEX_SPEC = {"provider": aux_engine.CODEX, "model": "gpt-5.5"}

# ---- 1. The override itself --------------------------------------------------------------
for m in ("suggest", "auto", "full"):
    ov = mcp_hub.codex_mode_override(m)
    h = effective_hub_headers(["-c", ov])
    check(f"override for {m} sets X-Javis-Mode={m}", h.get("X-Javis-Mode") == m, ov)
check("header name is a valid HTTP token (not quoted)",
      all(_TOKEN.match(k) for k in effective_hub_headers(["-c", mcp_hub.codex_mode_override("auto")])))
check("no level means full, like the shared profile (chat and workflow unchanged)",
      effective_hub_headers(["-c", mcp_hub.codex_mode_override(None)])["X-Javis-Mode"] == "full"
      and effective_hub_headers(["-c", mcp_hub.codex_mode_override("")])["X-Javis-Mode"] == "full")
check("level is case and space insensitive",
      effective_hub_headers(["-c", mcp_hub.codex_mode_override(" Suggest ")])["X-Javis-Mode"] == "suggest")
for bad in ("readonly", "safe", "bogus", "   "):
    check(f"unknown level {bad!r} fails closed to suggest (the hub treats unknown as full)",
          effective_hub_headers(["-c", mcp_hub.codex_mode_override(bad)])["X-Javis-Mode"] == "suggest")

# ---- 2. Replacing, never stacking ------------------------------------------------------------
extra = ["model_reasoning_effort=high", mcp_hub.codex_vault_override(str(BRAIN)),
         mcp_hub.codex_mode_override("full")]
for m in ("suggest", "auto", "suggest"):
    mcp_hub.dat_codex_mode(extra, m)
check("switching levels on one CodexCLI leaves exactly one mode override", len(mode_overrides(extra)) == 1, extra)
check("the remaining override is the current level", mode_overrides(extra)[0].endswith('"suggest"'), extra)
check("other overrides are untouched",
      "model_reasoning_effort=high" in extra and any("X-Javis-Vault" in x for x in extra))

# ---- 3. _build_codex: the hub sees the job's level, through the real argv ---------------------
for m in ("suggest", "auto", "full"):
    cc = aux_engine._build_codex(CODEX_SPEC, _Engine(), m, "reminder", shared_profile)
    argv = cc._build_args()
    h = effective_hub_headers(argv)
    shown = {k: v for k, v in h.items() if k.lower() != "authorization"}   # never print the hub token
    check(f"{m} job: hub receives X-Javis-Mode={m}", h.get("X-Javis-Mode") == m, shown)
    check(f"{m} job: brain header still sent", bool(h.get("X-Javis-Vault")), shown)
    check(f"{m} job: auth header still comes from the profile", str(h.get("Authorization", "")).startswith("Bearer "))
    check(f"{m} job: exactly one mode override in argv", len(mode_overrides(argv)) == 1, argv)
    check(f"{m} job: every header name is a valid HTTP token", all(_TOKEN.match(k) for k in h), list(h))

# ---- 4. The shared profile is not touched by a per-job level -----------------------------------
prof = Path.home() / ".codex" / f"{mcp_hub.codex_profile_name()}.config.toml"
before = prof.read_bytes()
aux_engine._build_codex(CODEX_SPEC, _Engine(), "suggest", "reminder", shared_profile)
after = tomllib.loads(prof.read_text(encoding="utf-8"))
check("shared profile still says full after a suggest job (chat lanes unaffected)",
      after["mcp_servers"]["javis"]["http_headers"]["X-Javis-Mode"] == "full")
check("shared profile bytes unchanged by the per-job level", prof.read_bytes() == before)

# ---- 5. Level taken from the engine when the caller passes none (Kanban sets javis_mode) -------
check("no mode argument: uses the engine's javis_mode",
      hub_mode(aux_engine._build_codex(CODEX_SPEC, _Engine(mode="suggest"), None, "dispatch", shared_profile))
      == "suggest")
check("no mode anywhere: full, as before",
      hub_mode(aux_engine._build_codex(CODEX_SPEC, _Engine(mode=None), None, "workflow", shared_profile)) == "full")

# ---- 6. No hub profile: no override, or Codex refuses to start ---------------------------------
cc = aux_engine._build_codex(CODEX_SPEC, _Engine(), "suggest", "loop")
check("without a profile writer: no mode override", not mode_overrides(cc._build_args()))
cc = aux_engine._build_codex(CODEX_SPEC, _Engine(), "suggest", "loop", lambda: None)
check("profile writer returned nothing: no mode override", not mode_overrides(cc._build_args()))

# ---- 7. Hub switched off in settings: per-server profile, no javis entry, no override ----------
set_hub(False)
cc = aux_engine._build_codex(CODEX_SPEC, _Engine(), "suggest", "loop", lambda: "javis")
check("hub off: no mode override", not mode_overrides(cc._build_args()))
set_hub(True)

# ---- 8. strip_tools (text-only judge) still removes every hub trace -----------------------------
cc = aux_engine._build_codex(CODEX_SPEC, _Engine(), "suggest", "reply-policy", shared_profile)
out = aux_engine.strip_tools(cc, object())
argv = out._build_args()
check("strip_tools: no profile and no mode override left", "-p" not in argv and not mode_overrides(argv), argv)
check("strip_tools: Codex sees no hub at all", effective_hub_headers(argv) == {}, sorted(effective_hub_headers(argv)))

# ---- 9. Through the router a reminder actually uses ---------------------------------------------


def via_router(m):
    out = aux_engine.swap(_Engine(mode=m), mode=m, tag="reminder", spec=CODEX_SPEC,
                          codex_profile=shared_profile, settings={})
    links = out._all() if hasattr(out, "_all") else [out]
    return [e for e in links if isinstance(e, claude_cli.CodexCLI)]


for m in ("suggest", "auto", "full"):
    codex = via_router(m)
    check(f"swap({m}) routes the job to Codex", len(codex) == 1)
    check(f"swap({m}): Codex reaches the hub at {m}", bool(codex) and hub_mode(codex[0]) == m)


class _Deps:
    def aux_swap(self, cli, mode=None, tag=None):
        return aux_engine.swap(cli, mode=mode, tag=tag, spec=CODEX_SPEC,
                               codex_profile=shared_profile, settings={})


out = aux_engine.apply(_Deps(), _Engine(), mode="suggest", tag="reminder")
links = out._all() if hasattr(out, "_all") else [out]
codex = [e for e in links if isinstance(e, claude_cli.CodexCLI)]
check("reminder path aux_engine.apply -> swap -> _build_codex: hub sees suggest",
      bool(codex) and hub_mode(codex[0]) == "suggest")

MAIN = (SERVER / "main.py").read_text(encoding="utf-8")
REM = (SERVER / "reminders.py").read_text(encoding="utf-8")
check("main._aux_swap forwards the job level to the router",
      "aux_engine.swap(cli, mode=mode, tag=tag, codex_profile=_write_codex_profile)" in MAIN)
check("reminders hand their muc_quyen to the router", "aux_engine.apply(self.deps, cli, mode=mq" in REM)

# ---- 10. Why the header matters: the hub caps by mode, not only by connection -------------------
GW = mcp_catalog.get("google-workspace")
check("core catalog has the google-workspace connector", isinstance(GW, dict) and bool(GW), type(GW).__name__)
ok, _ = mcp_catalog.allowed(GW, "readonly", "suggest", "search_gmail_messages",
                            {"query": "from:no-reply@goaffpro.com", "page_size": 10})
check("suggest + readonly connection: Gmail search (the reminder's read) is allowed", ok)
for tool in ("send_gmail_message", "manage_event", "create_drive_file"):
    ok_full_conn, _ = mcp_catalog.allowed(GW, "full", "suggest", tool, {})
    check(f"suggest caps {tool} even if the connection is raised to full", not ok_full_conn)
ok_old, _ = mcp_catalog.allowed(GW, "full", "full", "send_gmail_message", {})
check("CANARY: with mode=full only the connection cap stood in the way (pre-fix state)", ok_old)

print(("RED: " + str(len(fails))) if fails else "GREEN: all checks passed")
sys.exit(1 if fails else 0)
