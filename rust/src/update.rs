// SPDX-FileCopyrightText: 2026 Zwart04
// SPDX-License-Identifier: GPL-3.0-or-later
// SweepDesk: see LICENSE for copying terms and warranty disclaimer.
//! Check GitHub releases, download the package for this distribution, verify it
//! against the published SHA-256 list, and install it through pkexec.

use serde_json::Value;
use std::fs;
use std::io;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::time::Duration;

const LATEST: &str = "https://api.github.com/repos/Zwart04/sweepdesk/releases/latest";
const USER_AGENT: &str = concat!("SweepDesk/", env!("CARGO_PKG_VERSION"));

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Family {
    Deb,
    Dnf,
    Zypper,
    Pacman,
}

impl Family {
    pub fn detect() -> Self {
        let text = fs::read_to_string("/etc/os-release")
            .unwrap_or_default()
            .to_ascii_lowercase();
        if text.contains("suse") {
            Family::Zypper
        } else if text.contains("id=arch")
            || text.contains("manjaro")
            || text.contains("endeavouros")
        {
            Family::Pacman
        } else if text.contains("fedora")
            || text.contains("rhel")
            || text.contains("centos")
            || text.contains("rocky")
            || text.contains("alma")
        {
            Family::Dnf
        } else {
            Family::Deb
        }
    }

    fn suffix(self) -> &'static str {
        match self {
            Family::Deb => "_amd64.deb",
            Family::Dnf => "-1.fedora.x86_64.rpm",
            Family::Zypper => "-1.opensuse.x86_64.rpm",
            Family::Pacman => "-1-x86_64.pkg.tar.zst",
        }
    }
}

#[derive(Debug, Clone)]
pub struct Release {
    pub version: String,
    pub asset: String,
    pub url: String,
    pub sums: String,
}

/// Compare dotted versions numerically, so `0.6.10` is newer than `0.6.9`.
pub fn newer(candidate: &str, current: &str) -> bool {
    let parse = |text: &str| -> Vec<u64> {
        text.split(['.', '-', '+'])
            .map(|part| part.parse::<u64>().unwrap_or(0))
            .collect()
    };
    let (mut left, mut right) = (parse(candidate), parse(current));
    let width = left.len().max(right.len());
    left.resize(width, 0);
    right.resize(width, 0);
    left > right
}

/// Return the newest release when it is newer than the running version.
pub fn check() -> Result<Option<Release>, String> {
    let response = ureq::get(LATEST)
        .set("User-Agent", USER_AGENT)
        .set("Accept", "application/vnd.github+json")
        .timeout(Duration::from_secs(20))
        .call()
        .map_err(|error| error.to_string())?;
    let text = response.into_string().map_err(|error| error.to_string())?;
    let body: Value = serde_json::from_str(&text).map_err(|error| error.to_string())?;
    let version = body["tag_name"]
        .as_str()
        .unwrap_or_default()
        .trim_start_matches('v')
        .to_string();
    if version.is_empty() {
        return Err("release has no tag".into());
    }
    if !newer(&version, crate::VERSION) {
        return Ok(None);
    }
    let assets = body["assets"].as_array().cloned().unwrap_or_default();
    let suffix = Family::detect().suffix();
    let asset = assets
        .iter()
        .find(|asset| {
            asset["name"]
                .as_str()
                .is_some_and(|name| name.ends_with(suffix))
        })
        .ok_or_else(|| format!("release {version} has no {suffix} package"))?;
    let name = asset["name"].as_str().unwrap_or_default().to_string();
    let url = asset["browser_download_url"]
        .as_str()
        .unwrap_or_default()
        .to_string();
    let sums = assets
        .iter()
        .find(|asset| asset["name"].as_str() == Some("SHA256SUMS"))
        .and_then(|asset| asset["browser_download_url"].as_str())
        .unwrap_or_default()
        .to_string();
    if url.is_empty() || sums.is_empty() {
        return Err("release assets are incomplete".into());
    }
    Ok(Some(Release {
        version,
        asset: name,
        url,
        sums,
    }))
}

pub fn checksum_for(text: &str, name: &str) -> Option<String> {
    text.lines().find_map(|line| {
        let mut parts = line.split_whitespace();
        let hash = parts.next()?;
        let file = parts.next()?.trim_start_matches('*');
        (file == name).then(|| hash.to_ascii_lowercase())
    })
}

fn checksum(path: &Path) -> Result<String, String> {
    let output = Command::new("sha256sum")
        .arg(path)
        .output()
        .map_err(|error| format!("sha256sum: {error}"))?;
    if !output.status.success() {
        return Err("sha256sum failed".into());
    }
    Ok(String::from_utf8_lossy(&output.stdout)
        .split_whitespace()
        .next()
        .unwrap_or_default()
        .to_ascii_lowercase())
}

fn get_text(url: &str) -> Result<String, String> {
    ureq::get(url)
        .set("User-Agent", USER_AGENT)
        .timeout(Duration::from_secs(30))
        .call()
        .map_err(|error| error.to_string())?
        .into_string()
        .map_err(|error| error.to_string())
}

/// Download the release package and refuse it unless it matches `SHA256SUMS`.
pub fn download(release: &Release) -> Result<PathBuf, String> {
    let directory = std::env::temp_dir().join(format!("sweepdesk-update-{}", std::process::id()));
    let _ = fs::remove_dir_all(&directory);
    fs::create_dir_all(&directory).map_err(|error| error.to_string())?;
    let sums = get_text(&release.sums)?;
    let expected = checksum_for(&sums, &release.asset)
        .ok_or_else(|| format!("{} is not listed in SHA256SUMS", release.asset))?;
    let path = directory.join(&release.asset);
    let mut reader = ureq::get(&release.url)
        .set("User-Agent", USER_AGENT)
        .timeout(Duration::from_secs(600))
        .call()
        .map_err(|error| error.to_string())?
        .into_reader();
    let mut file = fs::File::create(&path).map_err(|error| error.to_string())?;
    io::copy(&mut reader, &mut file).map_err(|error| error.to_string())?;
    drop(file);
    let actual = checksum(&path)?;
    if actual != expected {
        let _ = fs::remove_dir_all(&directory);
        return Err("downloaded package does not match the published SHA-256".into());
    }
    Ok(path)
}

/// Install a verified package with the distribution's package manager.
pub fn install(path: &Path) -> Result<(), String> {
    let mut command = Command::new("pkexec");
    match Family::detect() {
        Family::Deb => {
            command.args(["apt-get", "install", "-y", "--allow-downgrades"]);
        }
        Family::Dnf => {
            command.args(["dnf", "install", "-y"]);
        }
        Family::Zypper => {
            command.args([
                "zypper",
                "--non-interactive",
                "install",
                "--allow-unsigned-rpm",
            ]);
        }
        Family::Pacman => {
            command.args(["pacman", "-U", "--noconfirm"]);
        }
    }
    command.arg(path);
    let output = command
        .output()
        .map_err(|error| format!("pkexec: {error}"))?;
    if output.status.success() {
        if let Some(directory) = path.parent() {
            let _ = fs::remove_dir_all(directory);
        }
        return Ok(());
    }
    let text = String::from_utf8_lossy(&output.stderr);
    let line = text
        .lines()
        .rev()
        .find(|line| !line.trim().is_empty())
        .unwrap_or("installation failed");
    Err(line.trim().to_string())
}
