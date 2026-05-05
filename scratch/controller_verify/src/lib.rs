// Re-export the real controller code so we test the production sources,
// not a copy that can drift. Paths are relative to this lib.rs file.

#[path = "../../../frontend/src-tauri/src/types.rs"]
pub mod types;

pub mod controller {
    #[path = "../../../../frontend/src-tauri/src/controller/backend.rs"]
    pub mod backend;

    #[path = "../../../../frontend/src-tauri/src/controller/mapping.rs"]
    pub mod mapping;

    #[path = "../../../../frontend/src-tauri/src/controller/macros.rs"]
    pub mod macros;
}

// `controller/mapping.rs` and `controller/macros.rs` reference types via
// `crate::types::...`. Provide a top-level `types` alias so those imports
// resolve in this crate exactly the same as in the Tauri crate.
