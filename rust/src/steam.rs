// SPDX-FileCopyrightText: 2026 Zwart04
// SPDX-License-Identifier: GPL-3.0-or-later
// SweepDesk: see LICENSE for copying terms and warranty disclaimer.
//! Steam library discovery and graph-free game removal planning.

use crate::model::{home, removable_user_path, App};
use std::collections::{HashMap, HashSet};
use std::fs;
use std::path::{Path, PathBuf};

/// Read top-level AppState fields without trusting or executing the file.
pub fn manifest_fields(manifest: &Path) -> Option<HashMap<String, String>> {
    let text = fs::read_to_string(manifest).ok()?;
    let head = text.split("\"InstalledDepots\"").next().unwrap_or(&text);
    let pattern = regex::Regex::new(r#"^\s*"([A-Za-z]+)"\s+"([^"]*)""#).ok()?;
    let mut fields = HashMap::new();
    for line in head.lines() {
        if let Some(captures) = pattern.captures(line) {
            fields.insert(captures[1].to_string(), captures[2].to_string());
        }
    }
    let appid = fields.get("appid")?.clone();
    let valid = !appid.is_empty()
        && appid.len() <= 10
        && appid.chars().all(|value| value.is_ascii_digit());
    if !valid || manifest.file_name()?.to_string_lossy() != format!("appmanifest_{appid}.acf") {
        return None;
    }
    Some(fields)
}

pub fn protected_dir(name: &str) -> bool {
    let lower = name.to_lowercase();
    lower.starts_with("proton") || lower.starts_with("steamlinuxruntime") || lower.starts_with("steamworks")
}

/// Steam tools, Proton and runtimes are not games and stay out of the list.
pub fn is_game(fields: &HashMap<String, String>) -> bool {
    let name = fields.get("name").map(|v| v.trim()).unwrap_or("");
    let install = fields.get("installdir").map(|v| v.trim()).unwrap_or("");
    if name.is_empty() || install.is_empty() || install.contains('/') || install == "." || install == ".." {
        return false;
    }
    if install.starts_with('.') || !install.chars().all(|c| !c.is_control()) {
        return false;
    }
    let lowered = format!("{} {}", name.to_lowercase(), install.to_lowercase());
    let installed = fields
        .get("StateFlags")
        .and_then(|value| value.parse::<u64>().ok())
        .map(|flags| flags & 4 != 0)
        .unwrap_or(false);
    installed
        && !(protected_dir(install)
            || name.to_lowercase().starts_with("proton")
            || name.to_lowercase().starts_with("steam linux runtime")
            || name.to_lowercase().starts_with("steamworks common")
            || lowered.contains("steamworks common redistributables"))
}

pub fn libraries() -> Vec<PathBuf> {
    let mut libraries: Vec<PathBuf> = Vec::new();
    for root in [
        home().join(".local/share/Steam"),
        home().join(".steam/steam"),
        home().join(".var/app/com.valvesoftware.Steam/.local/share/Steam"),
    ] {
        let folder = root.join("steamapps");
        if folder.is_dir()
            && !fs::symlink_metadata(&folder)
                .map(|meta| meta.file_type().is_symlink())
                .unwrap_or(true)
        {
            libraries.push(folder);
        }
    }
    for folder in libraries.clone() {
        let vdf = folder.join("libraryfolders.vdf");
        if !vdf.is_file()
            || fs::symlink_metadata(&vdf)
                .map(|meta| meta.file_type().is_symlink())
                .unwrap_or(true)
        {
            continue;
        }
        let Ok(text) = fs::read_to_string(&vdf) else {
            continue;
        };
        let pattern = regex::Regex::new(r#""path"\s+"([^"]+)""#).unwrap();
        for captures in pattern.captures_iter(&text) {
            let raw = captures[1].replace("\\\\", "/");
            let extra = PathBuf::from(raw).join("steamapps");
            if extra.is_dir()
                && !fs::symlink_metadata(&extra)
                    .map(|meta| meta.file_type().is_symlink())
                    .unwrap_or(true)
            {
                libraries.push(extra);
            }
        }
    }
    let mut seen = HashSet::new();
    let mut result = Vec::new();
    for folder in libraries {
        let resolved = folder.canonicalize().unwrap_or(folder);
        let text = resolved.to_string_lossy().into_owned();
        if seen.insert(text) {
            result.push(resolved);
        }
    }
    result
}

pub fn steam_inventory(libraries_override: Option<Vec<PathBuf>>) -> Vec<App> {
    let libraries = libraries_override.unwrap_or_else(libraries);
    let mut apps = Vec::new();
    for library in libraries {
        let mut referenced = HashSet::new();
        let mut parsed_all = true;
        let mut manifests: Vec<PathBuf> = fs::read_dir(&library)
            .map(|entries| {
                entries
                    .filter_map(Result::ok)
                    .map(|entry| entry.path())
                    .filter(|path| {
                        path.file_name()
                            .map(|name| {
                                let name = name.to_string_lossy();
                                name.starts_with("appmanifest_") && name.ends_with(".acf")
                            })
                            .unwrap_or(false)
                    })
                    .collect()
            })
            .unwrap_or_default();
        manifests.sort();
        for manifest in manifests {
            if fs::symlink_metadata(&manifest)
                .map(|meta| meta.file_type().is_symlink())
                .unwrap_or(true)
            {
                parsed_all = false;
                continue;
            }
            let fields = match manifest_fields(&manifest) {
                Some(value) => value,
                None => {
                    parsed_all = false;
                    continue;
                }
            };
            referenced.insert(
                fields
                    .get("installdir")
                    .cloned()
                    .unwrap_or_default()
                    .to_lowercase(),
            );
            if !is_game(&fields) {
                continue;
            }
            let appid = fields["appid"].clone();
            let install = library.join("common").join(fields["installdir"].clone());
            if !install.is_dir()
                || fs::symlink_metadata(&install)
                    .map(|meta| meta.file_type().is_symlink())
                    .unwrap_or(true)
            {
                continue;
            }
            let paths = vec![
                install.to_string_lossy().into_owned(),
                manifest.to_string_lossy().into_owned(),
            ];
            let mut app = App::new(
                fields.get("name").map(String::as_str).unwrap_or(&appid),
                &appid,
                fields.get("buildid").map(String::as_str).unwrap_or(""),
                "Steam",
            );
            app.description = format!("Steam game · {}", library.display());
            app.icon = "applications-games".into();
            app.size = fields
                .get("SizeOnDisk")
                .and_then(|value| value.parse().ok())
                .unwrap_or(0);
            app.manager = "steam-game".into();
            app.scope = "User".into();
            app.paths = paths.clone();
            app.location = library.to_string_lossy().into_owned();
            if !paths.iter().all(|path| removable_user_path(Path::new(path))) {
                app.readonly_reason =
                    "This Steam game is in a location SweepDesk cannot move to Trash safely.".into();
            }
            apps.push(app);
        }
        let common = library.join("common");
        if !parsed_all || !common.is_dir() {
            continue;
        }
        let Ok(entries) = fs::read_dir(&common) else {
            continue;
        };
        let mut installs: Vec<PathBuf> = entries
            .filter_map(Result::ok)
            .map(|entry| entry.path())
            .collect();
        installs.sort();
        for install in installs {
            let name = install
                .file_name()
                .unwrap_or_default()
                .to_string_lossy()
                .to_string();
            if !install.is_dir()
                || fs::symlink_metadata(&install)
                    .map(|meta| meta.file_type().is_symlink())
                    .unwrap_or(true)
                || name.starts_with('.')
                || name.chars().any(|c| c.is_control())
                || referenced.contains(&name.to_lowercase())
                || protected_dir(&name)
            {
                continue;
            }
            let mut app = App::new(&name, &name, "", "Steam");
            app.description = format!(
                "Steam library leftover · no app manifest · {}",
                library.display()
            );
            app.icon = "applications-games".into();
            app.manager = "steam-leftover".into();
            app.scope = "User".into();
            app.paths = vec![install.to_string_lossy().into_owned()];
            app.location = library.to_string_lossy().into_owned();
            if !removable_user_path(&install) {
                app.readonly_reason =
                    "This Steam library folder is in a location SweepDesk cannot move to Trash safely.".into();
            }
            apps.push(app);
        }
    }
    apps
}

/// Recompute the exact game folder and manifest inside the planned library.
pub fn game_paths(app: &App) -> Vec<String> {
    let library = Path::new(&app.location);
    let manifest = library.join(format!("appmanifest_{}.acf", app.package));
    if !manifest.is_file() {
        return Vec::new();
    }
    let Some(fields) = manifest_fields(&manifest) else {
        return Vec::new();
    };
    if !is_game(&fields) || fields.get("appid") != Some(&app.package) {
        return Vec::new();
    }
    if !libraries().contains(&library.canonicalize().unwrap_or(library.to_path_buf())) {
        return Vec::new();
    }
    let install = library.join("common").join(fields["installdir"].clone());
    if !install.is_dir() {
        return Vec::new();
    }
    vec![
        install.to_string_lossy().into_owned(),
        manifest.to_string_lossy().into_owned(),
    ]
}

/// Recheck a manifest-less library folder before it may be moved to Trash.
pub fn leftover_paths(app: &App) -> Vec<String> {
    let name = &app.package;
    if name.is_empty() || name.contains('/') || name.starts_with('.') || protected_dir(name) {
        return Vec::new();
    }
    for folder in libraries() {
        if folder.to_string_lossy() != app.location {
            continue;
        }
        let target = folder.join("common").join(name);
        if !target.is_dir() {
            return Vec::new();
        }
        let Ok(entries) = fs::read_dir(&folder) else {
            return Vec::new();
        };
        for entry in entries.filter_map(Result::ok) {
            let path = entry.path();
            let file = path.file_name().unwrap_or_default().to_string_lossy();
            if !file.starts_with("appmanifest_") || !file.ends_with(".acf") {
                continue;
            }
            let Some(fields) = manifest_fields(&path) else {
                continue;
            };
            if fields
                .get("installdir")
                .map(|value| value.to_lowercase())
                == Some(name.to_lowercase())
            {
                return Vec::new();
            }
        }
        return vec![target.to_string_lossy().into_owned()];
    }
    Vec::new()
}

/// Do not move game files while Steam or the game itself is running.
pub fn process_running(app: &App) -> bool {
    let mut roots: Vec<PathBuf> = app
        .paths
        .iter()
        .map(PathBuf::from)
        .filter(|path| path.is_dir())
        .collect();
    if !app.location.is_empty() {
        roots.push(Path::new(&app.location).join("compatdata").join(&app.package));
        if let Some(parent) = Path::new(&app.location).parent() {
            roots.push(parent.to_path_buf());
        }
    }
    let roots: Vec<PathBuf> = roots
        .into_iter()
        .map(|root| root.canonicalize().unwrap_or(root))
        .collect();
    let Ok(entries) = fs::read_dir("/proc") else {
        return false;
    };
    for entry in entries.filter_map(Result::ok) {
        let name = entry.file_name().to_string_lossy().to_string();
        if !name.chars().all(|value| value.is_ascii_digit()) {
            continue;
        }
        let Ok(target) = fs::read_link(entry.path().join("exe")) else {
            continue;
        };
        let target = PathBuf::from(target.to_string_lossy().replace(" (deleted)", ""));
        let file = target
            .file_name()
            .unwrap_or_default()
            .to_string_lossy()
            .to_string();
        if file == "steam" || file == "steamwebhelper" {
            return true;
        }
        let resolved = target.canonicalize().unwrap_or(target);
        if roots.iter().any(|root| resolved.starts_with(root)) {
            return true;
        }
    }
    false
}
