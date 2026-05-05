/**
 * Pixiis API Bridge — Tauri-native invoke() calls.
 *
 * The old Python sidecar / FastAPI HTTP API is gone in this build; every
 * function below routes through `@tauri-apps/api/core::invoke` to the
 * Rust commands defined in `frontend/src-tauri/src/commands/`.
 */

import { invoke } from '@tauri-apps/api/core';
import { convertFileSrc } from '@tauri-apps/api/core';

// Match the wire shape of crate::types::AppEntry (Pane 7 + library port).
// Frontend code historically called this `GameEntry`; kept as an alias so
// existing components (HomePage, GameTile) don't all have to change names.
export interface AppEntry {
  id: string;
  name: string;
  source: 'steam' | 'xbox' | 'epic' | 'gog' | 'ea' | 'startmenu' | 'manual';
  launch_command: string;
  exe_path: string | null;
  icon_path: string | null;
  art_url: string | null;
  metadata: Record<string, unknown>;
}
export type GameEntry = AppEntry;

export type Config = Record<string, unknown>;

// ── Library ──────────────────────────────────────────────────────────

export function getLibrary(): Promise<AppEntry[]> {
  return invoke<AppEntry[]>('library_get_all');
}

export function scanLibrary(): Promise<AppEntry[]> {
  return invoke<AppEntry[]>('library_scan');
}

export function launchGame(id: string): Promise<void> {
  return invoke('library_launch', { id });
}

export function toggleFavorite(id: string): Promise<boolean> {
  return invoke<boolean>('library_toggle_favorite', { id });
}

export function searchLibrary(query: string): Promise<AppEntry[]> {
  return invoke<AppEntry[]>('library_search', { query });
}

// ── Voice ────────────────────────────────────────────────────────────

export function voiceStart(): Promise<void> {
  return invoke('voice_start');
}

export async function voiceStop(): Promise<{ text: string }> {
  // Backend returns the transcribed text directly; wrap it so existing
  // callers that expect `{ text }` keep working.
  const text = await invoke<string>('voice_stop');
  return { text };
}

// ── Config ───────────────────────────────────────────────────────────

export function getConfig(): Promise<Config> {
  return invoke<Config>('config_get');
}

export function saveConfig(config: Partial<Config>): Promise<void> {
  return invoke('config_set', { values: config });
}

// ── Image proxy ──────────────────────────────────────────────────────

/**
 * Resolve an image URL for use in <img src>. For HTTP(S) URLs we currently
 * pass through unchanged (Steam CDN art is CORS-friendly). For local file
 * paths the helper falls back to Tauri's `convertFileSrc`, which produces
 * a `tauri://` or `asset://` URL that the webview can render directly.
 */
export function imageUrl(url: string | null): string {
  if (!url) return '';
  if (url.startsWith('http://') || url.startsWith('https://') || url.startsWith('data:')) {
    return url;
  }
  return convertFileSrc(url);
}
