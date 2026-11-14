// SPDX-FileCopyrightText: 2026 Zwart04
// SPDX-License-Identifier: GPL-3.0-or-later
// SweepDesk: see LICENSE for copying terms and warranty disclaimer.
//! Inventory model, process helpers and shared path safety rules.

use std::collections::HashSet;
use std::env;
use std::fs;
use std::os::unix::fs::MetadataExt;
use std::path::{Component, Path, PathBuf};
use std::process::Command;

pub const SOURCES: [&str; 16] = [
    "APT", "RPM", "Pacman", "APK", "npm", "pip", "Cargo", "Flatpak", "Snap", "pipx", "uv",
    "Bun", "Homebrew", "Steam", "ArtCraft", "Manual",
];

#[derive(Debug, Clone, Default, PartialEq)]
pub struct App {
    pub name: String,
    pub package: String,
    pub version: String,
    pub source: String,
    pub description: String,
    pub icon: String,
    pub size: u64,
    pub support: bool,
    pub essential: bool,
    pub executable: String,
    pub manager: String,
    pub scope: String,
    pub paths: Vec<String>,
    pub location: String,
    pub registry: String,
    pub readonly_reason: String,
}

impl App {
    pub fn new(name: &str, package: &str, version: &str, source: &str) -> Self {
        Self {
            name: name.into(),
            package: package.into(),
            version: version.into(),
            source: source.into(),
            ..Default::default()
        }
    }
}

#[derive(Debug, Clone, Default)]
pub struct Plan {
    pub app: App,
    pub commands: Vec<Vec<String>>,
    pub removed: Vec<String>,
    pub extra: Vec<String>,
    pub data: Vec<String>,
    pub files: Vec<String>,
    pub notes: Vec<String>,
    pub raw: String,
    pub fingerprint: String,
    pub cleanup_requested: bool,
}

pub fn home() -> PathBuf {
    PathBuf::from(env::var("HOME").unwrap_or_else(|_| "/root".into()))
}

pub fn data_home() -> PathBuf {
    match env::var("XDG_DATA_HOME") {
        Ok(value) if Path::new(&value).is_absolute() => PathBuf::from(value),
        _ => home().join(".local/share"),
    }
}

/// Run a command with a stable, non-interactive locale. No shell is involved.
pub fn run<S: AsRef<std::ffi::OsStr>>(
    args: &[S],
    timeout_secs: u64,
    check: bool,
) -> Result<String, String> {
    if args.is_empty() {
        return Ok(String::new());
    }
    let program = args[0].as_ref().to_string_lossy().into_owned();
    let mut command = Command::new(&program);
    command.args(&args[1..]);
    for (key, value) in [
        ("LC_ALL", "C"),
        ("LANG", "C"),
        ("NO_COLOR", "1"),
        ("HOMEBREW_NO_AUTO_UPDATE", "1"),
        ("HOMEBREW_NO_ANALYTICS", "1"),
        ("HOMEBREW_NO_AUTOREMOVE", "1"),
        ("PIP_DISABLE_PIP_VERSION_CHECK", "1"),
        ("npm_config_update_notifier", "false"),
    ] {
        command.env(key, value);
    }
    command.stdin(std::process::Stdio::null());
    let child = command
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped())
        .spawn()
        .map_err(|error| format!("{program}: {error}"))?;
    let _ = timeout_secs;
    let output = child
        .wait_with_output()
        .map_err(|error| format!("{program}: {error}"))?;
    let text = String::from_utf8_lossy(&output.stdout).into_owned();
    if check && !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        let message: String = stderr.chars().rev().take(4000).collect();
        let message: String = message.chars().rev().collect();
        return Err(format!("{program} failed: {}", message.trim()));
    }
    Ok(text)
}

pub fn which(name: &str) -> Option<PathBuf> {
    let path = env::var_os("PATH")?;
    env::split_paths(&path)
        .map(|dir| dir.join(name))
        .find(|candidate| candidate.is_file())
}

pub fn executable(name: &str, candidates: &[PathBuf]) -> Option<PathBuf> {
    which(name).or_else(|| candidates.iter().find(|path| path.is_file()).cloned())
}

pub fn is_flatpak() -> bool {
    Path::new("/.flatpak-info").exists()
}

/// Reject broad directories, traversal, parent symlinks and non-user-owned trees.
pub fn safe_user_path(path: &Path) -> bool {
    let home = home();
    if !path.is_absolute()
        || !path.starts_with(&home)
        || path.components().any(|part| part == Component::ParentDir)
    {
        return false;
    }
    let meta = match fs::symlink_metadata(path) {
        Ok(value) => value,
        Err(_) => return false,
    };
    if meta.file_type().is_symlink() || meta.uid() != current_uid() {
        return false;
    }
    let resolved = match path.canonicalize() {
        Ok(value) => value,
        Err(_) => return false,
    };
    if resolved == Path::new("/") || resolved == home {
        return false;
    }
    // Any parent symlink could redirect the move outside the tree we validated.
    let mut parent = path.parent();
    while let Some(directory) = parent {
        if fs::symlink_metadata(directory)
            .map(|entry| entry.file_type().is_symlink())
            .unwrap_or(false)
        {
            return false;
        }
        parent = directory.parent();
    }
    true
}

pub fn current_uid() -> u32 {
    fs::metadata("/proc/self").map(|meta| meta.uid()).unwrap_or(0)
}

/// Like `safe_user_path`, but also allows user-owned Steam libraries outside home.
pub fn removable_user_path(path: &Path) -> bool {
    if safe_user_path(path) {
        return true;
    }
    if !path.is_absolute() || path.components().any(|part| part == Component::ParentDir) {
        return false;
    }
    let parts: Vec<_> = path.components().collect();
    if parts.len() < 3 {
        return false;
    }
    if fs::symlink_metadata(path)
        .map(|meta| meta.file_type().is_symlink())
        .unwrap_or(true)
    {
        return false;
    }
    let mut parent = path.parent();
    while let Some(directory) = parent {
        if fs::symlink_metadata(directory)
            .map(|meta| meta.file_type().is_symlink())
            .unwrap_or(false)
        {
            return false;
        }
        parent = directory.parent();
    }
    fs::symlink_metadata(path)
        .map(|meta| meta.uid() == current_uid())
        .unwrap_or(false)
}

/// Small deterministic fingerprint for reviewed file lists.
pub fn fingerprint(paths: &[String]) -> Result<String, String> {
    let mut records = Vec::new();
    let mut unique: Vec<&String> = paths.iter().collect();
    unique.sort();
    unique.dedup();
    for path in unique {
        let item = Path::new(path);
        if !removable_user_path(item) {
            return Err("A path changed. Refresh the inventory.".into());
        }
        let meta = fs::symlink_metadata(item).map_err(|error| error.to_string())?;
        records.push(format!(
            "{}:{}:{}:{}:{}:{}:{}",
            item.display(),
            meta.dev(),
            meta.ino(),
            meta.mode(),
            meta.uid(),
            meta.size(),
            meta.mtime_nsec()
        ));
    }
    Ok(records.join("\n"))
}

pub fn unique_paths(paths: Vec<String>) -> Vec<String> {
    let mut seen = HashSet::new();
    paths
        .into_iter()
        .filter(|path| seen.insert(path.clone()))
        .collect()
}
