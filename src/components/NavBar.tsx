/**
 * NavBar — Editorial top chrome.
 *
 * The window is frameless (decorations: false in tauri.conf.json), so
 * NavBar owns the minimize / maximize / close buttons. They route
 * through Tauri 2's window API. The matching capability allow-list
 * lives in `src-tauri/capabilities/default.json`.
 */

import { useEffect, useState } from 'react';
import { NavLink } from 'react-router-dom';
import { getCurrentWindow } from '@tauri-apps/api/window';
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

  return (
    <nav className="navbar" data-tauri-drag-region>
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
