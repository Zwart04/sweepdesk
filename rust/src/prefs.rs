// SPDX-FileCopyrightText: 2026 Zwart04
// SPDX-License-Identifier: GPL-3.0-or-later
// SweepDesk: see LICENSE for copying terms and warranty disclaimer.
//! Small, validated per-user preferences. Inventories are never persisted.

use crate::model::{home, is_flatpak};
use serde::{Deserialize, Serialize};
use std::fs;
use std::io::Write;
use std::os::unix::fs::OpenOptionsExt;
use std::path::PathBuf;

pub const SCHEMA: u32 = 2;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(default)]
pub struct Preferences {
    pub schema: u32,
    pub auto_check_updates: bool,
    pub last_update_check: i64,
    pub language: String,
    pub theme: String,
    pub density: String,
    pub show_system: bool,
    pub show_details: bool,
    pub show_empty_sources: bool,
    pub scan_on_start: bool,
    pub remember_folders: bool,
    pub python_folders: Vec<String>,
    pub manual_folders: Vec<String>,
    pub enabled_sources: Vec<String>,
}

impl Default for Preferences {
    fn default() -> Self {
        Self {
            schema: SCHEMA,
            auto_check_updates: true,
            last_update_check: 0,
            language: "system".into(),
            theme: "dark".into(),
            density: "compact".into(),
            show_system: false,
            show_details: true,
            show_empty_sources: false,
            scan_on_start: true,
            remember_folders: true,
            python_folders: Vec::new(),
            manual_folders: Vec::new(),
            enabled_sources: crate::model::SOURCES
                .iter()
                .filter(|source| !(**source == "Manual" && is_flatpak()))
                .map(|source| source.to_string())
                .collect(),
        }
    }
}

impl Preferences {
    pub fn validate(mut self) -> Self {
        let defaults = Preferences::default();
        if !matches!(self.language.as_str(), "system" | "id" | "en") {
            self.language = defaults.language;
        }
        if !matches!(self.theme.as_str(), "dark" | "light" | "system") {
            self.theme = defaults.theme;
        }
        if !matches!(self.density.as_str(), "compact" | "comfortable") {
            self.density = defaults.density;
        }
        self.python_folders = self
            .python_folders
            .into_iter()
            .filter(|path| path.starts_with('/'))
            .collect();
        self.manual_folders = self
            .manual_folders
            .into_iter()
            .filter(|path| path.starts_with('/'))
            .collect();
        let mut enabled: Vec<String> = crate::model::SOURCES
            .iter()
            .filter(|source| self.enabled_sources.iter().any(|item| item == *source))
            .map(|source| source.to_string())
            .collect();
        if self.schema < 2 && !enabled.iter().any(|item| item == "Steam") {
            let position = enabled.iter().position(|item| item == "Homebrew").unwrap_or(enabled.len());
            enabled.insert(position, "Steam".into());
        }
        self.enabled_sources = enabled;
        self.schema = SCHEMA;
        self
    }
}

pub fn config_path() -> PathBuf {
    match std::env::var("XDG_CONFIG_HOME") {
        Ok(value) if PathBuf::from(&value).is_absolute() => {
            PathBuf::from(value).join("sweepdesk/preferences.json")
        }
        _ => home().join(".config/sweepdesk/preferences.json"),
    }
}

pub fn load() -> Preferences {
    let path = config_path();
    let Ok(text) = fs::read_to_string(&path) else {
        return Preferences::default();
    };
    serde_json::from_str::<Preferences>(&text)
        .map(Preferences::validate)
        .unwrap_or_default()
}

pub fn save(preferences: &Preferences) -> Result<(), String> {
    let path = config_path();
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|error| error.to_string())?;
        let _ = fs::set_permissions(parent, std::os::unix::fs::PermissionsExt::from_mode(0o700));
    }
    let text = serde_json::to_string_pretty(preferences).map_err(|error| error.to_string())?;
    let temp = path.with_extension("json.tmp");
    {
        let mut file = fs::OpenOptions::new()
            .write(true)
            .create(true)
            .truncate(true)
            .mode(0o600)
            .open(&temp)
            .map_err(|error| error.to_string())?;
        file.write_all(text.as_bytes())
            .map_err(|error| error.to_string())?;
    }
    fs::rename(&temp, &path).map_err(|error| error.to_string())
}

