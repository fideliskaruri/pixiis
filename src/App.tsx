/**
 * Pixiis — App Shell
 */

import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { NavBar } from './components/NavBar';
import { HomePage } from './pages/HomePage';
import { useSpatialNav } from './hooks/useSpatialNav';

import './styles/theme.css';
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
          <Route path="/game/:id" element={<Placeholder label="Game Detail" />} />
          <Route path="/settings" element={<Placeholder label="Settings" />} />
        </Routes>
      </main>
    </div>
  );
}

function Placeholder({ label }: { label: string }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      height: '100%', color: 'var(--text-muted)', fontSize: 24, fontWeight: 600,
    }}>
      {label} — coming soon
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AppContent />
    </BrowserRouter>
  );
}
