// SPDX-FileCopyrightText: 2026 Zwart04
// SPDX-License-Identifier: GPL-3.0-or-later
// SweepDesk: see LICENSE for copying terms and warranty disclaimer.
//! Reviewed removal plans. Every command is revalidated before it runs.

use crate::model::{data_home, fingerprint, home, removable_user_path, run, safe_user_path, App, Plan};
use crate::manual;
use crate::steam;
use std::fs;
use std::path::{Path, PathBuf};

fn xdg(variable: &str, fallback: PathBuf) -> PathBuf {
    match std::env::var(variable) {
        Ok(value) if Path::new(&value).is_absolute() => PathBuf::from(value),
        _ => fallback,
    }
}

pub fn profile_key(app: &App) -> String {
    let value = if app.source == "RPM" {
        app.location.to_lowercase()
    } else {
        app.package.to_lowercase()
    };
    if value.starts_with("libreoffice") {
        return "libreoffice".into();
    }
    match value.as_str() {
        "@anthropic-ai/claude-code" | "claude-code" => "claude".into(),
        "opencode-ai" => "opencode".into(),
        "@openai/codex" => "codex".into(),
        other => other.into(),
    }
}

pub fn data_paths(app: &App) -> Vec<String> {
    let config = xdg("XDG_CONFIG_HOME", home().join(".config"));
    let cache = xdg("XDG_CACHE_HOME", home().join(".cache"));
    let data = data_home();
    let state = xdg("XDG_STATE_HOME", home().join(".local/state"));
    let mut paths: Vec<PathBuf> = Vec::new();
    match (app.source.as_str(), app.manager.as_str()) {
        ("Manual", "horizon-launcher") => {
            paths.push(data.join("horizon-launcher"));
            paths.push(data.join("horizon"));
        }
        ("Steam", "steam-game") => {
            let library = PathBuf::from(&app.location);
            paths.push(library.join("compatdata").join(&app.package));
            paths.push(library.join("shadercache").join(&app.package));
        }
        ("Flatpak", _) if valid_flatpak_id(&app.package) => {
            paths.push(home().join(".var/app").join(&app.package));
        }
        _ => match profile_key(app).as_str() {
            "libreoffice" => {
                paths.push(config.join("libreoffice"));
                paths.push(cache.join("libreoffice"));
            }
            "opencode" => {
                paths.push(config.join("opencode"));
                paths.push(cache.join("opencode"));
                paths.push(data.join("opencode"));
                paths.push(state.join("opencode"));
            }
            "claude" => {
                paths.push(home().join(".claude"));
                paths.push(home().join(".claude.json"));
                paths.push(cache.join("claude"));
            }
            "codex" => paths.push(home().join(".codex")),
            "curl" => paths.push(home().join(".curlrc")),
            _ => {}
        },
    }
    let allowed = |path: &Path| {
        if app.source == "Steam" {
            removable_user_path(path)
        } else {
            safe_user_path(path)
        }
    };
    paths
        .into_iter()
        .filter(|path| (path.exists() || path.is_symlink()) && allowed(path))
        .map(|path| path.to_string_lossy().into_owned())
        .collect()
}

fn valid_flatpak_id(package: &str) -> bool {
    !package.is_empty()
        && package
            .chars()
            .all(|value| value.is_ascii_alphanumeric() || matches!(value, '_' | '.' | '-'))
}

fn valid_name(package: &str) -> bool {
    let (scope, name) = match package.split_once('/') {
        Some((scope, name)) => (Some(scope), name),
        None => (None, package),
    };
    if let Some(scope) = scope {
        if !scope.starts_with('@') || scope.len() < 2 {
            return false;
        }
    }
    !name.is_empty()
        && name
            .chars()
            .next()
            .map(|value| value.is_ascii_alphanumeric() || value == '_')
            .unwrap_or(false)
        && name
            .chars()
            .all(|value| value.is_ascii_alphanumeric() || matches!(value, '_' | '.' | '-'))
}

pub fn make_plan(app: &App, cleanup: bool, dependencies: bool, family: bool) -> Result<Plan, String> {
    let mut plan = Plan {
        app: app.clone(),
        ..Default::default()
    };
    if !app.readonly_reason.is_empty() {
        return Err(app.readonly_reason.clone());
    }
    match app.source.as_str() {
        "APT" => {
            let valid = !app.package.is_empty()
                && app.package.chars().next().unwrap_or('-').is_ascii_alphanumeric();
            if !valid {
                return Err("Invalid APT package name.".into());
            }
            let mut targets = vec![app.package.clone()];
            if family {
                if !app.package.starts_with("libreoffice") {
                    return Err("Suite removal is only available for LibreOffice.".into());
                }
                targets = crate::sources::apt_inventory()
                    .into_iter()
                    .filter(|item| item.package.starts_with("libreoffice"))
                    .map(|item| item.package)
                    .collect();
            }
            let mut args: Vec<String> = vec![
                "/usr/bin/apt-get".into(),
                "-s".into(),
                "purge".into(),
                "--".into(),
            ];
            args.extend(targets.iter().cloned());
            let base = run(&args, 90, true)?;
            plan.removed = apt_plan(&base)?;
            if dependencies {
                let before: std::collections::HashSet<String> = apt_plan(
                    &run(&["/usr/bin/apt-get", "-s", "autoremove"], 90, true)?,
                )?
                .into_iter()
                .collect();
                let mut with_extra = args.clone();
                with_extra.insert(1, "--autoremove".into());
                let after: std::collections::HashSet<String> =
                    apt_plan(&run(&with_extra, 90, true)?)?.into_iter().collect();
                plan.extra = after
                    .difference(&before)
                    .filter(|item| !plan.removed.contains(item))
                    .cloned()
                    .collect();
                plan.extra.sort();
                let mut final_args = args.clone();
                final_args.insert(1, "--autoremove".into());
                final_args.extend(plan.extra.iter().cloned());
                plan.raw = run(&final_args, 90, true)?;
            } else {
                plan.raw = base;
            }
            let mut command = vec![
                "/usr/bin/pkexec".into(),
                "/usr/bin/apt-get".into(),
                "-y".into(),
                "purge".into(),
                "--".into(),
            ];
            command.extend(targets);
            command.extend(plan.extra.iter().cloned());
            plan.commands = vec![command];
            if plan.removed.iter().any(|item| item == "gnome") {
                plan.notes.push("The gnome metapackage will also be removed. It groups desktop applications; gnome-shell and the core desktop are not in this plan.".into());
            }
            if dependencies {
                plan.notes.push("Also clean up support packages used by this app, if no other apps need them.".into());
            }
        }
        "Flatpak" => {
            if !valid_flatpak_id(&app.package) || !matches!(app.scope.as_str(), "user" | "system") {
                return Err("Invalid Flatpak identity.".into());
            }
            plan.commands = vec![vec![
                "flatpak".into(),
                format!("--{}", app.scope),
                "uninstall".into(),
                "-y".into(),
                "--app".into(),
                app.package.clone(),
            ]];
            plan.removed = vec![app.package.clone()];
            plan.notes.push("Flatpak calculates related extensions at execution time. Shared runtimes are retained; no global runtime cleanup is performed.".into());
        }
        "npm" => {
            if !valid_name(&app.package) {
                return Err("Invalid npm package name.".into());
            }
            if !Path::new(&app.scope).starts_with(home()) {
                return Err("This npm global prefix is outside your home folder. Manage this system-wide installation using its package manager or a terminal.".into());
            }
            plan.commands = vec![vec![
                app.manager.clone(),
                "uninstall".into(),
                "-g".into(),
                "--prefix".into(),
                app.scope.clone(),
                "--ignore-scripts".into(),
                "--".into(),
                app.package.clone(),
            ]];
            plan.removed = vec![app.package.clone()];
            plan.notes.push("npm manages this package and its dependencies. Lifecycle scripts are disabled during removal.".into());
        }
        "pip" => {
            if !valid_name(&app.package) || app.package.contains('/') {
                return Err("Invalid Python distribution name.".into());
            }
            let metadata = Path::new(&app.location);
            if !metadata.is_dir() || !metadata.join("METADATA").is_file() {
                return Err("Python distribution is missing or has overlapping installations. Refresh and resolve it in its environment.".into());
            }
            plan.removed = vec![app.package.clone()];
            plan.commands = vec![
                vec![
                    app.manager.clone(),
                    "-m".into(),
                    "pip".into(),
                    "uninstall".into(),
                    "-y".into(),
                    "--".into(),
                    app.package.clone(),
                ],
            ];
            plan.fingerprint = metadata.to_string_lossy().into_owned();
            plan.notes.push("pip removes files recorded by the distribution. Legacy/unrecorded files and shared download caches may remain.".into());
        }
        "Bun" => {
            if !valid_name(&app.package) {
                return Err("Invalid Bun package name.".into());
            }
            if !Path::new(&app.scope).starts_with(home()) {
                return Err("This Bun global installation is outside your home folder.".into());
            }
            plan.removed = vec![app.package.clone()];
            plan.commands = vec![vec![
                app.manager.clone(),
                "remove".into(),
                "--global".into(),
                "--ignore-scripts".into(),
                "--".into(),
                app.package.clone(),
            ]];
            plan.notes.push("Bun manages its dependency graph. Shared package caches are retained.".into());
        }
        "Homebrew" => {
            if !valid_name(&app.package) || app.package.contains("..") {
                return Err("Invalid Homebrew formula name.".into());
            }
            plan.removed = vec![app.package.clone()];
            plan.commands = vec![vec![
                app.manager.clone(),
                "uninstall".into(),
                "--formula".into(),
                app.package.clone(),
            ]];
            plan.notes.push("Homebrew refuses removal if other formulae still depend on this package. No --ignore-dependencies or global cache cleanup is used.".into());
        }
        "pipx" | "Cargo" | "Snap" | "uv" => {
            if !valid_name(&app.package) {
                return Err("Invalid package name.".into());
            }
            let command = match app.source.as_str() {
                "pipx" => vec!["pipx".into(), "uninstall".into(), app.package.clone()],
                "uv" => vec![app.manager.clone(), "tool".into(), "uninstall".into(), app.package.clone()],
                "Cargo" => vec![app.manager.clone(), "uninstall".into(), app.package.clone()],
                _ => {
                    plan.notes.push("Snap manages package data and automatic snapshots according to its policy. --purge is not used; existing snapshots are retained.".into());
                    vec![
                        "/usr/bin/pkexec".into(),
                        "/usr/bin/snap".into(),
                        "remove".into(),
                        app.package.clone(),
                    ]
                }
            };
            plan.commands = vec![command];
            plan.removed = vec![app.package.clone()];
        }
        "Steam" if app.manager == "steam-game" => {
            let expected = steam::game_paths(app);
            if expected.is_empty()
                || expected != app.paths
                || !expected.iter().all(|path| removable_user_path(Path::new(path)))
            {
                return Err("Steam game files changed or are outside a safe user folder. Refresh the inventory and try again.".into());
            }
            plan.fingerprint = fingerprint(&expected)?;
            plan.files = expected;
            plan.removed = vec![app.name.clone()];
            plan.notes.push("The Steam game folder and its app manifest will be moved to Trash. Steam will no longer list this game.".into());
        }
        "Steam" if app.manager == "steam-leftover" => {
            let expected = steam::leftover_paths(app);
            if expected.is_empty()
                || expected != app.paths
                || !expected.iter().all(|path| removable_user_path(Path::new(path)))
            {
                return Err("Steam library folder changed or is outside a safe user folder. Refresh the inventory and try again.".into());
            }
            plan.fingerprint = fingerprint(&expected)?;
            plan.files = expected;
            plan.removed = vec![app.name.clone()];
            plan.notes.push("This folder sits in the Steam library but has no app manifest. It will be moved to Trash; Steam does not list it as an installed game.".into());
        }
        "Manual" if app.manager == "horizon-launcher" => {
            let expected = manual::horizon_install_paths(&app.executable);
            if expected.is_empty()
                || expected != app.paths
                || !expected.iter().all(|path| safe_user_path(Path::new(path)))
            {
                return Err("Horizon launcher files changed or are outside a safe user folder. Refresh the inventory and try again.".into());
            }
            plan.fingerprint = manual::horizon_fingerprint(&expected, &app.executable)?;
            plan.files = expected;
            plan.removed = vec!["Horizon launcher".into()];
            plan.notes.push("Only the detected Horizon launcher, its menu shortcuts and user icons will be moved to Trash. Original Minecraft folders are kept.".into());
        }
        "ArtCraft" => {
            let expected = manual::artcraft_paths(app);
            if expected.is_empty() || !expected.iter().all(|path| safe_user_path(Path::new(path))) {
                return Err("The ArtCraft installation record changed. Refresh the inventory and try again.".into());
            }
            plan.files = expected;
            plan.removed = vec![app.name.clone()];
            plan.notes.push("The ArtCraft installation record will also be updated after its files are moved to Trash.".into());
        }
        "Manual" => {
            if app.paths.is_empty()
                || !app.paths.iter().all(|path| safe_user_path(Path::new(path)))
            {
                return Err("This manual executable is in a system location or a location that cannot be cleaned automatically. It is inventory-only; use the official uninstaller.".into());
            }
            plan.files = app.paths.clone();
            plan.removed = vec![app.name.clone()];
            plan.notes.push("Manual installation: only the listed paths will be moved to Trash. PATH edits, services and other installer-created files may not be detected.".into());
        }
        _ => return Err("Removal is not supported for this source yet.".into()),
    }
    if cleanup {
        if profile_key(app) == "libreoffice" && !family {
            return Err("LibreOffice settings are shared. Select the entire suite before cleaning its user data.".into());
        }
        plan.data = data_paths(app);
        plan.cleanup_requested = true;
        if app.manager == "horizon-launcher" && !plan.data.is_empty() {
            plan.notes.push("The listed Horizon folders include downloaded game files, versions, settings, worlds, servers and logs. Horizon accounts are signed out from the system keychain first; original Minecraft folders and custom data homes outside this list are kept.".into());
        } else if app.manager == "steam-game" && !plan.data.is_empty() {
            plan.notes.push("The listed Proton prefix and shader cache belong to this game. Steam Cloud saves, shared runtimes and other games are not changed.".into());
        } else if !plan.data.is_empty() {
            plan.notes.push("Selected data will be moved to Trash, including any history, sign-ins, profiles and settings inside the listed folders.".into());
        } else {
            plan.notes.push("No known user-data locations were found for this package. Complete cleanup cannot be guaranteed.".into());
        }
    }
    Ok(plan)
}

fn apt_plan(output: &str) -> Result<Vec<String>, String> {
    // `apt-get -s purge` prints "Purg", a plain remove prints "Remv".
    let pattern = regex::Regex::new(r"^(?:Remv|Purg) (\S+)").unwrap();
    let removed: Vec<String> = output
        .lines()
        .filter_map(|line| pattern.captures(line))
        .map(|captures| captures[1].split(':').next().unwrap_or("").to_string())
        .filter(|name| !name.is_empty())
        .collect();
    if removed.is_empty() && !output.contains("0 upgraded") {
        return Err("APT did not return a usable removal plan.".into());
    }
    Ok(removed)
}

fn move_to_trash(path: &Path) -> Result<(), String> {
    trash::delete(path).map_err(|error| format!("{}: {error}", path.display()))
}

/// Prefix of the progress line emitted per Trashed path. The UI counts these to
/// show how far the Trash move got.
pub const TRASH_PREFIX: &str = "Moving to Trash: ";

pub fn execute(plan: &Plan, emit: &mut dyn FnMut(&str)) -> Result<(), String> {
    let app = &plan.app;
    if app.manager == "horizon-launcher" {
        let expected = manual::horizon_install_paths(&app.executable);
        let expected_data = if plan.cleanup_requested {
            data_paths(app)
        } else {
            Vec::new()
        };
        if !plan.commands.is_empty()
            || expected != plan.files
            || plan.data != expected_data
            || !plan
                .files
                .iter()
                .chain(plan.data.iter())
                .all(|path| safe_user_path(Path::new(path)))
            || manual::horizon_fingerprint(&plan.files, &app.executable)? != plan.fingerprint
        {
            return Err("Horizon files changed after the preview. Create a new removal plan.".into());
        }
        if manual::horizon_process_running(app, &plan.data) {
            return Err("Close Horizon, the Horizon game and Horizon servers before removing their files.".into());
        }
        if plan.cleanup_requested {
            manual::sign_out_accounts(app, emit)?;
        }
    }
    if app.source == "Steam" && matches!(app.manager.as_str(), "steam-game" | "steam-leftover") {
        let expected = if app.manager == "steam-game" {
            steam::game_paths(app)
        } else {
            steam::leftover_paths(app)
        };
        let expected_data = if plan.cleanup_requested {
            data_paths(app)
        } else {
            Vec::new()
        };
        if !plan.commands.is_empty()
            || expected != plan.files
            || plan.data != expected_data
            || !plan
                .files
                .iter()
                .chain(plan.data.iter())
                .all(|path| removable_user_path(Path::new(path)))
            || fingerprint(&plan.files)? != plan.fingerprint
        {
            return Err("Steam files changed after the preview. Create a new removal plan.".into());
        }
        if steam::process_running(app) {
            return Err("Close Steam and this game before removing their files.".into());
        }
    }
    if app.source == "APT" && !plan.commands.is_empty() {
        let args = &plan.commands[0];
        let index = args.iter().position(|value| value == "--").unwrap_or(0);
        let mut sim = vec!["/usr/bin/apt-get".to_string(), "-s".to_string(), "purge".to_string(), "--".to_string()];
        sim.extend(args[index + 1..].iter().cloned());
        let actual = apt_plan(&run(&sim, 90, true)?)?;
        let expected: std::collections::HashSet<&String> =
            plan.removed.iter().chain(plan.extra.iter()).collect();
        if actual.iter().collect::<std::collections::HashSet<&String>>() != expected {
            return Err("Package state changed after the preview. Create a new plan before removal.".into());
        }
    }
    for command in &plan.commands {
        emit(&format!("$ {}\n", command.join(" ")));
        let output = run(command, 900, true)?;
        if !output.trim().is_empty() {
            emit(&output);
            if !output.ends_with('\n') {
                emit("\n");
            }
        }
    }
    for path in plan.files.iter().chain(plan.data.iter()) {
        let item = Path::new(path);
        let allowed = if app.source == "Steam" {
            removable_user_path(item)
        } else {
            safe_user_path(item)
        };
        if !allowed {
            return Err(format!("Path changed or is not safe to clean: {path}"));
        }
        emit(&format!("{TRASH_PREFIX}{path}\n"));
        move_to_trash(item)?;
    }
    if app.source == "ArtCraft" && !plan.files.is_empty() {
        manual::forget_artcraft(app)?;
    }
    Ok(())
}

pub fn describe(plan: &Plan) -> String {
    let mut lines = Vec::new();
    lines.push(format!("{} · {} · {}", plan.app.name, plan.app.package, plan.app.source));
    if !plan.commands.is_empty() {
        lines.push(String::new());
        lines.push("Commands:".into());
        for command in &plan.commands {
            lines.push(format!("  {}", command.join(" ")));
        }
    }
    let mut section = |title: &str, items: &[String]| {
        if items.is_empty() {
            return;
        }
        lines.push(String::new());
        lines.push(format!("{title}:"));
        for item in items {
            lines.push(format!("  {item}"));
        }
    };
    section("Packages to remove", &plan.removed);
    section("Additional dependencies", &plan.extra);
    section("Files moved to Trash", &plan.files);
    section("User data moved to Trash", &plan.data);
    if !plan.notes.is_empty() {
        lines.push(String::new());
        for note in &plan.notes {
            lines.push(format!("• {note}"));
        }
    }
    if !plan.raw.trim().is_empty() {
        lines.push(String::new());
        lines.push("Simulated output:".into());
        lines.push(plan.raw.clone());
    }
    let _ = fs::metadata(home());
    lines.join("\n")
}

#[cfg(test)]
mod plan_tests {
    use super::apt_plan;

    #[test]
    fn purge_output_lists_the_targets() {
        let output = "The following packages will be REMOVED:\n  7zip* file-roller*\n0 upgraded, 0 newly installed, 2 to remove.\nPurg file-roller [44.5-1]\nPurg 7zip [25.01+dfsg-1~deb13u2]\n";
        assert_eq!(apt_plan(output).unwrap(), vec!["file-roller", "7zip"]);
    }

    #[test]
    fn remove_output_still_parses() {
        assert_eq!(apt_plan("Remv qbittorrent [1.0]\n").unwrap(), vec!["qbittorrent"]);
    }
}
