# Changelog

## 0.5.2

- Show an animated loading state while scanning, preparing removal previews, and uninstalling; never show the empty-inventory prompt during a scan.
- Place a prominent consent checkbox, instructions, Cancel, and a trash-icon Uninstall button together at the bottom of removal review.
- Simplify support-package cleanup explanations in English and Indonesian without changing the conservative removal scope.
- License original code, application artwork, and documentation under GPL-3.0-or-later. Preserve third-party terms and historical MIT permissions through 0.5.1.

## 0.5.1

- Use fixed system paths for privileged update/native removal commands, independent of user PATH overrides.
- Add regression checks for native updater/remover command selection.

## 0.5.0

- Native RPM, Pacman/ALPM, and APK inventory/removal with protected system components, immutable-system guards, and reviewed/revalidated plans.
- Fedora/openSUSE RPM and Arch packages, plus a checksum-pinned release PKGBUILD and existing DEB/portable distribution.
- Automatic daily-at-startup GitHub release checks, manual Check for Updates, a visible Update Now button, checksum-verified native installation, and restart after success.
- Cross-distro CI builds, installs, and removes only explicit fixtures in disposable Fedora, Rocky, openSUSE, Arch, and Alpine containers.
- Website distribution selector and native download/install commands in English and Indonesian.
- Clearer Indonesian explanations for support-package and data cleanup.
- Handle duplicate lib/lib64 metadata aliases without treating one Python package as overlapping installations.

## 0.4.0

- Keep searching names, package IDs, and descriptions; show descriptions directly beneath names so matches are understandable.
- Distinct success and incomplete removal panels, with application names, clear icons, and retained technical logs.
- English, Bahasa Indonesia, and system-language preferences, applied without restarting or losing the current inventory and Activity.
- Indonesian website with a visible language switch, localized download/copy feedback, and matching UI previews.
- Expanded Indonesian documentation, source coverage, and troubleshooting.

## 0.3.0 — 2026-10-26

- GitHub Pages website with feature previews, current release downloads, install guide, and support links.
- Rebuilt the interface with a compact native toolbar, library/source sidebar, sortable software list, and selection inspector.
- Combined the icon and name into one column, removing the empty icon header.
- Added right-click and keyboard context menus, software details, installed-file lists, copy actions, install-folder links, and session activity.
- Added saved Settings for dark/light/system appearance, compact/comfortable density, system-package visibility, scan sources, and additional folders.
- Refined the support pill and native dialogs, including clear disabled and confirmation states.
- Added a simple app-management logo with subtle lighting; bundled SVG and PNG icons from 16 to 512 pixels, with a matching native application ID for menu/dock integration.
- Added consistent original line icons and official light-background variants for supported CLI logos.
- Expanded interface and preference tests. Package removal safeguards remain enforced.

## 0.2.0 — 2026-10-26

First public SweepDesk release.

- Native GTK interface with a neutral, macOS-inspired dark palette and blue accents.
- Software inventory across APT/DEB, npm global, pip, Cargo, Flatpak, Snap, pipx, uv tools, Bun, Homebrew, ArtCraft AppImages, and known manual executables.
- Filters, search, JSON export, added Python environments, and custom manual installation folders.
- Reviewed uninstall plans, APT core-component protection, conservative APT/pip dependency cleanup, and opt-in cleanup of known user data to Trash.
- Official offline CLI brand artwork for OpenCode, Command Code, curl, and npm.
- Debian package, portable source archive, per-user installer, English/Indonesian guides, and Debian/Ubuntu CI.
- Visible support link to [Zwart04 on Tako](https://tako.id/Zwart04), in the app, README, and GitHub funding configuration.

This release does not promise complete attribution of arbitrary installer scripts. Shared caches and uncertain dependencies are retained. See the README for exact source-specific behavior.
