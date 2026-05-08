/**
 * UiPrefsContext — Shared UI preference flags loaded from config.
 *
 * The Settings page owns mutation; this context exposes a read view
 * any page can consume without re-fetching. The flags here are the
 * ones discoverable on Home (greeting, recently-added rail, surprise
 * button) so users can disable each from one place. Defaults are
 * "feature on" — config absence means the user has never opted out.
 *
 * Writes happen via `saveConfig` from any consumer; the provider
 * listens for `pixiis://ui-prefs:changed` (a window CustomEvent) so a
 * Settings save can flag the in-memory snapshot as stale and we
 * re-read. Avoids a full app remount on every toggle.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { getConfig } from './bridge';

export interface UiPrefs {
  greetingEnabled: boolean;
  recentlyAddedEnabled: boolean;
  surpriseMeEnabled: boolean;
  weatherEnabled: boolean;
  weatherLatitude: number | undefined;
  weatherLongitude: number | undefined;
  /** Display name shown in the greeting. */
  displayName: string;
}

const DEFAULTS: UiPrefs = {
  greetingEnabled: true,
  recentlyAddedEnabled: true,
  surpriseMeEnabled: true,
  weatherEnabled: false,
  weatherLatitude: undefined,
  weatherLongitude: undefined,
  displayName: 'player',
};

const Ctx = createContext<UiPrefs>(DEFAULTS);

function readDotted(cfg: Record<string, unknown>, path: string): unknown {
  const keys = path.split('.');
  let node: unknown = cfg;
  for (const k of keys) {
    if (node === null || typeof node !== 'object') return undefined;
    node = (node as Record<string, unknown>)[k];
  }
  return node;
}

function asBool(v: unknown, fallback: boolean): boolean {
  return typeof v === 'boolean' ? v : fallback;
}

function asString(v: unknown, fallback: string): string {
  return typeof v === 'string' && v !== '' ? v : fallback;
}

function fromConfig(cfg: Record<string, unknown>): UiPrefs {
  // Latitude/longitude may land as a string in config (the Settings UI
  // edits them as text fields) — coerce here so the greeting only
  // fires the weather fetch when both values parse to finite numbers.
  const latRaw = readDotted(cfg, 'ui.home.weather_latitude');
  const lonRaw = readDotted(cfg, 'ui.home.weather_longitude');
  const latNum =
    typeof latRaw === 'number'
      ? latRaw
      : typeof latRaw === 'string' && latRaw !== ''
        ? Number(latRaw)
        : NaN;
  const lonNum =
    typeof lonRaw === 'number'
      ? lonRaw
      : typeof lonRaw === 'string' && lonRaw !== ''
        ? Number(lonRaw)
        : NaN;
  return {
    greetingEnabled: asBool(readDotted(cfg, 'ui.home.greeting'), DEFAULTS.greetingEnabled),
    recentlyAddedEnabled: asBool(
      readDotted(cfg, 'ui.home.recently_added'),
      DEFAULTS.recentlyAddedEnabled,
    ),
    surpriseMeEnabled: asBool(
      readDotted(cfg, 'ui.home.surprise_me'),
      DEFAULTS.surpriseMeEnabled,
    ),
    weatherEnabled: asBool(
      readDotted(cfg, 'ui.home.weather'),
      DEFAULTS.weatherEnabled,
    ),
    weatherLatitude: Number.isFinite(latNum) ? latNum : undefined,
    weatherLongitude: Number.isFinite(lonNum) ? lonNum : undefined,
    displayName: asString(
      readDotted(cfg, 'ui.home.display_name'),
      DEFAULTS.displayName,
    ),
  };
}

export const UI_PREFS_CHANGED_EVENT = 'pixiis://ui-prefs:changed';

export function notifyUiPrefsChanged(): void {
  window.dispatchEvent(new CustomEvent(UI_PREFS_CHANGED_EVENT));
}

export function UiPrefsProvider({ children }: { children: ReactNode }) {
  const [prefs, setPrefs] = useState<UiPrefs>(DEFAULTS);

  const reload = useCallback(() => {
    void getConfig().then(
      (cfg) => setPrefs(fromConfig(cfg ?? {})),
      () => {
        /* fall through to defaults */
      },
    );
  }, []);

  useEffect(() => {
    reload();
    const onChanged = (): void => reload();
    window.addEventListener(UI_PREFS_CHANGED_EVENT, onChanged);
    return () => window.removeEventListener(UI_PREFS_CHANGED_EVENT, onChanged);
  }, [reload]);

  const value = useMemo(() => prefs, [prefs]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useUiPrefs(): UiPrefs {
  return useContext(Ctx);
}
