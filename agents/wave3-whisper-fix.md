# Wave 3 — Fix whisper-rs build failure

**Branch:** `wave1/integration` (work directly on it — no separate branch)
**Worktree:** `/mnt/d/code/python/pixiis/` (the main worktree)

## The problem

User is building on Windows MSVC + LLVM 21 (latest libclang). The Rust build fails compiling **`whisper-rs 0.13.2`**:

```
error[E0609]: no field `greedy` on type `whisper_full_params`
  --> .../whisper-rs-0.13.2/src/whisper_params.rs:62:20
   |
62 |                 fp.greedy.best_of = best_of;
   |                    ^^^^^^ unknown field
   |
   = note: available field is: `_address`
```

…repeated for `beam_search`, `n_threads`, `n_max_text_ctx`, `offset_ms`, `duration_ms`, `translate`, `no_context`, `no_timestamps`, `single_segment`, `print_special`, …

**Diagnosis:** whisper-rs 0.13.2's source accesses C struct fields directly, but `whisper-rs-sys 0.11.1`'s bindgen output on the user's modern libclang treats `whisper_full_params` as an opaque struct (only exposing `_address`). The wrapper crate and the sys crate are mismatched against this libclang version.

**The Wave 1 spike used these same versions and built successfully** — but it built on a Linux toolchain (zig clang). The mismatch only surfaces on Windows MSVC + recent LLVM.

## Mission

Get the Rust build to compile through the whisper-rs step. Two fix paths to try, in order:

### Path A — Bump to a newer whisper-rs (preferred)

1. Run `cargo search whisper-rs --limit 5` to see current versions on crates.io.
2. Update `src-tauri/Cargo.toml` `whisper-rs = "0.13"` to the latest stable (likely `"0.14"` or `"0.15"` — pick the highest non-pre-release).
3. Run `cargo update -p whisper-rs` to lock the new version.
4. The newer crate may have **API changes** in `FullParams` — common breakages:
   - Field assignment (`params.fp.n_threads = N`) replaced with builder methods (`params.set_n_threads(N)`).
   - `SamplingStrategy::Greedy { best_of: N }` constructor variant.
   - Renamed/moved methods on `WhisperState`.
5. Update `src-tauri/src/voice/transcriber.rs` to match the new API. Read the current file to see what API surface is in use (search for `whisper_rs::`, `FullParams`, `SamplingStrategy`).
6. **Critical:** the user can run `cargo check` on Windows but you can't on WSL (libdbus). Don't try `cargo check` — instead, read the new whisper-rs's docs.rs page or its `tests/` directory for the canonical usage pattern, and hand-verify the diff is consistent.

### Path B — Pin libclang behavior (fallback)

If newer whisper-rs has too many breaking changes:

1. In `src-tauri/build.rs`, set env var `BINDGEN_EXTRA_CLANG_ARGS=-fparse-all-comments -fno-blocks -DWHISPER_NO_BLOCKS` (or whatever forces non-opaque struct generation — check whisper-rs-sys's build.rs for hints on what flags it normally accepts).
2. Or pin `whisper-rs-sys = "=0.11.0"` (or whatever earlier patch version works).
3. Or set `WHISPER_DONT_GENERATE_BINDINGS=1` env var in build.rs and use a vendored bindings file.

This path is brittle. Try A first.

## Verification (best-effort given WSL gap)

- `npx tsc -b --noEmit` should still pass (frontend not affected, but sanity).
- `grep -rn "whisper_rs::" src-tauri/src/` should still resolve in the source code.
- Read `transcriber.rs` end-to-end after edits — make sure the API calls are consistent with the bumped version.
- The user will be the one running `cargo build` again on Windows. Make sure your fix gives them a fighting chance — list any remaining concerns in the commit body.

## Out of scope

- Don't touch any other subsystem.
- Don't add features.
- Don't touch master.

## Commit

```
fix(voice): bump whisper-rs to <version> for Windows MSVC build

whisper-rs 0.13.2 + whisper-rs-sys 0.11.1 fail on libclang 21 (current
LLVM): bindgen produces opaque whisper_full_params struct, but the
wrapper accesses fields directly. Bumped to <new version>, adjusted
transcriber.rs for <API change summary>.

Verified: <whatever you verified>
Pending: user runs `cargo build` on Windows MSVC.
```

Use HEREDOC. Add the standard `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>` trailer.

## Return

Concise summary: which version you bumped to, what API breakages you fixed, sha of the commit, anything you couldn't verify.
