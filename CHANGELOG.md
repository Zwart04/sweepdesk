# Changelog

## 0.5.6

- Detect the verified Horizon Linux launcher, its standard visible/hidden desktop entries, and matching user hicolor icons; keep other launcher-only apps read-only.
- Add a reviewed Horizon removal plan with install files sent to Trash and user worlds/settings/downloads as an explicit opt-in.
- Sign Horizon accounts out of the system keychain only when data cleanup is selected; block while Horizon processes are running and revalidate the plan before moving files.
- Preserve original Minecraft folders and custom data paths outside the two detected Horizon data folders.

## 0.5.5

- Include installed apps discovered through valid user desktop launchers in the Manual inventory. Launcher commands are parsed as metadata and never executed; launcher-only apps stay read-only because their installation and removal scope cannot be verified.
- Keep desktop launcher apps in the Applications category and document the inventory-only safety behavior.

## 0.5.4

- Keep manual update checks, Update Now, verified installation progress, failure retry, and Restart in one window. No detour to the main-window update button.
- Remove trash icons from removal buttons; keep removal actions red, update actions blue, and unavailable actions subdued. Replace donation hearts/Support labels with original coffee cup artwork and Buy me a coffee / Traktir kopi across the app, README, and website.
- Sort through the native list store before filtering; reuse search text, escaped descriptions, and decoded icons. Batch view updates and coalesce input without the delayed search signal.
- Retain the existing list during refresh and preserve selection when a package is still installed. Density/detail changes no longer rebuild unrelated UI or reload the stylesheet.
- Read independent sources with at most four workers, skip disabled-source discovery, and batch literal Debian manual-file ownership queries. Removal scope and revalidation are unchanged.
- Use cleaner table rows and short native transitions. Add regression checks for the update dialog, native sorting, refresh behavior, parallel scan failure isolation, and ownership exclusions.

## 0.5.3

- Fix the disabled View button by attaching its popover directly to the native menu button.
- Add a visible View label and dropdown arrow; synchronize controls with Settings whenever the menu opens.
- Verify real button activation, working system/detail filters, density changes, and reopening after settings changes.

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
