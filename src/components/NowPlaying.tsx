/**
 * NowPlaying — Editorial pill that surfaces the running-game list.
 *
 * Mounts in the NavBar. Hidden when nothing is tracked. Each entry is a
 * small-caps "NOW PLAYING" label, the game name in the body serif, and
 * an accent-coloured STOP button. Multiple games stack vertically so a
 * Steam game running alongside a folder-launched exe both show up.
 *
 * The component is purely declarative against the `useRunningGames()`
 * hook — when the backend fires `library:running:changed`, the list
 * re-renders. Click STOP → bridge.stopGame(id) → toast → backend kills
 * the process → tracker prunes the row → list shrinks.
 */

import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { stopGame, useRunningGames, type RunningGame } from '../api/bridge';
import { useLibrary } from '../api/LibraryContext';
import { useToast } from '../api/ToastContext';
import './NowPlaying.css';

export function NowPlaying() {
  const running = useRunningGames();
  const { byId } = useLibrary();
  const { toast } = useToast();
  const navigate = useNavigate();
  // Track which ids are mid-stop so a double-click doesn't fire a second
  // kill (and the button can show STOPPING…). Cleared once the entry
  // disappears from `running` (the running-game event handler triggers
  // a re-render, which re-derives this set from the live list).
  const [stopping, setStopping] = useState<Set<string>>(new Set());

  if (running.length === 0) return null;

  const onStop = async (game: RunningGame): Promise<void> => {
    if (stopping.has(game.id)) return;
    setStopping((prev) => {
      const next = new Set(prev);
      next.add(game.id);
      return next;
    });
    try {
      await stopGame(game.id);
      // Use the library entry's name when we have it (display matches
      // what the tile shows); fall back to whatever the tracker has.
      const name = byId(game.id)?.name ?? game.name;
      toast(`Stopped ${name}`, 'success');
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      toast(`Failed to stop: ${msg}`, 'error');
      // Clear the stopping flag on failure so the user can retry. On
      // success the entry vanishes from `running` and the set is
      // implicitly cleaned up the next render.
      setStopping((prev) => {
        const next = new Set(prev);
        next.delete(game.id);
        return next;
      });
    }
  };

  return (
    <div className="now-playing" aria-label="Currently playing games">
      {running.map((game) => {
        const entry = byId(game.id);
        const name = entry?.name ?? game.name;
        const isStopping = stopping.has(game.id);
        const status = !game.attached ? 'LAUNCHING' : 'NOW PLAYING';
        return (
          <div key={game.id} className="now-playing__row">
            <button
              type="button"
              className="now-playing__name-btn"
              onClick={() => {
                if (entry !== undefined) navigate(`/game/${entry.id}`);
              }}
              data-focusable
              aria-label={`Open ${name} details`}
              disabled={entry === undefined}
            >
              <span className="label now-playing__status">{status}</span>
              <span className="now-playing__name">{name}</span>
            </button>
            <button
              type="button"
              className="now-playing__stop accent-btn"
              onClick={() => {
                void onStop(game);
              }}
              disabled={isStopping || !game.attached}
              data-focusable
              aria-label={`Stop ${name}`}
              title={
                !game.attached
                  ? 'Waiting to attach…'
                  : isStopping
                    ? 'Stopping…'
                    : `Stop ${name}`
              }
            >
              {isStopping ? 'STOPPING…' : 'STOP'}
            </button>
          </div>
        );
      })}
    </div>
  );
}
