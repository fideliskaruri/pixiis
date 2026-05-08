/**
 * NavBar — Editorial top chrome.
 *
 * The window is frameless (decorations: false in tauri.conf.json), so
 * NavBar owns the minimize / maximize / close buttons. They route
 * through Tauri 2's window API. The matching capability allow-list
 * lives in `src-tauri/capabilities/default.json`.
 */

import type { MouseEvent } from 'react';
import { useEffect, useState } from 'react';
import { NavLink } from 'react-router-dom';
import { getCurrentWindow } from '@tauri-apps/api/window';
import { NowPlaying } from './NowPlaying';
import './NavBar.css';

const NAV_ITEMS = [
  { path: '/', label: 'Home' },
  { path: '/library', label: 'Library' },
  { path: '/settings', label: 'Settings' },
];

export function NavBar() {
  const win = getCurrentWindow();
  const [maximized, setMaximized] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void win.isMaximized().then((m) => {
      if (!cancelled) setMaximized(m);
    });
    const unlisten = win.onResized(() => {
      void win.isMaximized().then((m) => {
        if (!cancelled) setMaximized(m);
      });
    });
    return () => {
      cancelled = true;
      void unlisten.then((fn) => fn());
    };
  }, [win]);

  const onMinimize = () => {
    void win.minimize();
  };
  const onToggleMaximize = () => {
    void win.toggleMaximize();
  };
  const onClose = () => {
    void win.close();
  };

  // Double-click on the NavBar (but not on a button or tab) toggles
  // fullscreen — matches the PySide6 build's frameless-window convention.
  // Maximize is a separate state and is NOT touched here.
  const onDoubleClick = (e: MouseEvent<HTMLElement>) => {
    const target = e.target as HTMLElement;
    if (target.closest('button, a')) return;
    void win.isFullscreen().then((fs) => win.setFullscreen(!fs));
  };

  return (
    <nav
      className="navbar"
      data-tauri-drag-region
      onDoubleClick={onDoubleClick}
    >
      <div className="navbar__logo" data-tauri-drag-region="false">
        PIXIIS
      </div>

      <div className="navbar__tabs" data-tauri-drag-region="false">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            className={({ isActive }) =>
              `navbar__tab ${isActive ? 'navbar__tab--active' : ''}`
            }
            data-focusable
          >
            {item.label}
          </NavLink>
        ))}
      </div>

      <div className="navbar__spacer" />

      {/* Now-Playing pill — sits right of the tabs, left of the window
          chrome. The component renders nothing when the running-game
          tracker is empty, so the NavBar reverts to its default layout
          when no game is live. */}
      <div className="navbar__now-playing" data-tauri-drag-region="false">
        <NowPlaying />
      </div>

      <div className="navbar__controls" data-tauri-drag-region="false">
        <button
          className="navbar__btn"
          aria-label="Minimize"
          title="Minimize"
          onClick={onMinimize}
          data-focusable
        >
          ─
        </button>
        <button
          className="navbar__btn"
          aria-label={maximized ? 'Restore' : 'Maximize'}
          title={maximized ? 'Restore' : 'Maximize'}
          onClick={onToggleMaximize}
          data-focusable
        >
          {maximized ? '❐' : '□'}
        </button>
        <button
          className="navbar__btn navbar__btn--close"
          aria-label="Close"
          title="Close"
          onClick={onClose}
          data-focusable
        >
          ✕
        </button>
      </div>
    </nav>
  );
}
