use std::path::{Path, PathBuf};
use std::str::FromStr;

use crate::error::{AppError, AppResult};
use serde_json::{Map, Value};
use tauri::{AppHandle, Manager, Runtime};
use tauri_plugin_global_shortcut::{GlobalShortcutExt, Shortcut};
use toml_edit::{Document, Item, Table};

// ── Global summon hotkey ─────────────────────────────────────────────
//
// Default: Ctrl+Shift+Alt+P (PIXIIS). Persisted at
// `daemon.summon_shortcut`. The string format is the human-readable
// `"Ctrl+Shift+Alt+P"` shape — `parse_summon_shortcut` translates
// single-letter keys to the W3C `KeyboardEvent.code` form
// (`KeyP`) before handing it to the plugin's `Shortcut` parser, which
// is strict about codes for letter keys.

pub const DEFAULT_SUMMON_SHORTCUT: &str = "Ctrl+Shift+Alt+P";

// ── User config file (%APPDATA%/pixiis/config.toml) ──────────────────
//
// Persistence model:
//   - `config_get` returns the merged view as a JSON map so the React
//     SettingsPage can use its existing dotted-path readers.
//   - `config_set` round-trips the user's TOML through `toml_edit` so
//     comments + ordering survive each Apply.
//   - `config_reset` deletes the user override (next read falls back to
//     the bundled `resources/default_config.toml`).

fn user_config_path(app: &AppHandle) -> AppResult<PathBuf> {
    let dir = app
        .path()
        .app_data_dir()
        .map_err(|e| AppError::Other(format!("app_data_dir unavailable: {e}")))?;
    Ok(dir.join("config.toml"))
}

/// Resolve `resources/default_config.toml` from either the bundled
/// resource path (release) or the source tree (dev). Returns the file
/// contents on success.
fn read_default_config_text() -> Option<String> {
    let candidates = [
        std::env::current_exe()
            .ok()
            .and_then(|p| p.parent().map(|p| p.join("resources/default_config.toml"))),
        Some(PathBuf::from("../resources/default_config.toml")),
        Some(PathBuf::from("resources/default_config.toml")),
    ];
    for path in candidates.into_iter().flatten() {
        if let Ok(text) = std::fs::read_to_string(&path) {
            return Some(text);
        }
    }
    None
}

/// Load the editable user config, falling back to the bundled default,
/// then to an empty document. A corrupt user file is reported via
/// `AppError` so the UI can show it instead of silently dropping the
/// user's settings.
fn load_document(app: &AppHandle) -> AppResult<Document> {
    let user_path = user_config_path(app)?;
    if user_path.exists() {
        let text = std::fs::read_to_string(&user_path)?;
        return text
            .parse::<Document>()
            .map_err(|e| AppError::Other(format!("config.toml parse error: {e}")));
    }
    if let Some(text) = read_default_config_text() {
        if let Ok(doc) = text.parse::<Document>() {
            return Ok(doc);
        }
    }
    Ok(Document::new())
}

/// Convert a `toml_edit::Item` into a `serde_json::Value` for the
/// frontend bridge. Datetimes are stringified (the Settings page never
/// reads any datetime fields, but losing them silently would be worse
/// than a string round-trip).
fn item_to_json(item: &Item) -> Value {
    match item {
        Item::None => Value::Null,
        Item::Value(v) => value_to_json(v),
        Item::Table(t) => Value::Object(table_to_json(t)),
        Item::ArrayOfTables(arr) => Value::Array(
            arr.iter()
                .map(|t| Value::Object(table_to_json(t)))
                .collect(),
        ),
    }
}

fn value_to_json(v: &toml_edit::Value) -> Value {
    use toml_edit::Value as TV;
    match v {
        TV::String(s) => Value::String(s.value().clone()),
        TV::Integer(i) => Value::Number((*i.value()).into()),
        TV::Float(f) => serde_json::Number::from_f64(*f.value())
            .map(Value::Number)
            .unwrap_or(Value::Null),
        TV::Boolean(b) => Value::Bool(*b.value()),
        TV::Datetime(d) => Value::String(d.value().to_string()),
        TV::Array(arr) => Value::Array(arr.iter().map(value_to_json).collect()),
        TV::InlineTable(t) => {
            let mut map = Map::new();
            for (k, v) in t.iter() {
                map.insert(k.to_string(), value_to_json(v));
            }
            Value::Object(map)
        }
    }
}

fn table_to_json(t: &Table) -> Map<String, Value> {
    let mut out = Map::new();
    for (k, v) in t.iter() {
        out.insert(k.to_string(), item_to_json(v));
    }
    out
}

/// Recursively merge a JSON patch into a TOML table. Object values
/// descend into nested tables (creating them if needed) so that e.g.
/// `{"library": {"providers": [...]}}` only replaces the providers list
/// without nuking sibling keys under `[library]`. Arrays + scalars
/// fully replace the existing value at that key.
fn merge_into_table(table: &mut Table, patch: &Map<String, Value>) -> AppResult<()> {
    for (key, value) in patch.iter() {
        match value {
            Value::Object(inner) => {
                // Nested object → ensure a Table at this key, then recurse.
                let entry = table.entry(key).or_insert(Item::Table(Table::new()));
                if !entry.is_table() {
                    *entry = Item::Table(Table::new());
                }
                let sub = entry
                    .as_table_mut()
                    .expect("just-inserted table should be a table");
                merge_into_table(sub, inner)?;
            }
            other => {
                let item = json_to_item(other)?;
                if matches!(item, Item::None) {
                    table.remove(key);
                } else {
                    table.insert(key, item);
                }
            }
        }
    }
    Ok(())
}

/// Convert a JSON scalar / array into a `toml_edit::Item`. Nested
/// objects are handled by `merge_into_table` (so we never lose sibling
/// keys); they should not reach this function.
fn json_to_item(v: &Value) -> AppResult<Item> {
    use toml_edit::value;
    Ok(match v {
        Value::Null => Item::None,
        Value::Bool(b) => value(*b),
        Value::Number(n) => {
            if let Some(i) = n.as_i64() {
                value(i)
            } else if let Some(f) = n.as_f64() {
                value(f)
            } else {
                return Err(AppError::InvalidArg(format!("unsupported number {n}")));
            }
        }
        Value::String(s) => value(s.clone()),
        Value::Array(items) => {
            let mut arr = toml_edit::Array::new();
            for item in items {
                arr.push(json_to_value(item)?);
            }
            value(arr)
        }
        Value::Object(_) => {
            // Inline tables would also be valid TOML, but every Settings
            // patch shape is intentionally a plain table — surface a
            // clear error rather than silently materialising one.
            return Err(AppError::InvalidArg(
                "nested object in array position is not supported".into(),
            ));
        }
    })
}

fn json_to_value(v: &Value) -> AppResult<toml_edit::Value> {
    use toml_edit::Value as TV;
    Ok(match v {
        Value::Null => {
            return Err(AppError::InvalidArg("null inside array".into()));
        }
        Value::Bool(b) => TV::from(*b),
        Value::Number(n) => {
            if let Some(i) = n.as_i64() {
                TV::from(i)
            } else if let Some(f) = n.as_f64() {
                TV::from(f)
            } else {
                return Err(AppError::InvalidArg(format!("unsupported number {n}")));
            }
        }
        Value::String(s) => TV::from(s.clone()),
        Value::Array(items) => {
            let mut arr = toml_edit::Array::new();
            for item in items {
                arr.push(json_to_value(item)?);
            }
            TV::from(arr)
        }
        Value::Object(map) => {
            let mut t = toml_edit::InlineTable::new();
            for (k, v) in map.iter() {
                t.insert(k, json_to_value(v)?);
            }
            TV::from(t)
        }
    })
}

/// Atomic-ish write: emit to a sibling tempfile then rename so a crash
/// mid-write never leaves the user with a half-written config.
fn write_document(path: &Path, doc: &Document) -> AppResult<()> {
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    let tmp = path.with_extension("toml.tmp");
    std::fs::write(&tmp, doc.to_string())?;
    std::fs::rename(&tmp, path)?;
    Ok(())
}

#[tauri::command]
pub async fn config_get(app: AppHandle) -> AppResult<Map<String, Value>> {
    let doc = load_document(&app)?;
    Ok(table_to_json(doc.as_table()))
}

/// Look up a dotted-path string value from the merged user/default
/// config. Used at startup to seed `ServicesContainer` with the API
/// keys the user persisted via Settings (the `config_set` command
/// writes them to `%APPDATA%/pixiis/config.toml`). Returns `None` when
/// the path is missing, the value isn't a string, or the value is
/// empty. An env-var fallback (e.g. `PIXIIS_YT_API_KEY`) is layered on
/// top by the caller — this helper is just the file source.
pub fn lookup_config_string<R: Runtime>(app: &AppHandle<R>, dotted: &str) -> Option<String> {
    let path = user_config_path_runtime(app).ok()?;
    let doc = if path.exists() {
        std::fs::read_to_string(&path).ok()?.parse::<Document>().ok()?
    } else {
        read_default_config_text()?.parse::<Document>().ok()?
    };

    let mut segments = dotted.split('.');
    let first = segments.next()?;
    let mut item: &Item = doc.as_table().get(first)?;
    for segment in segments {
        let table = item.as_table()?;
        item = table.get(segment)?;
    }
    let s = item.as_str()?.trim().to_string();
    if s.is_empty() { None } else { Some(s) }
}

#[tauri::command]
pub async fn config_set(app: AppHandle, patch: Map<String, Value>) -> AppResult<()> {
    let path = user_config_path(&app)?;
    let mut doc = load_document(&app)?;
    merge_into_table(doc.as_table_mut(), &patch)?;
    write_document(&path, &doc)?;
    Ok(())
}

#[tauri::command]
pub async fn config_reset(app: AppHandle) -> AppResult<()> {
    let path = user_config_path(&app)?;
    if path.exists() {
        std::fs::remove_file(&path)?;
    }
    Ok(())
}

#[tauri::command]
pub async fn app_quit(app: AppHandle) -> AppResult<()> {
    app.exit(0);
    Ok(())
}

#[tauri::command]
pub async fn app_show(app: AppHandle) -> AppResult<()> {
    if let Some(w) = app.get_webview_window("main") {
        let _ = w.show();
        let _ = w.unminimize();
        let _ = w.set_focus();
    }
    Ok(())
}

#[tauri::command]
pub async fn app_set_autostart(_enabled: bool) -> AppResult<()> {
    // Phase 1A stub. Real impl will use the autostart plugin's manager.
    Ok(())
}

// ── First-launch onboarding marker ───────────────────────────────────
//
// Mirrors the Python original's `cache_dir() / .onboarded` sentinel —
// presence (any contents) means the user has finished or skipped the
// onboarding flow. Stored under Tauri's app_data_dir which on Windows
// resolves to `%APPDATA%/pixiis/`.

fn onboarded_marker_path(app: &AppHandle) -> AppResult<PathBuf> {
    let dir = app
        .path()
        .app_data_dir()
        .map_err(|e| AppError::Other(format!("app_data_dir unavailable: {e}")))?;
    Ok(dir.join(".onboarded"))
}

#[tauri::command]
pub async fn app_get_onboarded(app: AppHandle) -> AppResult<bool> {
    Ok(onboarded_marker_path(&app)?.exists())
}

#[tauri::command]
pub async fn app_set_onboarded(app: AppHandle, value: bool) -> AppResult<()> {
    let path = onboarded_marker_path(&app)?;
    if value {
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent)?;
        }
        std::fs::write(&path, b"1")?;
    } else if path.exists() {
        std::fs::remove_file(&path)?;
    }
    Ok(())
}

/// Read `daemon.summon_shortcut` from the merged config (user override
/// then bundled default). Returns `None` if the key is absent or
/// non-string. An empty string is preserved (means "disabled") so the
/// caller can distinguish "user cleared it" from "never set".
pub fn read_summon_shortcut_string<R: Runtime>(app: &AppHandle<R>) -> Option<String> {
    let path = user_config_path_runtime(app).ok()?;
    let doc = if path.exists() {
        std::fs::read_to_string(&path).ok()?.parse::<Document>().ok()?
    } else {
        read_default_config_text()?.parse::<Document>().ok()?
    };
    doc.as_table()
        .get("daemon")
        .and_then(|d| d.as_table())
        .and_then(|t| t.get("summon_shortcut"))
        .and_then(|i| i.as_str())
        .map(|s| s.to_string())
}

fn user_config_path_runtime<R: Runtime>(app: &AppHandle<R>) -> AppResult<PathBuf> {
    let dir = app
        .path()
        .app_data_dir()
        .map_err(|e| AppError::Other(format!("app_data_dir unavailable: {e}")))?;
    Ok(dir.join("config.toml"))
}

/// Translate a user-friendly shortcut string into a `Shortcut`.
///
/// Accepts shapes the Settings UI emits:
///   `"Ctrl+Shift+Alt+P"`  →  `Ctrl+Shift+Alt+KeyP`
///   `"CommandOrControl+K"` →  `CommandOrControl+KeyK`
///
/// The plugin's parser also accepts `KeyP` directly, so we leave
/// already-prefixed key codes alone. Single-character digit/letter
/// terminals are rewritten because the parser rejects bare `P` /  `7`.
pub fn parse_summon_shortcut(input: &str) -> Result<Shortcut, String> {
    let normalised = normalise_shortcut(input);
    Shortcut::from_str(&normalised).map_err(|e| format!("{e}"))
}

fn normalise_shortcut(input: &str) -> String {
    let parts: Vec<&str> = input.split('+').map(|p| p.trim()).filter(|p| !p.is_empty()).collect();
    if parts.is_empty() {
        return String::new();
    }
    let (last, mods) = parts.split_last().expect("non-empty");
    let key = normalise_key(last);
    let mut out = String::new();
    for m in mods {
        out.push_str(m);
        out.push('+');
    }
    out.push_str(&key);
    out
}

fn normalise_key(key: &str) -> String {
    // Already a KeyboardEvent.code? Pass through.
    if key.starts_with("Key")
        || key.starts_with("Digit")
        || key.starts_with("Numpad")
        || key.starts_with('F')
            && key.len() >= 2
            && key[1..].chars().all(|c| c.is_ascii_digit())
        || matches!(
            key,
            "Space"
                | "Enter"
                | "Escape"
                | "Tab"
                | "Backspace"
                | "Delete"
                | "Insert"
                | "Home"
                | "End"
                | "PageUp"
                | "PageDown"
                | "ArrowUp"
                | "ArrowDown"
                | "ArrowLeft"
                | "ArrowRight"
                | "Minus"
                | "Equal"
                | "Comma"
                | "Period"
                | "Slash"
                | "Backslash"
                | "Semicolon"
                | "Quote"
                | "BracketLeft"
                | "BracketRight"
                | "Backquote"
        )
    {
        return key.to_string();
    }
    let chars: Vec<char> = key.chars().collect();
    if chars.len() == 1 {
        let c = chars[0];
        if c.is_ascii_alphabetic() {
            return format!("Key{}", c.to_ascii_uppercase());
        }
        if c.is_ascii_digit() {
            return format!("Digit{c}");
        }
    }
    // Unknown — let the plugin parser surface the error.
    key.to_string()
}

#[tauri::command]
pub async fn app_get_summon_shortcut(app: AppHandle) -> AppResult<String> {
    Ok(read_summon_shortcut_string(&app).unwrap_or_else(|| DEFAULT_SUMMON_SHORTCUT.to_string()))
}

/// Update + persist the global summon hotkey.
///
/// `shortcut = Some("")` disables the hotkey (writes empty string,
/// unregisters all). `None` is treated the same as `Some("")` for
/// callers that prefer that ergonomic. Persistence happens before
/// registration so a parse error in a fresh value still gets stored —
/// the user can correct it in the Settings UI without losing what they
/// typed. Returns the persisted string so the caller can reflect it.
#[tauri::command]
pub async fn app_set_summon_shortcut(
    app: AppHandle,
    shortcut: Option<String>,
) -> AppResult<String> {
    let value = shortcut.unwrap_or_default();
    // Persist into config.toml under [daemon].summon_shortcut.
    let path = user_config_path(&app)?;
    let mut doc = load_document(&app)?;
    {
        let table = doc.as_table_mut();
        let entry = table.entry("daemon").or_insert(Item::Table(Table::new()));
        if !entry.is_table() {
            *entry = Item::Table(Table::new());
        }
        let sub = entry
            .as_table_mut()
            .expect("just-inserted table should be a table");
        sub.insert("summon_shortcut", toml_edit::value(value.clone()));
    }
    write_document(&path, &doc)?;

    // Re-register: clear any prior binding, then register the new one
    // (unless the caller asked to disable it).
    let manager = app.global_shortcut();
    let _ = manager.unregister_all();
    if !value.is_empty() {
        let parsed = parse_summon_shortcut(&value)
            .map_err(|e| AppError::InvalidArg(format!("invalid shortcut '{value}': {e}")))?;
        manager
            .register(parsed)
            .map_err(|e| AppError::Other(format!("failed to register shortcut: {e}")))?;
    }
    Ok(value)
}

// ── Tests ────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn parse(s: &str) -> Document {
        s.parse::<Document>().unwrap()
    }

    #[test]
    fn merge_preserves_sibling_keys() {
        // [library] has two siblings; patching only `providers` must
        // leave `scan_interval_minutes` (and its comment) untouched.
        let mut doc = parse(
            r#"
[library]
providers = ["steam"]
# how often the background sweep runs
scan_interval_minutes = 60
"#,
        );
        let patch: Map<String, Value> = json!({
            "library": { "providers": ["steam", "xbox"] }
        })
        .as_object()
        .unwrap()
        .clone();
        merge_into_table(doc.as_table_mut(), &patch).unwrap();
        let s = doc.to_string();
        assert!(s.contains("scan_interval_minutes = 60"), "lost sibling: {s}");
        assert!(
            s.contains("how often the background sweep runs"),
            "lost comment: {s}"
        );
        assert!(s.contains(r#""xbox""#), "patch missed: {s}");
    }

    #[test]
    fn merge_handles_deep_nesting() {
        let mut doc = parse(
            r#"
[services.rawg]
api_key = ""

[services.youtube]
api_key = "old"
"#,
        );
        let patch: Map<String, Value> = json!({
            "services": {
                "rawg": { "api_key": "new-key" }
            }
        })
        .as_object()
        .unwrap()
        .clone();
        merge_into_table(doc.as_table_mut(), &patch).unwrap();
        let s = doc.to_string();
        assert!(s.contains(r#"api_key = "new-key""#), "{s}");
        assert!(
            s.contains(r#"api_key = "old""#),
            "youtube key was clobbered: {s}"
        );
    }

    #[test]
    fn merge_creates_missing_tables() {
        let mut doc = Document::new();
        let patch: Map<String, Value> = json!({
            "daemon": { "autostart": true }
        })
        .as_object()
        .unwrap()
        .clone();
        merge_into_table(doc.as_table_mut(), &patch).unwrap();
        let s = doc.to_string();
        assert!(s.contains("autostart = true"), "{s}");
    }

    #[test]
    fn json_view_round_trips_scalars() {
        let doc = parse(
            r#"
[voice]
model = "large-v3"
energy_threshold = 300
device = "auto"

[library]
providers = ["steam", "xbox"]
"#,
        );
        let json = table_to_json(doc.as_table());
        assert_eq!(
            json.get("voice").and_then(|v| v.get("model")),
            Some(&Value::String("large-v3".into()))
        );
        assert_eq!(
            json.get("library")
                .and_then(|v| v.get("providers"))
                .and_then(|v| v.as_array())
                .map(|a| a.len()),
            Some(2)
        );
    }

    #[test]
    fn normalise_letter_keys_to_keyboard_code() {
        assert_eq!(normalise_shortcut("Ctrl+Shift+Alt+P"), "Ctrl+Shift+Alt+KeyP");
        assert_eq!(normalise_shortcut("CommandOrControl+K"), "CommandOrControl+KeyK");
    }

    #[test]
    fn normalise_digits_to_digit_code() {
        assert_eq!(normalise_shortcut("Ctrl+5"), "Ctrl+Digit5");
    }

    #[test]
    fn normalise_passes_through_full_codes() {
        // Already in W3C code form — leave alone.
        assert_eq!(
            normalise_shortcut("Ctrl+Shift+KeyP"),
            "Ctrl+Shift+KeyP"
        );
        assert_eq!(normalise_shortcut("Alt+Space"), "Alt+Space");
        assert_eq!(normalise_shortcut("Ctrl+F12"), "Ctrl+F12");
    }

    #[test]
    fn parse_default_summon_shortcut_succeeds() {
        // The compiled-in default must always parse — guard against typos
        // creeping into DEFAULT_SUMMON_SHORTCUT.
        parse_summon_shortcut(DEFAULT_SUMMON_SHORTCUT)
            .expect("default summon shortcut should parse");
    }
}
