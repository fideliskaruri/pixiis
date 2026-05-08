/**
 * Pixiis — App Shell
 */

import { useEffect, useState } from 'react';
import {
  BrowserRouter,
  Routes,
  Route,
  useLocation,
  useNavigate,
} from 'react-router-dom';
import { getCurrentWindow } from '@tauri-apps/api/window';
import { NavBar } from './components/NavBar';
import { HomePage } from './pages/HomePage';
import { LibraryPage } from './pages/LibraryPage';
import { GameDetailPage } from './pages/GameDetailPage';
import { OnboardingPage } from './pages/OnboardingPage';
import { FileManagerPage } from './pages/FileManagerPage';
import { SettingsPage } from './pages/SettingsPage';
import { LibraryProvider } from './api/LibraryContext';
import { ToastProvider } from './api/ToastContext';
import { QuickResume } from './components/QuickResume';
import { VoiceOverlay } from './components/VoiceOverlay';
import { VirtualKeyboardProvider } from './components/VirtualKeyboard';
import { useSpatialNav } from './hooks/useSpatialNav';
import { getOnboarded } from './api/bridge';

// styles/tokens.css is loaded via index.css; theme.css is the legacy
// PS5-glass palette and must NOT be imported here — it shadows editorial
// :root variables (--bg, --accent, --text, --font, --ease-*).
import './styles/animations.css';

function AppContent() {
  useSpatialNav();
  const location = useLocation();
  const navigate = useNavigate();
  const [checkedOnboarded, setCheckedOnboarded] = useState(false);

  // F11 toggles fullscreen anywhere in the app — standard Windows
  // convention. Window-level keys don't depend on focus, so a single
  // window listener handles every page.
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key !== 'F11') return;
      e.preventDefault();
      const win = getCurrentWindow();
      void win.isFullscreen().then((fs) => win.setFullscreen(!fs));
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, []);

  // First-launch redirect: route to /onboarding when the marker is
  // absent. We only check once per app load; the onboarding page writes
  // the marker before navigating away.
  useEffect(() => {
    let cancelled = false;
    void getOnboarded()
      .then((done) => {
        if (cancelled) return;
        if (!done && location.pathname !== '/onboarding') {
          navigate('/onboarding', { replace: true });
        }
      })
      .catch(() => {
        // If the marker check fails (e.g. older backend without the
        // command), assume the user is onboarded — better than trapping
        // them in a loop they can't exit.
      })
      .finally(() => {
        if (!cancelled) setCheckedOnboarded(true);
      });
    return () => {
      cancelled = true;
    };
    // Run once on mount only — re-checking on every navigation would
    // bounce the user back to /onboarding mid-session if they hit Skip.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const onOnboarding = location.pathname === '/onboarding';

  if (onOnboarding) {
    return (
      <main style={{ height: '100vh', overflow: 'hidden' }}>
        <Routes>
          <Route path="/onboarding" element={<OnboardingPage />} />
        </Routes>
      </main>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh' }}>
      <NavBar />
      <main style={{ flex: 1, overflow: 'hidden' }}>
        {checkedOnboarded && (
          <Routes>
            <Route path="/" element={<HomePage />} />
            <Route path="/library" element={<LibraryPage />} />
            <Route path="/game/:id" element={<GameDetailPage />} />
            <Route path="/files" element={<FileManagerPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/onboarding" element={<OnboardingPage />} />
          </Routes>
        )}
      </main>
    </div>
  );
}

export default function App() {
  // Mount order matters: ToastProvider sits outside everything else so
  // any hook (including QuickResume's launch handler) can fire toasts;
  // QuickResume needs Library + Toast + Router; VirtualKeyboardProvider
  // wraps the routes so any focused input can request the keyboard.
  return (
    <BrowserRouter>
      <ToastProvider>
        <LibraryProvider>
          <VirtualKeyboardProvider>
            <QuickResume>
              <AppContent />
              <VoiceOverlay />
            </QuickResume>
          </VirtualKeyboardProvider>
        </LibraryProvider>
      </ToastProvider>
    </BrowserRouter>
  );
}
