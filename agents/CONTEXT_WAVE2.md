# Pixiis Wave 2 — Shared Context

> Read this first. Same for every Wave 2 pane.

## What changed since Wave 1

Wave 1 finished: all 3 Phase 0 spikes passed, Tauri scaffold + types + controller + services landed, integration branch (`wave1/integration`) merged everything and produced a buildable app.

You are working off `wave1/integration` (not master). Repo layout is now Tauri-shaped:

```
/mnt/d/code/python/pixiis/
├── src/                    React + TS (root, was frontend/)
│   ├── components/         NavBar.tsx etc.
│   ├── pages/              HomePage.tsx, GameDetailPage.tsx, ...
│   ├── api/                bridge.ts (now uses invoke(), not HTTP)
│   ├── api/types/          ts-rs generated types (17 files)
│   ├── styles/             tokens.css (editorial), animations.css, PALETTE.md
│   ├── hooks/              useController.ts, useSpatialNav.ts
│   └── pixiis/             ⚠️  OLD Python source — kept for reference, NOT shipped
├── src-tauri/              Rust crate
│   ├── src/
│   │   ├── lib.rs          builder + plugin wiring + invoke_handler
│   │   ├── types.rs        17 ts-rs DTOs (AppEntry, ControllerEvent, ...)
│   │   ├── error.rs        thiserror AppError
│   │   ├── commands/       library, voice, controller, services, config
│   │   ├── controller/     gilrs backend, mapping, macros
│   │   ├── services/       rawg, twitch, youtube, oauth, image_loader, vibration
│   │   └── library/        registry, cache, steam, folder (Wave 2 adds the rest)
│   ├── capabilities/default.json
│   └── tauri.conf.json
├── spike/                  Wave 1 Phase 0 spikes (whisper-bench, kokoro-bench, uwp-detect, baselines.md)
└── .worktrees/wave2-*/     your isolated worktrees
```

## What's already done (don't redo)

- `library/steam.rs`, `library/folder.rs`, `library/cache.rs` — implemented in integration
- `bridge.ts` migrated from HTTP fetch to `@tauri-apps/api/core::invoke()`
- Editorial design tokens (`src/styles/tokens.css`) — Fraunces + Inter, off-white palette, single accent
- HomePage, GameTile, GameDetailPage — already restyled to editorial (3 iterations of reviewer feedback)
- NavBar — visual chrome plus minimize/maximize/close handlers wired to Tauri 2 window API
- Controller subsystem (gilrs, 60 Hz background poller, macro engine)
- Services (RAWG/Twitch/YouTube/OAuth/image cache/vibration) — fully implemented
- `types.rs` + 17 generated `.ts` files

## What Wave 2 produces

| Pane | Branch | Purpose |
|---|---|---|
| 0 | wave2/chrome-fix | Fix `-webkit-app-region` (Electron API, ignored by Tauri) → `data-tauri-drag-region` so window dragging works. Plus minor chrome polish. |
| 1 | wave2/voice | Lift spike/whisper-bench → src-tauri/src/voice/. Audio capture, VAD, transcription pipeline. |
| 2 | wave2/tts | Lift spike/kokoro-bench → src-tauri/src/voice/tts.rs. Wire voice_speak. |
| 3 | wave2/scanners-misc | Port Epic / GOG / EA / StartMenu scanners |
| 4 | wave2/xbox | Lift spike/uwp-detect → src-tauri/src/library/xbox.rs |
| 5 | wave2/settings-page | New Settings page, editorial language |
| 6 | wave2/onboarding-page | New Onboarding page, editorial language |
| 7 | wave2/files-page | New File Manager page (manual entries) |
| 8 | wave2/library-polish | Review + tighten Library + GameDetail iterations |

## Rules (unchanged from Wave 1)

1. Stay in your worktree. Don't touch other panes' worktrees.
2. Commit to your branch, don't push, don't merge.
3. Update `agents/STATUS.md` at start, milestones, blocked, done. Append, don't overwrite.
4. Ask the user via your tmux pane if blocked on a real decision.
5. Don't refactor outside your brief.
6. Don't write README/docs unless explicitly asked.

## Where to look for reference

- Python source: `src/pixiis/` (in your worktree, untouched for reference)
- Wave 1 spike code: `spike/{whisper-bench,kokoro-bench,uwp-detect}/` (committed on integration)
- Wave 1 types: `src-tauri/src/types.rs` and `src/api/types/`
- Editorial design system: `src/styles/PALETTE.md`
- Existing pages for style reference: `src/pages/HomePage.tsx`, `GameDetailPage.tsx`
- Build recipe: `BUILD.md`
