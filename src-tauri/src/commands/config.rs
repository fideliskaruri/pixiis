use std::path::{Path, PathBuf};

use crate::error::{AppError, AppResult};
use serde_json::{Map, Value};
use tauri::{AppHandle, Manager};
use toml_edit::{Document, Item, Table};

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
}
