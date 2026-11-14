// SPDX-FileCopyrightText: 2026 Zwart04
// SPDX-License-Identifier: GPL-3.0-or-later
// SweepDesk: see LICENSE for copying terms and warranty disclaimer.
//! SweepDesk 0.6.5 — native software inventory and reviewed uninstall.

mod catalogue;
mod i18n;
mod icons;
mod manual;
mod model;
mod plan;
mod prefs;
mod sources;
mod steam;
mod update;

#[cfg(test)]
mod tests;

use i18n::tr;
use iced::widget::{
    lazy,
    button, checkbox, column, container, horizontal_space, image, row, scrollable, svg, text,
    text_input, vertical_space, Column,
};
use iced::futures::{SinkExt, StreamExt};
use iced::{
    Alignment, Border, Color, ContentFit, Element, Length, Padding, Shadow, Task, Theme,
};
use model::App;
use model::Plan;
use prefs::Preferences;
use std::rc::Rc;

const VERSION: &str = "0.6.5";
const LOGO: &[u8] = include_bytes!("../../assets/sweepdesk.png");
const SUPPORT_URL: &str = "https://tako.id/Zwart04";
const RELEASE_URL: &str = "https://github.com/Zwart04/sweepdesk/releases/latest";

#[derive(Debug, Clone, Copy, PartialEq)]
enum Category {
    All,
    Applications,
    CommandLine,
    System,
}

impl Category {
    fn label(self) -> &'static str {
        match self {
            Category::All => tr("All Software"),
            Category::Applications => tr("Applications"),
            Category::CommandLine => tr("Command Line"),
            Category::System => tr("System Packages"),
        }
    }
}

#[derive(Debug, Clone)]
enum Message {
    Loaded(Vec<App>, Vec<String>),
    SearchChanged(String),
    ToggleSystem(bool),
    CategoryChanged(Category),
    SourceChanged(Option<String>),
    Select(usize),
    RequestRemoval,
    CleanupToggled(bool),
    AcknowledgedToggled(bool),
    Confirmed,
    CancelPlan,
    Finished(Result<String, String>),
    PlanReady(Box<Plan>),
    Rescan,
    OpenSupport,
    OpenReleases,
    OpenSettings,
    CloseSettings,
    SaveSettings,
    SetLanguage(String),
    SetTheme(String),
    ToggleScanOnStart(bool),
    ToggleSource(String, bool),
    PythonInput(String),
    ManualInput(String),
    AddPythonFolder,
    AddManualFolder,
    RemoveFolder(bool, String),
    DismissMessage,
    IconsReady,
    CheckUpdates,
    UpdateChecked(Result<Option<update::Release>, String>),
    InstallUpdate,
    UpdateDownloaded(Result<std::path::PathBuf, String>),
    UpdateInstalled(Result<(), String>),
    DismissUpdate,
    Restart,
    Progress(String),
    Tick,
    ToggleLog,
    DismissOutcome,
}

#[derive(Debug, Clone, PartialEq)]
enum UpdatePhase {
    Checking,
    Available,
    Downloading,
    Installing,
    Done,
    UpToDate,
    Failed(String),
}

/// Result of a finished removal, kept on screen until dismissed so the user is
/// not dropped back into the list without knowing what happened.
#[derive(Debug, Clone)]
struct Outcome {
    ok: bool,
    log: String,
}

impl Outcome {
    fn summary(&self) -> String {
        self.log
            .lines()
            .map(str::trim)
            .find(|line| !line.is_empty())
            .unwrap_or("")
            .to_string()
    }
}

/// One inventory row, materialized once per filter change so the list widget
/// can be built lazily instead of rebuilding thousands of rows every frame.
#[derive(Debug, Clone)]
struct Row {
    index: usize,
    name: String,
    subtitle: String,
    size: String,
    icon: String,
    cli: bool,
}

struct SweepDesk {
    prefs: Preferences,
    apps: Vec<App>,
    rows: Rc<Vec<Row>>,
    search: String,
    category: Category,
    source: Option<String>,
    selected: Option<usize>,
    busy: bool,
    warning: Vec<String>,
    plan: Option<Plan>,
    plan_text: String,
    cleanup: bool,
    acknowledged: bool,
    previewing: bool,
    removal: bool,
    progress: Vec<String>,
    show_log: bool,
    tick: u64,
    outcome: Option<Outcome>,
    message: Option<String>,
    error: Option<String>,
    settings: bool,
    draft: Option<Preferences>,
    python_input: String,
    manual_input: String,
    update: Option<UpdatePhase>,
    release: Option<update::Release>,
}

fn source_list(apps: &[App]) -> Vec<(String, usize)> {
    let mut counts: Vec<(String, usize)> = model::SOURCES
        .iter()
        .map(|source| (source.to_string(), 0usize))
        .collect();
    for app in apps {
        if let Some(entry) = counts.iter_mut().find(|(source, _)| *source == app.source) {
            entry.1 += 1;
        }
    }
    counts
}

fn is_cli(app: &App) -> bool {
    if app.source == "Steam"
        || (app.source == "Manual" && app.manager == "desktop-launcher")
        || app.icon == "applications-games"
    {
        return false;
    }
    matches!(
        app.source.as_str(),
        "npm" | "pip" | "Cargo" | "pipx" | "uv" | "Bun" | "Homebrew" | "Manual"
    ) || app.icon.contains("utilities-terminal")
        || matches!(app.source.as_str(), "RPM" | "Pacman" | "APK")
            && app.icon == "package-x-generic"
}

fn size_label(size: u64) -> String {
    if size == 0 {
        return String::new();
    }
    let mut value = size as f64;
    for unit in ["B", "KB", "MB", "GB"] {
        if value < 1024.0 || unit == "GB" {
            return if value >= 10.0 || unit == "B" {
                format!("{value:.0} {unit}")
            } else {
                format!("{value:.1} {unit}")
            };
        }
        value /= 1024.0;
    }
    String::new()
}

impl SweepDesk {
    fn refilter(&mut self) {
        let query = self.search.trim().to_lowercase();
        self.rows = Rc::new(
        self
            .apps
            .iter()
            .enumerate()
            .filter(|(_, app)| {
                if app.support && !self.prefs.show_system && self.category != Category::System {
                    return false;
                }
                match self.category {
                    Category::All => {}
                    Category::Applications if is_cli(app) => return false,
                    Category::CommandLine if !is_cli(app) => return false,
                    Category::System if !app.support => return false,
                    _ => {}
                }
                if let Some(source) = &self.source {
                    if &app.source != source {
                        return false;
                    }
                }
                if query.is_empty() {
                    return true;
                }
                let haystack = format!(
                    "{} {} {} {}",
                    app.name.to_lowercase(),
                    app.package.to_lowercase(),
                    app.source.to_lowercase(),
                    app.description.to_lowercase()
                );
                haystack.contains(&query)
            })
            .map(|(index, app)| Row {
                index,
                name: app.name.clone(),
                subtitle: format!("{} · {}", app.package, app.source),
                size: size_label(app.size),
                icon: app.icon.clone(),
                cli: is_cli(app),
            })
            .collect(),
        );
    }

    fn selected_app(&self) -> Option<&App> {
        self.selected.and_then(|index| self.apps.get(index))
    }

    fn can_remove(&self, app: &App) -> bool {
        !self.busy && !app.essential && app.readonly_reason.is_empty()
    }

    fn category_count(&self, category: Category) -> usize {
        self.apps
            .iter()
            .filter(|app| {
                if app.support && !self.prefs.show_system && category != Category::System {
                    return false;
                }
                match category {
                    Category::All => true,
                    Category::Applications => !is_cli(app),
                    Category::CommandLine => is_cli(app),
                    Category::System => app.support,
                }
            })
            .count()
    }

    fn sidebar(&self) -> Element<'_, Message> {
        let mut list = Column::new().spacing(2).padding(10);
        for category in [
            Category::All,
            Category::Applications,
            Category::CommandLine,
            Category::System,
        ] {
            list = list.push(nav_row(
                category.label().to_string(),
                self.category_count(category),
                self.category == category,
                Message::CategoryChanged(category),
            ));
        }
        list = list.push(vertical_space().height(14));
        list = list.push(
            text(tr("SOURCES"))
                .size(10)
                .style(muted),
        );
        list = list.push(nav_row(
            tr("All Software").to_string(),
            self.apps.len(),
            self.source.is_none(),
            Message::SourceChanged(None),
        ));
        for (source, count) in source_list(&self.apps) {
            if count == 0 && !self.prefs.show_empty_sources {
                continue;
            }
            let active = self.source.as_deref() == Some(source.as_str());
            list = list.push(nav_row(
                source.clone(),
                count,
                active,
                Message::SourceChanged(Some(source)),
            ));
        }
        list = list.push(vertical_space().height(14));
        list = list.push(
            checkbox(tr("Show system packages"), self.prefs.show_system)
                .on_toggle(Message::ToggleSystem)
                .size(15)
                .text_size(11),
        );
        container(scrollable(list).style(scroll_style))
            .width(Length::Fixed(232.0))
            .height(Length::Fill)
            .into()
    }

    fn list(&self) -> Element<'_, Message> {
        if self.apps.is_empty() {
            return container(text(tr("Scanning installed software…")).size(13).style(muted))
                .padding(24)
                .into();
        }
        if self.rows.is_empty() {
            return container(text(tr("Try another search or choose a different source.")).size(13).style(muted))
                .padding(24)
                .into();
        }
        let rows = Rc::clone(&self.rows);
        let selected = self.selected;
        let list = lazy(
            (rows.len(), selected, icons::version()),
            move |_| rows_view(Rc::clone(&rows), selected),
        );
        scrollable(list)
            .height(Length::Fill)
            .style(scroll_style)
            .into()
    }

    fn details(&self) -> Element<'_, Message> {
        let Some(app) = self.selected_app() else {
            return container(text(tr("Select an item to see its details.")).size(12).style(muted))
                .padding(18)
                .width(Length::Fill)
                .height(Length::Fill)
                .center_y(Length::Fill)
                .into();
        };
        let mut card = Column::new().spacing(12).padding(18);
        card = card.push(
            row![
                app_icon(app, 54.0),
                column![
                    text(&app.name).size(17),
                    text(if app.description.is_empty() {
                        tr("Installed software")
                    } else {
                        &app.description
                    })
                    .size(11)
                    .style(muted),
                ]
                .spacing(3)
                .width(Length::Fill),
            ]
            .spacing(12)
            .align_y(Alignment::Center),
        );
        card = card.push(container(text("")).width(Length::Fill).height(1).style(divider));
        for (label, value) in [
            (tr("Version"), app.version.clone()),
            (tr("Source"), app.source.clone()),
            (tr("Size"), size_label(app.size)),
            ("ID", app.package.clone()),
            (tr("Scope"), app.scope.clone()),
        ] {
            if value.is_empty() {
                continue;
            }
            card = card.push(
                row![
                    text(label).size(11).width(Length::Fixed(76.0)).style(muted),
                    text(value).size(12).width(Length::Fill),
                ]
                .spacing(6),
            );
        }
        if !app.readonly_reason.is_empty() {
            card = card.push(
                container(text(&app.readonly_reason).size(11))
                    .padding(10)
                    .width(Length::Fill)
                    .style(warn_box),
            );
        }
        card = card.push(vertical_space());
        card = card.push(
            button(text(tr("Review Removal")).size(13))
                .on_press_maybe(self.can_remove(app).then_some(Message::RequestRemoval))
                .width(Length::Fill)
                .padding([9, 14])
                .style(danger_button),
        );
        container(card)
            .width(Length::Fill)
            .height(Length::Fill)
            .into()
    }

    /// Shown right after "Review removal" is pressed, so the click never looks
    /// like it was ignored while the package list is being read.
    fn preparing_view(&self) -> Element<'_, Message> {
        let content = column![
            text(tr("Preparing a removal preview…")).size(16),
            self.activity_bar(),
            text(tr(
                "Reading installed packages and known data locations. Nothing is changed yet."
            ))
            .size(12)
            .style(muted),
        ]
        .spacing(12);

        container(
            container(content)
                .padding(20)
                .width(Length::Fill)
                .max_width(560.0)
                .style(card),
        )
        .width(Length::Fill)
        .height(Length::Fill)
        .center_x(Length::Fill)
        .center_y(Length::Fill)
        .into()
    }

    fn review_view(&self, plan: &Plan) -> Element<'_, Message> {
        let app = &plan.app;
        let mut body = Column::new().spacing(14).padding(22);
        body = body.push(text(tr("Remove {name}").replace("{name}", &app.name)).size(20));
        body = body.push(text(format!("{} · {}", app.package, app.source)).size(12).style(muted));

        let mut steps = Column::new().spacing(7);
        if !plan.removed.is_empty() {
            steps = steps.push(text(tr("These packages will be removed:")).size(12));
            steps = steps.push(text(preview_list(&plan.removed)).size(12).style(muted));
        }
        if !plan.extra.is_empty() {
            steps = steps.push(
                text(
                    tr("{count} extra dependencies will be removed too")
                        .replace("{count}", &plan.extra.len().to_string()),
                )
                .size(12)
                .style(muted),
            );
        }
        let trash = plan.files.len() + plan.data.len();
        if trash > 0 {
            steps = steps.push(
                text(
                    tr("{count} files and folders are moved to Trash, not deleted permanently.")
                        .replace("{count}", &trash.to_string()),
                )
                .size(12)
                .style(muted),
            );
        } else if self.cleanup {
            steps = steps.push(
                text(tr("No known user data was found for this app, so only the installed files are removed."))
                    .size(12)
                    .style(muted),
            );
        }
        body = body.push(
            container(column![text(tr("What will happen")).size(13), steps].spacing(8))
                .padding(14)
                .width(Length::Fill)
                .style(card),
        );

        let needs_admin = plan
            .commands
            .iter()
            .flatten()
            .any(|argument| argument.contains("pkexec"));
        if needs_admin {
            body = body.push(
                container(
                    text(tr(
                        "Administrator permission is required. Enter your password in the system window that opens. Nothing changes until you press the button below."
                    ))
                    .size(12),
                )
                .padding(12)
                .width(Length::Fill)
                .style(warn_box),
            );
        }

        body = body.push(
            container(
                column![
                    checkbox(tr("Also move known user data to Trash"), self.cleanup)
                        .on_toggle(Message::CleanupToggled)
                        .size(16)
                        .text_size(12),
                    checkbox(
                        tr("I have checked the list and agree to remove these items"),
                        self.acknowledged,
                    )
                    .on_toggle(Message::AcknowledgedToggled)
                    .size(16)
                    .text_size(12),
                ]
                .spacing(8),
            )
            .padding(14)
            .width(Length::Fill)
            .style(card),
        );
        if self.previewing {
            body = body.push(
                column![
                    self.activity_bar(),
                    text(tr("Updating the preview…")).size(11).style(muted),
                ]
                .spacing(6),
            );
        }
        body = body.push(
            text(tr(
                "Packages can be reinstalled later. Files moved to Trash can be restored from there."
            ))
            .size(11)
            .style(muted),
        );

        body = body.push(
            button(
                text(if self.show_log {
                    tr("Hide technical details")
                } else {
                    tr("Technical details (commands and raw output)")
                })
                .size(11),
            )
            .on_press(Message::ToggleLog)
            .padding([4, 10])
            .style(ghost_button),
        );
        if self.show_log {
            body = body.push(
                container(
                    scrollable(text(plan_details(plan, &self.plan_text)).size(10).font(iced::Font::MONOSPACE))
                        .height(Length::Fixed(200.0)),
                )
                .padding(10)
                .width(Length::Fill)
                .style(code_box),
            );
        }

        let can_confirm = self.acknowledged && !self.previewing;
        body = body.push(
            row![
                button(text(tr("Cancel")).size(13))
                    .on_press(Message::CancelPlan)
                    .padding([8, 16])
                    .style(ghost_button),
                horizontal_space(),
                button(text(tr("Remove")).size(13))
                    .on_press_maybe(can_confirm.then_some(Message::Confirmed))
                    .padding([8, 16])
                    .style(danger_button),
            ]
            .spacing(8),
        );
        container(scrollable(
            container(container(body).max_width(760.0))
                .center_x(Length::Fill)
                .width(Length::Fill),
        ))
        .width(Length::Fill)
        .height(Length::Fill)
        .style(panel)
        .into()
    }

    fn running_view(&self) -> Element<'_, Message> {
        let name = self
            .plan
            .as_ref()
            .map(|plan| plan.app.name.clone())
            .unwrap_or_default();
        let (phase, hint) = self.removal_phase();
        let mut body = column![
            text(tr("Uninstalling {name}…").replace("{name}", &name)).size(18),
            self.activity_bar(),
            text(phase).size(12),
            text(hint).size(11).style(muted),
            text(tr(
                "Keep this window open until the removal finishes. This usually takes a few seconds."
            ))
            .size(11)
            .style(muted),
        ]
        .spacing(10);

        let tail = self.tail(8);
        if !tail.is_empty() {
            body = body.push(text(tr("Live output")).size(11).style(muted));
            body = body.push(
                container(text(tail).size(10).font(iced::Font::MONOSPACE))
                    .padding(10)
                    .width(Length::Fill)
                    .style(code_box),
            );
        }
        body = body.push(self.log_toggle());
        if self.show_log {
            body = body.push(self.log_box(240.0));
        }
        container(container(body).padding(22).max_width(760.0))
            .width(Length::Fill)
            .height(Length::Fill)
            .center_x(Length::Fill)
            .style(panel)
            .into()
    }

    fn outcome_view<'a>(&'a self, outcome: &'a Outcome) -> Element<'a, Message> {
        let name = self
            .plan
            .as_ref()
            .map(|plan| plan.app.name.clone())
            .unwrap_or_default();
        let mut body = Column::new().spacing(12).padding(22);
        if outcome.ok {
            body = body.push(text(tr("Removal finished.")).size(18).style(success));
            body = body.push(
                text(tr("{name} is no longer on this computer.").replace("{name}", &name))
                    .size(12)
                    .style(muted),
            );
        } else {
            body = body.push(text(tr("Removal failed")).size(18).style(warn));
            body = body.push(text(outcome.summary()).size(12));
            body = body.push(
                text(tr("Nothing else was changed. Close this message to try again."))
                    .size(11)
                    .style(muted),
            );
        }
        body = body.push(self.log_toggle());
        if self.show_log {
            body = body.push(
                container(
                    scrollable(text(&outcome.log).size(10).font(iced::Font::MONOSPACE))
                        .height(Length::Fixed(260.0)),
                )
                .padding(10)
                .width(Length::Fill)
                .style(code_box),
            );
        }
        body = body.push(
            row![
                horizontal_space(),
                button(text(tr("Close")).size(13))
                    .on_press(Message::DismissOutcome)
                    .padding([8, 16])
                    .style(primary_button),
            ]
            .align_y(Alignment::Center),
        );
        container(container(body).max_width(760.0).center_x(Length::Fill))
            .width(Length::Fill)
            .height(Length::Fill)
            .style(panel)
            .into()
    }

    fn plan_view(&self) -> Element<'_, Message> {
        if let Some(outcome) = &self.outcome {
            return self.outcome_view(outcome);
        }
        if self.removal {
            return self.running_view();
        }
        match &self.plan {
            Some(plan) => self.review_view(plan),
            None => self.preparing_view(),
        }
    }

    /// An indeterminate bar. It exists so every wait has something visibly
    /// moving; it carries no real percentage on purpose.
    fn activity_bar(&self) -> Element<'_, Message> {
        const SLOTS: u64 = 48;
        const CHUNK: u64 = 7;
        let cycle = SLOTS - CHUNK;
        let step = self.tick % (cycle * 2);
        let head = if step <= cycle { step } else { cycle * 2 - step };
        let tail = SLOTS - head - CHUNK;
        container(
            row![
                horizontal_space().width(Length::FillPortion(head.max(1) as u16)),
                container(horizontal_space())
                    .height(Length::Fixed(5.0))
                    .width(Length::FillPortion(CHUNK as u16))
                    .style(activity_chunk),
                horizontal_space().width(Length::FillPortion(tail.max(1) as u16)),
            ]
            .height(Length::Fixed(5.0)),
        )
        .width(Length::Fill)
        .height(Length::Fixed(5.0))
        .style(activity_track)
        .into()
    }

    fn removal_phase(&self) -> (String, String) {
        let (trash_expected, needs_admin) = match &self.plan {
            Some(plan) => (
                plan.files.len() + plan.data.len(),
                plan.commands
                    .iter()
                    .flatten()
                    .any(|argument| argument.contains("pkexec")),
            ),
            None => (0, false),
        };
        let moved = self
            .progress
            .iter()
            .filter(|line| line.starts_with(plan::TRASH_PREFIX))
            .count();
        if moved > 0 {
            return (
                tr("Moving files to Trash ({done} of {total})…")
                    .replace("{done}", &moved.to_string())
                    .replace("{total}", &trash_expected.max(moved).to_string()),
                tr("Your files and folders stay recoverable from the Trash.").into(),
            );
        }
        if needs_admin && !self.progress.iter().any(|line| line.starts_with("$ ")) {
            return (
                tr("Waiting for administrator permission…").into(),
                tr("If a password window appears, enter your administrator password there.").into(),
            );
        }
        (
            tr("Removing packages…").into(),
            tr("This can take a moment. The text below updates while it works.").into(),
        )
    }

    fn log_text(&self) -> String {
        self.progress.join("")
    }

    /// The last few lines only, so the newest activity is always on screen.
    fn tail(&self, limit: usize) -> String {
        let mut lines: Vec<String> = Vec::new();
        for chunk in &self.progress {
            for line in chunk.lines() {
                let line = line.trim_end();
                if line.is_empty() {
                    continue;
                }
                let short: String = line.chars().take(160).collect();
                if short.chars().count() < line.chars().count() {
                    lines.push(format!("{short}…"));
                } else {
                    lines.push(short);
                }
            }
        }
        let start = lines.len().saturating_sub(limit);
        lines[start..].join("\n")
    }

    fn log_toggle(&self) -> Element<'_, Message> {
        button(
            text(if self.show_log {
                tr("Hide log")
            } else {
                tr("Show log")
            })
            .size(11),
        )
        .on_press(Message::ToggleLog)
        .padding([4, 10])
        .style(ghost_button)
        .into()
    }

    fn log_box(&self, height: f32) -> Element<'_, Message> {
        container(
            scrollable(text(self.log_text()).size(10).font(iced::Font::MONOSPACE))
                .height(Length::Fixed(height)),
        )
        .padding(10)
        .width(Length::Fill)
        .style(code_box)
        .into()
    }

    fn settings_view(&self) -> Element<'_, Message> {
        let Some(draft) = &self.draft else {
            return container(text("")).into();
        };
        let mut body = Column::new().spacing(10).padding(20);
        body = body.push(text(tr("Settings")).size(20));
        body = body.push(text(tr("Language")).size(12).style(muted));
        body = body.push(
            row![
                self.language_button(draft, "system", tr("System")),
                self.language_button(draft, "en", "English"),
                self.language_button(draft, "id", "Indonesia"),
            ]
            .spacing(6),
        );
        body = body.push(text(tr("Appearance")).size(12).style(muted));
        body = body.push(
            row![
                self.theme_button(draft, "dark", tr("Dark")),
                self.theme_button(draft, "light", tr("Light")),
                self.theme_button(draft, "system", tr("System")),
            ]
            .spacing(6),
        );
        body = body.push(text(tr("Inventory")).size(12).style(muted));
        body = body.push(
            checkbox(tr("Show system packages"), draft.show_system)
                .on_toggle(Message::ToggleSystem)
                .size(16)
                .text_size(12),
        );
        body = body.push(
            checkbox(tr("Scan when SweepDesk opens"), draft.scan_on_start)
                .on_toggle(Message::ToggleScanOnStart)
                .size(16)
                .text_size(12),
        );
        let mut source_columns = row![].spacing(18);
        let half = model::SOURCES.len().div_ceil(2);
        for chunk in model::SOURCES.chunks(half) {
            let mut source_column = Column::new().spacing(2).width(Length::Fill);
            for source in chunk {
                let source = *source;
                source_column = source_column.push(
                    checkbox(source, draft.enabled_sources.iter().any(|item| item == source))
                        .on_toggle(move |value| Message::ToggleSource(source.to_string(), value))
                        .size(15)
                        .text_size(11),
                );
            }
            source_columns = source_columns.push(source_column);
        }
        body = body.push(text(tr("Sources")).size(12).style(muted));
        body = body.push(container(source_columns).padding(10).width(Length::Fill).max_width(680.0).style(card));
        body = body.push(text(tr("Extra Python folders")).size(12).style(muted));
        body = body.push(
            row![
                text_input(tr("Folder path"), &self.python_input)
                    .on_input(Message::PythonInput)
                    .width(Length::Fixed(420.0))
                    .padding([7, 10])
                    .size(12),
                button(text(tr("Add")).size(12))
                    .on_press(Message::AddPythonFolder)
                    .padding([7, 12])
                    .style(ghost_button),
            ]
            .spacing(6),
        );
        for folder in &draft.python_folders {
            body = body.push(self.folder_row(folder, true));
        }
        body = body.push(text(tr("Extra manual folders")).size(12).style(muted));
        body = body.push(
            row![
                text_input(tr("Folder path"), &self.manual_input)
                    .on_input(Message::ManualInput)
                    .width(Length::Fixed(420.0))
                    .padding([7, 10])
                    .size(12),
                button(text(tr("Add")).size(12))
                    .on_press(Message::AddManualFolder)
                    .padding([7, 12])
                    .style(ghost_button),
            ]
            .spacing(6),
        );
        for folder in &draft.manual_folders {
            body = body.push(self.folder_row(folder, false));
        }
        let footer = row![
            button(text(tr("Cancel")).size(13))
                .on_press(Message::CloseSettings)
                .padding([8, 18])
                .style(ghost_button),
            horizontal_space(),
            button(text(tr("Save")).size(13))
                .on_press(Message::SaveSettings)
                .padding([8, 18])
                .style(primary_button),
        ]
        .spacing(8)
        .padding([12, 24]);

        container(
            column![
                container(scrollable(container(body).max_width(760.0).center_x(Length::Fill)).style(scroll_style))
                    .height(Length::Fill)
                    .width(Length::Fill)
                    .padding([8, 24]),
                container(footer).width(Length::Fill).style(header_bar),
            ]
            .height(Length::Fill),
        )
        .width(Length::Fill)
        .height(Length::Fill)
        .style(panel)
        .into()
    }

    fn language_button<'a>(&self, draft: &Preferences, value: &'static str, label: &'a str) -> iced::widget::Button<'a, Message> {
        let active = draft.language == value;
        button(text(label).size(12))
            .on_press(Message::SetLanguage(value.into()))
            .padding([7, 12])
            .style(move |theme, status| nav_style(theme, status, active))
    }

    fn theme_button<'a>(&self, draft: &Preferences, value: &'static str, label: &'a str) -> iced::widget::Button<'a, Message> {
        let active = draft.theme == value;
        button(text(label).size(12))
            .on_press(Message::SetTheme(value.into()))
            .padding([7, 12])
            .style(move |theme, status| nav_style(theme, status, active))
    }

    fn folder_row(&self, folder: &str, python: bool) -> Element<'_, Message> {
        let value = folder.to_string();
        row![
            text(value.clone()).size(11).width(Length::Fill),
            button(text("×").size(13))
                .on_press(Message::RemoveFolder(python, value))
                .padding([0, 6]),
        ]
        .align_y(Alignment::Center)
        .into()
    }

    fn view(&self) -> Element<'_, Message> {
        let brand = row![
            image(logo())
                .width(Length::Fixed(26.0))
                .height(Length::Fixed(26.0))
                .content_fit(ContentFit::Contain),
            column![
                text("SweepDesk").size(16),
                text(tr("Your software, in one place.")).size(10).style(muted),
            ]
            .spacing(0),
        ]
        .spacing(9)
        .align_y(Alignment::Center);

        let header = row![
            brand,
            horizontal_space(),
            text_input(tr("Search software…"), &self.search)
                .on_input(Message::SearchChanged)
                .width(Length::Fixed(280.0))
                .padding([7, 10])
                .size(12),
            ghost(
                if self.busy && self.plan.is_none() && !self.previewing {
                    tr("Scanning…")
                } else {
                    tr("Refresh")
                },
                Message::Rescan,
            ),
            ghost(tr("Settings"), Message::OpenSettings),
        ]
        .spacing(8)
        .align_y(Alignment::Center)
        .padding([10, 18]);

        let body: Element<'_, Message> = if self.settings {
            self.settings_view()
        } else if self.previewing || self.plan.is_some() {
            self.plan_view()
        } else {
            row![
                self.sidebar(),
                container(self.list())
                    .width(Length::Fill)
                    .height(Length::Fill)
                    .padding([6, 4])
                    .style(card),
                container(self.details())
                    .width(Length::Fixed(320.0))
                    .height(Length::Fill)
                    .padding([6, 4])
                    .style(card),
            ]
            .spacing(10)
            .padding(Padding { top: 10.0, right: 12.0, bottom: 0.0, left: 12.0 })
            .height(Length::Fill)
            .into()
        };

        let mut layout = Column::new().push(
            container(header)
                .width(Length::Fill)
                .style(header_bar),
        );
        if let Some(banner) = self.update_banner() {
            layout = layout.push(banner);
        }
        if self.busy && self.plan.is_none() && !self.previewing {
            layout = layout.push(
                container(text(tr("Scanning installed software…")).size(11).style(muted))
                    .padding([6, 18])
                    .width(Length::Fill),
            );
        }
        for warning in &self.warning {
            layout = layout.push(
                container(text(warning).size(11).style(warn))
                    .padding([4, 18])
                    .width(Length::Fill),
            );
        }
        if let Some(error) = &self.error {
            layout = layout.push(
                container(
                    row![
                        text(error).size(11).style(warn).width(Length::Fill),
                        button(text("×").size(13))
                            .on_press(Message::DismissMessage)
                            .padding([0, 6]),
                    ]
                    .align_y(Alignment::Center),
                )
                .padding([6, 18])
                .width(Length::Fill),
            );
        }
        if let Some(message) = &self.message {
            layout = layout.push(
                container(
                    row![
                        text(message).size(11).width(Length::Fill),
                        button(text("×").size(13))
                            .on_press(Message::DismissMessage)
                            .padding([0, 6]),
                    ]
                    .align_y(Alignment::Center),
                )
                .padding([6, 18])
                .width(Length::Fill),
            );
        }
        layout = layout.push(body);
        layout = layout.push(
            container(
                row![
                    text(format!(
                        "{} {} · {}",
                        tr("Version"),
                        VERSION,
                        tr("Made by Zwart04")
                    ))
                    .size(10)
                    .style(muted),
                    horizontal_space(),
                    button(text(tr("Check for Updates")).size(10))
                        .on_press(Message::CheckUpdates)
                        .padding([3, 8])
                        .style(ghost_button),
                    button(text(tr("Buy me a coffee")).size(10))
                        .on_press(Message::OpenSupport)
                        .padding([3, 8])
                        .style(ghost_button),
                    text(items_label(self.rows.len())).size(10).style(muted),
                ]
                .spacing(10)
                .align_y(Alignment::Center)
                .padding([6, 18]),
            )
            .width(Length::Fill)
            .style(panel),
        );
        container(layout)
            .width(Length::Fill)
            .height(Length::Fill)
            .into()
    }

    fn update_banner(&self) -> Option<Element<'_, Message>> {
        let phase = self.update.as_ref()?;
        let version = self
            .release
            .as_ref()
            .map(|release| release.version.clone())
            .unwrap_or_default();
        let body: Element<'_, Message> = match phase {
            UpdatePhase::Checking => row![text(tr("Checking for updates…")).size(11)]
                .align_y(Alignment::Center)
                .into(),
            UpdatePhase::Available => row![
                text(
                    tr("SweepDesk {version} is available.")
                        .replace("{version}", &version)
                )
                .size(11)
                .width(Length::Fill),
                button(text(tr("Install update")).size(11))
                    .on_press(Message::InstallUpdate)
                    .padding([5, 12])
                    .style(primary_button),
                button(text(tr("Later")).size(11))
                    .on_press(Message::DismissUpdate)
                    .padding([5, 12])
                    .style(ghost_button),
            ]
            .spacing(8)
            .align_y(Alignment::Center)
            .into(),
            UpdatePhase::Downloading => row![text(tr("Downloading update…")).size(11)]
                .align_y(Alignment::Center)
                .into(),
            UpdatePhase::Installing => row![text(tr("Installing update…")).size(11)]
                .align_y(Alignment::Center)
                .into(),
            UpdatePhase::Done => row![
                text(
                    tr("SweepDesk {version} installed. Restart to finish.")
                        .replace("{version}", &version)
                )
                .size(11)
                .width(Length::Fill),
                button(text(tr("Restart")).size(11))
                    .on_press(Message::Restart)
                    .padding([5, 12])
                    .style(primary_button),
            ]
            .spacing(8)
            .align_y(Alignment::Center)
            .into(),
            UpdatePhase::UpToDate => row![
                text(tr("SweepDesk is up to date.")).size(11).width(Length::Fill),
                button(text(tr("Dismiss")).size(11))
                    .on_press(Message::DismissUpdate)
                    .padding([5, 12])
                    .style(ghost_button),
            ]
            .spacing(8)
            .align_y(Alignment::Center)
            .into(),
            UpdatePhase::Failed(error) => row![
                text(format!("{}: {}", tr("Update failed"), error))
                    .size(11)
                    .width(Length::Fill),
                button(text(tr("Open release page")).size(11))
                    .on_press(Message::OpenReleases)
                    .padding([5, 12])
                    .style(ghost_button),
                button(text(tr("Dismiss")).size(11))
                    .on_press(Message::DismissUpdate)
                    .padding([5, 12])
                    .style(ghost_button),
            ]
            .spacing(8)
            .align_y(Alignment::Center)
            .into(),
        };
        let style = if matches!(phase, UpdatePhase::Failed(_)) {
            warn_box
        } else {
            panel
        };
        Some(
            container(body)
                .padding([7, 18])
                .width(Length::Fill)
                .style(style)
                .into(),
        )
    }

    fn update(&mut self, message: Message) -> Task<Message> {
        match message {
            Message::Loaded(apps, warnings) => {
                self.apps = apps;
                self.warning = warnings;
                self.busy = false;
                self.refilter();
                if let Some(index) = self.selected {
                    if index >= self.apps.len() {
                        self.selected = None;
                    }
                }
                let names = icon_names(&self.apps);
                Task::perform(
                    async move { icons::preload(names) },
                    |_| Message::IconsReady,
                )
            }
            Message::IconsReady => Task::none(),
            Message::ToggleSystem(value) => {
                if let Some(draft) = self.draft.as_mut() {
                    draft.show_system = value;
                    return Task::none();
                }
                self.prefs.show_system = value;
                let _ = prefs::save(&self.prefs);
                self.refilter();
                Task::none()
            }
            Message::SearchChanged(value) => {
                self.search = value;
                self.refilter();
                Task::none()
            }
            Message::CategoryChanged(category) => {
                self.category = category;
                self.refilter();
                Task::none()
            }
            Message::SourceChanged(source) => {
                self.source = source;
                self.refilter();
                Task::none()
            }
            Message::Select(index) => {
                self.selected = Some(index);
                Task::none()
            }
            Message::RequestRemoval => {
                let Some(app) = self.selected_app().cloned() else {
                    return Task::none();
                };
                self.busy = true;
                self.error = None;
                self.previewing = true;
                self.outcome = None;
                self.progress.clear();
                self.show_log = false;
                Task::perform(
                    async move { plan::make_plan(&app, false, false, false) },
                    |result| match result {
                        Ok(plan) => Message::PlanReady(Box::new(plan)),
                        Err(error) => Message::Finished(Err(error)),
                    },
                )
            }
            Message::CleanupToggled(value) => {
                self.cleanup = value;
                self.rebuild_plan()
            }
            Message::AcknowledgedToggled(value) => {
                self.acknowledged = value;
                Task::none()
            }
            Message::Confirmed => {
                let Some(plan) = self.plan.clone() else {
                    return Task::none();
                };
                self.busy = true;
                self.removal = true;
                self.progress.clear();
                self.outcome = None;
                self.show_log = false;
                self.tick = 0;
                Task::stream(execute_stream(plan))
            }
            Message::Progress(line) => {
                self.progress.push(line);
                if self.progress.len() > 80 {
                    self.progress.drain(..20);
                }
                Task::none()
            }
            Message::Tick => {
                self.tick = self.tick.wrapping_add(1);
                Task::none()
            }
            Message::ToggleLog => {
                self.show_log = !self.show_log;
                Task::none()
            }
            Message::DismissOutcome => {
                self.outcome = None;
                self.plan = None;
                self.plan_text.clear();
                self.progress.clear();
                self.removal = false;
                self.previewing = false;
                Task::none()
            }
            Message::CancelPlan => {
                self.plan = None;
                self.plan_text.clear();
                self.cleanup = false;
                self.acknowledged = false;
                self.busy = false;
                self.previewing = false;
                self.removal = false;
                self.progress.clear();
                self.show_log = false;
                self.outcome = None;
                Task::none()
            }
            Message::Finished(result) => {
                self.busy = false;
                self.previewing = false;
                match result {
                    Ok(log) => {
                        let log = if log.trim().is_empty() {
                            self.log_text()
                        } else {
                            log
                        };
                        self.removal = false;
                        self.cleanup = false;
                        self.acknowledged = false;
                        self.show_log = false;
                        self.outcome = Some(Outcome { ok: true, log });
                        self.selected = None;
                        self.scan()
                    }
                    Err(error) => {
                        if self.removal {
                            self.removal = false;
                            self.show_log = false;
                            self.outcome = Some(Outcome {
                                ok: false,
                                log: error,
                            });
                            Task::none()
                        } else {
                            self.error = Some(error);
                            Task::none()
                        }
                    }
                }
            }
            Message::PlanReady(plan) => {
                self.busy = false;
                self.previewing = false;
                self.plan_text = plan::describe(&plan);
                self.plan = Some(*plan);
                self.acknowledged = false;
                Task::none()
            }
            Message::Rescan => self.scan(),
            Message::CheckUpdates => {
                self.update = Some(UpdatePhase::Checking);
                self.release = None;
                Task::perform(async { update::check() }, Message::UpdateChecked)
            }
            Message::UpdateChecked(result) => {
                match result {
                    Ok(Some(release)) => {
                        self.release = Some(release);
                        self.update = Some(UpdatePhase::Available);
                    }
                    Ok(None) => {
                        self.release = None;
                        self.update = Some(UpdatePhase::UpToDate);
                    }
                    Err(error) => {
                        self.release = None;
                        self.update = Some(UpdatePhase::Failed(error));
                    }
                }
                Task::none()
            }
            Message::InstallUpdate => {
                let Some(release) = self.release.clone() else {
                    return Task::none();
                };
                self.update = Some(UpdatePhase::Downloading);
                Task::perform(
                    async move { update::download(&release) },
                    Message::UpdateDownloaded,
                )
            }
            Message::UpdateDownloaded(result) => match result {
                Ok(path) => {
                    self.update = Some(UpdatePhase::Installing);
                    Task::perform(
                        async move { update::install(&path) },
                        Message::UpdateInstalled,
                    )
                }
                Err(error) => {
                    self.update = Some(UpdatePhase::Failed(error));
                    Task::none()
                }
            },
            Message::UpdateInstalled(result) => {
                self.update = Some(match result {
                    Ok(()) => UpdatePhase::Done,
                    Err(error) => UpdatePhase::Failed(error),
                });
                Task::none()
            }
            Message::DismissUpdate => {
                self.update = None;
                self.release = None;
                Task::none()
            }
            Message::Restart => {
                if let Ok(executable) = std::env::current_exe() {
                    let _ = std::process::Command::new(executable).spawn();
                }
                std::process::exit(0);
            }
            Message::OpenReleases => {
                let _ = std::process::Command::new("xdg-open").arg(RELEASE_URL).spawn();
                Task::none()
            }
            Message::OpenSettings => {
                self.draft = Some(self.prefs.clone());
                self.settings = true;
                self.python_input.clear();
                self.manual_input.clear();
                Task::none()
            }
            Message::CloseSettings => {
                self.settings = false;
                self.draft = None;
                Task::none()
            }
            Message::SaveSettings => {
                if let Some(draft) = self.draft.take() {
                    self.prefs = draft.validate();
                    let _ = prefs::save(&self.prefs);
                    i18n::configure(&self.prefs.language);
                    self.settings = false;
                    self.refilter();
                }
                Task::none()
            }
            Message::SetLanguage(value) => {
                if let Some(draft) = self.draft.as_mut() {
                    draft.language = value.clone();
                    i18n::configure(&value);
                }
                Task::none()
            }
            Message::SetTheme(value) => {
                if let Some(draft) = self.draft.as_mut() {
                    draft.theme = value;
                }
                Task::none()
            }
            Message::ToggleScanOnStart(value) => {
                if let Some(draft) = self.draft.as_mut() {
                    draft.scan_on_start = value;
                }
                Task::none()
            }
            Message::ToggleSource(source, value) => {
                if let Some(draft) = self.draft.as_mut() {
                    if value {
                        if !draft.enabled_sources.contains(&source) {
                            draft.enabled_sources.push(source);
                        }
                    } else {
                        draft.enabled_sources.retain(|item| item != &source);
                    }
                }
                Task::none()
            }
            Message::PythonInput(value) => {
                self.python_input = value;
                Task::none()
            }
            Message::ManualInput(value) => {
                self.manual_input = value;
                Task::none()
            }
            Message::AddPythonFolder => {
                let value = self.python_input.trim().to_string();
                if value.starts_with('/') {
                    if let Some(draft) = self.draft.as_mut() {
                        if !draft.python_folders.contains(&value) {
                            draft.python_folders.push(value);
                        }
                    }
                    self.python_input.clear();
                }
                Task::none()
            }
            Message::AddManualFolder => {
                let value = self.manual_input.trim().to_string();
                if value.starts_with('/') {
                    if let Some(draft) = self.draft.as_mut() {
                        if !draft.manual_folders.contains(&value) {
                            draft.manual_folders.push(value);
                        }
                    }
                    self.manual_input.clear();
                }
                Task::none()
            }
            Message::RemoveFolder(python, value) => {
                if let Some(draft) = self.draft.as_mut() {
                    let list = if python { &mut draft.python_folders } else { &mut draft.manual_folders };
                    list.retain(|item| item != &value);
                }
                Task::none()
            }
            Message::OpenSupport => {
                let _ = std::process::Command::new("xdg-open")
                    .arg(SUPPORT_URL)
                    .spawn();
                Task::none()
            }
            Message::DismissMessage => {
                self.error = None;
                self.message = None;
                Task::none()
            }
        }
    }

    fn rebuild_plan(&mut self) -> Task<Message> {
        let Some(app) = self.selected_app().cloned() else {
            return Task::none();
        };
        let cleanup = self.cleanup;
        self.busy = true;
        self.previewing = true;
        Task::perform(
            async move { plan::make_plan(&app, cleanup, false, false) },
            |result| match result {
                Ok(plan) => Message::PlanReady(Box::new(plan)),
                Err(error) => Message::Finished(Err(error)),
            },
        )
    }

    fn scan(&mut self) -> Task<Message> {
        self.busy = true;
        let options = sources::ScanOptions {
            enabled_sources: self.prefs.enabled_sources.clone(),
            extra_python: self.prefs.python_folders.clone(),
            extra_manual: self.prefs.manual_folders.clone(),
        };
        Task::perform(
            async move { sources::scan(&options) },
            |(apps, warnings)| Message::Loaded(apps, warnings),
        )
    }
}

/// Builds the whole inventory list. Only runs when the filter, the selection,
/// or the icon cache change; scrolling reuses the cached widget tree.
fn rows_view(rows: Rc<Vec<Row>>, selected: Option<usize>) -> Element<'static, Message> {
    let mut list = Column::new().spacing(2).padding(Padding { right: 8.0, ..Padding::ZERO });
    for row in rows.iter() {
        let active = selected == Some(row.index);
        let body = row![
            row_icon(row, 26.0),
            column![
                text(row.name.clone()).size(13),
                text(row.subtitle.clone()).size(11).style(muted),
            ]
            .spacing(2)
            .width(Length::Fill),
            text(row.size.clone()).size(11).style(muted),
        ]
        .align_y(Alignment::Center)
        .spacing(10);
        let index = row.index;
        list = list.push(
            button(body)
                .on_press(Message::Select(index))
                .width(Length::Fill)
                .padding([6, 10])
                .style(move |theme, status| row_style(theme, status, active)),
        );
    }
    list.into()
}

fn row_icon(row: &Row, size: f32) -> Element<'static, Message> {
    icon_element(&row.icon, row.cli, size)
}

fn app_icon(app: &App, size: f32) -> Element<'static, Message> {
    icon_element(&app.icon, is_cli(app), size)
}

fn icon_element(name: &str, cli: bool, size: f32) -> Element<'static, Message> {
    let kind = if cli {
        icons::Glyph::Terminal
    } else {
        icons::Glyph::Application
    };
    match icons::cached(name, kind) {
        icons::Icon::Svg(handle) => svg(handle)
            .width(Length::Fixed(size))
            .height(Length::Fixed(size))
            .content_fit(ContentFit::Contain)
            .into(),
        icons::Icon::Raster(handle) => image(handle)
            .width(Length::Fixed(size))
            .height(Length::Fixed(size))
            .content_fit(ContentFit::Contain)
            .into(),
    }
}

/// The window logo is decoded once; rebuilding the handle each frame re-read a
/// 900 kB PNG and re-rasterized a 1013×1013 image on every redraw.
fn logo() -> image::Handle {
    static HANDLE: std::sync::OnceLock<image::Handle> = std::sync::OnceLock::new();
    HANDLE
        .get_or_init(|| image::Handle::from_bytes(LOGO.to_vec()))
        .clone()
}

/// Runs the removal off the UI thread and forwards every output line, so the
/// running screen animates and shows progress instead of appearing to hang on
/// the administrator prompt or the Trash moves.
fn execute_stream(plan: Plan) -> impl iced::futures::Stream<Item = Message> {
    iced::stream::channel(
        64,
        move |mut sender: iced::futures::channel::mpsc::Sender<Message>| async move {
            let (tx, mut rx) = iced::futures::channel::mpsc::unbounded::<Message>();
            std::thread::spawn(move || {
                let result = plan::execute(&plan, &mut |line| {
                    let _ = tx.unbounded_send(Message::Progress(line.to_string()));
                });
                let message = match result {
                    Ok(()) => Message::Finished(Ok(String::new())),
                    Err(error) => Message::Finished(Err(error)),
                };
                let _ = tx.unbounded_send(message);
            });
            while let Some(message) = rx.next().await {
                if sender.send(message).await.is_err() {
                    break;
                }
            }
        },
    )
}

/// Raw plan text plus the planner's notes, shown only behind the technical
/// details toggle.
fn plan_details(plan: &Plan, text: &str) -> String {
    let mut body = text.to_string();
    for note in &plan.notes {
        body.push_str("\n• ");
        body.push_str(note);
    }
    body
}

/// First few names, so the review never turns into a wall of package names.
fn preview_list(items: &[String]) -> String {
    const LIMIT: usize = 8;
    let joined = items
        .iter()
        .take(LIMIT)
        .cloned()
        .collect::<Vec<String>>()
        .join(", ");
    let extra = items.len().saturating_sub(LIMIT);
    if extra == 0 {
        joined
    } else {
        format!(
            "{joined}, {}",
            tr("and {count} more").replace("{count}", &extra.to_string())
        )
    }
}

fn items_label(count: usize) -> String {
    tr("{count} items").replace("{count}", &count.to_string())
}

fn icon_names(apps: &[App]) -> Vec<String> {
    let mut names: Vec<String> = Vec::new();
    for app in apps {
        if !app.icon.is_empty() && !names.contains(&app.icon) {
            names.push(app.icon.clone());
        }
    }
    names
}

fn nav_row<'a>(
    label: String,
    count: usize,
    active: bool,
    message: Message,
) -> Element<'a, Message> {
    button(
        row![
            text(label).size(12).width(Length::Fill),
            text(count.to_string()).size(11).width(Length::Shrink).style(muted),
        ]
        .spacing(8)
        .align_y(Alignment::Center),
    )
    .on_press(message)
    .width(Length::Fill)
    .padding([7, 10])
    .style(move |theme, status| nav_style(theme, status, active))
    .into()
}

fn ghost<'a>(label: &'a str, message: Message) -> Element<'a, Message> {
    button(text(label).size(12))
        .on_press(message)
        .padding([7, 12])
        .style(ghost_button)
        .into()
}

fn main() -> iced::Result {
    let prefs = prefs::load();
    if std::env::args().any(|arg| arg == "--scan") {
        let started = std::time::Instant::now();
        let options = sources::ScanOptions {
            enabled_sources: prefs.enabled_sources.clone(),
            extra_python: prefs.python_folders.clone(),
            extra_manual: prefs.manual_folders.clone(),
        };
        let (apps, warnings) = sources::scan(&options);
        println!("{} apps in {:?}", apps.len(), started.elapsed());
        for warning in warnings {
            println!("warning: {warning}");
        }
        let mut counts: std::collections::BTreeMap<&str, usize> = std::collections::BTreeMap::new();
        for app in &apps {
            *counts.entry(app.source.as_str()).or_default() += 1;
        }
        println!("{counts:?}");
        return Ok(());
    }
    i18n::configure(&prefs.language);
    let mut state = SweepDesk {
        prefs,
        apps: Vec::new(),
        rows: Rc::new(Vec::new()),
        search: String::new(),
        category: Category::All,
        source: None,
        selected: None,
        busy: true,
        warning: Vec::new(),
        plan: None,
        plan_text: String::new(),
        cleanup: false,
        acknowledged: false,
        previewing: false,
        removal: false,
        progress: Vec::new(),
        show_log: false,
        tick: 0,
        outcome: None,
        message: None,
        error: None,
        settings: false,
        draft: None,
        python_input: String::new(),
        manual_input: String::new(),
        update: None,
        release: None,
    };
    iced::application("SweepDesk", SweepDesk::update, SweepDesk::view)
        .theme(|state: &SweepDesk| match state.draft.as_ref().unwrap_or(&state.prefs).theme.as_str() {
            "light" => Theme::Light,
            _ => Theme::Dark,
        })
        .window(iced::window::Settings {
            size: iced::Size::new(1080.0, 720.0),
            min_size: Some(iced::Size::new(820.0, 560.0)),
            icon: iced::window::icon::from_file_data(LOGO, None).ok(),
            platform_specific: iced::window::settings::PlatformSpecific {
                application_id: "io.github.Zwart04.SweepDesk".into(),
                ..Default::default()
            },
            ..Default::default()
        })
        .antialiasing(true)
        .subscription(|state: &SweepDesk| {
            if state.busy {
                iced::time::every(iced::time::Duration::from_millis(90)).map(|_| Message::Tick)
            } else {
                iced::Subscription::none()
            }
        })
        .run_with(move || {
            let task = if state.prefs.scan_on_start {
                state.scan()
            } else {
                Task::none()
            };
            (state, task)
        })
}

fn blend(base: Color, other: Color, amount: f32) -> Color {
    Color {
        r: base.r + (other.r - base.r) * amount,
        g: base.g + (other.g - base.g) * amount,
        b: base.b + (other.b - base.b) * amount,
        a: 1.0,
    }
}

fn surface(theme: &Theme) -> Color {
    blend(
        theme.extended_palette().background.base.color,
        theme.palette().text,
        0.055,
    )
}

fn line(theme: &Theme) -> Color {
    blend(
        theme.extended_palette().background.base.color,
        theme.palette().text,
        0.11,
    )
}

fn accent_fill(theme: &Theme) -> Color {
    blend(
        theme.extended_palette().background.base.color,
        theme.extended_palette().primary.base.color,
        0.24,
    )
}

fn muted(theme: &Theme) -> iced::widget::text::Style {
    let palette = theme.palette();
    iced::widget::text::Style {
        color: Some(palette.text.scale_alpha(0.62)),
        ..Default::default()
    }
}

fn success(_theme: &Theme) -> iced::widget::text::Style {
    iced::widget::text::Style {
        color: Some(Color::from_rgb(0.45, 0.80, 0.55)),
    }
}

fn warn(_theme: &Theme) -> iced::widget::text::Style {
    iced::widget::text::Style {
        color: Some(Color::from_rgb(0.95, 0.62, 0.30)),
        ..Default::default()
    }
}

fn panel(theme: &Theme) -> iced::widget::container::Style {
    let palette = theme.palette();
    iced::widget::container::Style {
        background: Some(theme.extended_palette().background.base.color.into()),
        text_color: Some(palette.text),
        border: Border::default(),
        ..Default::default()
    }
}

fn header_bar(theme: &Theme) -> iced::widget::container::Style {
    let palette = theme.palette();
    iced::widget::container::Style {
        background: Some(theme.extended_palette().background.base.color.into()),
        text_color: Some(palette.text),
        border: Border {
            color: palette.text.scale_alpha(0.10),
            width: 0.0,
            radius: 0.0.into(),
        },
        ..Default::default()
    }
}

fn card(theme: &Theme) -> iced::widget::container::Style {
    let palette = theme.palette();
    iced::widget::container::Style {
        background: Some(surface(theme).into()),
        text_color: Some(palette.text),
        border: Border::default().rounded(10).width(1).color(line(theme)),
        ..Default::default()
    }
}

fn divider(theme: &Theme) -> iced::widget::container::Style {
    let palette = theme.palette();
    iced::widget::container::Style {
        background: Some(palette.text.scale_alpha(0.10).into()),
        ..Default::default()
    }
}

fn scroll_style(theme: &Theme, _status: scrollable::Status) -> scrollable::Style {
    let palette = theme.palette();
    let rail = scrollable::Rail {
        background: None,
        border: Border::default(),
        scroller: scrollable::Scroller {
            color: palette.text.scale_alpha(0.20),
            border: Border::default().rounded(3),
        },
    };
    scrollable::Style {
        container: iced::widget::container::Style::default(),
        vertical_rail: rail,
        horizontal_rail: rail,
        gap: None,
    }
}

fn warn_box(theme: &Theme) -> iced::widget::container::Style {
    let palette = theme.palette();
    iced::widget::container::Style {
        background: Some(Color::from_rgb(0.95, 0.62, 0.30).scale_alpha(0.12).into()),
        text_color: Some(palette.text),
        border: Border::default()
            .rounded(6)
            .color(Color::from_rgb(0.95, 0.62, 0.30).scale_alpha(0.35)),
        ..Default::default()
    }
}

fn primary_button(theme: &Theme, status: button::Status) -> button::Style {
    let extended = theme.extended_palette();
    let hovered = matches!(status, button::Status::Hovered | button::Status::Pressed);
    button::Style {
        background: Some(
            if hovered {
                extended.primary.strong.color
            } else {
                extended.primary.base.color
            }
            .into(),
        ),
        text_color: extended.primary.base.text,
        border: Border::default().rounded(6),
        shadow: Shadow::default(),
    }
}

fn ghost_button(theme: &Theme, status: button::Status) -> button::Style {
    let palette = theme.palette();
    let hovered = matches!(status, button::Status::Hovered | button::Status::Pressed);
    button::Style {
        background: Some(
            if hovered {
                surface(theme)
            } else {
                Color::TRANSPARENT
            }
            .into(),
        ),
        text_color: palette.text,
        border: Border::default().rounded(6).width(1).color(line(theme)),
        shadow: Shadow::default(),
    }
}

fn code_box(theme: &Theme) -> iced::widget::container::Style {
    let palette = theme.palette();
    let extended = theme.extended_palette();
    iced::widget::container::Style {
        background: Some(extended.background.base.color.into()),
        border: Border::default()
            .rounded(6)
            .width(1)
            .color(extended.background.strong.color),
        text_color: Some(palette.text),
        ..Default::default()
    }
}

fn activity_track(theme: &Theme) -> iced::widget::container::Style {
    iced::widget::container::Style {
        background: Some(line(theme).into()),
        border: Border::default().rounded(3),
        ..Default::default()
    }
}

fn activity_chunk(theme: &Theme) -> iced::widget::container::Style {
    iced::widget::container::Style {
        background: Some(theme.extended_palette().primary.base.color.into()),
        border: Border::default().rounded(3),
        ..Default::default()
    }
}

fn nav_style(theme: &Theme, status: button::Status, active: bool) -> button::Style {
    let palette = theme.palette();
    let hovered = matches!(status, button::Status::Hovered | button::Status::Pressed);
    button::Style {
        background: if active {
            Some(accent_fill(theme).into())
        } else if hovered {
            Some(surface(theme).into())
        } else {
            Some(Color::TRANSPARENT.into())
        },
        text_color: palette.text,
        border: Border::default().rounded(6),
        shadow: Shadow::default(),
    }
}

fn row_style(theme: &Theme, status: button::Status, active: bool) -> button::Style {
    let palette = theme.palette();
    let hovered = matches!(status, button::Status::Hovered | button::Status::Pressed);
    button::Style {
        background: if active {
            Some(accent_fill(theme).into())
        } else if hovered {
            Some(surface(theme).into())
        } else {
            Some(Color::TRANSPARENT.into())
        },
        text_color: palette.text,
        border: Border::default().rounded(6),
        shadow: Shadow::default(),
    }
}

fn danger_button(_theme: &Theme, status: button::Status) -> button::Style {
    let hovered = matches!(status, button::Status::Hovered | button::Status::Pressed);
    button::Style {
        background: Some(
            if hovered {
                Color::from_rgb(0.72, 0.22, 0.22)
            } else {
                Color::from_rgb(0.58, 0.18, 0.18)
            }
            .into(),
        ),
        text_color: Color::WHITE,
        border: Border::default().rounded(6),
        shadow: Shadow::default(),
    }
}
