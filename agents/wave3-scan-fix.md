# Wave 3 — Fix scan returning 0 results silently

**Branch:** `wave1/integration` (work directly on it)
**Worktree:** `/mnt/d/code/python/pixiis/`

## The bug

`LibraryService::scan()` in `src-tauri/src/library/mod.rs` iterates providers and calls each one's `scan()` synchronously. **If any single provider panics, the whole iteration unwinds.** The Tauri command at `src-tauri/src/commands/library.rs::library_scan` wraps the call in `tokio::task::spawn_blocking(...).await.unwrap_or_default()` — meaning a panic becomes `JoinError`, which `unwrap_or_default()` swallows and returns `Vec::new()`. The user sees "Found 0 entries" with **zero diagnostic information**.

The user just hit this — they have games installed across multiple storefronts and `scan_library()` returned zero. We can't tell which provider crashed without logs.

## Mission

1. **Make scan resilient to provider panics.**
2. **Surface what each provider did.** Log to disk + emit Tauri events.
3. **Don't break the build** (you can't verify on WSL — see verification gaps below).

## Files

- `src-tauri/src/library/mod.rs` — `LibraryService::scan()`
- `src-tauri/src/commands/library.rs` — `library_scan` command
- `src-tauri/src/lib.rs` — service construction (already on disk; you may need to pass an `AppHandle` to scan for event emission)
- `src-tauri/Cargo.toml` — `chrono` may already be there for the log timestamp, otherwise add a simple `std::time::SystemTime` formatter

## Deliverables

### 1. `LibraryService::scan_with_progress(&self, app: &AppHandle) -> ScanReport`

Replace the existing `pub fn scan(&self)` with a new method that takes a Tauri `AppHandle` for event emission. Keep `scan()` as a thin wrapper that calls `scan_with_progress` with `None` for backward compat (or just inline the change — either way).

```rust
pub struct ScanReport {
    pub entries: Vec<AppEntry>,
    pub providers: Vec<ProviderReport>,
}

#[derive(Serialize, Clone)]
pub struct ProviderReport {
    pub name: String,
    pub state: ProviderState,  // "scanning" | "done" | "unavailable" | "error"
    pub count: usize,
    pub error: Option<String>,
    pub elapsed_ms: u64,
}
```

For each provider:
- Emit `library:scan:progress` event with `ProviderReport { state: "scanning", ... }`
- Time it
- Wrap the call in `std::panic::catch_unwind(AssertUnwindSafe(|| p.scan()))` so panics are caught
- On success, emit progress with `state: "done", count: N`
- On panic, emit progress with `state: "error", error: <panic message>`
- On `is_available() == false`, emit `state: "unavailable"`
- Append a structured log line to `%APPDATA%/pixiis/scan_debug.log`

The log line format:
```
2026-05-08T15:30:00Z  steam        done          43 entries   ( 124ms)
2026-05-08T15:30:00Z  xbox         error          0 entries   (   0ms)  WinRT activation failed: ...
2026-05-08T15:30:00Z  folder       done          12 entries   ( 873ms)
```

Append-only, simple text. Truncate/rotate if it exceeds ~1 MB so it doesn't grow unbounded — keep the most recent ~100 KB.

### 2. `commands/library.rs::library_scan` — return `ScanReport`

Change the response shape from `Vec<AppEntry>` to:

```rust
#[derive(Serialize, ts_rs::TS)]
#[ts(export)]
pub struct ScanResult {
    pub entries: Vec<AppEntry>,
    pub providers: Vec<ProviderReport>,  // also TS-exported
}
```

The frontend (`src/api/bridge.ts::scanLibrary`) must be updated to match the new shape. It currently does:
```ts
return enrichAll(await invoke<WireAppEntry[]>('library_scan'));
```
Change to something like:
```ts
const result = await invoke<{ entries: WireAppEntry[]; providers: ProviderReport[] }>('library_scan');
console.log('[scan]', result.providers); // dev visibility
return enrichAll(result.entries);
```

Or expose a richer return if Settings page wants to display per-provider stats.

### 3. Settings page provider report (optional but nice)

If straightforward, after Settings → Scan Now, render the per-provider report below the existing "Found N entries" line:

```
STEAM     ✓  43 entries   124ms
XBOX      ✗  WinRT activation failed
EPIC      —  not detected
FOLDER    ✓  12 entries   873ms
…
```

If it adds too much UI churn, skip — the events are emitted and the log file is the actionable data.

### 4. Onboarding scan-progress UI now works

The Onboarding page already listens for `library:scan:progress` events (per `OnboardingPage.tsx`). Verify the event payload shape it expects matches what you emit — adjust either side to align. You'll need to read `OnboardingPage.tsx` for the shape.

## Verification

- **WSL can't `cargo check`** (libdbus). Read code carefully and trust the agents that already have working `cargo test`/`cargo build` patterns.
- `npx tsc -b --noEmit` from repo root must pass after frontend changes.
- `grep` to ensure no remaining `unwrap_or_default()` swallowing panics in `library_scan`.
- The new log file path uses `dirs::data_dir()` or equivalent — match the existing pattern in `lib.rs` for `%APPDATA%\pixiis\`.

## Out of scope

- Don't fix the underlying provider bug yet — we need the diagnostic output first to know which provider's broken.
- Don't refactor providers.
- Don't touch master.

## Commit

```
fix(library): isolate provider panics + surface per-provider scan report

Previously LibraryService::scan() ran each provider synchronously; any
panic unwound the whole iteration and library_scan's tokio::spawn_blocking
JoinError got `unwrap_or_default()`-ed into Vec::new(). The user saw
"Found 0 entries" with no error and no clue which provider failed.

Now each provider's scan call is wrapped in catch_unwind, timed, and
emitted as a `library:scan:progress` event. Per-provider state + count +
error message also lands in %APPDATA%/pixiis/scan_debug.log so the user
can paste it for triage. The Tauri command returns ScanResult { entries,
providers } so the frontend can show what actually ran.
```

Use HEREDOC. Standard `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>` trailer.

## Return

Concise summary: which files changed, line count delta, sha, anything you couldn't verify, and the EXACT path the user should `type` (PowerShell) after running scan to see the debug log:
```
type "$env:APPDATA\pixiis\scan_debug.log"
```
