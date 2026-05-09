/**
 * SearchBar — Search with mic button and controller support.
 *
 * The mic button is a click-to-toggle alternative to the controller's
 * hold-to-talk trigger (`useVoiceTrigger`). First click → `voiceStart()`;
 * second click → `voiceStop()`. Both paths drive the same backend, so
 * the VoiceOverlay reflects whichever interaction the user chose.
 *
 * Parents may still pass `onMicToggle` / `isMicActive` to override the
 * default click handler (e.g. coordinating with another voice surface).
 * When omitted, the SearchBar wires the click directly to the bridge —
 * that's the common case for Home / Library where the mic is the only
 * discoverable mouse path to voice.
 */

import { useCallback, useState, useRef } from 'react';
import { useVirtualKeyboard } from './VirtualKeyboard';
import { voiceStart, voiceStop } from '../api/bridge';
import './SearchBar.css';

interface Props {
  value: string;
  onChange: (query: string) => void;
  /**
   * Optional click-to-toggle override. Pass when the parent wants to
   * own the voice session (e.g. Settings test path). Omitted on
   * Home / Library — the SearchBar then drives `voice_start` /
   * `voice_stop` directly.
   */
  onMicToggle?: () => void;
  isMicActive?: boolean;
  placeholder?: string;
}

export function SearchBar({
  value,
  onChange,
  onMicToggle,
  isMicActive,
  placeholder = 'Search games...',
}: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [focused, setFocused] = useState(false);
  // Internal recording state — used when the parent doesn't supply
  // `isMicActive`. Tracks whether the click handler last opened the
  // session so the next click closes it. Falls back to the parent's
  // value when supplied.
  const [internalActive, setInternalActive] = useState(false);
  const vkbd = useVirtualKeyboard();

  const effectiveActive = isMicActive ?? internalActive;

  // The list itself is filtered downstream; the input just forwards each
  // keystroke. (A previous version queued a debounced no-op alongside.)
  const handleChange = (e: React.ChangeEvent<HTMLInputElement>): void => {
    onChange(e.target.value);
  };

  const handleFocus = (): void => {
    setFocused(true);
    // Hand the input to the on-screen keyboard provider — it decides
    // whether to actually open based on recent gamepad activity.
    if (inputRef.current !== null) vkbd.onInputFocus(inputRef.current);
  };

  // Default mic toggle: first click → voiceStart; second click →
  // voiceStop. Errors are swallowed — VoiceOverlay surfaces user-
  // visible state via `voice:state` events; toasting on top would
  // double-up. Optimistic state flip handles partial failures (we
  // revert on rejection so a re-press can retry cleanly).
  const handleMicToggleDefault = useCallback(() => {
    if (effectiveActive) {
      setInternalActive(false);
      void voiceStop().catch(() => {
        // best-effort
      });
    } else {
      setInternalActive(true);
      void voiceStart().catch(() => {
        // Roll back so the next click can retry.
        setInternalActive(false);
      });
    }
  }, [effectiveActive]);

  const handleMicToggle = onMicToggle ?? handleMicToggleDefault;

  return (
    <div className={`search-bar ${focused ? 'search-bar--focused' : ''} ${effectiveActive ? 'search-bar--recording' : ''}`}>
      {/* Magnifying glass */}
      <svg className="search-bar__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <circle cx="10.5" cy="10.5" r="7" />
        <line x1="15.5" y1="15.5" x2="21" y2="21" />
      </svg>

      <input
        ref={inputRef}
        className="search-bar__input"
        type="text"
        value={value}
        onChange={handleChange}
        onFocus={handleFocus}
        onBlur={() => setFocused(false)}
        placeholder={effectiveActive ? 'Listening...' : placeholder}
        data-focusable
      />

      {/* Clear button */}
      {value && (
        <button
          className="search-bar__clear"
          onClick={() => onChange('')}
          aria-label="Clear search"
        >
          ✕
        </button>
      )}

      {/* Mic button — click-to-toggle. The controller hold-to-talk
          trigger lives in `useVoiceTrigger`; both paths drive the
          same `voice_start` / `voice_stop` backend. */}
      <button
        className={`search-bar__mic ${effectiveActive ? 'search-bar__mic--active' : ''}`}
        onClick={handleMicToggle}
        aria-label={effectiveActive ? 'Stop recording' : 'Voice search'}
        data-focusable
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <rect x="9" y="1" width="6" height="11" rx="3" />
          <path d="M5 10a7 7 0 0 0 14 0" />
          <line x1="12" y1="17" x2="12" y2="21" />
          <line x1="8" y1="21" x2="16" y2="21" />
        </svg>
      </button>
    </div>
  );
}
