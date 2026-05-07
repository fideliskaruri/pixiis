# Wave 2 Pane 7 — File Manager page (manual entries editor)

**Branch:** `wave2/files-page`
**Worktree:** `/mnt/d/code/python/pixiis/.worktrees/wave2-files/`

> Read `agents/CONTEXT_WAVE2.md` first.

## Mission

Build a new **File Manager** page that lets the user manually add/edit games not picked up by any storefront scanner. Editorial, simple, list + form.

## Reference

- Python original: `src/pixiis/ui/pages/file_manager_page.py` + `widgets/file_browser.py`
- Config section: `library.manual.apps` (read/written via `config_get` / `config_set`)
- Tokens: `src/styles/tokens.css`
- Commands: `config_get`, `config_set`, `library_scan`

## Deliverables

1. **`src/pages/FileManagerPage.tsx`** — route `/files`:
   - List of manual entries on the left (each row: name + path + delete)
   - Form on the right: Name, Executable path (browse button uses `dialog:allow-open`), Args, Icon path (browse), Working dir (browse). Save / Cancel.
   - "Add new entry" button at top of list opens an empty form
2. **`src/pages/FileManagerPage.css`** — editorial; small-caps `MANUAL ENTRIES` heading, monospace for paths
3. **File picker:** use `@tauri-apps/plugin-dialog`'s `open()` with appropriate filters (`.exe`, `.lnk`, etc. for executable; `.png/.jpg/.ico` for icon)
4. **Persistence:** save updates the `library.manual.apps` array via `config_set`. Then call `library_scan` so the new entries appear in Library immediately.
5. **Validation:**
   - Executable must exist (use `fs:default` to stat — already in capabilities)
   - Name not empty, no duplicate names
   - Show inline error in red `var(--accent)` only on form fields (single-accent rule)
6. **Route registration** in `App.tsx`.

## Acceptance criteria

- Add an entry → it shows up in the list and in Library after scan
- Delete an entry → removed from config, scan refreshes
- File pickers work (system native)
- All paths render in monospace
- Editorial language only

## Out of scope

- Scan custom folders — Folder Scanner already handles that, configured in Settings
- Drag-and-drop import (future)
- Bulk import from CSV (future)

## Reporting

Append to `agents/STATUS.md`. Commit to `wave2/files-page`.
