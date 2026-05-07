# Pixiis Migration — Shared Context

**Read this before reading your individual brief.** It's the same for every pane.

## Project

Pixiis is a Windows game launcher with controller + voice control, currently written in Python (PySide6 UI + faster-whisper STT + Kokoro TTS + XInput controller + storefront scanners). We are porting to **Tauri 2 + Vite 8 + React 19 + Rust** with a new **editorial** design language.

The migration plan is 9 phases. You are part of Wave 1 — the maximum-parallel set of tasks that have no hard dependencies on each other (or that have explicit "wait until X exists" gates).

## Repo paths

| Path | What |
|---|---|
| `/mnt/d/code/python/pixiis/` | Main repo (master branch). **Do not edit here.** |
| `/mnt/d/code/python/pixiis/.worktrees/paneN-<task>/` | Your isolated worktree. **Edit here.** |
| `/mnt/d/code/python/pixiis/agents/` | Briefs + status board (shared across panes) |
| `/mnt/d/code/python/pixiis/spike/` | Phase 0 spike workspace (panes 1–4 use this) |
| `/mnt/d/code/python/pixiis/src/pixiis/` | Existing Python source — read it for contracts, don't modify |
| `/mnt/d/code/python/pixiis/frontend/` | Existing Vite/React frontend — Tauri-aware, ~60% complete |

## What we're keeping

- **`frontend/src/api/bridge.ts`** — currently HTTP REST to Python sidecar, will become `invoke()` calls. Don't replace yet.
- **`frontend/src/hooks/useController.ts`** + **`useSpatialNav.ts`** — mature gamepad hooks. Keep.
- **`frontend/src/pages/HomePage.tsx`** — works end-to-end, but will be **restyled** (PS5 glass → editorial).

## What we're replacing

- **All of `src/pixiis/`** (Python) → Rust under `frontend/src-tauri/src/`
- **PS5 glass-morphism CSS** in `frontend/src/styles/theme.css`, `animations.css`, and component CSS → editorial language
- **`frontend/src/api/bridge.ts` HTTP** → Tauri `invoke()` (Phase 1A)

## Editorial design language

- **Type:** Fraunces (serif display) for game titles + section heads, Inter (sans) for body, small-caps tracked labels for `FEATURED` / `CONTINUE PLAYING` / `PLAYED`
- **Color:** warm near-black bg `#0F0E0C`, off-white type `#EDE9DD`, dim `#8A8478`, single accent `#C5402F` reserved for the `▶ PLAY` CTA and focus rings only
- **Motion:** 200 ms ease-in-out cross-fades. **No springs, no overshoots.** That was the old PS5 language.
- **Layout:** generous whitespace, asymmetric featured slot, horizontal rules between sections, captioned metadata

## Reporting

Every pane MUST:

1. **Commit work to its branch** as you go. Don't push. Don't merge.
2. **Update `/mnt/d/code/python/pixiis/agents/STATUS.md`** when you start, hit a milestone, get blocked, or finish. Append to it — don't overwrite. Format:
   ```
   ## paneN-<task> — <ISO timestamp>
   <STATUS: started | progress | blocked | done>
   <one-paragraph note>
   ```
3. **Ask the user via the chat** if you're blocked on a real decision (the user is attached to your tmux pane and can answer).
4. **Don't touch other panes' worktrees.** Stay in your own.

## Anti-scope

- Don't refactor things that are out of your brief.
- Don't add features beyond the brief.
- Don't write README/docs unless explicitly asked.
- Don't push to remote.
- Don't merge branches.
- Don't run destructive git commands.

## Coordination quirks

- Some panes wait for others (your brief will say). While waiting, do useful prep work (study the relevant Python source, sketch types, draft tests). Don't sit idle.
- All worktrees start from commit `9b35bfe` on `master` (the React+Tauri-aware HEAD).
- The user can attach to any pane with `tmux attach -t pixiis-build` and `Ctrl-b + arrow` to switch panes. They may interrupt to redirect you.
