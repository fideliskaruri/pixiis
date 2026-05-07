# Wave 2 Pane 0 — Window chrome fix

**Branch:** `wave2/chrome-fix`
**Worktree:** `/mnt/d/code/python/pixiis/.worktrees/wave2-chrome/`

> Read `agents/CONTEXT_WAVE2.md` first.

## Mission

Fix the broken window dragging and tighten window-control polish. The buttons themselves work after a rebuild (commit `8acdf56`), but **the navbar isn't actually a drag region** because `NavBar.css` uses Electron's `-webkit-app-region: drag`, which Tauri 2 ignores. Tauri 2 wants `data-tauri-drag-region` as an HTML attribute.

## Files

- `src/components/NavBar.tsx` — handlers + drag attribute
- `src/components/NavBar.css` — remove the dead `-webkit-app-region` rules
- `src-tauri/capabilities/default.json` — verify allow-list (probably OK already)

## Deliverables

1. **Drag region:** add `data-tauri-drag-region` to the `<nav className="navbar">` element. Add `data-tauri-drag-region={false}` (note the inverted boolean attribute — Tauri checks the attribute *value*) explicitly on:
   - the logo (`navbar__logo`)
   - the nav-tabs container
   - the controls container (so buttons inside aren't drag handles)
2. **Remove** every `-webkit-app-region: drag | no-drag` line from `NavBar.css`. Document in a 1-line comment that drag is now `data-tauri-drag-region`.
3. **Verify** the close handler doesn't deadlock on cleanup. `getCurrentWindow().close()` should fire the `WindowEvent::CloseRequested` listener (if any) — check that any teardown in `lib.rs::run` (controller poller, services container) doesn't block. If it does, run teardown async or use a timeout.
4. **Manual smoke checklist** in `agents/STATUS.md` once committed:
   - drag the navbar — window moves
   - click min — window minimises
   - click max — window maximises (icon swaps to ❐)
   - click close — window closes cleanly within 1 s

## Out of scope

- Don't touch any other component
- Don't add new commands

## Reporting

Append to `agents/STATUS.md` at start, on commit, when done. Commit to `wave2/chrome-fix`.
