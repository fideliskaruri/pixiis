/**
 * FileManagerPage — Editorial editor for `library.manual.apps`.
 *
 * Lets the user register games / executables that no storefront scanner
 * picked up. Two columns: the list of existing entries on the left,
 * the active form on the right. Saving rewrites the config slice and
 * re-scans the library so the row appears immediately.
 */

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from 'react';
import { open as openDialog } from '@tauri-apps/plugin-dialog';
import { exists } from '@tauri-apps/plugin-fs';
import {
  getConfig,
  saveConfig,
  scanLibrary,
  type Config,
} from '../api/bridge';
import { useToast } from '../api/ToastContext';
import './FileManagerPage.css';

interface ManualEntry {
  name: string;
  exe_path: string;
  args: string;
  icon_path: string;
  working_dir: string;
}

const EMPTY: ManualEntry = {
  name: '',
  exe_path: '',
  args: '',
  icon_path: '',
  working_dir: '',
};

const EXE_FILTERS = [
  { name: 'Executable', extensions: ['exe', 'lnk', 'bat', 'cmd', 'url'] },
  { name: 'All files', extensions: ['*'] },
];

const ICON_FILTERS = [
  { name: 'Image', extensions: ['png', 'jpg', 'jpeg', 'ico', 'webp', 'bmp'] },
];

type LoadStatus = 'loading' | 'ready' | 'error';

// ── Config helpers ─────────────────────────────────────────────────────

function readManualApps(cfg: Config): ManualEntry[] {
  const lib = cfg.library as Record<string, unknown> | undefined;
  const manual = lib?.manual as Record<string, unknown> | undefined;
  const apps = manual?.apps;
  if (!Array.isArray(apps)) return [];
  return apps.map((raw) => {
    const r = (raw ?? {}) as Record<string, unknown>;
    return {
      name: typeof r.name === 'string' ? r.name : '',
      exe_path: typeof r.exe_path === 'string' ? r.exe_path : '',
      args: typeof r.args === 'string' ? r.args : '',
      icon_path: typeof r.icon_path === 'string' ? r.icon_path : '',
      working_dir: typeof r.working_dir === 'string' ? r.working_dir : '',
    };
  });
}

async function writeManualApps(entries: ManualEntry[]): Promise<void> {
  const cfg = await getConfig();
  const lib = (cfg.library as Record<string, unknown> | undefined) ?? {};
  const manual = (lib.manual as Record<string, unknown> | undefined) ?? {};
  await saveConfig({
    library: { ...lib, manual: { ...manual, apps: entries } },
  });
}

// Best-effort existence check. The fs plugin can refuse paths outside the
// default allow-list; we treat that as "can't verify" rather than "missing".
async function pathExists(path: string): Promise<boolean | null> {
  try {
    return await exists(path);
  } catch {
    return null;
  }
}

// ── Page ───────────────────────────────────────────────────────────────

export function FileManagerPage() {
  const { toast } = useToast();
  const [entries, setEntries] = useState<ManualEntry[]>([]);
  const [status, setStatus] = useState<LoadStatus>('loading');
  const [loadError, setLoadError] = useState('');

  // null = no form open. number = editing entries[selectedIndex]. -1 = adding new.
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  const [draft, setDraft] = useState<ManualEntry>(EMPTY);
  const [fieldErrors, setFieldErrors] = useState<Partial<Record<keyof ManualEntry, string>>>({});
  const [formError, setFormError] = useState('');
  const [saving, setSaving] = useState(false);

  const nameInputRef = useRef<HTMLInputElement | null>(null);

  const isFormOpen = selectedIndex !== null;
  const isNewEntry = selectedIndex === -1;

  const refresh = useCallback(async (): Promise<void> => {
    setStatus('loading');
    setLoadError('');
    try {
      const cfg = await getConfig();
      setEntries(readManualApps(cfg));
      setStatus('ready');
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : String(err));
      setStatus('error');
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // Auto-focus the name field whenever a form opens.
  useEffect(() => {
    if (isFormOpen) {
      nameInputRef.current?.focus();
    }
  }, [isFormOpen, selectedIndex]);

  const startNew = (): void => {
    setSelectedIndex(-1);
    setDraft({ ...EMPTY });
    setFieldErrors({});
    setFormError('');
  };

  const startEdit = (index: number): void => {
    const entry = entries[index];
    if (entry === undefined) return;
    setSelectedIndex(index);
    setDraft({ ...entry });
    setFieldErrors({});
    setFormError('');
  };

  const cancelForm = (): void => {
    setSelectedIndex(null);
    setDraft({ ...EMPTY });
    setFieldErrors({});
    setFormError('');
  };

  const updateField = <K extends keyof ManualEntry>(key: K, value: string): void => {
    setDraft((prev) => ({ ...prev, [key]: value }));
    setFieldErrors((prev) => {
      if (prev[key] === undefined) return prev;
      const next = { ...prev };
      delete next[key];
      return next;
    });
  };

  const validate = useCallback(async (): Promise<Partial<Record<keyof ManualEntry, string>>> => {
    const errs: Partial<Record<keyof ManualEntry, string>> = {};
    const trimmedName = draft.name.trim();
    const trimmedExe = draft.exe_path.trim();

    if (trimmedName === '') {
      errs.name = 'Name is required.';
    } else {
      const lower = trimmedName.toLowerCase();
      const collision = entries.some((entry, i) => {
        if (selectedIndex !== -1 && i === selectedIndex) return false;
        return entry.name.trim().toLowerCase() === lower;
      });
      if (collision) errs.name = 'Another entry already uses this name.';
    }

    if (trimmedExe === '') {
      errs.exe_path = 'Executable path is required.';
    } else {
      const ok = await pathExists(trimmedExe);
      if (ok === false) errs.exe_path = 'No file at this path.';
    }

    return errs;
  }, [draft, entries, selectedIndex]);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault();
    if (saving) return;
    setFormError('');

    const errs = await validate();
    if (Object.keys(errs).length > 0) {
      setFieldErrors(errs);
      return;
    }

    const cleaned: ManualEntry = {
      name: draft.name.trim(),
      exe_path: draft.exe_path.trim(),
      args: draft.args.trim(),
      icon_path: draft.icon_path.trim(),
      working_dir: draft.working_dir.trim(),
    };

    const next = entries.slice();
    if (isNewEntry) {
      next.push(cleaned);
    } else if (selectedIndex !== null) {
      next[selectedIndex] = cleaned;
    }

    setSaving(true);
    try {
      await writeManualApps(next);
      // Scan so the new row materialises in Library immediately. A failure
      // here is non-fatal — the entry is persisted and the next manual scan
      // will catch up.
      try {
        await scanLibrary();
      } catch {
        /* ignore — user can re-scan */
      }
      setEntries(next);
      toast(isNewEntry ? `Added ${cleaned.name}` : `Updated ${cleaned.name}`, 'success');
      cancelForm();
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setFormError(msg);
      toast(`Save failed: ${msg}`, 'error');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (index: number): Promise<void> => {
    const target = entries[index];
    if (target === undefined) return;
    const ok = window.confirm(`Remove "${target.name}" from manual entries?`);
    if (!ok) return;

    const next = entries.filter((_, i) => i !== index);
    try {
      await writeManualApps(next);
      try {
        await scanLibrary();
      } catch {
        /* ignore — user can re-scan */
      }
      setEntries(next);
      toast(`Removed ${target.name}`, 'success');
      if (selectedIndex === index) {
        cancelForm();
      } else if (selectedIndex !== null && selectedIndex > index) {
        setSelectedIndex(selectedIndex - 1);
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setFormError(msg);
      toast(`Delete failed: ${msg}`, 'error');
    }
  };

  // The Tauri dialog plugin returns `null` when the user dismisses the
  // file/folder picker, so the caller naturally no-ops. We still wrap in
  // try/catch in case a future plugin version surfaces cancellation as a
  // thrown string — `isCancellation()` keeps quiet errors out of the UI.
  const isCancellation = (err: unknown): boolean => {
    const msg = (err instanceof Error ? err.message : String(err ?? '')).toLowerCase();
    return msg.includes('cancel') || msg.includes('dismiss');
  };

  const pickFile = async (
    key: keyof ManualEntry,
    label: string,
    filters: typeof EXE_FILTERS,
  ): Promise<void> => {
    try {
      const result = await openDialog({
        multiple: false,
        directory: false,
        title: label,
        filters,
      });
      if (typeof result === 'string') {
        updateField(key, result);
      }
    } catch (err) {
      if (isCancellation(err)) return;
      const msg = err instanceof Error ? err.message : String(err);
      setFormError(msg);
      toast(`File picker failed: ${msg}`, 'error');
    }
  };

  const pickDirectory = async (key: keyof ManualEntry, label: string): Promise<void> => {
    try {
      const result = await openDialog({
        multiple: false,
        directory: true,
        title: label,
      });
      if (typeof result === 'string') {
        updateField(key, result);
      }
    } catch (err) {
      if (isCancellation(err)) return;
      const msg = err instanceof Error ? err.message : String(err);
      setFormError(msg);
      toast(`File picker failed: ${msg}`, 'error');
    }
  };

  const sortedEntries = useMemo(() => {
    return entries
      .map((entry, index) => ({ entry, index }))
      .sort((a, b) =>
        a.entry.name.localeCompare(b.entry.name, undefined, { sensitivity: 'base' }),
      );
  }, [entries]);

  // ── Render ───────────────────────────────────────────────────────────

  return (
    <div className="files fade-in">
      <header className="files__header">
        <p className="label files__eyebrow">MANUAL ENTRIES</p>
        <h1 className="display files__title">Add games by hand.</h1>
        <p className="files__subtitle">
          Anything the storefront scanners miss — emulators, installers,
          or one-off launchers — lives here. Saved entries appear in the
          library next to your scanned games.
        </p>
      </header>

      <hr className="rule files__rule" />

      <div className="files__layout">
        <section className="files__list" aria-label="Manual entries">
          <div className="files__list-head">
            <p className="label files__list-label">
              {entries.length === 0
                ? 'NONE YET'
                : `${entries.length} ${entries.length === 1 ? 'ENTRY' : 'ENTRIES'}`}
            </p>
            <button
              type="button"
              className="files__add"
              onClick={startNew}
              data-focusable
            >
              + New entry
            </button>
          </div>

          {status === 'loading' ? (
            <p className="files__list-empty">Loading entries…</p>
          ) : status === 'error' ? (
            <div className="files__list-empty" role="alert">
              <p>Couldn’t read the config.</p>
              <p className="files__list-detail">{loadError}</p>
              <button
                type="button"
                className="files__retry"
                onClick={() => void refresh()}
                data-focusable
              >
                Retry
              </button>
            </div>
          ) : sortedEntries.length === 0 ? (
            <p className="files__list-empty">
              No manual entries yet. Click <em>New entry</em> to add one.
            </p>
          ) : (
            <ul className="files__rows">
              {sortedEntries.map(({ entry, index }) => {
                const active = selectedIndex === index;
                return (
                  <li
                    key={`${entry.name}-${index}`}
                    className={`files__row ${active ? 'files__row--active' : ''}`}
                  >
                    <button
                      type="button"
                      className="files__row-main"
                      onClick={() => startEdit(index)}
                      data-focusable
                      aria-pressed={active}
                    >
                      <span className="files__row-name">{entry.name}</span>
                      <span className="files__row-path">
                        {entry.exe_path === '' ? '—' : entry.exe_path}
                      </span>
                    </button>
                    <button
                      type="button"
                      className="files__row-delete"
                      onClick={() => void handleDelete(index)}
                      aria-label={`Delete ${entry.name}`}
                      data-focusable
                    >
                      Delete
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </section>

        <section className="files__form-pane" aria-label="Entry editor">
          {!isFormOpen ? (
            <div className="files__placeholder">
              <p className="label">EDITOR</p>
              <p className="files__placeholder-body">
                Pick an entry to edit, or start a new one.
              </p>
            </div>
          ) : (
            <form className="files__form" onSubmit={(e) => void handleSubmit(e)}>
              <p className="label files__form-label">
                {isNewEntry ? 'NEW ENTRY' : 'EDIT ENTRY'}
              </p>

              <Field
                id="manual-name"
                label="Name"
                error={fieldErrors.name}
              >
                <input
                  id="manual-name"
                  ref={nameInputRef}
                  className="files__input"
                  type="text"
                  value={draft.name}
                  onChange={(e) => updateField('name', e.target.value)}
                  placeholder="Half-Life 3"
                  autoComplete="off"
                  spellCheck={false}
                  data-focusable
                />
              </Field>

              <Field
                id="manual-exe"
                label="Executable path"
                error={fieldErrors.exe_path}
                browse={() => void pickFile('exe_path', 'Choose executable', EXE_FILTERS)}
              >
                <input
                  id="manual-exe"
                  className="files__input files__input--mono"
                  type="text"
                  value={draft.exe_path}
                  onChange={(e) => updateField('exe_path', e.target.value)}
                  placeholder="C:\Games\HL3\hl3.exe"
                  spellCheck={false}
                  data-focusable
                />
              </Field>

              <Field id="manual-args" label="Arguments" hint="Optional">
                <input
                  id="manual-args"
                  className="files__input files__input--mono"
                  type="text"
                  value={draft.args}
                  onChange={(e) => updateField('args', e.target.value)}
                  placeholder="-novid -windowed"
                  spellCheck={false}
                  data-focusable
                />
              </Field>

              <Field
                id="manual-icon"
                label="Icon path"
                hint="Optional"
                browse={() => void pickFile('icon_path', 'Choose icon', ICON_FILTERS)}
              >
                <input
                  id="manual-icon"
                  className="files__input files__input--mono"
                  type="text"
                  value={draft.icon_path}
                  onChange={(e) => updateField('icon_path', e.target.value)}
                  placeholder="C:\Games\HL3\icon.png"
                  spellCheck={false}
                  data-focusable
                />
              </Field>

              <Field
                id="manual-cwd"
                label="Working directory"
                hint="Optional"
                browse={() => void pickDirectory('working_dir', 'Choose working directory')}
              >
                <input
                  id="manual-cwd"
                  className="files__input files__input--mono"
                  type="text"
                  value={draft.working_dir}
                  onChange={(e) => updateField('working_dir', e.target.value)}
                  placeholder="C:\Games\HL3"
                  spellCheck={false}
                  data-focusable
                />
              </Field>

              {formError !== '' && (
                <p className="files__form-error" role="alert">
                  {formError}
                </p>
              )}

              <div className="files__form-actions">
                <button
                  type="submit"
                  className="files__save"
                  disabled={saving}
                  data-focusable
                >
                  {saving ? 'Saving…' : 'Save'}
                </button>
                <button
                  type="button"
                  className="files__cancel"
                  onClick={cancelForm}
                  disabled={saving}
                  data-focusable
                >
                  Cancel
                </button>
              </div>
            </form>
          )}
        </section>
      </div>
    </div>
  );
}

// ── Field shell ────────────────────────────────────────────────────────

interface FieldProps {
  id: string;
  label: string;
  hint?: string;
  error?: string;
  browse?: () => void;
  children: ReactNode;
}

function Field({ id, label, hint, error, browse, children }: FieldProps) {
  return (
    <div className={`files__field ${error !== undefined ? 'files__field--error' : ''}`}>
      <div className="files__field-head">
        <label htmlFor={id} className="label files__field-label">
          {label}
        </label>
        {hint !== undefined && error === undefined && (
          <span className="files__field-hint">{hint}</span>
        )}
      </div>
      <div className="files__field-row">
        {children}
        {browse !== undefined && (
          <button
            type="button"
            className="files__browse"
            onClick={browse}
            data-focusable
          >
            Browse…
          </button>
        )}
      </div>
      {error !== undefined && (
        <p className="files__field-error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
