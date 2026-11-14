// SPDX-FileCopyrightText: 2026 Zwart04
// SPDX-License-Identifier: GPL-3.0-or-later
// SweepDesk: see LICENSE for copying terms and warranty disclaimer.
//! Assert-based self-checks for parsing, migration and path safety.

use crate::catalogue::ID;
use crate::i18n;
use crate::icons;
use crate::manual;
use crate::model::safe_user_path;
use crate::prefs::Preferences;
use crate::steam;
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicUsize, Ordering};

static COUNTER: AtomicUsize = AtomicUsize::new(0);

fn tempdir() -> PathBuf {
    let path = std::env::temp_dir().join(format!(
        "sweepdesk-test-{}-{}",
        std::process::id(),
        COUNTER.fetch_add(1, Ordering::SeqCst)
    ));
    let _ = fs::remove_dir_all(&path);
    fs::create_dir_all(&path).unwrap();
    path
}

fn placeholders(text: &str) -> Vec<String> {
    let pattern = regex::Regex::new(r"\{([a-z_]+)\}").unwrap();
    let mut fields: Vec<String> = pattern
        .captures_iter(text)
        .map(|captures| captures[1].to_string())
        .collect();
    fields.sort();
    fields
}

#[test]
fn catalogue_keeps_every_format_field() {
    for (source, translated) in ID {
        assert_eq!(
            placeholders(source),
            placeholders(translated),
            "placeholder mismatch for {source}"
        );
    }
    assert_eq!(i18n::resolve_language("id"), "id");
    assert_eq!(i18n::resolve_language("en"), "en");
    assert!(matches!(i18n::resolve_language("system").as_str(), "id" | "en"));
    assert!(i18n::language() == "en" || i18n::language() == "id");
}

#[test]
fn unknown_icons_fall_back_to_a_glyph() {
    assert!(matches!(
        icons::cached("__sweepdesk_missing_icon__", icons::Glyph::Application),
        icons::Icon::Svg(_)
    ));
    assert!(matches!(
        icons::cached("__sweepdesk_missing_icon__", icons::Glyph::Terminal),
        icons::Icon::Svg(_)
    ));
}

#[test]
fn version_comparison_is_numeric() {
    use crate::update::newer;
    assert!(newer("0.6.2", "0.6.1"));
    assert!(newer("0.7.0", "0.6.9"));
    assert!(newer("0.6.10", "0.6.9"));
    assert!(newer("1.0", "0.9.9"));
    assert!(!newer("0.6.1", "0.6.1"));
    assert!(!newer("0.6.0", "0.6.1"));
}

#[test]
fn checksum_lookup_reads_sha256sums_lines() {
    use crate::update::checksum_for;
    let text = "aaaa  sweepdesk_0.6.1_amd64.deb\nbbbb  sweepdesk-0.6.1-x86_64.tar.gz\n";
    assert_eq!(
        checksum_for(text, "sweepdesk_0.6.1_amd64.deb"),
        Some("aaaa".into())
    );
    assert_eq!(checksum_for(text, "missing.deb"), None);
}

#[test]
fn preferences_migrate_the_steam_source_once() {
    let mut raw = Preferences::default();
    raw.schema = 1;
    raw.enabled_sources = vec!["APT".into(), "npm".into()];
    let migrated = raw.clone().validate();
    assert!(migrated.enabled_sources.contains(&"Steam".to_string()));
    assert_eq!(
        migrated.enabled_sources,
        vec!["APT", "npm", "Steam"]
            .into_iter()
            .map(str::to_string)
            .collect::<Vec<_>>()
    );
    let mut current = Preferences::default();
    current.enabled_sources = vec!["APT".into()];
    assert_eq!(current.validate().enabled_sources, vec!["APT"]);
    let mut invalid = Preferences::default();
    invalid.theme = "neon".into();
    invalid.density = "dense".into();
    invalid.language = "xx".into();
    invalid.manual_folders = vec!["relative".into(), "/valid".into()];
    let clean = invalid.validate();
    assert_eq!((clean.theme.as_str(), clean.density.as_str()), ("dark", "compact"));
    assert_eq!(clean.language, "system");
    assert_eq!(clean.manual_folders, vec!["/valid"]);
}

#[test]
fn user_paths_reject_traversal_and_system_trees() {
    assert!(!safe_user_path(Path::new("/etc/passwd")));
    assert!(!safe_user_path(Path::new("/usr/bin/env")));
    assert!(!safe_user_path(Path::new("../relative")));
    let home = crate::model::home();
    assert!(!safe_user_path(&home));
    let outside = tempdir();
    assert!(!safe_user_path(&outside));
    let _ = fs::remove_dir_all(outside);
}

#[test]
fn steam_manifests_accept_games_only() {
    let folder = tempdir();
    let manifest = folder.join("appmanifest_12345.acf");
    fs::write(
        &manifest,
        "\"AppState\"\n{\n\t\"appid\"\t\"12345\"\n\t\"name\"\t\"Demo Game\"\n\t\"StateFlags\"\t\"4\"\n\t\"installdir\"\t\"Demo Game\"\n\t\"SizeOnDisk\"\t\"2048\"\n\t\"InstalledDepots\"\n\t{\n\t}\n}\n",
    )
    .unwrap();
    let fields = steam::manifest_fields(&manifest).expect("manifest should parse");
    assert_eq!(fields["appid"], "12345");
    assert!(steam::is_game(&fields));
    let tool = folder.join("appmanifest_1493710.acf");
    fs::write(
        &tool,
        "\"AppState\"\n{\n\t\"appid\"\t\"1493710\"\n\t\"name\"\t\"Proton Experimental\"\n\t\"StateFlags\"\t\"4\"\n\t\"installdir\"\t\"Proton - Experimental\"\n}\n",
    )
    .unwrap();
    let tool_fields = steam::manifest_fields(&tool).unwrap();
    assert!(!steam::is_game(&tool_fields));
    let mismatched = folder.join("appmanifest_999.acf");
    fs::write(&mismatched, "\"AppState\"\n{\n\t\"appid\"\t\"12345\"\n}\n").unwrap();
    assert!(steam::manifest_fields(&mismatched).is_none());
    let _ = fs::remove_dir_all(folder);
}

#[test]
fn artcraft_records_and_launchers_are_read_from_a_fake_home() {
    let home = tempdir();
    let previous = std::env::var("HOME").ok();
    std::env::set_var("HOME", &home);
    std::env::set_var("XDG_DATA_HOME", home.join(".local/share"));

    let bin = home.join(".local/bin");
    fs::create_dir_all(&bin).unwrap();
    let appimage = home.join("GridCraft.AppImage");
    fs::write(&appimage, "fixture").unwrap();
    let launcher = bin.join("demo-launcher");
    fs::write(&launcher, "fixture").unwrap();
    use std::os::unix::fs::PermissionsExt;
    fs::set_permissions(&launcher, fs::Permissions::from_mode(0o755)).unwrap();

    let registry = home.join(".local/share/artcraft-launcher");
    fs::create_dir_all(&registry).unwrap();
    fs::write(
        registry.join("installed.json"),
        serde_json::json!({"apps": {"gridcraft": {"path": appimage, "kind": "AppImage", "version": "1.0", "files": []}}})
            .to_string(),
    )
    .unwrap();

    let applications = home.join(".local/share/applications");
    fs::create_dir_all(&applications).unwrap();
    fs::write(
        applications.join("demo.desktop"),
        format!(
            "[Desktop Entry]\nType=Application\nName=Demo\nExec={}\nIcon=demo\n",
            launcher.display()
        ),
    )
    .unwrap();

    let apps = manual::appimage_inventory(&[]);
    assert_eq!(apps.len(), 1);
    assert_eq!(apps[0].package, "gridcraft");
    assert_eq!(apps[0].source, "ArtCraft");

    let launchers = manual::desktop_launcher_inventory(&apps);
    assert_eq!(launchers.len(), 1);
    assert_eq!(launchers[0].manager, "desktop-launcher");
    assert!(!launchers[0].readonly_reason.is_empty());

    let manual_apps = crate::sources::manual_inventory(&[], &[]);
    assert!(manual_apps.iter().any(|app| app.executable == launcher.to_string_lossy()));

    match previous {
        Some(value) => std::env::set_var("HOME", value),
        None => std::env::remove_var("HOME"),
    }
    std::env::remove_var("XDG_DATA_HOME");
    let _ = fs::remove_dir_all(home);
}
