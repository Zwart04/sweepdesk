// SPDX-FileCopyrightText: 2026 Zwart04
// SPDX-License-Identifier: GPL-3.0-or-later
// SweepDesk: see LICENSE for copying terms and warranty disclaimer.
//! SweepDesk 0.6.0 — native software inventory and reviewed uninstall.

mod catalogue;
mod i18n;
mod manual;
mod model;
mod plan;
mod prefs;
mod sources;
mod steam;

#[cfg(test)]
mod tests;

use i18n::tr;
use iced::widget::{
    button, checkbox, column, container, horizontal_space, image, row, scrollable, text,
    text_input, vertical_space, Column,
};
use iced::{Alignment, Border, Color, Element, Length, Shadow, Task, Theme};
use model::App;
use model::Plan;
use prefs::Preferences;

const VERSION: &str = "0.6.0";
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
}

struct SweepDesk {
    prefs: Preferences,
    apps: Vec<App>,
    filtered: Vec<usize>,
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
    message: Option<String>,
    error: Option<String>,
    settings: bool,
    draft: Option<Preferences>,
    python_input: String,
    manual_input: String,
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
        self.filtered = self
            .apps
            .iter()
            .enumerate()
            .filter(|(_, app)| {
                if app.support && !self.prefs.show_system {
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
            .map(|(index, _)| index)
            .collect();
    }

    fn selected_app(&self) -> Option<&App> {
        self.selected.and_then(|index| self.apps.get(index))
    }

    fn can_remove(&self, app: &App) -> bool {
        !self.busy && !app.essential && app.readonly_reason.is_empty()
    }

    fn sidebar(&self) -> Element<'_, Message> {
        let mut list = Column::new().spacing(2).padding(8);
        for category in [
            Category::All,
            Category::Applications,
            Category::CommandLine,
            Category::System,
        ] {
            let active = self.category == category;
            list = list.push(
                button(text(category.label()).size(13))
                    .on_press(Message::CategoryChanged(category))
                    .width(Length::Fill)
                    .padding([7, 10])
                    .style(move |theme, status| nav_style(theme, status, active)),
            );
        }
        list = list.push(vertical_space().height(10));
        list = list.push(text(tr("SOURCES")).size(10).style(muted));
        list = list.push(
            button(text(format!("{} ({})", tr("All Software"), self.apps.len())).size(12))
                .on_press(Message::SourceChanged(None))
                .width(Length::Fill)
                .padding([6, 10])
                .style(move |theme, status| nav_style(theme, status, self.source.is_none())),
        );
        for (source, count) in source_list(&self.apps) {
            if count == 0 && !self.prefs.show_empty_sources {
                continue;
            }
            let active = self.source.as_deref() == Some(source.as_str());
            list = list.push(
                button(text(format!("{source} ({count})")).size(12))
                    .on_press(Message::SourceChanged(Some(source.clone())))
                    .width(Length::Fill)
                    .padding([5, 10])
                    .style(move |theme, status| nav_style(theme, status, active)),
            );
        }
        list = list.push(vertical_space().height(10));
        list = list.push(
            checkbox(tr("Show system packages"), self.prefs.show_system)
                .on_toggle(Message::ToggleSystem)
                .size(15)
                .text_size(11),
        );
        container(scrollable(list))
            .width(Length::Fixed(210.0))
            .height(Length::Fill)
            .style(panel)
            .into()
    }

    fn list(&self) -> Element<'_, Message> {
        if self.apps.is_empty() {
            return container(text(tr("Scanning installed software…")).size(13))
                .padding(24)
                .into();
        }
        let mut rows = Column::new().spacing(1);
        for index in &self.filtered {
            let Some(app) = self.apps.get(*index) else {
                continue;
            };
            let active = self.selected == Some(*index);
            let subtitle = if app.readonly_reason.is_empty() {
                format!("{} · {}", app.package, app.source)
            } else {
                format!("{} · {} · {}", app.package, app.source, app.readonly_reason)
            };
            let body = row![
                column![
                    text(&app.name).size(13),
                    text(subtitle).size(11).style(muted),
                ]
                .spacing(1)
                .width(Length::Fill),
                text(size_label(app.size)).size(11).style(muted),
            ]
            .align_y(Alignment::Center)
            .spacing(8);
            rows = rows.push(
                button(body)
                    .on_press(Message::Select(*index))
                    .width(Length::Fill)
                    .padding([7, 10])
                    .style(move |theme, status| row_style(theme, status, active)),
            );
        }
        if self.filtered.is_empty() {
            return container(text(tr("Try another search or choose a different source.")).size(13))
                .padding(24)
                .into();
        }
        scrollable(rows).height(Length::Fill).into()
    }

    fn details(&self) -> Element<'_, Message> {
        let Some(app) = self.selected_app() else {
            return container(text(tr("Select an item to see its details.")).size(12).style(muted))
                .padding(16)
                .width(Length::Fill)
                .style(panel)
                .into();
        };
        let mut card = Column::new().spacing(10).padding(16);
        card = card.push(text(&app.name).size(18));
        card = card.push(
            text(if app.description.is_empty() {
                tr("Installed software")
            } else {
                &app.description
            })
            .size(12)
            .style(muted),
        );
        for (label, value) in [
            (tr("Version"), app.version.clone()),
            (tr("Source"), app.source.clone()),
            (tr("Size"), size_label(app.size)),
            ("ID", app.package.clone()),
            ("Scope", app.scope.clone()),
        ] {
            if value.is_empty() {
                continue;
            }
            card = card.push(
                row![
                    text(label).size(11).width(Length::Fixed(70.0)).style(muted),
                    text(value).size(11),
                ]
                .spacing(8),
            );
        }
        if !app.readonly_reason.is_empty() {
            card = card.push(text(&app.readonly_reason).size(11).style(warn));
        }
        card = card.push(vertical_space().height(6));
        card = card.push(
            button(text(tr("Review Removal")).size(13))
                .on_press_maybe(self.can_remove(app).then_some(Message::RequestRemoval))
                .padding([8, 14])
                .style(danger_button),
        );
        container(card)
            .width(Length::Fixed(300.0))
            .height(Length::Fill)
            .style(panel)
            .into()
    }

    fn plan_view(&self) -> Element<'_, Message> {
        let Some(plan) = &self.plan else {
            return container(text("")).into();
        };
        let app = &plan.app;
        let mut body = Column::new().spacing(12).padding(20);
        body = body.push(text(tr("Review Removal")).size(20));
        body = body.push(text(format!("{} · {}", app.name, app.package)).size(13).style(muted));
        let mut summary = vec![format!("{} items to remove", plan.removed.len())];
        if !plan.extra.is_empty() {
            summary.push(format!("{} extra dependencies", plan.extra.len()));
        }
        if !plan.data.is_empty() {
            summary.push(format!("{} data locations", plan.data.len()));
        }
        body = body.push(text(summary.join(" · ")).size(12).style(muted));
        body = body.push(
            container(scrollable(text(&self.plan_text).size(11).font(iced::Font::MONOSPACE)))
                .height(Length::Fill)
                .padding(10)
                .style(code_box),
        );
        body = body.push(
            container(
                column![
                    text(tr("Confirm before removing")).size(13),
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
            .padding(12)
            .style(panel),
        );
        let can_confirm = self.acknowledged && !self.busy;
        body = body.push(
            row![
                button(text(tr("Cancel")).size(13))
                    .on_press(Message::CancelPlan)
                    .padding([8, 16]),
                horizontal_space(),
                button(text(if self.busy { tr("Removing…") } else { tr("Remove") }).size(13))
                    .on_press_maybe(can_confirm.then_some(Message::Confirmed))
                    .padding([8, 16])
                    .style(danger_button),
            ]
            .spacing(8),
        );
        container(body)
            .width(Length::Fill)
            .height(Length::Fill)
            .padding(16)
            .style(panel)
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
        body = body.push(container(source_columns).padding(8).style(panel));
        body = body.push(text(tr("Extra Python folders")).size(12).style(muted));
        body = body.push(
            row![
                text_input(tr("Folder path"), &self.python_input)
                    .on_input(Message::PythonInput)
                    .padding(7)
                    .size(12),
                button(text(tr("Add")).size(12))
                    .on_press(Message::AddPythonFolder)
                    .padding([7, 12]),
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
                    .padding(7)
                    .size(12),
                button(text(tr("Add")).size(12))
                    .on_press(Message::AddManualFolder)
                    .padding([7, 12]),
            ]
            .spacing(6),
        );
        for folder in &draft.manual_folders {
            body = body.push(self.folder_row(folder, false));
        }
        body = body.push(horizontal_space().height(4));
        body = body.push(
            row![
                button(text(tr("Cancel")).size(13))
                    .on_press(Message::CloseSettings)
                    .padding([8, 16]),
                horizontal_space(),
                button(text(tr("Save")).size(13))
                    .on_press(Message::SaveSettings)
                    .padding([8, 16])
                    .style(danger_button),
            ]
            .spacing(8),
        );
        container(scrollable(body))
            .width(Length::Fill)
            .height(Length::Fill)
            .padding(16)
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
        let header = row![
            image(image::Handle::from_bytes(LOGO.to_vec())).width(Length::Fixed(22.0)).height(Length::Fixed(22.0)),
            text("SweepDesk").size(18),
            text(tr("Your software, in one place.")).size(11).style(muted),
            horizontal_space(),
            text_input(tr("Search software…"), &self.search)
                .on_input(Message::SearchChanged)
                .width(Length::Fixed(260.0))
                .padding(7)
                .size(12),
            button(text(if self.busy { tr("Scanning…") } else { tr("Refresh") }).size(12))
                .on_press_maybe((!self.busy).then_some(Message::Rescan))
                .padding([7, 12]),
            button(text(tr("Settings")).size(12))
                .on_press(Message::OpenSettings)
                .padding([7, 12]),
        ]
        .spacing(10)
        .align_y(Alignment::Center)
        .padding([8, 16]);

        let body: Element<'_, Message> = if self.settings {
            self.settings_view()
        } else if self.plan.is_some() {
            self.plan_view()
        } else {
            row![self.sidebar(), self.list(), self.details()]
                .spacing(1)
                .height(Length::Fill)
                .into()
        };

        let mut layout = Column::new().push(
            container(header)
                .width(Length::Fill)
                .style(panel),
        );
        if self.busy && self.plan.is_none() {
            layout = layout.push(
                container(text(tr("Scanning installed software…")).size(12).style(muted))
                    .padding([6, 16])
                    .width(Length::Fill),
            );
        }
        for warning in &self.warning {
            layout = layout.push(
                container(text(warning).size(11).style(warn))
                    .padding([5, 16])
                    .width(Length::Fill),
            );
        }
        if let Some(error) = &self.error {
            layout = layout.push(
                container(
                    row![
                        text(error).size(11).style(warn).width(Length::Fill),
                        button(text("×").size(13)).on_press(Message::DismissMessage).padding([0, 6]),
                    ]
                    .align_y(Alignment::Center),
                )
                .padding([5, 16])
                .width(Length::Fill),
            );
        }
        if let Some(message) = &self.message {
            layout = layout.push(
                container(
                    row![
                        text(message).size(11).width(Length::Fill),
                        button(text("×").size(13)).on_press(Message::DismissMessage).padding([0, 6]),
                    ]
                    .align_y(Alignment::Center),
                )
                .padding([5, 16])
                .width(Length::Fill),
            );
        }
        layout = layout.push(body);
        layout = layout.push(
            container(
                row![
                    text(format!(
                        "{} {} · {}", tr("Version"), VERSION, tr("Made by Zwart04")
                    ))
                    .size(10)
                    .style(muted),
                    horizontal_space(),
                    button(text(tr("Check for Updates")).size(10))
                        .on_press(Message::OpenReleases)
                        .padding([1, 6]),
                    button(text(tr("Buy me a coffee")).size(10))
                        .on_press(Message::OpenSupport)
                        .padding([1, 6]),
                    text(format!("{} items", self.filtered.len())).size(10).style(muted),
                ]
                .spacing(10)
                .align_y(Alignment::Center)
                .padding([5, 16]),
            )
            .width(Length::Fill)
            .style(panel),
        );
        container(layout)
            .width(Length::Fill)
            .height(Length::Fill)
            .into()
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
                Task::none()
            }
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
                Task::perform(
                    async move {
                        let mut log = String::new();
                        let result = plan::execute(&plan, &mut |line| log.push_str(line));
                        match result {
                            Ok(()) => Ok(log),
                            Err(error) => Err(format!("{error}\n\n{log}")),
                        }
                    },
                    Message::Finished,
                )
            }
            Message::CancelPlan => {
                self.plan = None;
                self.cleanup = false;
                self.acknowledged = false;
                self.busy = false;
                Task::none()
            }
            Message::Finished(result) => {
                self.busy = false;
                match result {
                    Ok(log) => {
                        self.plan = None;
                        self.cleanup = false;
                        self.acknowledged = false;
                        self.message = Some(if log.trim().is_empty() {
                            tr("Removal finished.").into()
                        } else {
                            log
                        });
                        self.selected = None;
                        self.scan()
                    }
                    Err(error) => {
                        self.error = Some(error);
                        Task::none()
                    }
                }
            }
            Message::PlanReady(plan) => {
                self.busy = false;
                self.plan_text = plan::describe(&plan);
                self.plan = Some(*plan);
                self.acknowledged = false;
                Task::none()
            }
            Message::Rescan => self.scan(),
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
        filtered: Vec::new(),
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
        message: None,
        error: None,
        settings: false,
        draft: None,
        python_input: String::new(),
        manual_input: String::new(),
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
            ..Default::default()
        })
        .antialiasing(true)
        .run_with(move || {
            let task = if state.prefs.scan_on_start {
                state.scan()
            } else {
                Task::none()
            };
            (state, task)
        })
}

fn muted(theme: &Theme) -> iced::widget::text::Style {
    let palette = theme.palette();
    iced::widget::text::Style {
        color: Some(palette.text.scale_alpha(0.62)),
        ..Default::default()
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
        background: Some(palette.background.scale_alpha(0.75).into()),
        text_color: Some(palette.text),
        border: Border::default(),
        ..Default::default()
    }
}

fn code_box(theme: &Theme) -> iced::widget::container::Style {
    let palette = theme.palette();
    iced::widget::container::Style {
        background: Some(palette.background.scale_alpha(0.4).into()),
        border: Border::default().rounded(6).color(palette.text.scale_alpha(0.12)),
        text_color: Some(palette.text),
        ..Default::default()
    }
}

fn nav_style(theme: &Theme, status: button::Status, active: bool) -> button::Style {
    let palette = theme.palette();
    let hovered = matches!(status, button::Status::Hovered | button::Status::Pressed);
    button::Style {
        background: if active {
            Some(palette.primary.scale_alpha(0.22).into())
        } else if hovered {
            Some(palette.text.scale_alpha(0.08).into())
        } else {
            Some(Color::TRANSPARENT.into())
        },
        text_color: if active { palette.primary } else { palette.text },
        border: Border::default().rounded(5),
        shadow: Shadow::default(),
    }
}

fn row_style(theme: &Theme, status: button::Status, active: bool) -> button::Style {
    let palette = theme.palette();
    let hovered = matches!(status, button::Status::Hovered | button::Status::Pressed);
    button::Style {
        background: if active {
            Some(palette.primary.scale_alpha(0.20).into())
        } else if hovered {
            Some(palette.text.scale_alpha(0.07).into())
        } else {
            Some(Color::TRANSPARENT.into())
        },
        text_color: palette.text,
        border: Border::default().rounded(5),
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
