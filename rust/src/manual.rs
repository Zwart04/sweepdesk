// SPDX-FileCopyrightText: 2026 Zwart04
// SPDX-License-Identifier: GPL-3.0-or-later
// SweepDesk: see LICENSE for copying terms and warranty disclaimer.
//! ArtCraft AppImages, user desktop launchers and the verified Horizon launcher.

use crate::model::{data_home, home, run, safe_user_path, App};
use serde_json::Value;
use std::collections::{HashMap, HashSet};
use std::fs;
use std::hash::{Hash, Hasher};
use std::os::unix::fs::MetadataExt;
use std::path::{Path, PathBuf};

pub const DESKTOP_READONLY: &str = "Found from a user desktop shortcut. SweepDesk cannot verify its installation or remove it safely; use the original installer.";

/// Minimal Desktop Entry parser: keys of the `[Desktop Entry]` group only.
pub fn desktop_fields(text: &str) -> HashMap<String, String> {
    let mut section = String::new();
    let mut fields = HashMap::new();
    for raw in text.lines() {
        let line = raw.trim();
        if line.starts_with('[') && line.ends_with(']') {
            section = line.trim_matches(['[', ']']).to_string();
            continue;
        }
        if section != "Desktop Entry" || line.starts_with('#') {
            continue;
        }
        if let Some((key, value)) = line.split_once('=') {
            fields.insert(key.trim().to_string(), value.trim().to_string());
        }
    }
    fields
}

fn exec_path(command: &str) -> Option<PathBuf> {
    let token = command
        .split_whitespace()
        .next()?
        .trim_matches('"')
        .trim_matches('\'');
    if token.is_empty() {
        return None;
    }
    Some(PathBuf::from(token))
}

pub fn appimage_inventory(registered: &[App]) -> Vec<App> {
    let mut apps = Vec::new();
    let mut seen: HashSet<PathBuf> = registered
        .iter()
        .flat_map(|app| app.paths.iter())
        .filter_map(|path| Path::new(path).canonicalize().ok())
        .collect();
    let manifest = home().join(".local/share/artcraft-launcher/installed.json");
    if let Ok(text) = fs::read_to_string(&manifest) {
        if let Ok(data) = serde_json::from_str::<Value>(&text) {
            if let Some(entries) = data.get("apps").and_then(|value| value.as_object()) {
                for (key, record) in entries {
                    if record.get("kind").and_then(|value| value.as_str()) != Some("AppImage") {
                        continue;
                    }
                    let Some(path) = record.get("path").and_then(|value| value.as_str()) else {
                        continue;
                    };
                    let path = Path::new(path);
                    if !path.is_file() || !safe_user_path(path) {
                        continue;
                    }
                    let mut files = vec![path.to_string_lossy().into_owned()];
                    files.extend(
                        record
                            .get("files")
                            .and_then(|value| value.as_array())
                            .map(|items| {
                                items
                                    .iter()
                                    .filter_map(|item| item.as_str())
                                    .filter(|item| safe_user_path(Path::new(item)))
                                    .map(str::to_string)
                                    .collect::<Vec<_>>()
                            })
                            .unwrap_or_default(),
                    );
                    let mut title = key.clone();
                    if let Some(first) = title.get_mut(0..1) {
                        first.make_ascii_uppercase();
                    }
                    let mut app = App::new(
                        &title,
                        key,
                        record.get("version").and_then(|value| value.as_str()).unwrap_or(""),
                        "ArtCraft",
                    );
                    app.description = "AppImage registered with ArtCraft Launcher".into();
                    app.icon = format!("ai.storyteller.{key}");
                    app.executable = path.to_string_lossy().into_owned();
                    app.paths = files;
                    app.registry = manifest.to_string_lossy().into_owned();
                    app.scope = "User".into();
                    apps.push(app);
                    if let Ok(resolved) = path.canonicalize() {
                        seen.insert(resolved);
                    }
                }
            }
        }
    }
    let Ok(entries) = fs::read_dir(home().join(".local/share/applications")) else {
        return apps;
    };
    let mut shortcuts: Vec<PathBuf> = entries
        .filter_map(Result::ok)
        .map(|entry| entry.path())
        .filter(|path| path.extension().map(|value| value == "desktop").unwrap_or(false))
        .collect();
    shortcuts.sort();
    for shortcut in shortcuts {
        let Ok(text) = fs::read_to_string(&shortcut) else {
            continue;
        };
        let fields = desktop_fields(&text);
        let Some(exec) = fields.get("Exec").and_then(|value| exec_path(value)) else {
            continue;
        };
        if exec.extension().map(|value| value.to_string_lossy().to_lowercase()) != Some("appimage".into())
            || !exec.is_file()
            || !safe_user_path(&exec)
        {
            continue;
        }
        let Ok(resolved) = exec.canonicalize() else {
            continue;
        };
        if !seen.insert(resolved) {
            continue;
        }
        let mut app = App::new(
            fields.get("Name").map(String::as_str).unwrap_or_else(|| {
                exec.file_stem().unwrap_or_default().to_str().unwrap_or("AppImage")
            }),
            exec.file_name().unwrap_or_default().to_string_lossy().as_ref(),
            "—",
            "Manual",
        );
        app.description = "AppImage from a user launcher · executable and shortcut tracked".into();
        app.icon = fields
            .get("Icon")
            .cloned()
            .unwrap_or_else(|| "application-x-executable".into());
        app.executable = exec.to_string_lossy().into_owned();
        app.paths = vec![
            exec.to_string_lossy().into_owned(),
            shortcut.to_string_lossy().into_owned(),
        ];
        app.scope = "User".into();
        apps.push(app);
    }
    apps
}

/// Only a directly installed, user-owned Horizon launcher executable is accepted.
pub fn horizon_launcher(name: &str, command: &str) -> Option<PathBuf> {
    if name.trim().to_lowercase() != "horizon" {
        return None;
    }
    let candidate = exec_path(command)?;
    let home = home();
    let absolute = if candidate.is_absolute() {
        candidate
    } else {
        return None;
    };
    if absolute.file_name()? != "horizon-launcher"
        || !absolute.starts_with(&home)
        || !safe_user_path(&absolute)
        || !absolute.is_file()
    {
        return None;
    }
    Some(absolute)
}

pub fn horizon_install_paths(executable: &str) -> Vec<String> {
    let exe = PathBuf::from(executable);
    if horizon_launcher("Horizon", &exe.to_string_lossy()) != Some(exe.clone()) {
        return Vec::new();
    }
    let mut paths = Vec::new();
    let install_dir = exe.parent().unwrap_or(Path::new("/"));
    let dir_name = install_dir
        .file_name()
        .unwrap_or_default()
        .to_string_lossy()
        .to_lowercase();
    if dir_name.starts_with("horizon-launcher-") || dir_name.starts_with("horizon-launcher_") {
        if let Ok(entries) = fs::read_dir(install_dir) {
            let items: Vec<PathBuf> = entries.filter_map(Result::ok).map(|e| e.path()).collect();
            if items.len() == 1 && items[0] == exe && safe_user_path(install_dir) {
                paths.push(install_dir.to_string_lossy().into_owned());
            }
        }
    }
    if paths.is_empty() && safe_user_path(&exe) {
        paths.push(exe.to_string_lossy().into_owned());
    }
    let desktop_root = data_home().join("applications");
    if let Ok(entries) = fs::read_dir(&desktop_root) {
        let mut shortcuts: Vec<PathBuf> = entries
            .filter_map(Result::ok)
            .map(|entry| entry.path())
            .filter(|path| path.extension().map(|value| value == "desktop").unwrap_or(false))
            .collect();
        shortcuts.sort();
        for shortcut in shortcuts {
            if !safe_user_path(&shortcut) {
                continue;
            }
            let Ok(text) = fs::read_to_string(&shortcut) else {
                continue;
            };
            let fields = desktop_fields(&text);
            let stem = shortcut
                .file_stem()
                .unwrap_or_default()
                .to_string_lossy()
                .to_lowercase();
            let matches_launcher = stem == "horizon-launcher"
                && horizon_launcher(
                    fields.get("Name").map(String::as_str).unwrap_or(""),
                    fields.get("Exec").map(String::as_str).unwrap_or(""),
                ) == Some(exe.clone());
            let matches_game = stem == "horizon"
                && fields
                    .get("NoDisplay")
                    .map(|value| value.eq_ignore_ascii_case("true"))
                    .unwrap_or(false)
                && fields
                    .get("Exec")
                    .and_then(|value| exec_path(value))
                    .map(|path| {
                        path.file_name()
                            .map(|name| name.to_string_lossy().to_lowercase() == "horizon-client")
                            .unwrap_or(false)
                    })
                    .unwrap_or(false);
            if fields.get("Type").map(String::as_str) == Some("Application")
                && fields
                    .get("Name")
                    .map(|value| value.trim().to_lowercase() == "horizon")
                    .unwrap_or(false)
                && fields
                    .get("Icon")
                    .map(|value| value.trim().to_lowercase() == "horizon")
                    .unwrap_or(false)
                && (matches_launcher || matches_game)
            {
                paths.push(shortcut.to_string_lossy().into_owned());
            }
        }
    }
    let icon_root = data_home().join("icons/hicolor");
    if let Ok(levels) = fs::read_dir(&icon_root) {
        for level in levels.filter_map(Result::ok) {
            let apps_dir = level.path().join("apps");
            let Ok(icons) = fs::read_dir(&apps_dir) else {
                continue;
            };
            for icon in icons.filter_map(Result::ok) {
                let path = icon.path();
                let stem = path.file_stem().unwrap_or_default().to_string_lossy().to_lowercase();
                if stem == "horizon" && path.is_file() && safe_user_path(&path) {
                    paths.push(path.to_string_lossy().into_owned());
                }
            }
        }
    }
    crate::model::unique_paths(paths)
}

pub fn horizon_fingerprint(paths: &[String], executable: &str) -> Result<String, String> {
    if !safe_user_path(Path::new(executable)) {
        return Err("The Horizon launcher could not be checked safely. Refresh the inventory.".into());
    }
    let mut records = Vec::new();
    let mut all: Vec<String> = paths.to_vec();
    all.push(executable.to_string());
    all.sort();
    all.dedup();
    for path in all {
        let item = Path::new(&path);
        if !safe_user_path(item) {
            return Err("A Horizon installation path changed. Refresh the inventory.".into());
        }
        let meta = fs::symlink_metadata(item).map_err(|error| error.to_string())?;
        let bytes = fs::read(item).map_err(|error| error.to_string())?;
        let mut hasher = std::collections::hash_map::DefaultHasher::new();
        bytes.hash(&mut hasher);
        records.push(format!(
            "{path}:{}:{}:{}:{}:{}",
            meta.ino(),
            meta.mode(),
            meta.size(),
            meta.mtime(),
            hasher.finish()
        ));
    }
    Ok(records.join("\n"))
}

pub fn horizon_process_running(app: &App, data: &[String]) -> bool {
    let target = PathBuf::from(&app.executable);
    let mut roots: Vec<PathBuf> = app
        .paths
        .iter()
        .chain(data.iter())
        .map(PathBuf::from)
        .filter(|path| path.is_dir())
        .map(|path| path.canonicalize().unwrap_or(path))
        .collect();
    roots.push(target);
    let Ok(entries) = fs::read_dir("/proc") else {
        return false;
    };
    for entry in entries.filter_map(Result::ok) {
        let name = entry.file_name().to_string_lossy().to_string();
        if !name.chars().all(|value| value.is_ascii_digit()) {
            continue;
        }
        let Ok(exe) = fs::read_link(entry.path().join("exe")) else {
            continue;
        };
        let exe = PathBuf::from(exe.to_string_lossy().replace(" (deleted)", ""));
        let file = exe
            .file_name()
            .unwrap_or_default()
            .to_string_lossy()
            .to_lowercase();
        if file == "horizon-launcher"
            || file == "horizon-client"
            || file == "horizon-server"
            || file == "horizon-prepare"
        {
            return true;
        }
        let resolved = exe.canonicalize().unwrap_or(exe);
        if roots.iter().any(|root| resolved.starts_with(root)) {
            return true;
        }
    }
    false
}

/// Clear keychain tokens through the launcher CLI without printing account details.
pub fn sign_out_accounts(app: &App, emit: &mut dyn FnMut(&str)) -> Result<(), String> {
    let accounts_file = data_home().join("horizon-launcher/accounts.json");
    if !accounts_file.exists() || !safe_user_path(&accounts_file) {
        return Ok(());
    }
    let failure = || {
        "Horizon could not safely clear its saved sign-in tokens. No Horizon files were moved; sign out in Horizon and try again.".to_string()
    };
    let listed = run(&[&app.executable, "--json", "account", "list"], 30, false).map_err(|_| failure())?;
    let payload: Value = serde_json::from_str(&listed).map_err(|_| failure())?;
    let accounts = payload
        .get("accounts")
        .and_then(|value| value.as_array())
        .cloned()
        .unwrap_or_default();
    let pattern = regex::Regex::new(
        r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-8][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$",
    )
    .unwrap();
    let mut identifiers = Vec::new();
    for account in &accounts {
        let Some(value) = account.get("uuid").and_then(|value| value.as_str()) else {
            return Err(failure());
        };
        if !pattern.is_match(value) {
            return Err(failure());
        }
        identifiers.push(value.to_string());
    }
    if identifiers.is_empty() {
        return Ok(());
    }
    emit("Signing out Horizon accounts from the system keychain…\n");
    for identifier in identifiers {
        run(
            &[&app.executable, "account", "sign-out", &identifier],
            30,
            true,
        )
        .map_err(|_| {
            "Horizon could not finish signing out its saved accounts. No Horizon files were moved; check Horizon account state before retrying.".to_string()
        })?;
    }
    emit("Horizon accounts signed out.\n");
    Ok(())
}

pub fn desktop_launcher_inventory(registered: &[App]) -> Vec<App> {
    let Ok(entries) = fs::read_dir(home().join(".local/share/applications")) else {
        return Vec::new();
    };
    let known: HashSet<String> = registered
        .iter()
        .flat_map(|app| app.paths.iter().cloned())
        .collect();
    let mut apps = Vec::new();
    let mut shortcuts: Vec<PathBuf> = entries
        .filter_map(Result::ok)
        .map(|entry| entry.path())
        .filter(|path| path.extension().map(|value| value == "desktop").unwrap_or(false))
        .collect();
    shortcuts.sort();
    for shortcut in shortcuts {
        let Ok(text) = fs::read_to_string(&shortcut) else {
            continue;
        };
        let fields = desktop_fields(&text);
        if fields.get("Type").map(String::as_str) != Some("Application") {
            continue;
        }
        let Some(exec) = fields.get("Exec").and_then(|value| exec_path(value)) else {
            continue;
        };
        if !exec.is_file() || !safe_user_path(&exec) || known.contains(&*exec.to_string_lossy()) {
            continue;
        }
        if horizon_launcher(
            fields.get("Name").map(String::as_str).unwrap_or(""),
            fields.get("Exec").map(String::as_str).unwrap_or(""),
        )
        .is_some()
        {
            let paths = horizon_install_paths(&exec.to_string_lossy());
            if !paths.is_empty() {
                let mut app = App::new(
                    fields.get("Name").map(String::as_str).unwrap_or("Horizon"),
                    "horizon-launcher",
                    "—",
                    "Manual",
                );
                app.description = "Horizon Launcher · verified user launcher, shortcuts and icons".into();
                app.icon = fields.get("Icon").cloned().unwrap_or_else(|| "horizon".into());
                app.executable = exec.to_string_lossy().into_owned();
                app.paths = paths;
                app.manager = "horizon-launcher".into();
                app.scope = "User".into();
                apps.push(app);
                continue;
            }
        }
        let mut app = App::new(
            fields.get("Name").map(String::as_str).unwrap_or("Desktop application"),
            exec.file_name().unwrap_or_default().to_string_lossy().as_ref(),
            "—",
            "Manual",
        );
        app.description = "Application from a user desktop shortcut".into();
        app.icon = fields
            .get("Icon")
            .cloned()
            .unwrap_or_else(|| "application-x-executable".into());
        app.executable = exec.to_string_lossy().into_owned();
        app.paths = vec![shortcut.to_string_lossy().into_owned()];
        app.manager = "desktop-launcher".into();
        app.scope = "User".into();
        app.readonly_reason = DESKTOP_READONLY.into();
        apps.push(app);
    }
    apps
}

/// Recheck an ArtCraft record before its files are moved to Trash.
pub fn artcraft_paths(app: &App) -> Vec<String> {
    let manifest = Path::new(&app.registry);
    let Ok(text) = fs::read_to_string(manifest) else {
        return Vec::new();
    };
    let Ok(data) = serde_json::from_str::<Value>(&text) else {
        return Vec::new();
    };
    let Some(record) = data.get("apps").and_then(|apps| apps.get(&app.package)) else {
        return Vec::new();
    };
    let Some(path) = record.get("path").and_then(|value| value.as_str()) else {
        return Vec::new();
    };
    if !Path::new(path).is_file() || !safe_user_path(Path::new(path)) {
        return Vec::new();
    }
    let mut files = vec![path.to_string()];
    files.extend(
        record
            .get("files")
            .and_then(|value| value.as_array())
            .map(|items| {
                items
                    .iter()
                    .filter_map(|item| item.as_str())
                    .filter(|item| safe_user_path(Path::new(item)))
                    .map(str::to_string)
                    .collect::<Vec<_>>()
            })
            .unwrap_or_default(),
    );
    files
}

pub fn forget_artcraft(app: &App) -> Result<(), String> {
    let manifest = Path::new(&app.registry);
    let text = fs::read_to_string(manifest).map_err(|error| error.to_string())?;
    let mut data: Value = serde_json::from_str(&text).map_err(|error| error.to_string())?;
    if let Some(apps) = data.get_mut("apps").and_then(|value| value.as_object_mut()) {
        apps.remove(&app.package);
    }
    let text = serde_json::to_string_pretty(&data).map_err(|error| error.to_string())?;
    fs::write(manifest, text).map_err(|error| error.to_string())
}
