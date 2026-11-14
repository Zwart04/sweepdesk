// SPDX-FileCopyrightText: 2026 Zwart04
// SPDX-License-Identifier: GPL-3.0-or-later
// SweepDesk: see LICENSE for copying terms and warranty disclaimer.
//! Resolve freedesktop icon names to PNG or SVG files and keep the handles in memory.

use crate::model::{data_home, home};
use iced::widget::image;
use iced::widget::svg;
use std::collections::HashMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::{Mutex, OnceLock};

const APP_GLYPH: &[u8] = include_bytes!("../../assets/ui/app-symbolic.svg");
const TERMINAL_GLYPH: &[u8] = include_bytes!("../../assets/ui/terminal-symbolic.svg");
const SIZES: [&str; 7] = [
    "64x64", "48x48", "128x128", "32x32", "256x256", "512x512", "scalable",
];

#[derive(Debug, Clone)]
pub enum Icon {
    Svg(svg::Handle),
    Raster(image::Handle),
}

#[derive(Debug, Clone, Copy)]
pub enum Glyph {
    Application,
    Terminal,
}

impl Glyph {
    fn key(self) -> &'static str {
        match self {
            Glyph::Application => "\u{0}app",
            Glyph::Terminal => "\u{0}terminal",
        }
    }

    fn data(self) -> &'static [u8] {
        match self {
            Glyph::Application => APP_GLYPH,
            Glyph::Terminal => TERMINAL_GLYPH,
        }
    }
}

fn cache() -> &'static Mutex<HashMap<String, Icon>> {
    static CACHE: OnceLock<Mutex<HashMap<String, Icon>>> = OnceLock::new();
    CACHE.get_or_init(|| Mutex::new(HashMap::new()))
}

fn theme_roots() -> Vec<PathBuf> {
    vec![
        data_home().join("icons"),
        home().join(".icons"),
        PathBuf::from("/usr/local/share/icons"),
        PathBuf::from("/usr/share/icons"),
    ]
}

fn pixmap_roots() -> Vec<PathBuf> {
    vec![
        data_home().join("pixmaps"),
        home().join(".local/share/pixmaps"),
        PathBuf::from("/usr/local/share/pixmaps"),
        PathBuf::from("/usr/share/pixmaps"),
    ]
}

fn themes(root: &Path) -> Vec<String> {
    let mut names = vec!["hicolor".to_string(), "Adwaita".to_string()];
    if let Ok(entries) = fs::read_dir(root) {
        let mut extra: Vec<String> = entries
            .flatten()
            .filter(|entry| entry.path().join("index.theme").is_file())
            .filter_map(|entry| entry.file_name().into_string().ok())
            .collect();
        extra.sort();
        for name in extra {
            if !names.contains(&name) {
                names.push(name);
            }
        }
    }
    names
}

fn candidate(name: &str) -> Option<PathBuf> {
    if name.is_empty() {
        return None;
    }
    let direct = Path::new(name);
    if direct.is_absolute() {
        return direct.is_file().then(|| direct.to_path_buf());
    }
    let base = name
        .strip_suffix(".png")
        .or_else(|| name.strip_suffix(".svg"))
        .or_else(|| name.strip_suffix(".xpm"))
        .unwrap_or(name);
    let roots = theme_roots();
    for root in &roots {
        for theme in themes(root) {
            for size in SIZES {
                for folder in ["apps", "devices", "categories", ""] {
                    let mut path = root.join(&theme).join(size);
                    if !folder.is_empty() {
                        path = path.join(folder);
                    }
                    for extension in ["png", "svg"] {
                        let file = path.join(format!("{base}.{extension}"));
                        if file.is_file() {
                            return Some(file);
                        }
                    }
                }
            }
        }
    }
    for root in pixmap_roots() {
        for extension in ["png", "svg"] {
            let file = root.join(format!("{base}.{extension}"));
            if file.is_file() {
                return Some(file);
            }
        }
    }
    None
}

fn load(path: &Path) -> Option<Icon> {
    let bytes = fs::read(path).ok()?;
    if path.extension().and_then(|value| value.to_str()) == Some("svg") {
        Some(Icon::Svg(svg::Handle::from_memory(bytes)))
    } else {
        Some(Icon::Raster(image::Handle::from_path(path)))
    }
}

fn glyph(kind: Glyph) -> Icon {
    Icon::Svg(svg::Handle::from_memory(kind.data()))
}

/// Look up a cached icon without touching the filesystem; the glyph is used until
/// [`preload`] has resolved the name.
pub fn cached(name: &str, kind: Glyph) -> Icon {
    if let Some(icon) = cache().lock().ok().and_then(|map| map.get(name).cloned()) {
        return icon;
    }
    if let Some(icon) = cache()
        .lock()
        .ok()
        .and_then(|map| map.get(kind.key()).cloned())
    {
        return icon;
    }
    glyph(kind)
}

/// Resolve every name and store the handles so later frames only read the cache.
pub fn preload(names: Vec<String>) {
    let mut resolved = Vec::with_capacity(names.len());
    for name in names {
        let icon = candidate(&name).and_then(|path| load(&path));
        resolved.push((name, icon));
    }
    if let Ok(mut map) = cache().lock() {
        for (name, icon) in resolved {
            if let Some(icon) = icon {
                map.insert(name, icon);
            }
        }
        for kind in [Glyph::Application, Glyph::Terminal] {
            map.entry(kind.key().to_string())
                .or_insert_with(|| glyph(kind));
        }
    }
}
