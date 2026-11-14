// SPDX-FileCopyrightText: 2026 Zwart04
// SPDX-License-Identifier: GPL-3.0-or-later
// SweepDesk: see LICENSE for copying terms and warranty disclaimer.
//! English/Indonesian UI catalogue. Package names and command logs stay intact.

use crate::catalogue::ID;
use std::collections::HashMap;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::OnceLock;

static INDONESIAN: AtomicBool = AtomicBool::new(false);
static TABLE: OnceLock<HashMap<&'static str, &'static str>> = OnceLock::new();

fn table() -> &'static HashMap<&'static str, &'static str> {
    TABLE.get_or_init(|| ID.iter().copied().collect())
}

pub fn resolve_language(value: &str) -> String {
    if matches!(value, "en" | "id") {
        return value.into();
    }
    for name in ["LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"] {
        if let Ok(value) = std::env::var(name) {
            let primary = value
                .split(':')
                .next()
                .unwrap_or("")
                .replace('-', "_")
                .split('_')
                .next()
                .unwrap_or("")
                .to_lowercase();
            return if primary == "id" || primary == "in" {
                "id".into()
            } else {
                "en".into()
            };
        }
    }
    "en".into()
}

pub fn configure(value: &str) {
    INDONESIAN.store(resolve_language(value) == "id", Ordering::Relaxed);
}

pub fn language() -> &'static str {
    if INDONESIAN.load(Ordering::Relaxed) {
        "id"
    } else {
        "en"
    }
}

pub fn tr<'a>(text: &'a str) -> &'a str {
    if language() == "id" {
        table().get(text).copied().unwrap_or(text)
    } else {
        text
    }
}
