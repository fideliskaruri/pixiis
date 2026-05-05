/**
 * SearchBar — Search with mic button and controller support.
 */

import { useState, useRef, useCallback } from 'react';
import './SearchBar.css';

interface Props {
  value: string;
  onChange: (query: string) => void;
  onMicToggle?: () => void;
  isMicActive?: boolean;
  placeholder?: string;
}

export function SearchBar({
  value,
  onChange,
  onMicToggle,
  isMicActive = false,
  placeholder = 'Search games...',
}: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [focused, setFocused] = useState(false);

  // Debounce
  const debounceRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const handleChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value;
    onChange(val); // immediate update for display
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      // Could trigger a filtered search here
    }, 300);
  }, [onChange]);

  return (
    <div className={`search-bar ${focused ? 'search-bar--focused' : ''} ${isMicActive ? 'search-bar--recording' : ''}`}>
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
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
        placeholder={isMicActive ? 'Listening...' : placeholder}
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

      {/* Mic button */}
      <button
        className={`search-bar__mic ${isMicActive ? 'search-bar__mic--active' : ''}`}
        onClick={onMicToggle}
        aria-label={isMicActive ? 'Stop recording' : 'Voice search'}
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
