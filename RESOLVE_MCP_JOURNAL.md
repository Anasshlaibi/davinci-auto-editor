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

## Processing footage that lives under ~/Downloads (or Desktop/Documents)

**The single biggest gotcha found doing real editing work (2026-08-04).** macOS
protects Downloads/Desktop/Documents at the OS level (TCC), independent of any
Claude Code sandbox setting. This means:

- `ffmpeg`, `whisper`, `dd`, `cp` — **any** subprocess spawned from the Bash
  tool — gets `Operation not permitted` trying to read file *content* from
  those folders, even though `ls`/`stat`/`test -f` on the same path succeed
  (directory listing and content read are different TCC permissions).
  `dangerouslyDisableSandbox: true` does **not** fix this — it's macOS's OS
  sandbox, not Claude Code's.
- Claude Code's own `Read` tool (and DaVinci Resolve's app process, and the
  Resolve MCP bridge acting through it) are **not** affected — they can read
  the same file fine. So `media_storage.import_to_pool`,
  `media_pool_item.get_clip_property`, etc. all work directly on a clip still
  sitting in `~/Downloads`.
- But anything the MCP server shells out for — `media_pool_item.extract_frames`
  (uses ffmpeg), `media_pool_item.transcribe_audio` (Resolve's native
  transcription — this one fails **instantly and silently**,
  `{"success": false}`, no error text, when the source is in a protected
  folder; same call works once the file lives somewhere else) — fails the
  same way ffmpeg does directly.
- **Workaround that works**: render the clip (or just the piece you need) out
  of Resolve to an accessible location first — `render.prepare_render_job` +
  `render.start` (NOT `render.quick_export`/`safe_quick_export`, which pops a
  UI dialog and throws `bridge_timeout: Resolve did not answer in time` from
  the MCP side — the low-level render-queue API doesn't have this problem).
  Once the render lands outside the protected folder, `ffmpeg`/`whisper`/
  Resolve's own `transcribe_audio` all work on it normally.
- Corollary: any media you generate this way (corrected audio, transcripts,
  etc.) that a **persistent** Resolve project will keep referencing must be
  moved out of the session scratchpad (`/private/tmp/claude-*/.../scratchpad`)
  before the session ends — that directory is not guaranteed to survive, and
  the Resolve project just stores a file path, not the media itself. Convention
  adopted: `~/Movies/<project-name>-video-production/` as the permanent home
  for generated (not raw-source) audio/video assets tied to a specific edit.

## Color grading API gotcha

- `timeline_item_color.safe_set_cdl` **validates successfully but silently
  fails to apply** — returns `{"success": false}` with no error, even though
  `dry_run: true` on the identical params reports `valid: true`. Confirmed by
  checking `grade_evidence_base` before/after: no node tools added.
- **Fix**: use the raw `set_cdl` action instead, with the exact string-keyed
  shape the validator's `normalized` field shows (`NodeIndex`, `Slope`,
  `Offset`, `Power`, `Saturation` as space-separated `"r g b"` strings, not
  the friendlier `slope`/`offset`/`power` array shape `safe_set_cdl` accepts).
  Worth re-testing `safe_set_cdl` next time in case it's fixed upstream before
  reaching for the raw workaround again.
- Also: `SetCDL` (and color grading generally) behaved more reliably after
  switching Resolve to the **Color page** (`resolve_control.open_page`,
  `page: "color"`) first — not confirmed as the actual cause of the
  `safe_set_cdl` failure above, but did coincide with the raw `set_cdl` call
  succeeding on retry.

## Real loudness numbers from this phone/mic setup

Footage recorded on the phone in the usual desk setup (see
`work-with-ai/projects/islamic-study/PROJECT.md`) measures **very quiet**:
integrated loudness around **-34 LUFS**, true peak around **-11 dBTP**, i.e.
~20 LU below the -14 LUFS most platforms target, but with the peak already
much closer to that target than the average is. That gap means a flat
**Volume** gain on the Resolve timeline item (the only audio control exposed
by the MCP's `timeline_item.set_audio`) is **not safe** — a static gain big
enough to fix the average would clip the peaks. Real fix needs dynamic
loudness normalization (ffmpeg's two-pass `loudnorm`, measure then apply with
`measured_I`/`measured_TP`/`measured_LRA`/`measured_thresh`), done externally,
then imported as a separate audio track with the original muted (see Work Log
below for the exact steps) — Resolve's scriptable audio API has no
compressor/limiter to do this in-place.

## Network notes (addendum to the ones below)

- `openaipublic.azureedge.net` (Whisper's default model-weight host) and
  `huggingface.co` model downloads are both extremely throttled on this
  network (tens of bytes/sec to a few KB/s) — much worse than the general
  GitHub-release-asset slowness already noted below, and enough to corrupt a
  large download mid-transfer (hit this with the `base` model — checksum
  mismatch after a 13+ minute partial download). General internet (Google,
  PyPI) is fine, so this is CDN/host-specific, not a dead connection.
- A **`tiny` model (~72MB) already fully downloaded in a prior session**
  (`~/.cache/whisper/tiny.pt`) loads and works with zero network access —
  check for an existing cached model before attempting any fresh download on
  this network. If better accuracy than `tiny` is needed later, try fetching
  `base`/`small` when this specific CDN is behaving (e.g. test with
  `curl -r 0-3000000 --max-time 15 <model-url>` first rather than launching
  the full whisper download blind).
- **Model loading fine ≠ transcription fast.** Confirmed 2026-08-06: vanilla
  `openai-whisper` (`tiny`, PyTorch CPU backend) loading the cached
  `tiny.pt` above still took **78+ minutes and never finished** transcribing
  an 18-minute clip on this Intel Mac (no GPU, no AVX-optimized build) —
  had to `kill -9` it. Root cause not fully isolated (possibly whisper's
  temperature-fallback retry loop on a difficult segment, possibly just slow
  generic PyTorch CPU inference), but `--condition_on_previous_text False
  --temperature 0` didn't fix it on retry either. **Use `faster-whisper`
  (CTranslate2 backend, INT8 CPU quantization) instead of `openai-whisper`
  for anything beyond a trivial clip** — same model weights conceptually,
  dramatically faster CPU inference by design. It's what actually worked
  (once its own model-weight download succeeded) — see the 2026-08-06 Work
  Log entry.
- Tried offloading transcription to another machine on the LAN (a Ubuntu
  server at `192.168.1.127`) hoping for better bandwidth — no faster. That
  server's download of a `faster-whisper` model from Hugging Face stalled at
  the same few-KB/s rate as the Mac. This confirms the throttling is
  network/ISP-level (Cameroon), not specific to one machine — moving to
  another local box doesn't route around it. A cloud API (pay-per-use,
  small upload instead of a large model download) is the more reliable
  fix when this CDN is behaving badly, not switching hardware.

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

### 2026-08-04 — First real edit: color + audio pass on a Quran-memorization clip

Full first end-to-end editing session (not just setup). Project: "Introduction
to islam" (already existed in Resolve from the 2026-08-03 connection test).
Source: `~/Downloads/phone raw photage/july/19/20260719_051923.mp4`, 18:23,
1080p30, phone footage. Content/context logged in
`work-with-ai/projects/islamic-study/PROJECT.md`.

- Hit the Downloads-folder TCC wall immediately (see new section above) —
  this drove most of the session's workflow. Worked around it by rendering
  through Resolve's render queue rather than fighting the permission.
- Built the real working timeline (`Intro - Quran Memorization Struggle`)
  from the full source clip. Timeline frame rate is **59.94fps** even though
  the source is natively 30fps — Resolve conforms on placement, so timeline
  frame numbers (e.g. `record_frame`) are in 59.94fps terms, not the source's
  30fps. Worth remembering before doing manual frame-math for clip placement.
- Applied a corrective CDL grade (see "Color grading API gotcha" above) —
  pulled down blown highlights on one side of frame, small gamma lift,
  +5% saturation.
- Measured real loudness (very quiet phone audio, see "Real loudness numbers"
  above), produced a corrected track with ffmpeg's two-pass `loudnorm`,
  added it as a second audio track (`media_pool.append_to_timeline` with
  `start_frame`/`end_frame`/`record_frame`, since audio needs an explicit
  source range — plain `clip_ids` isn't enough), muted the original track
  (`timeline.set_track_enable`), renamed both tracks for clarity. ~1 frame
  of tail drift between the corrected audio and video (audio ends ~66 frames
  /~1.1s before video) — acceptable, didn't try to force-stretch it.
- Ran `silencedetect` on the full audio: only 5 pauses over 1.5-2s in the
  whole 18 minutes. This content type (continuous spoken narration) doesn't
  need silence-based auto-trimming — don't reach for it by default on this
  kind of footage.
- Transcription: Resolve's native `transcribe_audio` (`MediaPoolItem.
  TranscribeAudio`) failed on the Downloads-path clip first (looked like the
  TCC issue again) — but it *also* failed, instantly (~0.4s, no error text),
  once pointed at an accessible copy, and `timeline_ai.create_subtitles`
  failed the same instant, silent way. This is a **Free-edition license
  gate**, not a file-access problem: native AI transcription/subtitles are
  Studio-only, and the free edition (confirmed elsewhere in this doc) just
  returns `{"success": false}` with no explanation instead of an informative
  error. Don't waste time debugging this path on the free edition — go
  straight to external `whisper`/`faster-whisper`. Always check
  `job_status` for actual completion rather than trusting
  `{"success": true, "status": "running"}` alone; quiet failures don't throw.
- Generated media (corrected audio, later the transcript) permanently stored
  at `~/Movies/islamic-study-video-production/` — not the git repo (too
  large), not the session scratchpad (not durable). Relinked the Resolve
  media pool item to the permanent path with `media_pool_item.replace_clip`
  after moving the file.
- Cleaned up disposable multi-GB intermediate renders from scratchpad once
  their data was extracted (full-quality render used only for loudness
  measurement/silence detection — no reason to keep it after).

### 2026-08-06 — Final export for actual publish (not just analysis)

- `render.prepare_render_job` refuses a permanent `target_dir` by default
  (`"target_dir must be under the system temp directory unless
  require_temp_target=False"`) — same guard as the LUT-export/DRX-apply
  actions noted elsewhere. Pass `require_temp_target: false` explicitly to
  render straight to a real destination (e.g. `~/Movies/...`) instead of
  routing through temp + a manual move.
- Stale render-queue jobs from earlier analysis renders (this session's
  scratch exports) persisted in the queue across the whole session —
  `render.delete_job` each stale `job_id` before `render.start`, or you'll
  re-render junk alongside the real job.
- Full 18:23 1080p H.264 final export (graded + corrected-audio timeline)
  took ~7 minutes on this machine — worth knowing when estimating a
  publish-day timeline.
