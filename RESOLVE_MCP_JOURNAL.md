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

## Related machine-wide Claude Code tooling (not Resolve-specific)

- **superpowers** plugin (`obra/superpowers`, MIT), installed from the
  **official** Anthropic plugin marketplace:
  `claude plugin install superpowers@claude-plugins-official`. Confirmed
  legitimate before installing: distributed via
  `anthropics/claude-plugins-official` (not just a random repo), 23.7k forks /
  324 open issues / 183 PRs against 265k stars — engagement proportional to
  stars, consistent with organic virality rather than bought stars — author
  is an established open-source dev.
- Adds 14 skills (brainstorming, TDD, systematic-debugging, subagent-driven
  development, writing/executing plans, code review patterns, etc.) plus one
  lightweight SessionStart hook. No agents, no MCP servers. ~688 tokens
  always-on cost per session.
- Installed at **user scope** — active in every project, including this one,
  not just davinci-resolve-mcp. Check status: `claude plugin list`. Manage
  with `claude plugin disable/enable/uninstall superpowers`.
- Relevant here mainly for *how we work* on this repo going forward (e.g. its
  brainstorming/planning/TDD skills may activate when doing larger MCP
  feature work), not for Resolve control itself.

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
- This network times out hard on GitHub Pages' CDN (`*.github.io`, incl.
  `formulae.brew.sh`) specifically — plain `github.com`, `python.org`, and
  `evermeet.cx` all work fine. If `brew install` hangs, that's why; either
  retry (it's not always down) or avoid brew for that package (pip / a direct
  static-binary download both worked around it).
- Bash commands that get auto-relocated to a background task run in an
  **isolated sandbox copy** — files they write (even to the scratchpad) do not
  appear in the normal filesystem afterward. Re-run download/extract/install
  steps in the foreground (with `dangerouslyDisableSandbox` if needed) rather
  than trusting a backgrounded command's on-disk side effects.

## Video/audio tooling (machine-wide, not Resolve-specific)

Installed 2026-08-03 so Claude Code can actually fetch and process YouTube
(and other) video links — download, extract audio, get captions/metadata —
rather than just fetching the webpage:

- **yt-dlp** (`pip3 install --user yt-dlp`, framework Python 3.12) —
  symlinked to `/usr/local/bin/yt-dlp`. Avoided Homebrew because of the
  GitHub Pages CDN block above.
- **ffmpeg** 8.1.2 — static build from `evermeet.cx` (long-established,
  widely-trusted source for macOS ffmpeg builds; GPG signature not verified
  since `gpg` isn't installed, but binary was sanity-checked: valid Mach-O,
  runs, correct `-version` output) — installed to `/usr/local/bin/ffmpeg`,
  quarantine attribute cleared.
- **Gotcha hit**: the framework Python installed above for the Resolve bridge
  has no CA certs by default → yt-dlp failed with
  `CERTIFICATE_VERIFY_FAILED`. Fixed by running
  `"/Applications/Python 3.12/Install Certificates.command"`. Needed again if
  a future framework Python version is installed.
- **Optional, not yet installed**: yt-dlp recommends a JS runtime (`deno`) for
  full format/subtitle reliability on some videos. Currently works without it
  for basic metadata/caption extraction; revisit if extraction starts failing
  on specific videos.
- Verified end-to-end against a real video (`jNQXAC9IVRw`, "Me at the zoo") —
  metadata and format extraction both worked.
- **whisper** (OpenAI, `pip3 install --user openai-whisper`) — local
  speech-to-text, CLI at `/usr/local/bin/whisper`. Hit two more dependency
  snags before it worked:
  - `numba`/`llvmlite` (whisper deps) had no prebuilt wheel for this
    Python/platform combo at the latest version → pip tried to build
    `llvmlite` from source, which needs `cmake`. Installing `cmake` (via pip
    or a static binary) turned out to be a dead end — see below.
  - **Fix**: pinned to older versions that *do* ship prebuilt wheels —
    `llvmlite==0.45.1` + `numba==0.62.0` (matched via numba's own
    `Requires-Dist: llvmlite<0.46,>=0.45.0dev0`) — installed those first,
    then `openai-whisper` on top reused them instead of trying to build.
  - `torch` (2.2.2, whisper's own pin) needs NumPy 1.x; numba's install
    pulled NumPy 2.3.5 → ABI-mismatch warning on import. Fixed with
    `pip3 install --user "numpy<2"` (landed on 1.26.4).
  - Verified end-to-end: downloaded "Me at the zoo" audio via yt-dlp, ran
    `whisper zoo.mp3 --model tiny`, got a correct transcript.
- Dead end worth remembering: the pip `cmake` package installs fine but its
  console-script shim isn't visible to pip's **isolated build subprocess**
  for another package (build isolation excludes user-site-packages) — so
  `pip install cmake` does not actually make `cmake` usable for building
  other packages via pip, even though `which cmake` and `cmake --version`
  work fine standalone. A real `cmake` install (or, better, avoiding the
  source build entirely as done above) is the way around it.
- GitHub **release asset** downloads (`github.com/.../releases/download/...`,
  e.g. Kitware/CMake) were extremely slow/unreliable on this network
  (~100-150KB/s, frequent mid-transfer drops) — worse than the GitHub Pages
  CDN block noted above, and different from it (release assets aren't on
  `*.github.io`). PyPI (`pypi.org`/`files.pythonhosted.org`) was reliable
  throughout. When a GitHub-hosted binary download is flaky, check PyPI for
  an equivalent package first before fighting the download.

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
- Installed the `superpowers` Claude Code plugin (user scope, official
  marketplace) — see "Related machine-wide Claude Code tooling" above. Not
  Resolve-specific, but active for this repo's sessions too.
- Installed `yt-dlp` + `ffmpeg` (see "Video/audio tooling" above) so YouTube
  links can actually be downloaded/transcribed, not just fetched as a
  webpage. Also not Resolve-specific, but relevant if we ever pull reference
  clips or source footage from video links into a Resolve project.
