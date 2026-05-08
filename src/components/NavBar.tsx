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
import { useWindowFullscreen } from '../hooks/useBigPicture';
import './NavBar.css';

const NAV_ITEMS = [
  { path: '/', label: 'Home' },
  { path: '/library', label: 'Library' },
  { path: '/settings', label: 'Settings' },
];

export function NavBar() {
  const win = getCurrentWindow();
  const [maximized, setMaximized] = useState(false);
  // Fullscreen owns the screen — minimize/maximize/close lose all
  // meaning and the drag region is moot. Hide the cluster entirely.
  const fullscreen = useWindowFullscreen();

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
          // D-pad navigation is reserved for in-page content; page
          // switching happens via the LB/RB bumpers. Mark these tabs
          // with `data-no-spatial` so useSpatialNav skips them — they
          // remain mouse-clickable and reachable via Tab.
          <NavLink
            key={item.path}
            to={item.path}
            className={({ isActive }) =>
              `navbar__tab ${isActive ? 'navbar__tab--active' : ''}`
            }
            data-no-spatial
          >
            {item.label}
          </NavLink>
        ))}
      </div>

      <div className="navbar__spacer" />

      {!fullscreen && (
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
      )}
    </nav>
  );
}
