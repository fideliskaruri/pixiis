/**
 * HomeGreeting — Editorial greeting badge for HomePage.
 *
 * Layout (top-left of Home):
 *   GOOD EVENING,           ← small-caps tracked label (--text-dim)
 *   fwachira                ← serif (Fraunces), --text
 *   18:42 · 14° CLOUDY      ← monospace temp + small-caps condition
 *
 * Time updates every minute (cheap; the next-minute timeout is
 * scheduled exactly on the boundary so we don't drift). Weather is
 * fetched once on mount when `services.weather.api_key` (Open-Meteo
 * needs no key — but we keep a config gate so users can opt out by
 * leaving it empty in the config). When no key is configured we just
 * show time. The component never throws — a network failure quietly
 * renders the time-only line.
 *
 * Can be turned off entirely via the Settings → About → "Show home
 * greeting" toggle (config: ui.greeting_enabled). The HomePage reads
 * the same config and skips rendering this component when disabled.
 */

import { useEffect, useState } from 'react';
import './HomeGreeting.css';

interface Props {
  /** User's display name — usually the OS username. */
  name: string;
  /** Open-Meteo lat / lon pair when weather is enabled. */
  weatherEnabled: boolean;
  latitude?: number;
  longitude?: number;
}

interface WeatherSnapshot {
  temperatureC: number;
  condition: string;
}

function greetingFor(hour: number): string {
  if (hour < 5) return 'GOOD NIGHT';
  if (hour < 12) return 'GOOD MORNING';
  if (hour < 18) return 'GOOD AFTERNOON';
  return 'GOOD EVENING';
}

function formatTime(d: Date): string {
  const h = d.getHours().toString().padStart(2, '0');
  const m = d.getMinutes().toString().padStart(2, '0');
  return `${h}:${m}`;
}

// Open-Meteo's WMO weather codes, condensed to the labels we'd actually
// want to surface. Matches the "wxxx" codes the free /v1/forecast?...
// endpoint emits on the `current_weather.weathercode` field.
function describeWeatherCode(code: number): string {
  if (code === 0) return 'CLEAR';
  if (code <= 2) return 'PARTLY CLOUDY';
  if (code === 3) return 'OVERCAST';
  if (code === 45 || code === 48) return 'FOG';
  if (code >= 51 && code <= 57) return 'DRIZZLE';
  if (code >= 61 && code <= 67) return 'RAIN';
  if (code >= 71 && code <= 77) return 'SNOW';
  if (code >= 80 && code <= 82) return 'RAIN SHOWERS';
  if (code >= 85 && code <= 86) return 'SNOW SHOWERS';
  if (code >= 95) return 'THUNDERSTORM';
  return '';
}

export function HomeGreeting({
  name,
  weatherEnabled,
  latitude,
  longitude,
}: Props) {
  const [now, setNow] = useState<Date>(() => new Date());
  const [weather, setWeather] = useState<WeatherSnapshot | null>(null);

  // Schedule the next tick at the top of the next minute so the
  // displayed clock flips exactly when wall-clock seconds = 0. A
  // re-render every minute is too cheap to budget around.
  useEffect(() => {
    let timer: number | undefined;
    const tick = (): void => {
      setNow(new Date());
      const ms = 60_000 - (Date.now() % 60_000);
      timer = window.setTimeout(tick, ms);
    };
    const ms = 60_000 - (Date.now() % 60_000);
    timer = window.setTimeout(tick, ms);
    return () => {
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, []);

  // Fetch weather once. Open-Meteo is free + key-less; we still gate
  // on `weatherEnabled` so the user can opt out.
  useEffect(() => {
    if (!weatherEnabled) return;
    if (latitude === undefined || longitude === undefined) return;
    let cancelled = false;
    const url =
      `https://api.open-meteo.com/v1/forecast` +
      `?latitude=${latitude}&longitude=${longitude}` +
      `&current_weather=true&timezone=auto`;
    fetch(url)
      .then((r) => (r.ok ? r.json() : null))
      .then((j: unknown) => {
        if (cancelled || j === null || typeof j !== 'object') return;
        const cw = (j as { current_weather?: unknown }).current_weather;
        if (cw === undefined || cw === null || typeof cw !== 'object') return;
        const t = (cw as { temperature?: number }).temperature;
        const code = (cw as { weathercode?: number }).weathercode;
        if (typeof t !== 'number' || typeof code !== 'number') return;
        setWeather({
          temperatureC: Math.round(t),
          condition: describeWeatherCode(code),
        });
      })
      .catch(() => {
        // Quiet on network failure — the greeting still shows time.
      });
    return () => {
      cancelled = true;
    };
  }, [weatherEnabled, latitude, longitude]);

  const greeting = greetingFor(now.getHours());
  const timeStr = formatTime(now);
  const tempStr =
    weather === null
      ? ''
      : `${weather.temperatureC}°${weather.condition !== '' ? ` · ${weather.condition}` : ''}`;

  return (
    <div className="greeting" aria-live="polite">
      <p className="label greeting__hello">{greeting},</p>
      <p className="greeting__name">{name}</p>
      <p className="greeting__strip">
        <span className="greeting__time">{timeStr}</span>
        {tempStr !== '' && (
          <>
            <span className="greeting__sep" aria-hidden="true">
              ·
            </span>
            <span className="greeting__weather label">{tempStr}</span>
          </>
        )}
      </p>
    </div>
  );
}
