/**
 * NavBar — Top navigation bar.
 * Minimal chrome — the content IS the interface.
 */

import { NavLink } from 'react-router-dom';
import './NavBar.css';

const NAV_ITEMS = [
  { path: '/', label: 'Home' },
  { path: '/library', label: 'Library' },
  { path: '/settings', label: 'Settings' },
];

export function NavBar() {
  return (
    <nav className="navbar">
      <div className="navbar__logo">PIXIIS</div>

      <div className="navbar__tabs">
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

      {/* Window controls (frameless window) */}
      <div className="navbar__controls">
        <button className="navbar__btn" aria-label="Minimize">─</button>
        <button className="navbar__btn" aria-label="Maximize">□</button>
        <button className="navbar__btn navbar__btn--close" aria-label="Close">✕</button>
      </div>
    </nav>
  );
}
