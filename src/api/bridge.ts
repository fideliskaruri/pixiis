/**
 * Pixiis API Bridge — Tauri-native invoke() calls.
 *
 * The wire shape comes straight from the Rust types via ts-rs
 * (`src/api/types/AppEntry.ts`). The bridge then enriches every
 * row with derived fields (favorite, last-played, playtime display)
 * so React components can read flat properties without going
 * through the metadata map.
 */

import { invoke, convertFileSrc } from '@tauri-apps/api/core';
import type { AppEntry as WireAppEntry } from './types/AppEntry';
import type { AppSource } from './types/AppSource';
import type { RawgGameData } from './types/RawgGameData';

// Public, enriched shape used by every React component. `extends` the
// generated wire type so any new field (or change to AppSource) becomes
// a TypeScript error here, not a silent drift.
export interface AppEntry extends WireAppEntry {
  is_favorite: boolean;
  is_game: boolean;
  is_installed: boolean;
  playtime_minutes: number;
  playtime_display: string;
  last_played: number;
}
export type GameEntry = AppEntry;
export type { AppSource, RawgGameData };

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

function enrich(raw: WireAppEntry): AppEntry {
  const m = raw.metadata ?? {};
  const playtime_minutes = asNumber(m.playtime_minutes);
  return {
    ...raw,
    metadata: m,
    is_favorite: m.favorite === true,
    is_game: raw.source !== 'manual' || /\.exe$/i.test(raw.launch_command),
    is_installed: raw.exe_path !== null,
    playtime_minutes,
    playtime_display: formatPlaytime(playtime_minutes),
    last_played: asNumber(m.last_played),
  };
}

function enrichAll(rows: WireAppEntry[]): AppEntry[] {
  return rows.map(enrich);
}

// ── Library ──────────────────────────────────────────────────────────

export async function getLibrary(): Promise<AppEntry[]> {
  return enrichAll(await invoke<WireAppEntry[]>('library_get_all'));
}

export async function scanLibrary(): Promise<AppEntry[]> {
  return enrichAll(await invoke<WireAppEntry[]>('library_scan'));
}

export function launchGame(id: string): Promise<void> {
  return invoke('library_launch', { id });
}

export function toggleFavorite(id: string): Promise<boolean> {
  return invoke<boolean>('library_toggle_favorite', { id });
}

export async function searchLibrary(query: string): Promise<AppEntry[]> {
  return enrichAll(await invoke<WireAppEntry[]>('library_search', { query }));
}

// ── RAWG metadata ────────────────────────────────────────────────────

/**
 * Fetch RAWG metadata (description, screenshots, genres, …) for a game
 * by its display name. Returns `null` when no API key is configured or
 * RAWG returns no match — never throws into the UI for missing data.
 */
export function lookupRawg(gameName: string): Promise<RawgGameData | null> {
  return invoke<RawgGameData | null>('services_rawg_lookup', { gameName });
}

// ── Voice ────────────────────────────────────────────────────────────

export function voiceStart(): Promise<void> {
  return invoke('voice_start');
}

export async function voiceStop(): Promise<{ text: string }> {
  // Backend returns the transcribed text; wrap it so existing callers
  // that destructure `{ text }` keep working.
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
 * Resolve an image URL for use in <img src>. HTTP(S) URLs pass through
 * unchanged (Steam CDN art is CORS-friendly). Local file paths fall
 * back to Tauri's `convertFileSrc`, which produces a `tauri://` URL the
 * webview can render directly.
 */
export function imageUrl(url: string | null): string {
  if (url === null || url === '') return '';
  if (url.startsWith('http://') || url.startsWith('https://') || url.startsWith('data:')) {
    return url;
  }
  return convertFileSrc(url);
}
