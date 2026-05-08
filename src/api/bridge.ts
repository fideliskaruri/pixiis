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
import type { ProviderReport } from './types/ProviderReport';
import type { RawgGameData } from './types/RawgGameData';
import type { TranscriptionEvent } from './types/TranscriptionEvent';

export type { ProviderReport };
export type { ProviderState } from './types/ProviderState';

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
    // Mirrors Rust AppEntry::is_game() exactly. Storefront entries
    // (Steam / Epic / GOG / EA) are always games. Xbox checks the
    // MicrosoftGame.Config probe (`is_xbox_game` set by xbox.rs).
    // Manual entries (user added them via FileManagerPage) carry
    // `is_game: true` in metadata by default — see manual.rs.
    // Folder-scanned and start-menu shortcuts are NOT games — Home
    // should hide them.
    is_game: ((): boolean => {
      switch (raw.source) {
        case 'steam':
        case 'epic':
        case 'gog':
        case 'ea':
          return true;
        case 'xbox':
          return m.is_xbox_game === true;
        case 'manual':
          return m.is_game === true;
        case 'folder':
          return false;
        case 'startmenu':
        default:
          return false;
      }
    })(),
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

interface ScanResultWire {
  entries: WireAppEntry[];
  providers: ProviderReport[];
}

export async function scanLibrary(): Promise<AppEntry[]> {
  const result = await invoke<ScanResultWire>('library_scan');
  // Per-provider report is persisted to `%APPDATA%\pixiis\scan_debug.log`
  // by the backend; UI surfaces (SettingsPage, Onboarding) consume the
  // same data via `scanLibraryWithReport` rather than the console.
  return enrichAll(result.entries);
}

/// Variant returning the raw per-provider report alongside enriched
/// entries — for surfaces that want to render storefront-by-storefront
/// stats (e.g. a Settings panel "Found 43 from Steam, 0 from Xbox").
export async function scanLibraryWithReport(): Promise<{
  entries: AppEntry[];
  providers: ProviderReport[];
}> {
  const result = await invoke<ScanResultWire>('library_scan');
  return { entries: enrichAll(result.entries), providers: result.providers };
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
 * by its display name. Returns `null` when no API key is configured,
 * when RAWG returns no match, or when the IPC call rejects — never
 * throws into the UI.
 */
export async function lookupRawg(gameName: string): Promise<RawgGameData | null> {
  try {
    return await invoke<RawgGameData | null>('services_rawg_lookup', { gameName });
  } catch {
    return null;
  }
}

// ── Voice ────────────────────────────────────────────────────────────

export function voiceStart(): Promise<void> {
  return invoke('voice_start');
}

export async function voiceStop(): Promise<TranscriptionEvent> {
  // Backend returns the full TranscriptionEvent struct ({ text, is_final,
  // timestamp }) — older versions returned a bare string. We unwrap a
  // string just in case a stub build is wired in, but the typed shape is
  // the source of truth. Callers that only need the text destructure it.
  const result = await invoke<TranscriptionEvent | string>('voice_stop');
  if (typeof result === 'string') {
    return { text: result, is_final: true, timestamp: Date.now() / 1000 };
  }
  return result;
}

// ── Config ───────────────────────────────────────────────────────────

export function getConfig(): Promise<Config> {
  return invoke<Config>('config_get');
}

export function saveConfig(config: Partial<Config>): Promise<void> {
  // Arg name matches the Rust signature `config_set(_patch: Map<...>)` and
  // the inline call in SettingsPage; previously this used `values:` which
  // would silently miss the parameter once the stub gets a real impl.
  return invoke('config_set', { patch: config });
}

// ── Onboarding marker ────────────────────────────────────────────────

export function getOnboarded(): Promise<boolean> {
  return invoke<boolean>('app_get_onboarded');
}

export function setOnboarded(value: boolean): Promise<void> {
  return invoke('app_set_onboarded', { value });
}

// ── System power ─────────────────────────────────────────────────────

export function systemSleep(): Promise<void> {
  return invoke('system_sleep');
}

export function systemLock(): Promise<void> {
  return invoke('system_lock');
}

export function systemRestart(): Promise<void> {
  return invoke('system_restart');
}

// ── Global summon hotkey ─────────────────────────────────────────────

/**
 * Read the currently configured global summon hotkey
 * (default: `Ctrl+Shift+Alt+P`). Empty string means "disabled".
 */
export function getSummonShortcut(): Promise<string> {
  return invoke<string>('app_get_summon_shortcut');
}

/**
 * Persist + re-register the global summon hotkey. Pass an empty string
 * to disable. Returns the persisted value (round-tripped from Rust so
 * callers can reflect "what we actually saved").
 */
export function setSummonShortcut(shortcut: string): Promise<string> {
  return invoke<string>('app_set_summon_shortcut', { shortcut });
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
