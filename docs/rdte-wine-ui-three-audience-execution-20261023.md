# WineBot Windows application qualification work plan — 2026-10-23

**Execution authority:** WineBot project draft PRs, security `SemperSupra/agent-dispatch-private#515` and project/portfolio handoff `SemperSupra/agent-dispatch-private#107`. This is a staged DLE (**Durable, Legible, Executable**) plan, not authorization to merge, publish, or bypass controls.

## Observed baseline

- Real WineBot `intent-rel` in disposable Linux CI under Xvfb/Wine: Notepad, Wine File Manager, Wine Configuration, Registry Editor all **launched with visible X11 windows and window-only screenshots** in the synthetic 96/144 DPI trials. RDTE #131: [run 39994111643](https://github.com/SemperSupra/WineBot/actions/runs/39994111643), [run 39995188180](https://github.com/SemperSupra/WineBot/actions/runs/39995188180).
- 144 DPI grayscale materially improves classic-menu/dialog legibility but may clip content in fixed-size file-manager/registry windows. At 144 DPI ClearType did not produce an observed static-font improvement under Xvfb; grayscale is the validated deterministic screenshot baseline.
- Authenticated `GET /windows` succeeds during Notepad; `GET /wininspect/capabilities` and `GET /wininspect/windows` were unavailable. Container diagnostic: WinInspect enabled but expected **flat-root** `wininspectd.exe` and `wininspect.exe` missing. Release `v0.4.4` build script stages binaries under **`App/WinInspect/`**; WineBot unzips its verified package under `/opt/winebot/windows-tools/WinSpy`. Last runtime evidence: [run 39997099944](https://github.com/SemperSupra/WineBot/actions/runs/39997099944).
- Production main still pins missing WinInspect `v0.4.0`; distinct draft **#124** fixes the verified package download to `v0.4.4`. Draft **#125** suppresses automatic BuildKit uploads, **#127** minimizes public conformance reports/console payloads, **#129** distinguishes source from tested checkout. All remain separate and gated. Legacy v1 conformance **54 pass / 8 fail / 9 skip** remains red under **#123** contract-policy review.

## Dependency-aware execution

### READY A — exact executable path and semantic startup, independent of graphics research

1. Preserve flat-install compatibility, discover the **complete** nested `App/WinInspect` directory when both daemon and CLI are present; honor explicit env path and fail closed for incomplete or unrelated tool directories.
2. Add positive/negative synthetic path tests and include them in normal unit lane (prior `test_wininspect.py` is not run by the default unit script and has stale protocol assertions; fix those independently).
3. Qualify with a **disposable public** WineBot release-intent image using the previously verified, unmerged safe image/build composition from closed #130. Do not merge security drafts just to test.
4. Launch synthetic Notepad, probe `/windows`, `/health/wininspect`, `/wininspect/capabilities`, and `/wininspect/windows` via read-only authenticated API calls, record **booleans + count classes + allowlisted component versions only**. Never upload full WinInspect responses, screenshot root or runtime process/host paths.
5. Distinguish installation, daemon readiness, transport, protocol negotiation and semantic window results. A successful build is not a semantic acceptance. Record first failure and next minimal correction; maintain draft until reviewed.

### READY B — independent CPU software 3D / gaming

- [Draft renderer PR #132](https://github.com/SemperSupra/WineBot/pull/132): qualification of CPU LLVMpipe GLX and Lavapipe Vulkan, SwiftShader only when a pinned ICD is explicitly admitted. Do not promote generic GPU acceleration, CV-training quality or Direct3D parity from renderer smoke.
- [Draft game PR #133](https://github.com/SemperSupra/WineBot/pull/133): bounded Windows OpenTTD 15.3/OpenGFX 8.0 executable launch. Require actual visible window; input, FPS, save/readback, screenshot correctness and sustained game performance are subsequent gates.
- Keep both branches independently qualified, record exact run/source/pinned input checksums, avoid duplicate runners/parallel execution on the same authority branch.

### READY C — visual and audience UX specification

- **Human:** readable `144 DPI` default candidate with DPI-aware window placement/minimum client sizes, clearly described active app/focus and observer/control holder, responsive dashboard, visible safety controls and no untrusted state optimism.
- **Assistive technology:** keyboard focus/labels and real Wine/WinInspect semantic tree to assistive clients. Do not equate successful X11 screenshot with assistive technology acceptance.
- **Automation:** pinned profile (`DPI`, resolution, smoothing, window geometry), typed application lifecycle and stable operation receipts with deterministic output hash.
- **Agents:** observe (WinInspect/Win32 and X11) → bounded plan → broker-authorized action → independent readback → durable receipt. Distinguish Linux X11 ID vs Windows HWND and note provider capability limitations. Preserve revoked/denied actions as such.
- Add *orthogonal* visual profile selector in a separately reviewed PR after experiments; don't silently mutate use-case/performance profiles.

### WAITING D — brokered transactional WinBot app UX

After WinInspect observation and actor/lease admission: Notepad **broker-mediated** launch, locate editor, input synthetic data, save, content readback and crop/hash verification; then File Manager navigation and Paint-like canvas case. Confirm correct lease epoch/generation, idempotency key, human handback/STOP_NOW, and independent input outcome. No direct Wine shell/xdotool or raw Python mutation may count as this gate.

### WAITING E — CV / held-out capture training

Private `desktop-ui-cv` draft #44's schema/validator qualifies synthetic manifests locally. Requires independent candidate inventory digest, dated pre-capture checkpoint witness, private image/data custody, explicit human review and qualified target model before actual capture/model fine-tuning. No private GitHub Actions minutes or model/cloud data spill by default.

### WAITING F — production/release

Independent security #515 review/approval of #125/#127/#129, packaging #124, #123 v1/vNext conformance semantics; changes must be requalified after merge ordering. Keep all experimental PRs draft/unmerged and preserve first failures, worktrees and immutable receipts. Do not prune branches or archive until source history/worktree/consumer gates are satisfied.

## Version and proof fields required on every new app qualification run

`source_sha`, `tested_checkout_sha`, image digest if available, image base tag, actual `wine --version`, package versions for Xvfb/Openbox/Mesa/GLX/Vulkan when probed, WinInspect release and API protocol outcome, `WINE_DPI`, smoothing, `DISPLAY` class (not host address), screenshot digest/size if publication admitted, app name+free-license provenance and exact read-only/interaction outcome.

Public logs/artifacts may include **only software/version and safe abstract status fields**. Do not disclose hostname, hardware, CPU/GPU model, device configuration, username, IP, local paths or actual runtime window titles. Hold raw evidence job-local/private as appropriate.

**Next baton:** execute A with exact-head local unit tests and combined public CI runtime probe; in parallel reconcile B terminal workflows and record first failures. Leave D/E/F blocked until their independently owned gates pass.
