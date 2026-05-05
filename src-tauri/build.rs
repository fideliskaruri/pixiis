// `ts-rs` writes one .ts file per `#[ts(export)]` type into the path declared
// by each type's `#[ts(export_to = "../src/api/types/")]` attribute (resolved
// from CARGO_MANIFEST_DIR), driven by the auto-generated `#[test]` hooks that
// fire on `cargo test`. We only need build.rs to (a) hand off to tauri-build
// and (b) re-trigger when the wire-format types change.
fn main() {
    println!("cargo:rerun-if-changed=src/types.rs");
    tauri_build::build();
}
