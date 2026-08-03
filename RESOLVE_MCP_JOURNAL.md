# DaVinci Resolve MCP — Setup Reference & Work Log

This file is personal, not part of the upstream repo. Read this at the start
of any session touching DaVinci Resolve so setup doesn't need to be redone.
Append to the Work Log at the end of a session (or major task) so future
sessions inherit context instead of re-discovering it.

## Environment facts (2026-08-03)

- **Repo**: `/Users/apple/dev/davinci-resolve-mcp` (clone of
  `samuelgursky/davinci-resolve-mcp`, main branch)
- **Venv**: `/Users/apple/dev/davinci-resolve-mcp/venv` (Python 3.13.5, Homebrew).
  Has the MCP SDK installed. Used to run the MCP server itself.
- **DaVinci Resolve**: v20.0.1.6, **free edition** (not Studio) — confirmed via
  live connection test. External scripting via `scriptapp("Resolve")` is
  blocked on this edition regardless of the Preferences setting.
- **MCP registration**: registered as a **user-scoped** Claude Code MCP server
  (`~/.claude.json`), so it's available from any project directory, not just
  this repo. Check with `claude mcp get davinci-resolve`.
- **Connection transport**: the **in-app bridge**, because free edition blocks
  the direct API. `DAVINCI_RESOLVE_BRIDGE=1` is set in the MCP server's env.
  Bridge config/token: `~/.config/davinci-resolve-mcp/bridge.json`. Listens on
  `127.0.0.1:49632`.
- **Framework Python**: installed at `/Library/Frameworks/Python.framework/Versions/3.12`
  (python.org 3.12.10, notarized installer) specifically because Resolve's
  Workspace ▸ Scripts menu only lists `.py` scripts from a framework build —
  Homebrew/pyenv/conda are invisible to it. This is what runs the bridge script
  inside Resolve; it's separate from the venv above.

## Every-session checklist

1. Open DaVinci Resolve, open a saved project (Scripts menu is empty at the
   Project Manager screen).
2. Workspace ▸ Scripts ▸ **resolve_bridge** — run it. (Only needed after
   Resolve was restarted; it doesn't survive a quit.)
3. Confirm it's listening: `lsof -iTCP:49632 -sTCP:LISTEN` should show a
   `fuscript` process.
4. From here, Claude Code's `davinci-resolve` MCP tools talk to live Resolve
   state automatically — no per-project setup needed.

If tools report "resolve unavailable": it's almost always step 2 not done yet
for this Resolve session.

## Re-running the installer (updates, re-config, moving machines)

```bash
cd /Users/apple/dev/davinci-resolve-mcp
git pull                                    # picks up upstream MCP updates
venv/bin/python3 -m pip install -r requirements.txt  # if deps changed
python3 install.py --no-venv --clients claude-code --python venv/bin/python3
```

Bridge reinstall (only needed if bridge files are missing/stale, e.g. after a
`git pull` that touched `scripts/install_resolve_bridge.py` or
`src/utils/resolve_bridge*.py`):

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 scripts/install_resolve_bridge.py
```

Then restart Resolve and re-run resolve_bridge from Workspace ▸ Scripts.

## Known gotchas

- Don't bother checking Preferences ▸ General ▸ "External scripting using" on
  this machine — it's a Studio-only setting and has no effect on the free
  edition install here.
- The in-Resolve bridge runtime is a **copy taken at install time**. If the
  repo's bridge code changes, re-run the installer above; the running bridge
  can reload without a Resolve restart (see `docs/SKILL.md`).
- `pkgutil --check-signature` is worth running on any downloaded installer on
  this network — a prior python.org download silently corrupted in transit
  (checksum mismatch) and `installer` reported a misleading "invalid package
  path" error instead of a signature failure.

## Work Log

### 2026-08-03 — Initial setup
- Cloned repo, created venv, installed MCP SDK.
- Registered `davinci-resolve` as user-scoped Claude Code MCP server.
- Discovered free edition blocks direct scripting API (`scriptapp("Resolve")`
  → `None`).
- Installed python.org framework Python 3.12.10 (Homebrew Python isn't
  detected by Resolve's Scripts menu) so the in-app bridge script would appear
  in Workspace ▸ Scripts.
- Installed and started the bridge (`resolve_bridge`); verified live
  connection — read current project "Introduction to islam" over the bridge.
- End state: fully working, MCP tools can read/control the running Resolve
  session.
