/**
 * Pixiis API Bridge — Tauri-native invoke() calls.
 *
 * The old Python sidecar / FastAPI HTTP API is gone in this build; every
 * function below routes through `@tauri-apps/api/core::invoke` to the
 * Rust commands defined in `frontend/src-tauri/src/commands/`.
 */

import { invoke } from '@tauri-apps/api/core';
import { convertFileSrc } from '@tauri-apps/api/core';

// The wire shape of crate::types::AppEntry (Pane 7 + library port). The
// fields below `metadata` are *derived* on the JS side from metadata
// values that the Rust helpers (is_favorite / playtime_minutes / etc.)
// also key on — kept here so existing React components can read flat
// properties without thinking about the metadata map. Frontend code
// historically called this type `GameEntry`; alias retained.
export interface AppEntry {
  id: string;
  name: string;
  source: 'steam' | 'xbox' | 'epic' | 'gog' | 'ea' | 'startmenu' | 'manual';
  launch_command: string;
  exe_path: string | null;
  icon_path: string | null;
  art_url: string | null;
  metadata: Record<string, unknown>;
  // ── Derived (filled by enrich()) ──
  is_favorite: boolean;
  is_game: boolean;
  is_installed: boolean;
  playtime_minutes: number;
  playtime_display: string;
  last_played: number;
}
export type GameEntry = AppEntry;

export type Config = Record<string, unknown>;

function asNumber(v: unknown): number {
  return typeof v === 'number' && Number.isFinite(v) ? v : 0;
}

function formatPlaytime(minutes: number): string {
  if (minutes <= 0) return '';
  if (minutes < 60) return `${minutes}m`;
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return m === 0 ? `${h}h` : `${h}h ${m}m`;
}

function enrich(raw: AppEntry): AppEntry {
  const m = raw.metadata ?? {};
  const playtime_minutes = asNumber(m.playtime_minutes);
  return {
    ...raw,
    metadata: m,
    is_favorite: m.favorite === true,
    is_game: raw.source !== 'manual' || /\.exe$/i.test(raw.launch_command),
    is_installed: raw.exe_path != null,
    playtime_minutes,
    playtime_display: formatPlaytime(playtime_minutes),
    last_played: asNumber(m.last_played),
  };
}

function enrichAll(rows: AppEntry[]): AppEntry[] {
  return rows.map(enrich);
}

// ── Library ──────────────────────────────────────────────────────────

export async function getLibrary(): Promise<AppEntry[]> {
  return enrichAll(await invoke<AppEntry[]>('library_get_all'));
}

export async function scanLibrary(): Promise<AppEntry[]> {
  return enrichAll(await invoke<AppEntry[]>('library_scan'));
}

export function launchGame(id: string): Promise<void> {
  return invoke('library_launch', { id });
}

export function toggleFavorite(id: string): Promise<boolean> {
  return invoke<boolean>('library_toggle_favorite', { id });
}

export async function searchLibrary(query: string): Promise<AppEntry[]> {
  return enrichAll(await invoke<AppEntry[]>('library_search', { query }));
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
