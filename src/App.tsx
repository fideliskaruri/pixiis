/**
 * Pixiis — App Shell
 */

import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { NavBar } from './components/NavBar';
import { HomePage } from './pages/HomePage';
import { GameDetailPage } from './pages/GameDetailPage';
import { SettingsPage } from './pages/SettingsPage';
import { LibraryProvider } from './api/LibraryContext';
import { useSpatialNav } from './hooks/useSpatialNav';

// styles/tokens.css is loaded via index.css; theme.css is the legacy
// PS5-glass palette and must NOT be imported here — it shadows editorial
// :root variables (--bg, --accent, --text, --font, --ease-*).
import './styles/animations.css';

function AppContent() {
  useSpatialNav();

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh' }}>
      <NavBar />
      <main style={{ flex: 1, overflow: 'hidden' }}>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/library" element={<Placeholder label="Library" />} />
          <Route path="/game/:id" element={<GameDetailPage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Routes>
      </main>
    </div>
  );
}

function Placeholder({ label }: { label: string }) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        height: '100%',
        color: 'var(--text-mute)',
        fontFamily: 'var(--font-body)',
        fontSize: 'var(--t-title)',
        fontWeight: 500,
      }}
    >
      {label} — coming soon
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <LibraryProvider>
        <AppContent />
      </LibraryProvider>
    </BrowserRouter>
  );
}
