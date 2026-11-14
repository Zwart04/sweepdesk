// SPDX-FileCopyrightText: 2026 Zwart04
// SPDX-License-Identifier: GPL-3.0-or-later
// SweepDesk: see LICENSE for copying terms and warranty disclaimer.
//! Read-only inventory for every supported package manager.

use crate::model::{data_home, executable, home, is_flatpak, run, unique_paths, App};
use crate::manual;
use crate::steam;
use std::collections::{HashMap, HashSet};
use std::fs;
use std::path::{Path, PathBuf};

#[derive(Clone)]
pub struct DesktopEntry {
    pub name: String,
    pub icon: String,
}

pub type DesktopIndex = HashMap<String, DesktopEntry>;

fn parse_desktop(text: &str) -> Option<(String, String, bool)> {
    let mut section = String::new();
    let mut name = None;
    let mut icon = String::new();
    let mut exec = String::new();
    let mut nodisplay = false;
    for raw in text.lines() {
        let line = raw.trim();
        if line.starts_with('[') && line.ends_with(']') {
            section = line.trim_matches(['[', ']']).to_string();
            continue;
        }
        if section != "Desktop Entry" || line.starts_with('#') {
            continue;
        }
        let Some((key, value)) = line.split_once('=') else {
            continue;
        };
        match key.trim() {
            "Type" if value.trim() != "Application" => return None,
            "Name" => name = Some(value.trim().to_string()),
            "Icon" => icon = value.trim().to_string(),
            "Exec" => exec = value.trim().to_string(),
            "NoDisplay" if value.trim().eq_ignore_ascii_case("true") => nodisplay = true,
            _ => {}
        }
    }
    if nodisplay {
        return None;
    }
    Some((
        name.unwrap_or_default(),
        if icon.is_empty() {
            "application-x-executable".into()
        } else {
            icon
        },
        !exec.is_empty(),
    ))
        .map(|(name, icon, _)| (name, icon, true))
}

pub fn desktop_index() -> DesktopIndex {
    let mut result = DesktopIndex::new();
    let roots = [
        PathBuf::from("/usr/share/applications"),
        PathBuf::from("/usr/local/share/applications"),
        data_home().join("applications"),
    ];
    for root in roots {
        let Ok(entries) = fs::read_dir(&root) else {
            continue;
        };
        let mut paths: Vec<PathBuf> = entries
            .filter_map(Result::ok)
            .map(|entry| entry.path())
            .filter(|path| path.extension().map(|e| e == "desktop").unwrap_or(false))
            .collect();
        paths.sort();
        for path in paths {
            let Ok(text) = fs::read_to_string(&path) else {
                continue;
            };
            let Some((name, icon, _)) = parse_desktop(&text) else {
                continue;
            };
            let stem = path.file_stem().unwrap_or_default().to_string_lossy().to_string();
            let info = DesktopEntry { name, icon };
            let mut keys = vec![stem.to_lowercase()];
            if let Some(last) = stem.split('.').last() {
                keys.push(last.to_lowercase());
            }
            if let Some(first) = text
                .lines()
                .find(|line| line.starts_with("Exec="))
                .and_then(|line| line.trim_start_matches("Exec=").split_whitespace().next())
            {
                keys.push(
                    Path::new(first)
                        .file_name()
                        .unwrap_or_default()
                        .to_string_lossy()
                        .to_lowercase(),
                );
            }
            for key in keys {
                result.insert(key, info.clone());
            }
        }
    }
    result
}

pub fn decorate(app: &mut App, desktops: &DesktopIndex) {
    let key = app.package.split(':').next().unwrap_or("").to_string();
    let aliases = [
        ("@anthropic-ai/claude-code", "claude"),
        ("@openai/codex", "codex"),
        ("opencode-ai", "opencode"),
        ("curl", "curl"),
        ("steam-launcher", "steam"),
    ];
    let alias = aliases
        .iter()
        .find(|(package, _)| *package == key)
        .map(|(_, value)| *value)
        .unwrap_or("");
    let exe_name = Path::new(&app.executable)
        .file_name()
        .unwrap_or_default()
        .to_string_lossy()
        .to_lowercase();
    let rpm_location = if app.source == "RPM" {
        app.location.clone()
    } else {
        String::new()
    };
    for candidate in [rpm_location, key.clone(), alias.to_string(), exe_name] {
        if candidate.is_empty() {
            continue;
        }
        let Some(entry) = desktops.get(&candidate.to_lowercase()) else {
            continue;
        };
        app.icon = entry.icon.clone();
        if matches!(app.source.as_str(), "APT" | "RPM" | "Pacman" | "APK" | "ArtCraft") {
            app.name = entry.name.clone();
            app.support = false;
        }
        break;
    }
    if let Some(part) = app.package.strip_prefix("libreoffice-") {
        if matches!(part, "writer" | "calc" | "impress" | "draw" | "math" | "base") {
            let mut title = part.to_string();
            if let Some(first) = title.get_mut(0..1) {
                first.make_ascii_uppercase();
            }
            app.name = format!("LibreOffice {title}");
            app.icon = format!("libreoffice-{part}");
        }
    }
    if key == "command-code" {
        app.name = "Command Code".into();
    }
}

pub fn python_locations(extra: &[String]) -> Vec<PathBuf> {
    let mut paths: Vec<PathBuf> = Vec::new();
    if let Some(found) = crate::model::which("python3") {
        paths.push(found);
    }
    paths.push(PathBuf::from("/usr/bin/python3"));
    for name in ["VIRTUAL_ENV", "CONDA_PREFIX"] {
        if let Ok(value) = std::env::var(name) {
            paths.push(Path::new(&value).join("bin/python"));
        }
    }
    let pyenv = home().join(".pyenv/versions");
    if let Ok(entries) = fs::read_dir(&pyenv) {
        for entry in entries.filter_map(Result::ok) {
            paths.push(entry.path().join("bin/python"));
        }
    }
    paths.extend(extra.iter().map(PathBuf::from));
    unique_paths(
        paths
            .into_iter()
            .filter(|path| path.is_file())
            .map(|path| path.to_string_lossy().into_owned())
            .collect(),
    )
    .into_iter()
    .map(PathBuf::from)
    .collect()
}

/// Read `*.dist-info` metadata directly; no interpreter is executed.
fn site_packages(interpreter: &Path) -> Vec<PathBuf> {
    let prefix = interpreter.parent().and_then(|bin| bin.parent()).unwrap_or(Path::new("/usr"));
    let mut roots = Vec::new();
    for lib in [prefix.join("lib"), prefix.join("lib64")] {
        let Ok(entries) = fs::read_dir(&lib) else {
            continue;
        };
        for entry in entries.filter_map(Result::ok) {
            let name = entry.file_name().to_string_lossy().to_string();
            if name.starts_with("python") {
                roots.push(entry.path().join("site-packages"));
                roots.push(entry.path().join("dist-packages"));
            }
        }
    }
    roots.into_iter().filter(|path| path.is_dir()).collect()
}

fn read_field(path: &Path, field: &str) -> Option<String> {
    let text = fs::read_to_string(path).ok()?;
    for line in text.lines() {
        if line.is_empty() {
            break;
        }
        if let Some(value) = line.strip_prefix(&format!("{field}:")) {
            return Some(value.trim().to_string());
        }
    }
    None
}

pub fn pip_inventory(extra: &[String]) -> Vec<App> {
    let mut apps = Vec::new();
    let mut seen = HashSet::new();
    for interpreter in python_locations(extra) {
        let prefix = interpreter
            .parent()
            .and_then(|bin| bin.parent())
            .unwrap_or(Path::new("/usr"))
            .to_path_buf();
        for root in site_packages(&interpreter) {
            let Ok(entries) = fs::read_dir(&root) else {
                continue;
            };
            for entry in entries.filter_map(Result::ok) {
                let name = entry.file_name().to_string_lossy().to_string();
                if !name.ends_with(".dist-info") {
                    continue;
                }
                let metadata = entry.path().join("METADATA");
                let Some(package) = read_field(&metadata, "Name") else {
                    continue;
                };
                let identity = (package.clone(), entry.path().to_string_lossy().into_owned());
                if !seen.insert(identity) {
                    continue;
                }
                if root.to_string_lossy().contains("/pipx/venvs/")
                    || root.to_string_lossy().contains("/uv/tools/")
                {
                    continue;
                }
                let installer = read_field(&entry.path().join("INSTALLER"), "x")
                    .or_else(|| fs::read_to_string(entry.path().join("INSTALLER")).ok())
                    .unwrap_or_default()
                    .trim()
                    .to_string();
                let under_home = root.starts_with(home());
                if !matches!(installer.as_str(), "pip" | "uv") && !under_home {
                    continue;
                }
                let mut app = App::new(
                    &package,
                    &package,
                    &read_field(&metadata, "Version").unwrap_or_default(),
                    "pip",
                );
                app.description = format!("Python distribution · {}", interpreter.display());
                app.manager = interpreter.to_string_lossy().into_owned();
                app.scope = prefix.to_string_lossy().into_owned();
                app.location = entry.path().to_string_lossy().into_owned();
                app.readonly_reason = pip_readonly(&root, &entry.path(), &installer);
                apps.push(app);
            }
        }
    }
    apps
}

fn pip_readonly(root: &Path, metadata: &Path, installer: &str) -> String {
    let home = home();
    if !root.starts_with(&home) || !metadata.starts_with(&home) {
        return "This package is outside your home folder; manage it through its owning package manager.".into();
    }
    if !metadata.join("RECORD").is_file() {
        return "The distribution has no RECORD file; its installed files cannot be reliably uninstalled.".into();
    }
    if root.starts_with("/usr") && installer != "pip" {
        return "This Python is externally managed (PEP 668). SweepDesk will not override the system protection. Use a virtual environment or the owning package manager.".into();
    }
    String::new()
}

pub fn uv_inventory() -> Vec<App> {
    let Some(manager) = executable(
        "uv",
        &[home().join(".local/bin/uv"), home().join(".cargo/bin/uv")],
    ) else {
        return Vec::new();
    };
    let Ok(output) = run(&[manager.to_string_lossy().as_ref(), "tool", "list"], 90, true) else {
        return Vec::new();
    };
    let pattern = regex::Regex::new(r"^([A-Za-z0-9][A-Za-z0-9_.-]*) v(\S+)").unwrap();
    output
        .lines()
        .filter_map(|line| pattern.captures(line))
        .map(|captures| {
            let mut app = App::new(
                &captures[1],
                &captures[1],
                &captures[2],
                "uv",
            );
            app.description = "Isolated Python tool managed by uv".into();
            app.manager = manager.to_string_lossy().into_owned();
            app
        })
        .collect()
}

pub fn bun_inventory() -> Vec<App> {
    let Some(manager) = executable("bun", &[home().join(".bun/bin/bun")]) else {
        return Vec::new();
    };
    let base = PathBuf::from(
        std::env::var("BUN_INSTALL").unwrap_or_else(|_| home().join(".bun").to_string_lossy().into_owned()),
    );
    let mut folder = PathBuf::from(
        std::env::var("BUN_INSTALL_GLOBAL_DIR")
            .unwrap_or_else(|_| base.join("install/global").to_string_lossy().into_owned()),
    );
    if let Ok(output) = run(
        &[
            manager.to_string_lossy().as_ref(),
            "pm",
            "ls",
            "--global",
        ],
        90,
        false,
    ) {
        if let Some(candidate) = output
            .lines()
            .find(|line| line.contains(" node_modules"))
            .and_then(|line| line.rsplit_once(" node_modules"))
            .map(|(path, _)| PathBuf::from(path))
        {
            if candidate.is_absolute() {
                folder = candidate;
            }
        }
    }
    let manifest = folder.join("package.json");
    let Ok(text) = fs::read_to_string(&manifest) else {
        return Vec::new();
    };
    let Ok(data) = serde_json::from_str::<serde_json::Value>(&text) else {
        return Vec::new();
    };
    let Some(dependencies) = data.get("dependencies").and_then(|value| value.as_object()) else {
        return Vec::new();
    };
    let valid = regex::Regex::new(r"^(?:@[A-Za-z0-9_.-]+/)?[A-Za-z0-9_][A-Za-z0-9_.-]*$").unwrap();
    dependencies
        .keys()
        .filter(|name| valid.is_match(name))
        .map(|name| {
            let meta = folder.join("node_modules").join(name).join("package.json");
            let version = fs::read_to_string(&meta)
                .ok()
                .and_then(|text| serde_json::from_str::<serde_json::Value>(&text).ok())
                .and_then(|value| value.get("version").and_then(|v| v.as_str()).map(str::to_string))
                .unwrap_or_default();
            let mut app = App::new(name, name, &version, "Bun");
            app.description = format!("Global Bun package · {}", folder.display());
            app.manager = manager.to_string_lossy().into_owned();
            app.scope = folder.to_string_lossy().into_owned();
            app
        })
        .collect()
}

pub fn brew_inventory() -> Vec<App> {
    let Some(manager) = executable(
        "brew",
        &[
            PathBuf::from("/home/linuxbrew/.linuxbrew/bin/brew"),
            home().join(".linuxbrew/bin/brew"),
        ],
    ) else {
        return Vec::new();
    };
    let Ok(output) = run(
        &[
            manager.to_string_lossy().as_ref(),
            "info",
            "--json=v2",
            "--installed",
        ],
        90,
        true,
    ) else {
        return Vec::new();
    };
    let Ok(report) = serde_json::from_str::<serde_json::Value>(&output) else {
        return Vec::new();
    };
    let Some(formulae) = report.get("formulae").and_then(|value| value.as_array()) else {
        return Vec::new();
    };
    formulae
        .iter()
        .map(|formula| {
            let name = formula
                .get("full_name")
                .and_then(|value| value.as_str())
                .or_else(|| formula.get("name").and_then(|value| value.as_str()))
                .unwrap_or_default();
            let installs = formula
                .get("installed")
                .and_then(|value| value.as_array())
                .cloned()
                .unwrap_or_default();
            let version = installs
                .iter()
                .filter_map(|entry| entry.get("version").and_then(|v| v.as_str()))
                .collect::<Vec<_>>()
                .join(", ");
            let mut app = App::new(
                formula.get("name").and_then(|v| v.as_str()).unwrap_or(name),
                name,
                &version,
                "Homebrew",
            );
            app.description = formula
                .get("desc")
                .and_then(|value| value.as_str())
                .unwrap_or_default()
                .into();
            app.manager = manager.to_string_lossy().into_owned();
            app.support = !installs.iter().any(|entry| {
                entry
                    .get("installed_on_request")
                    .and_then(|value| value.as_bool())
                    .unwrap_or(true)
            });
            app
        })
        .collect()
}

pub fn apt_inventory() -> Vec<App> {
    let format = "${binary:Package}\t${Version}\t${Installed-Size}\t${Essential}\t${Priority}\t${db:Status-Abbrev}\t${binary:Summary}\n";
    let Ok(output) = run(&["/usr/bin/dpkg-query", "-W", &format!("-f={format}")], 90, true) else {
        return Vec::new();
    };
    let automatic: HashSet<String> = run(&["/usr/bin/apt-mark", "showauto"], 90, false)
        .unwrap_or_default()
        .lines()
        .map(str::to_string)
        .collect();
    let mut apps = Vec::new();
    for line in output.lines() {
        let parts: Vec<&str> = line.split('\t').collect();
        if parts.len() != 7 || !parts[5].starts_with("ii") {
            continue;
        }
        let (pkg, version, size, essential, priority, _, description) =
            (parts[0], parts[1], parts[2], parts[3], parts[4], parts[5], parts[6]);
        let base = pkg.split(':').next().unwrap_or(pkg);
        let support = essential == "yes"
            || matches!(priority, "required" | "important")
            || automatic.contains(pkg)
            || automatic.contains(base)
            || base.starts_with("lib")
            || ["fonts-", "gir1.", "linux-", "python3-", "steam-libs"]
                .iter()
                .any(|prefix| base.starts_with(prefix));
        let mut app = App::new(base, pkg, version, "APT");
        app.description = description.to_string();
        app.icon = if support {
            "package-x-generic".into()
        } else {
            "utilities-terminal".into()
        };
        app.size = size.parse::<u64>().unwrap_or(0) * 1024;
        app.support = support;
        app.essential = essential == "yes" || priority == "required";
        apps.push(app);
    }
    apps
}

pub fn flatpak_inventory() -> Vec<App> {
    let mut apps = Vec::new();
    for scope in ["user", "system"] {
        let Ok(output) = run(
            &[
                "flatpak",
                &format!("--{scope}"),
                "list",
                "--app",
                "--columns=application,name,version,size",
            ],
            90,
            false,
        ) else {
            continue;
        };
        for line in output.lines() {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() < 2 {
                continue;
            }
            let mut app = App::new(
                parts[1],
                parts[0],
                parts.get(2).copied().unwrap_or(""),
                "Flatpak",
            );
            app.description = format!("Flatpak application · {scope}");
            app.icon = parts[0].into();
            app.scope = scope.into();
            apps.push(app);
        }
    }
    apps
}

pub fn npm_locations() -> Vec<PathBuf> {
    let mut paths = Vec::new();
    if let Some(found) = crate::model::which("npm") {
        paths.push(found);
    }
    for base in [home().join(".nvm/versions/node")] {
        if let Ok(entries) = fs::read_dir(&base) {
            for entry in entries.filter_map(Result::ok) {
                paths.push(entry.path().join("bin/npm"));
            }
        }
    }
    if let Ok(entries) = fs::read_dir(home().join(".local/share/fnm/node-versions")) {
        for entry in entries.filter_map(Result::ok) {
            paths.push(entry.path().join("installation/bin/npm"));
        }
    }
    let mut result = Vec::new();
    let mut seen = HashSet::new();
    for path in paths {
        if !path.is_file() {
            continue;
        }
        let real = path.canonicalize().unwrap_or_else(|_| path.clone());
        if seen.insert(real) {
            result.push(path);
        }
    }
    result
}

fn npm_run(manager: &Path, args: &[&str]) -> Result<String, String> {
    let mut owned: Vec<String> = vec![manager.to_string_lossy().into_owned()];
    owned.extend(args.iter().map(|value| value.to_string()));
    run(&owned, 90, true)
}

pub fn npm_inventory() -> Vec<App> {
    let mut apps = Vec::new();
    let mut seen = HashSet::new();
    for manager in npm_locations() {
        let Ok(output) = npm_run(&manager, &["list", "-g", "--depth=0", "--json"]) else {
            continue;
        };
        let Ok(data) = serde_json::from_str::<serde_json::Value>(&output) else {
            continue;
        };
        let Ok(prefix) = npm_run(&manager, &["prefix", "-g"]) else {
            continue;
        };
        let prefix = prefix.trim().to_string();
        if !Path::new(&prefix).is_absolute() {
            continue;
        }
        let Some(dependencies) = data.get("dependencies").and_then(|value| value.as_object()) else {
            continue;
        };
        for (package, meta) in dependencies {
            if !seen.insert((prefix.clone(), package.clone())) {
                continue;
            }
            let mut app = App::new(
                package,
                package,
                meta.get("version").and_then(|value| value.as_str()).unwrap_or(""),
                "npm",
            );
            app.description = format!("Global Node.js package · {prefix}");
            app.manager = manager.to_string_lossy().into_owned();
            app.scope = prefix.clone();
            apps.push(app);
        }
    }
    apps
}

pub fn pipx_inventory() -> Vec<App> {
    let Ok(output) = run(&["pipx", "list", "--json"], 90, true) else {
        return Vec::new();
    };
    let Ok(data) = serde_json::from_str::<serde_json::Value>(&output) else {
        return Vec::new();
    };
    let Some(venvs) = data.get("venvs").and_then(|value| value.as_object()) else {
        return Vec::new();
    };
    venvs
        .iter()
        .map(|(name, value)| {
            let version = value
                .get("metadata")
                .and_then(|meta| meta.get("main_package"))
                .and_then(|pkg| pkg.get("package_version"))
                .and_then(|value| value.as_str())
                .unwrap_or("");
            let mut app = App::new(name, name, version, "pipx");
            app.description = "Python application in an isolated pipx environment".into();
            app
        })
        .collect()
}

pub fn cargo_inventory() -> Vec<App> {
    let Some(manager) = executable("cargo", &[home().join(".cargo/bin/cargo")]) else {
        return Vec::new();
    };
    let Ok(output) = run(
        &[manager.to_string_lossy().as_ref(), "install", "--list"],
        90,
        true,
    ) else {
        return Vec::new();
    };
    let pattern = regex::Regex::new(r"^(\S+) v([^:]+):$").unwrap();
    output
        .lines()
        .filter_map(|line| pattern.captures(line))
        .map(|captures| {
            let mut app = App::new(&captures[1], &captures[1], &captures[2], "Cargo");
            app.description = "Rust application · cargo install".into();
            app.manager = manager.to_string_lossy().into_owned();
            app
        })
        .collect()
}

pub fn snap_inventory() -> Vec<App> {
    let Ok(output) = run(&["snap", "list"], 90, true) else {
        return Vec::new();
    };
    output
        .lines()
        .skip(1)
        .filter_map(|line| {
            let parts: Vec<&str> = line.split_whitespace().collect();
            if parts.len() < 6 {
                return None;
            }
            let notes = parts[parts.len() - 1];
            let mut app = App::new(parts[0], parts[0], parts[1], "Snap");
            app.description = format!("Snap package · {notes}");
            app.icon = "package-x-generic".into();
            app.support = notes.contains("base");
            Some(app)
        })
        .collect()
}

pub fn rpm_inventory() -> Vec<App> {
    let format = "%{NAME}\t%{EPOCHNUM}:%{VERSION}-%{RELEASE}.%{ARCH}\t%{VERSION}-%{RELEASE}\t%{SIZE}\t%{SUMMARY}\t%{NAME}-%{EPOCHNUM}:%{VERSION}-%{RELEASE}.%{ARCH}\n";
    let Ok(output) = run(&["rpm", "-qa", &format!("--qf={format}")], 90, true) else {
        return Vec::new();
    };
    let identity = regex::Regex::new(r"^[A-Za-z0-9][A-Za-z0-9+_.~^:-]*$").unwrap();
    output
        .lines()
        .filter_map(|line| {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 6 || !identity.is_match(parts[5]) {
                return None;
            }
            let mut app = App::new(parts[0], parts[5], parts[1], "RPM");
            app.description = parts[4].into();
            app.icon = "package-x-generic".into();
            app.size = parts[3].parse().unwrap_or(0);
            app.support = looks_like_support(parts[0]);
            app.manager = "/usr/bin/rpm".into();
            app.scope = parts[5].rsplit('.').next().unwrap_or_default().into();
            app.location = parts[0].into();
            Some(app)
        })
        .collect()
}

fn looks_like_support(name: &str) -> bool {
    let critical = ["glibc", "bash", "coreutils", "systemd", "rpm", "pacman", "apk-tools", "dpkg"];
    critical.contains(&name)
        || name.starts_with("lib")
        || ["python3-", "python-", "perl-", "ruby-", "typelib-", "fonts-", "font-", "gstreamer-"]
            .iter()
            .any(|prefix| name.starts_with(prefix))
        || ["-libs", "-common", "-data", "-devel", "-doc", "-lang", "-debuginfo"]
            .iter()
            .any(|suffix| name.ends_with(suffix))
}

fn parse_pacman_desc(text: &str) -> HashMap<String, Vec<String>> {
    let mut fields = HashMap::new();
    let mut current: Option<String> = None;
    for line in text.lines() {
        if line.starts_with('%') && line.ends_with('%') {
            current = Some(line.trim_matches('%').to_string());
            fields.insert(current.clone().unwrap(), Vec::new());
        } else if !line.is_empty() {
            if let Some(field) = &current {
                fields.entry(field.clone()).or_default().push(line.to_string());
            }
        }
    }
    fields
}

pub fn pacman_inventory() -> Vec<App> {
    let database = Path::new("/var/lib/pacman/local");
    let Ok(entries) = fs::read_dir(database) else {
        return Vec::new();
    };
    let mut paths: Vec<PathBuf> = entries
        .filter_map(Result::ok)
        .map(|entry| entry.path().join("desc"))
        .filter(|path| path.is_file())
        .collect();
    paths.sort();
    paths
        .into_iter()
        .filter_map(|path| {
            let fields = parse_pacman_desc(&fs::read_to_string(&path).ok()?);
            let get = |key: &str| {
                fields
                    .get(key)
                    .and_then(|values| values.first())
                    .cloned()
                    .unwrap_or_default()
            };
            let name = get("NAME");
            if name.is_empty() {
                return None;
            }
            let mut app = App::new(&name, &name, &get("VERSION"), "Pacman");
            app.description = get("DESC");
            app.icon = "package-x-generic".into();
            app.size = get("ISIZE").parse().unwrap_or(0);
            app.support = get("REASON") == "1" || looks_like_support(&name);
            app.manager = "/usr/bin/pacman".into();
            app.scope = get("ARCH");
            app.location = path.to_string_lossy().into_owned();
            Some(app)
        })
        .collect()
}

pub fn apk_inventory() -> Vec<App> {
    let explicit: HashSet<String> = fs::read_to_string("/etc/apk/world")
        .unwrap_or_default()
        .lines()
        .filter(|line| !line.is_empty() && !line.starts_with('#'))
        .map(|line| {
            line.split(['<', '>', '=', '~', '@'])
                .next()
                .unwrap_or(line)
                .to_string()
        })
        .collect();
    let Ok(database) = fs::read_to_string("/lib/apk/db/installed") else {
        return Vec::new();
    };
    database
        .split("\n\n")
        .filter_map(|block| {
            let mut fields: HashMap<char, String> = HashMap::new();
            for line in block.lines() {
                let mut chars = line.chars();
                let (Some(key), Some(':')) = (chars.next(), chars.next()) else {
                    continue;
                };
                if "PVTIA".contains(key) {
                    fields.insert(key, chars.collect());
                }
            }
            let name = fields.get(&'P')?.clone();
            let mut app = App::new(&name, &name, fields.get(&'V').map(String::as_str).unwrap_or(""), "APK");
            app.description = fields.get(&'T').cloned().unwrap_or_default();
            app.icon = "package-x-generic".into();
            app.size = fields.get(&'I').and_then(|v| v.parse().ok()).unwrap_or(0);
            app.support = !explicit.contains(&name) || looks_like_support(&name);
            app.manager = "/sbin/apk".into();
            app.scope = fields.get(&'A').cloned().unwrap_or_default();
            Some(app)
        })
        .collect()
}

pub fn manual_inventory(registered: &[App], extra_dirs: &[String]) -> Vec<App> {
    let managed: HashSet<&str> = registered
        .iter()
        .filter(|app| !matches!(app.source.as_str(), "APT" | "RPM" | "Pacman" | "APK"))
        .map(|app| app.package.as_str())
        .collect();
    let known = [
        ("claude", "Claude Code", "@anthropic-ai/claude-code"),
        ("opencode", "OpenCode", "opencode-ai"),
        ("codex", "Codex CLI", "@openai/codex"),
        ("commandcode", "Command Code", "command-code"),
        ("command-code", "Command Code", "command-code"),
    ];
    let mut candidates: Vec<PathBuf> = Vec::new();
    let mut folders = vec![
        home().join(".local/bin"),
        home().join("bin"),
        home().join(".opencode/bin"),
        PathBuf::from("/usr/local/bin"),
    ];
    folders.extend(extra_dirs.iter().map(PathBuf::from));
    for folder in folders {
        let Ok(entries) = fs::read_dir(&folder) else {
            continue;
        };
        for entry in entries.filter_map(Result::ok) {
            let path = entry.path();
            if path.is_file() && is_executable(&path) {
                candidates.push(path);
            }
        }
    }
    for (name, _, _) in known {
        if let Some(path) = crate::model::which(name) {
            candidates.push(path);
        }
    }
    let owned = dpkg_owned(&candidates);
    let mut apps = Vec::new();
    let mut seen = HashSet::new();
    for path in candidates {
        let resolved = path.canonicalize().unwrap_or_else(|_| path.clone());
        if !seen.insert(resolved.clone()) {
            continue;
        }
        let file = path
            .file_name()
            .unwrap_or_default()
            .to_string_lossy()
            .to_string();
        let (title, package) = known
            .iter()
            .find(|(name, _, _)| *name == file)
            .map(|(_, title, package)| (*title, *package))
            .unwrap_or((file.as_str(), file.as_str()));
        if managed.contains(package)
            || resolved.to_string_lossy().contains("node_modules/")
            || resolved.to_string_lossy().contains("/pipx/venvs/")
            || resolved.to_string_lossy().contains("/.cargo/bin/")
        {
            continue;
        }
        if owned.as_ref().map(|set| set.contains(&resolved)).unwrap_or(false) {
            continue;
        }
        let mut paths = vec![path.to_string_lossy().into_owned()];
        let app = App::new(title, package, "—", "Manual");
        let mut app = app;
        app.description = "Unregistered executable. Review its install location before removal.".into();
        app.executable = path.to_string_lossy().into_owned();
        app.scope = if path.starts_with(home()) {
            "User".into()
        } else {
            "System".into()
        };
        if package == "opencode" && resolved.starts_with(home().join(".opencode")) {
            paths = vec![home().join(".opencode").to_string_lossy().into_owned()];
        }
        app.paths = paths;
        if !app.paths.iter().all(|item| crate::model::safe_user_path(Path::new(item))) {
            app.readonly_reason = "This manual executable is in a system location. It is inventory-only; use the official uninstaller.".into();
        }
        apps.push(app);
    }
    apps
}

/// Ask dpkg once whether a batch of executables is already package-managed.
fn dpkg_owned(candidates: &[PathBuf]) -> Option<HashSet<PathBuf>> {
    if crate::model::which("dpkg-query").is_none() || candidates.is_empty() {
        return None;
    }
    let mut arguments: Vec<String> = vec!["/usr/bin/dpkg-query".into(), "-S".into(), "--".into()];
    let mut unique: Vec<String> = Vec::new();
    for path in candidates {
        for value in [path.clone(), path.canonicalize().unwrap_or_else(|_| path.clone())] {
            let text = value.to_string_lossy().into_owned();
            if !text.contains(['*', '?', '[', ']', '\n', '\r']) && !unique.contains(&text) {
                unique.push(text);
            }
        }
    }
    arguments.extend(unique);
    let output = run(&arguments, 90, false).ok()?;
    let mut owned = HashSet::new();
    for line in output.lines() {
        if let Some((_, path)) = line.split_once(": ") {
            owned.insert(PathBuf::from(path));
        }
    }
    Some(owned)
}

fn is_executable(path: &Path) -> bool {
    use std::os::unix::fs::PermissionsExt;
    fs::metadata(path)
        .map(|meta| meta.permissions().mode() & 0o111 != 0)
        .unwrap_or(false)
}

pub struct ScanOptions {
    pub enabled_sources: Vec<String>,
    pub extra_python: Vec<String>,
    pub extra_manual: Vec<String>,
}

pub fn scan(options: &ScanOptions) -> (Vec<App>, Vec<String>) {
    let enabled: HashSet<&str> = options.enabled_sources.iter().map(String::as_str).collect();
    let desktops = desktop_index();
    let mut apps: Vec<App> = Vec::new();
    let mut warnings = Vec::new();
    fn add(apps: &mut Vec<App>, desktops: &DesktopIndex, mut batch: Vec<App>) {
        for app in &mut batch {
            decorate(app, desktops);
        }
        apps.append(&mut batch);
    }

    if enabled.contains("APT") && crate::model::which("dpkg-query").is_some() {
        add(&mut apps, &desktops, apt_inventory());
    }
    if enabled.contains("RPM") && crate::model::which("rpm").is_some() {
        add(&mut apps, &desktops, rpm_inventory());
    }
    if enabled.contains("Pacman") && Path::new("/var/lib/pacman/local").is_dir() {
        add(&mut apps, &desktops, pacman_inventory());
    }
    if enabled.contains("APK") && Path::new("/lib/apk/db/installed").is_file() {
        add(&mut apps, &desktops, apk_inventory());
    }
    if enabled.contains("Flatpak") && crate::model::which("flatpak").is_some() {
        add(&mut apps, &desktops, flatpak_inventory());
    }
    if enabled.contains("npm") {
        add(&mut apps, &desktops, npm_inventory());
    }
    if enabled.contains("Cargo") {
        add(&mut apps, &desktops, cargo_inventory());
    }
    if enabled.contains("Snap") && crate::model::which("snap").is_some() {
        add(&mut apps, &desktops, snap_inventory());
    }
    if enabled.contains("pipx") && crate::model::which("pipx").is_some() {
        add(&mut apps, &desktops, pipx_inventory());
    }
    if enabled.contains("uv") {
        add(&mut apps, &desktops, uv_inventory());
    }
    if enabled.contains("Bun") {
        add(&mut apps, &desktops, bun_inventory());
    }
    if enabled.contains("Homebrew") {
        add(&mut apps, &desktops, brew_inventory());
    }
    if enabled.contains("Steam") {
        add(&mut apps, &desktops, steam::steam_inventory(None));
    }
    if enabled.contains("pip") {
        add(&mut apps, &desktops, pip_inventory(&options.extra_python));
    }
    if enabled.contains("Manual") {
        let manual = manual_inventory(&apps, &options.extra_manual);
        add(&mut apps, &desktops, manual);
    }
    if enabled.contains("ArtCraft") {
        let artcraft = manual::appimage_inventory(&apps);
        add(&mut apps, &desktops, artcraft);
    }
    if enabled.contains("Manual") {
        let launchers = manual::desktop_launcher_inventory(&apps);
        add(&mut apps, &desktops, launchers);
    }
    if enabled.contains("APT")
        && crate::model::which("dpkg-query").is_none()
        && !is_flatpak()
    {
        warnings.push("dpkg-query is not available.".into());
    }
    (apps, warnings)
}
