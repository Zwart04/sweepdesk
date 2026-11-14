# Changelog

## 0.6.4

- Draw the interface with the GPU (`wgpu`) instead of the software rasterizer, and keep the software renderer as an automatic fallback when no usable graphics driver is present. Scrolling the inventory list no longer burns a full CPU core: the same scroll burst costs roughly four times less CPU here even with a software Vulkan driver, and far less on real hardware. The binary grows from 9.8 MB to 12.1 MB.
- Build the inventory rows once per filter change instead of on every frame (`iced`'s lazy widget), so scrolling no longer rebuilds thousands of text widgets.
- Stop rebuilding the window logo image on every frame. The header decoded a 900 kB PNG and re-rasterized a 1013×1013 bitmap for each redraw; it is now decoded once.
- Reuse one handle per fallback icon glyph instead of allocating a new SVG handle per row per frame.

## 0.6.3

- Draw application icons in the right place at fractional display scales (125%, 150%, 175%, 200% on HiDPI screens). The bundled SVG renderer scaled every icon twice and offset it by the scaled position, so logos drifted right and down and overlapped the text. Icons are now rasterized at the physical pixel size and blitted unscaled, which is also cheaper to draw.
- Keep the fix in `rust/vendor/iced_tiny_skia` (patched through `[patch.crates-io]`) until the upstream crates.io release behaves the same.

## 0.6.2

- Update from inside the app. **Check for Updates** asks the GitHub releases API for the newest version, offers to install it, downloads the package that matches your distribution, verifies it against the published `SHA256SUMS`, and installs it through `pkexec` so your package manager stays the source of truth. A **Restart** button relaunches the app when the install finishes.
- Show the update state in a banner: checking, available with the version number, downloading, installing, up to date, and failures with a link to the release page. Nothing is installed unless you press **Install update** and approve the administrator prompt.
- Give the window a proper X11/Wayland application id (`io.github.Zwart04.SweepDesk`) so the taskbar and app switcher match the installed desktop entry and show the SweepDesk logo instead of a generic icon.

## 0.6.1

- Draw real per-application icons in the list and the details panel by resolving freedesktop icon names from the installed themes (SVG and PNG), with a neutral app glyph and a terminal glyph as fallbacks. Icons load in the background after the first scan.
- Redesign the main window: header with brand, search, Refresh, and Settings; 232 px sidebar with live counts per category and source; card-based list and details panels; details pinned **Review Removal** action; fixed footer with the item count.
- Rebuild the settings screen with a scrollable centred form and a fixed Cancel/Save footer, and make Save a primary action instead of a destructive one.
- Style every surface from the theme's extended palette so dark and light themes stay consistent, including the scrollbar rail.
- Localise the remaining strings: scope, refresh, inventory headings, add/remove buttons, plan summary counts, and the footer links.
- Keep the System category count visible even when system packages are hidden from the other views.

## 0.6.0

- Rewrite the application in Rust with the iced toolkit. The release binary is a single ~7 MB executable that links only against glibc, and measured resident memory drops from roughly 118 MB to 24 MB; GTK, PyGObject, and librsvg are no longer runtime dependencies.
- Keep the same inventory sources: APT, RPM, Pacman, APK, Flatpak, npm, pip, pipx, uv, Cargo, Snap, Bun, Homebrew, Steam, ArtCraft, manual installs, and user desktop launchers.
- Keep reviewed removal plans, simulated APT runs, Trash-only handling of user files, path ownership and symlink checks, Steam fingerprint revalidation, Horizon sign-out, ArtCraft registry rewrite, and the Indonesian/English interface.
- Read pip inventories from `*.dist-info` metadata without executing an interpreter.
- Move libraries, release/update, and packaging commands to Cargo and `scripts/build.py`. Packages are now `amd64`, `x86_64`, and `x86_64` instead of `all/noarch/any`.
- Replace the in-app update installer with a **Check for Updates** button that opens the releases page.
- Refresh both preview screenshots from the Rust interface and remove the obsolete update-dialog screenshots.
- Ship the new penguin-in-a-bin artwork across the window icon, desktop entry, hicolor PNG sizes, website, and README.

## 0.5.7

- Detect installed Steam games from `appmanifest_*.acf` files in native, Flatpak, and extra `libraryfolders.vdf` libraries, including games on other user-owned drives.
- Show Steam games with their real names, build IDs, and sizes; skip Proton, Steam Linux Runtime, and Steamworks redistributable manifests.
- Add a reviewed Steam removal plan that moves the game folder and manifest to Trash, with the game's Proton prefix and shader cache as an explicit opt-in.
- Detect manifest-less folders left inside `steamapps/common` so stale game data can be cleaned without touching shared runtimes.
- Block Steam removal while Steam or the selected game is running, and revalidate paths and fingerprints before moving anything.
- Decorate the `steam-launcher` APT package as **Steam** with its own icon and group `steam-libs*` dependencies as support packages.

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
