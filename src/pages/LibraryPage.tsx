/**
 * LibraryPage — Magazine-style "table of contents" for every entry the
 * scanner has surfaced (games AND non-game apps like Start Menu shortcuts
 * or folder-scanned executables).
 *
 * Reads from `useLibrary()`; never re-fetches. The page is purely a
 * filter + sort + render surface over the shared library state.
 *
 * Filter model:
 *   - kind: 'all' | 'games' | 'apps'
 *   - source: optional AppSource — when set, narrows to a single
 *     storefront/scanner. Source chips only render for sources that
 *     have at least one entry in the current library.
 *
 * Sort model:
 *   - 'az'      — name A→Z (default)
 *   - 'recent'  — last played, desc; never-played fall back to name
 *   - 'source'  — by source label, then name
 *   - 'added'   — best-effort "recently added" using metadata.added_at
 *                 / metadata.mtime when present; falls back to name
 *                 (no springs-style spinner — just a stable order).
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { GameTile } from '../components/GameTile';
import { SearchBar } from '../components/SearchBar';
import { useLibrary } from '../api/LibraryContext';
import { useActionFooter } from '../api/ActionFooterContext';
import { useAutoFocus } from '../hooks/useAutoFocus';
import type { AppEntry, AppSource } from '../api/bridge';
import './LibraryPage.css';

type KindFilter = 'all' | 'games' | 'apps';
type SortMode = 'az' | 'recent' | 'source' | 'added';

const SOURCE_ORDER: AppSource[] = [
  'steam',
  'xbox',
  'epic',
  'gog',
  'ea',
  'startmenu',
  'folder',
  'manual',
];

// Display labels for source chips. Mirrors GameTile's SOURCE_LABELS in
// title-case (chip row reads quieter than the all-caps tile badge).
const SOURCE_LABELS: Record<AppSource, string> = {
  steam: 'Steam',
  xbox: 'Xbox',
  epic: 'Epic',
  gog: 'GOG',
  ea: 'EA',
  startmenu: 'Start Menu',
  folder: 'Folder',
  manual: 'Manual',
};

/**
 * Best-effort timestamp for "Recently Added". The current backend
 * doesn't write a dedicated added_at/mtime field, so we look for either
 * convention defensively and fall back to 0 (which lands these rows at
 * the bottom; the secondary sort by name keeps the ordering stable).
 */
function addedAt(g: AppEntry): number {
  const m = g.metadata;
  const candidates = [m.added_at, m.mtime, m.modified, m.created_at];
  for (const c of candidates) {
    if (typeof c === 'number' && Number.isFinite(c)) return c;
  }
  return 0;
}

export function LibraryPage() {
  const { games, status, error, refresh } = useLibrary();
  const navigate = useNavigate();

  const [kind, setKind] = useState<KindFilter>('all');
  const [source, setSource] = useState<AppSource | null>(null);
  const [searchInput, setSearchInput] = useState('');
  const [search, setSearch] = useState('');
  const [sort, setSort] = useState<SortMode>('az');

  // LibraryPage's controller hint set — distinct from Home in that
  // LT/RT cycle the active source-chip filter (handled inside the
  // page's existing controller plumbing). The Voice cue stays at RT
  // so muscle memory carries across pages; LT/RT for filter is only
  // surfaced when source chips are present.
  useActionFooter([
    { glyph: 'A', verb: 'Open' },
    { glyph: 'Y', verb: 'Favorite' },
    { glyph: 'X', verb: 'Search' },
    { glyph: 'LB', verb: 'Tab' },
    { glyph: 'RB', verb: 'Tab' },
    { glyph: 'LT', verb: 'Filter' },
    { glyph: 'RT', verb: 'Voice' },
  ]);

  // Column count of .library__grid, observed for `data-grid-row` on
  // each tile (wave 5 § 5.5 row-aware spatial nav).
  const gridRef = useRef<HTMLDivElement | null>(null);
  const [columnsPerRow, setColumnsPerRow] = useState(1);

  // 300ms debounce — typing is responsive in the input itself, but the
  // (potentially large) filter pass only re-runs once the user pauses.
  useEffect(() => {
    const id = window.setTimeout(() => setSearch(searchInput), 300);
    return () => {
      window.clearTimeout(id);
    };
  }, [searchInput]);

  // Source chips: only show storefronts that contributed ≥1 entry.
  // Uses a Set so the order matches SOURCE_ORDER (storefronts first,
  // then Start Menu / Manual last) regardless of scanner timing.
  const availableSources = useMemo(() => {
    const seen = new Set<AppSource>();
    for (const g of games) seen.add(g.source);
    return SOURCE_ORDER.filter((s) => seen.has(s));
  }, [games]);

  // If the active source chip stops being available (e.g. a scan
  // pruned the last Epic entry), drop the filter so the user isn't
  // staring at an empty grid with no obvious recovery.
  useEffect(() => {
    if (source !== null && !availableSources.includes(source)) {
      setSource(null);
    }
  }, [availableSources, source]);

  const filtered = useMemo(() => {
    let list: AppEntry[] = games;

    if (kind === 'games') list = list.filter((g) => g.is_game);
    else if (kind === 'apps') list = list.filter((g) => !g.is_game);

    if (source !== null) list = list.filter((g) => g.source === source);

    if (search !== '') {
      const q = search.toLowerCase();
      list = list.filter((g) => g.name.toLowerCase().includes(q));
    }

    list = list.slice().sort((a, b) => {
      // Favorites always float to the top within any sort mode — same
      // convention as HomePage so the two surfaces feel consistent.
      if (a.is_favorite !== b.is_favorite) return a.is_favorite ? -1 : 1;
      if (sort === 'recent') {
        if (a.last_played !== b.last_played) return b.last_played - a.last_played;
        return a.name.localeCompare(b.name);
      }
      if (sort === 'source') {
        if (a.source !== b.source) return a.source.localeCompare(b.source);
        return a.name.localeCompare(b.name);
      }
      if (sort === 'added') {
        const da = addedAt(a);
        const db = addedAt(b);
        if (da !== db) return db - da;
        return a.name.localeCompare(b.name);
      }
      return a.name.localeCompare(b.name);
    });
    return list;
  }, [games, kind, source, search, sort]);

  const totalCount = games.length;
  const onOpen = (g: AppEntry): void => {
    navigate(`/game/${encodeURIComponent(g.id)}`);
  };

  // Mirror HomePage: read computed grid-template-columns to drive the
  // tile-row indices `useSpatialNav` consumes. Re-measures on resize,
  // fullscreen toggle, and filter change. Wave 5 § 5.5.
  useEffect(() => {
    const grid = gridRef.current;
    if (grid === null) return;

    const measure = (): void => {
      const cols = window
        .getComputedStyle(grid)
        .getPropertyValue('grid-template-columns')
        .split(' ')
        .filter((s) => s.trim() !== '').length;
      setColumnsPerRow(Math.max(1, cols));
    };

    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(grid);
    return () => ro.disconnect();
  }, [filtered.length]);

  // Auto-focus the first interactive control on mount. Library always
  // has the "All" chip, so `.library__chip` is reliable; the comma
  // selector falls through to the first tile on the (rare) chance the
  // chip strip hasn't rendered yet. Re-runs when chip availability or
  // tile set shifts so post-scan loads pick the focus back up.
  useAutoFocus('.library__chip, .library__grid .game-tile', [
    availableSources.length,
    filtered[0]?.id ?? '',
  ]);

  return (
    <div className="library fade-in">
      {/* ── Masthead ─────────────────────────────────────────────── */}
      <header className="library__masthead">
        <h1 className="library__title">Library</h1>
        <p className="library__subhead">
          {totalCount} {totalCount === 1 ? 'title' : 'titles'}
        </p>
      </header>

      <hr className="rule library__rule" />

      {/* ── Toolbar: search + sort ───────────────────────────────── */}
      <div className="library__toolbar">
        <SearchBar
          value={searchInput}
          onChange={setSearchInput}
          placeholder="Search library..."
        />
        <label className="library__sort">
          <span className="label library__sort-label">Sort</span>
          <select
            className="library__sort-select"
            value={sort}
            onChange={(e) => setSort(e.target.value as SortMode)}
            data-focusable
            aria-label="Sort library"
          >
            <option value="az">Name (A–Z)</option>
            <option value="recent">Last Played</option>
            <option value="source">Source</option>
            <option value="added">Recently Added</option>
          </select>
        </label>
      </div>

      {/* ── Filter chips ─────────────────────────────────────────── */}
      <div className="library__chips" role="toolbar" aria-label="Filters">
        <Chip
          active={kind === 'all' && source === null}
          onClick={() => {
            setKind('all');
            setSource(null);
          }}
        >
          All
        </Chip>
        <Chip
          active={kind === 'games' && source === null}
          onClick={() => {
            setKind('games');
            setSource(null);
          }}
        >
          Games
        </Chip>
        <Chip
          active={kind === 'apps' && source === null}
          onClick={() => {
            setKind('apps');
            setSource(null);
          }}
        >
          Apps
        </Chip>

        {availableSources.length > 0 && (
          <span className="library__chip-divider" aria-hidden="true" />
        )}

        {availableSources.map((s) => (
          <Chip
            key={s}
            active={source === s}
            onClick={() => {
              setSource(source === s ? null : s);
              // Source chips don't reset the kind filter — a user can
              // scope to "Apps from Start Menu" by combining the two.
            }}
          >
            {SOURCE_LABELS[s]}
          </Chip>
        ))}

        <span className="library__count">
          {filtered.length} {filtered.length === 1 ? 'result' : 'results'}
        </span>
      </div>

      {/* ── Grid / states ────────────────────────────────────────── */}
      {status === 'error' ? (
        <div className="library__empty" role="alert">
          <p className="library__empty-title">Failed to load library</p>
          <p className="library__empty-body">{error}</p>
          <button
            className="library__retry"
            onClick={refresh}
            data-focusable
          >
            Retry
          </button>
        </div>
      ) : status === 'loading' && games.length === 0 ? (
        <div className="library__empty">
          <p className="library__empty-title">One moment.</p>
          <p className="label">LOADING LIBRARY</p>
        </div>
      ) : filtered.length === 0 ? (
        <div className="library__empty">
          <p className="library__empty-title">
            {games.length === 0
              ? 'No entries on file'
              : 'No games match the current filter'}
          </p>
          <p className="library__empty-body">
            {games.length === 0
              ? 'Run a scan from Settings → Library, or add a manual entry from Files.'
              : 'Try a different filter, clear the search, or trigger a fresh scan from Settings → Library.'}
          </p>
          {games.length > 0 && (kind !== 'all' || source !== null || search !== '') && (
            <button
              type="button"
              className="library__retry"
              onClick={() => {
                setKind('all');
                setSource(null);
                setSearchInput('');
                setSearch('');
              }}
              data-focusable
            >
              Clear filters
            </button>
          )}
        </div>
      ) : (
        <div className="library__grid" ref={gridRef}>
          {filtered.map((game, idx) => (
            <GameTile
              key={game.id}
              game={game}
              onSelect={onOpen}
              rowIndex={(idx / columnsPerRow) | 0}
            />
          ))}
        </div>
      )}
    </div>
  );
}

interface ChipProps {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}

function Chip({ active, onClick, children }: ChipProps) {
  return (
    <button
      className={`library__chip ${active ? 'library__chip--active' : ''}`}
      onClick={onClick}
      data-focusable
      aria-pressed={active}
      type="button"
    >
      {children}
    </button>
  );
}
