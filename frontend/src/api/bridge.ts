/**
 * Pixiis API Bridge — communicates with the Python backend.
 *
 * In development: connects to localhost:8420 (FastAPI server).
 * In production (Tauri): connects to the sidecar on a dynamic port.
 */

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8420';

export interface GameEntry {
  id: string;
  name: string;
  source: string;
  launch_command: string;
  exe_path: string | null;
  icon_path: string | null;
  art_url: string | null;
  is_game: boolean;
  is_installed: boolean;
  is_favorite: boolean;
  playtime_minutes: number;
  playtime_display: string;
  last_played: number;
  metadata: Record<string, unknown>;
}

export interface Config {
  [key: string]: unknown;
}

// ── Library ──────────────────────────────────────────────────────────

export async function getLibrary(): Promise<GameEntry[]> {
  const res = await fetch(`${API_BASE}/library`);
  return res.json();
}

export async function scanLibrary(): Promise<GameEntry[]> {
  const res = await fetch(`${API_BASE}/library/scan`, { method: 'POST' });
  return res.json();
}

export async function launchGame(id: string): Promise<void> {
  await fetch(`${API_BASE}/library/launch/${id}`, { method: 'POST' });
}

export async function toggleFavorite(id: string): Promise<boolean> {
  const res = await fetch(`${API_BASE}/library/favorite/${id}`, { method: 'POST' });
  const data = await res.json();
  return data.is_favorite;
}

// ── Voice ────────────────────────────────────────────────────────────

export async function voiceStart(): Promise<void> {
  await fetch(`${API_BASE}/voice/start`, { method: 'POST' });
}

export async function voiceStop(): Promise<{ text: string }> {
  const res = await fetch(`${API_BASE}/voice/stop`, { method: 'POST' });
  return res.json();
}

// ── Config ───────────────────────────────────────────────────────────

export async function getConfig(): Promise<Config> {
  const res = await fetch(`${API_BASE}/config`);
  return res.json();
}

export async function saveConfig(config: Partial<Config>): Promise<void> {
  await fetch(`${API_BASE}/config`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  });
}

// ── Image proxy (for CORS-safe image loading) ────────────────────────

export function imageUrl(url: string | null): string {
  if (!url) return '';
  // Steam CDN and most game art URLs are CORS-friendly
  return url;
}
