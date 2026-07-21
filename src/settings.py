"""PrePaste Settings — a standalone desktop control panel.

Run with:  python settings.py
Preferences are saved in %LOCALAPPDATA%\\PrePaste\\settings.json.
"""

from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
import subprocess
import sys
import time
import flet as ft

from config_store import (
    CREDENTIAL_TYPES,
    PII_ENTITIES,
    clear_history,
    data_directory,
    history_path,
    load_history,
    load_settings,
    save_settings,
    select_redaction_for_viewer,
    settings_path,
)

PURPLE = "#7357E8"
INK = "#252033"
MUTED = "#756E82"
CANVAS = "#F7F5FC"
CARD = "#FFFFFF"
BORDER = "#E8E3F1"
SUCCESS = "#23A56A"

ENTITY_DETAILS = {
    "EMAIL_ADDRESS": ("Email address", "Personal and work email"),
    "PHONE_NUMBER": ("Phone number", "International and local numbers"),
    "CREDIT_CARD": ("Credit card", "Card numbers and payment data"),
    "US_SSN": ("Social security number", "US SSNs"),
    "LOCATION": ("Location", "Addresses and place names"),
    "DATE_TIME": ("Date & time", "Dates that may identify someone"),
    "ORGANIZATION": ("Organization", "Company and institution names"),
    "IP_ADDRESS": ("IP address", "Public network addresses"),
    "URL": ("URL", "Web addresses"),
    "IBAN_CODE": ("IBAN", "International bank account numbers"),
    "NRP": ("Nationality / religion / politics", "Sensitive identity information"),
    "PERSON": ("Person", "Names of people"),
}

CREDENTIAL_DETAILS = {
    "OpenAI API key": ("OpenAI", "sk-… and project keys"),
    "Anthropic API key": ("Anthropic", "sk-ant-… keys"),
    "Hugging Face token": ("Hugging Face", "hf_… tokens"),
    "GitHub personal access token": ("GitHub", "ghp_… tokens"),
    "Google API key": ("Google API", "AIza… keys"),
    "Google OAuth token": ("Google OAuth", "ya29.… tokens"),
    "AWS access key ID": ("AWS", "AKIA / ASIA key IDs"),
    "Stripe secret key": ("Stripe", "Live and test secret keys"),
    "Slack token": ("Slack", "xox… tokens"),
    "MongoDB connection URI": ("MongoDB", "Credential-bearing database URLs"),
    "Supabase JWT": ("Supabase", "Service JSON web tokens"),
}


def main(page: ft.Page) -> None:
    page.title = "PrePaste Settings"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.bgcolor = CANVAS
    page.padding = 0
    page.window.width = 960
    page.window.height = 680
    page.window.min_width = 860
    page.window.min_height = 600

    state = load_settings()
    current_page = "Protection"
    nav_buttons: dict[str, ft.Container] = {}
    nav_labels: dict[str, ft.Text] = {}
    content = ft.Column(expand=True, scroll=ft.ScrollMode.AUTO, spacing=18)
    save_note = ft.Text("Changes save automatically", size=11, color=MUTED)

    def notify(message: str) -> None:
        page.snack_bar = ft.SnackBar(ft.Text(message), bgcolor=INK, open=True)
        page.update()

    def persist(message: str = "Saved") -> None:
        save_settings(state)
        save_note.value = "Saved just now"
        if save_note.page:
            save_note.update()
        if message:
            notify(message)

    def title(eyebrow: str, heading: str, copy: str) -> ft.Control:
        return ft.Column(
            spacing=4,
            controls=[
                ft.Text(
                    eyebrow.upper(), size=10, weight=ft.FontWeight.W_700, color=PURPLE
                ),
                ft.Text(heading, size=28, weight=ft.FontWeight.BOLD, color=INK),
                ft.Text(copy, size=13, color=MUTED),
            ],
        )

    def card(*controls: ft.Control, padding: int = 18) -> ft.Container:
        return ft.Container(
            bgcolor=CARD,
            border=ft.Border.all(1, BORDER),
            border_radius=16,
            padding=padding,
            content=ft.Column(spacing=12, controls=list(controls)),
        )

    def section_header(
        heading: str, copy: str, trailing: ft.Control | None = None
    ) -> ft.Control:
        row_controls: list[ft.Control] = [
            ft.Column(
                expand=True,
                spacing=2,
                controls=[
                    ft.Text(heading, size=16, weight=ft.FontWeight.W_700, color=INK),
                    ft.Text(copy, size=11, color=MUTED),
                ],
            )
        ]
        if trailing:
            row_controls.append(trailing)
        return ft.Row(
            controls=row_controls, vertical_alignment=ft.CrossAxisAlignment.CENTER
        )

    def toggle_row(
        key: str,
        label: str,
        description: str,
        bucket: str,
        icon: str = ft.Icons.SHIELD_OUTLINED,
    ) -> ft.Control:
        def on_change(e: ft.ControlEvent) -> None:
            state[bucket][key] = bool(e.control.value)
            persist("Detection preference saved")

        return ft.Container(
            padding=ft.Padding.symmetric(vertical=7),
            content=ft.Row(
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Container(
                        width=34,
                        height=34,
                        border_radius=10,
                        alignment=ft.Alignment.CENTER,
                        bgcolor="#F0ECFF",
                        content=ft.Icon(icon, size=17, color=PURPLE),
                    ),
                    ft.Column(
                        expand=True,
                        spacing=1,
                        controls=[
                            ft.Text(
                                label, size=13, weight=ft.FontWeight.W_600, color=INK
                            ),
                            ft.Text(description, size=10, color=MUTED),
                        ],
                    ),
                    ft.Switch(
                        value=bool(state[bucket].get(key, False)),
                        active_color=PURPLE,
                        on_change=on_change,
                    ),
                ],
            ),
        )

    def protection_view() -> list[ft.Control]:
        enabled = sum(bool(value) for value in state["entities"].values())
        all_enabled = enabled == len(PII_ENTITIES)

        def set_all(e: ft.ControlEvent) -> None:
            for key in state["entities"]:
                state["entities"][key] = bool(e.control.value)
            persist("All personal-data detectors updated")
            show_page("Protection")

        personal_controls = [
            section_header(
                "Personal data",
                f"{enabled} of {len(PII_ENTITIES)} detectors enabled",
            ),
            ft.Divider(height=1, color=BORDER),
        ]
        personal_controls.extend(
            toggle_row(key, *ENTITY_DETAILS[key], "entities", ft.Icons.PERSON_OUTLINE)
            for key in PII_ENTITIES
        )
        return [
            title(
                "Privacy controls",
                "What should PrePaste protect?",
                "Choose the information types that should trigger a warning before you paste.",
            ),
            card(*personal_controls),
        ]

    def credentials_view() -> list[ft.Control]:
        enabled = sum(bool(value) for value in state["credential_types"].values())
        all_enabled = enabled == len(CREDENTIAL_TYPES)

        def set_all(e: ft.ControlEvent) -> None:
            for key in state["credential_types"]:
                state["credential_types"][key] = bool(e.control.value)
            persist("All credential detectors updated")
            show_page("API keys")

        controls = [
            section_header(
                "Credential patterns",
                f"{enabled} of {len(CREDENTIAL_TYPES)} patterns enabled",
                ft.Switch(value=all_enabled, active_color=PURPLE, on_change=set_all),
            ),
            ft.Divider(height=1, color=BORDER),
        ]
        controls.extend(
            toggle_row(
                key, *CREDENTIAL_DETAILS[key], "credential_types", ft.Icons.KEY_OUTLINED
            )
            for key in CREDENTIAL_TYPES
        )
        return [
            title(
                "Secret detection",
                "API keys & credentials",
                "PrePaste checks the format of common secrets locally.",
            ),
            card(*controls),
        ]

    def preferences_view() -> list[ft.Control]:
        model_options = [
            ft.dropdown.Option("en_core_web_sm", "Small — quicker, lower memory"),
        ]

        def model_changed(e: ft.ControlEvent) -> None:
            state["model"] = e.control.value
            persist("Language model saved")

        def threshold_changed(e: ft.ControlEvent) -> None:
            state["confidence_threshold"] = int(e.control.value) / 100
            threshold_label.value = f"{int(e.control.value)}% confidence"
            threshold_label.update()
            persist("Confidence threshold saved")

        def simple_toggle(key: str, label: str, description: str) -> ft.Control:
            def changed(e: ft.ControlEvent) -> None:
                state[key] = bool(e.control.value)
                persist("Preference saved")

            return ft.Switch(
                label=label,
                value=bool(state.get(key)),
                active_color=PURPLE,
                on_change=changed,
                tooltip=description,
            )

        def history_limit_changed(e: ft.ControlEvent) -> None:
            state["history_limit"] = int(e.control.value)
            persist("History limit saved")

        threshold_label = ft.Text(
            f"{int(float(state['confidence_threshold']) * 100)}% confidence",
            size=12,
            weight=ft.FontWeight.W_600,
            color=PURPLE,
        )
        return [
            title(
                "How PrePaste works",
                "Scanning preferences",
                "Tune accuracy, model size, and how the clipboard companion behaves.",
            ),
            card(
                section_header(
                    "Language model",
                    "Small is fast; Large is more accurate with people and organisations.",
                ),
                ft.Dropdown(
                    value=state["model"],
                    options=model_options,
                    border_color=BORDER,
                    focused_border_color=PURPLE,
                    on_text_change=model_changed,
                ),
            ),
            card(
                section_header(
                    "Detection sensitivity",
                    "Only findings at or above this confidence level create a warning.",
                    threshold_label,
                ),
                ft.Slider(
                    min=50,
                    max=100,
                    divisions=13,
                    value=int(float(state["confidence_threshold"]) * 100),
                    active_color=PURPLE,
                    on_change=threshold_changed,
                ),
            ),
            card(
                section_header(
                    "Behaviour",
                    "These switches are saved for the clipboard companion to use.",
                ),
                simple_toggle(
                    "scan_clipboard",
                    "Monitor clipboard",
                    "Scan new clipboard text for enabled detectors.",
                ),
                simple_toggle(
                    "show_flet_notification",
                    "Show Windows native notification instead",
                    "Keep the Hide Sensitive action available.",
                ),
                simple_toggle(
                    "launch_at_sign_in",
                    "Open when I sign in",
                    "Saved for the PrePaste launcher; this app does not edit system startup entries.",
                ),
                simple_toggle(
                    "show_desktop_alerts",
                    "Show desktop alerts",
                    "Show the compact warning window when a match is found.",
                ),
                simple_toggle(
                    "always_on_top",
                    "Keep warning above other windows",
                    "Keep the compact warning visible while you decide.",
                ),
            ),
            card(
                section_header(
                    "Local history",
                    "Each redaction stores the full original and redacted clipboard text locally.",
                ),
                simple_toggle(
                    "keep_history",
                    "Keep scan history",
                    "Save local scan summaries so you can review activity later.",
                ),
                ft.Dropdown(
                    label="Keep up to",
                    value=str(state["history_limit"]),
                    options=[
                        ft.dropdown.Option(str(limit), f"{limit} scans")
                        for limit in (25, 50, 100, 250)
                    ],
                    border_color=BORDER,
                    focused_border_color=PURPLE,
                    on_text_change=history_limit_changed,
                ),
            ),
        ]

    def history_view() -> list[ft.Control]:
        entries = load_history()

        def open_in_viewer(entry: dict) -> None:
            """Select one record first, then launch the separate review window."""
            record_id = entry.get("id")
            if not isinstance(record_id, str) or not record_id.strip():
                notify("This history record cannot be opened")
                return

            try:
                print("coming here")
                select_redaction_for_viewer(record_id)
            except Exception as e:
                print(e)
                notify("Could not select this redaction for review")
                return

            root_dir = Path(__file__).parent.parent

            # 2. Build the exact path to the .exe
            exe_path = root_dir / "build_viewer" / "prepaste.exe"
            if not exe_path.is_file():
                print("hbuu here")
                notify("Selection saved, but redaction_viewer.py was not found")
                return

            try:
                subprocess.Popen(
                    [str(exe_path)],
                    cwd=str(
                        exe_path.parent
                    ),  # Optional: sets the working directory to root/a
                    creationflags=(
                        getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                        | getattr(subprocess, "DETACHED_PROCESS", 0)
                    ),
                )
                print("Executable launched!")
            except Exception as e:
                print(f"Failed to launch: {e}")

        def delete_all(e: ft.ControlEvent) -> None:
            clear_history()
            notify("History deleted")
            show_page("History")

        header = ft.Row(
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            controls=[
                ft.Text(
                    f"{len(entries)} local scan{'s' if len(entries) != 1 else ''}",
                    size=12,
                    color=MUTED,
                ),
                ft.TextButton(
                    "Delete all",
                    icon=ft.Icons.DELETE_OUTLINE,
                    style=ft.ButtonStyle(color="#C23D53"),
                    on_click=delete_all,
                ),
            ],
        )
        rows: list[ft.Control] = [header, ft.Divider(height=1, color=BORDER)]
        if not entries:
            rows.append(
                ft.Container(
                    height=230,
                    alignment=ft.Alignment.CENTER,
                    content=ft.Column(
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        alignment=ft.MainAxisAlignment.CENTER,
                        controls=[
                            ft.Icon(
                                ft.Icons.HISTORY_TOGGLE_OFF_OUTLINED,
                                size=42,
                                color="#B2AABD",
                            ),
                            ft.Text(
                                "No scan history yet",
                                size=15,
                                weight=ft.FontWeight.W_600,
                                color=INK,
                            ),
                            ft.Text(
                                "PrePaste stores scan summaries here, never copied text or secrets.",
                                size=11,
                                color=MUTED,
                            ),
                        ],
                    ),
                )
            )
        for entry in entries:
            try:
                happened = (
                    datetime.fromisoformat(
                        str(entry["timestamp"]).replace("Z", "+00:00")
                    )
                    .astimezone()
                    .strftime("%d %b, %I:%M %p")
                )
            except (KeyError, ValueError):
                happened = "Unknown time"
            line_numbers = entry.get("line_numbers", [])
            line_label = ", ".join(str(line) for line in line_numbers) or "—"
            count = (
                len(line_numbers)
                if line_numbers
                else int(entry.get("finding_count", 0))
            )
            redacted_preview = entry.get("redacted_text")
            description_controls: list[ft.Control] = [
                ft.Text(
                    f"Lines: {line_label}",
                    size=13,
                    weight=ft.FontWeight.W_600,
                    color=INK,
                ),
                ft.Text(
                    f"{count} affected line{'s' if count != 1 else ''}",
                    size=10,
                    color=MUTED,
                    max_lines=1,
                    overflow=ft.TextOverflow.ELLIPSIS,
                ),
            ]
            if redacted_preview:
                description_controls.append(
                    ft.Text(
                        str(redacted_preview).replace("\n", " "),
                        size=10,
                        color="#5E5668",
                        italic=True,
                        max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    )
                )
            can_open = (
                entry.get("kind") == "redaction"
                and isinstance(entry.get("id"), str)
                and isinstance(entry.get("original_text"), str)
                and isinstance(entry.get("redacted_text"), str)
            )
            row_controls: list[ft.Control] = [
                ft.Container(
                    width=34,
                    height=34,
                    border_radius=10,
                    bgcolor="#FFF1F3",
                    alignment=ft.Alignment.CENTER,
                    content=ft.Icon(
                        ft.Icons.PRIVACY_TIP_OUTLINED, color="#D7546A", size=17
                    ),
                ),
                ft.Column(expand=True, spacing=1, controls=description_controls),
                ft.Column(
                    horizontal_alignment=ft.CrossAxisAlignment.END,
                    spacing=1,
                    controls=[
                        ft.Text(happened, size=10, color=MUTED),
                        ft.Text(str(entry.get("source", "Scan")), size=9, color=PURPLE),
                    ],
                ),
            ]
            if can_open:
                row_controls.append(
                    ft.Icon(ft.Icons.CHEVRON_RIGHT, color="#B2AABD", size=18)
                )
            rows.append(
                ft.Container(
                    padding=ft.Padding.symmetric(vertical=8),
                    border_radius=10,
                    ink=can_open,
                    on_click=(
                        (lambda e, saved_entry=entry: open_in_viewer(saved_entry))
                        if can_open
                        else None
                    ),
                    content=ft.Row(controls=row_controls),
                )
            )
        return [
            title(
                "Privacy record",
                "Scan history",
                "A local record of redactions, including the full original and redacted clipboard text.",
            ),
            card(*rows),
        ]

    def about_view() -> list[ft.Control]:
        location = str(data_directory())
        return [
            title(
                "PrePaste",
                "Paste with confidence",
                "A local-first privacy guard for the information that should not leave your clipboard by accident.",
            ),
            card(
                ft.Row(
                    controls=[
                        ft.Container(
                            width=48,
                            height=48,
                            border_radius=14,
                            bgcolor="#EEE9FF",
                            alignment=ft.Alignment.CENTER,
                            content=ft.Icon(
                                ft.Icons.SHIELD_OUTLINED, size=27, color=PURPLE
                            ),
                        ),
                        ft.Column(
                            spacing=2,
                            controls=[
                                ft.Text(
                                    "PrePaste",
                                    size=18,
                                    weight=ft.FontWeight.BOLD,
                                    color=INK,
                                ),
                                ft.Text(
                                    "Settings & privacy control centre",
                                    size=11,
                                    color=MUTED,
                                ),
                            ],
                        ),
                    ]
                ),
                ft.Divider(color=BORDER),
                ft.Text(
                    "PrePaste checks clipboard text locally using Microsoft Presidio and optional, format-based credential detectors. It warns you before a paste may expose personal data or secrets to online forums or LLM's.",
                    size=13,
                    color=INK,
                ),
                ft.Text(
                    "Privacy promise", size=14, weight=ft.FontWeight.W_700, color=INK
                ),
                ft.Text(
                    "Your copied text is processed on your computer. When history is enabled, each redaction stores the full original and redacted text only in this Windows user's local history file.",
                    size=12,
                    color=MUTED,
                ),
                ft.Text(
                    "If you like this project, consider giving it a star ⭐ ",
                    size=12,
                    color=MUTED,
                ),
                ft.Text(
                    "Found a bug? Have a feature request? I'd love to hear from you 😊\nPlease open an issue on GitHub.",
                    size=12,
                    color=MUTED,
                ),
            ),
            card(
                section_header(
                    "Local files",
                    "These files belong only to the current Windows user.",
                ),
                ft.Text(
                    f"Settings: {settings_path()}", size=11, color=INK, selectable=True
                ),
                ft.Text(
                    f"History: {history_path()}", size=11, color=INK, selectable=True
                ),
                ft.Text("Version 1.0", size=11, color=MUTED),
            ),
        ]

    views = {
        "Protection": protection_view,
        "API keys": credentials_view,
        "Preferences": preferences_view,
        "History": history_view,
        "About": about_view,
    }

    def show_page(name: str) -> None:
        nonlocal current_page
        current_page = name
        content.controls = views[name]()
        for label, button in nav_buttons.items():
            selected = label == name
            button.bgcolor = "#EEE9FF" if selected else None
            nav_labels[label].color = PURPLE if selected else MUTED
        page.update()

    def navigation_item(label: str, icon: str) -> ft.Control:
        label_control = ft.Text(label, size=13, weight=ft.FontWeight.W_600, color=MUTED)
        item = ft.Container(
            border_radius=10,
            padding=ft.Padding.symmetric(horizontal=12, vertical=10),
            ink=True,
            on_click=lambda e: show_page(label),
            content=ft.Row(
                spacing=12,
                controls=[ft.Icon(icon, size=18, color=PURPLE), label_control],
            ),
        )
        nav_buttons[label] = item
        nav_labels[label] = label_control
        return item

    async def open_github(e):
        launcher = ft.UrlLauncher()
        page.services.append(launcher)
        await launcher.launch_url(
            "https://github.com/TheAnshulPrakash/PrePaste",
            mode=ft.LaunchMode.EXTERNAL_APPLICATION,
        )

    sidebar = ft.Container(
        width=218,
        bgcolor=CARD,
        padding=18,
        content=ft.Column(
            expand=True,
            controls=[
                ft.Row(
                    spacing=9,
                    controls=[
                        ft.Container(
                            width=31,
                            height=31,
                            border_radius=10,
                            alignment=ft.Alignment.CENTER,
                            content=ft.Image("PrePaste.png", width=41, height=41),
                        ),
                        ft.Column(
                            spacing=0,
                            controls=[
                                ft.Text(
                                    "PREPASTE",
                                    size=13,
                                    weight=ft.FontWeight.BOLD,
                                    color=INK,
                                ),
                                ft.Text("Privacy, before paste", size=9, color=MUTED),
                            ],
                        ),
                    ],
                ),
                ft.Container(height=22),
                ft.Text(
                    "PROTECTION", size=9, weight=ft.FontWeight.BOLD, color="#A49BAC"
                ),
                navigation_item("Protection", ft.Icons.SHIELD_OUTLINED),
                navigation_item("API keys", ft.Icons.KEY_OUTLINED),
                ft.Container(height=8),
                ft.Text("APP", size=9, weight=ft.FontWeight.BOLD, color="#A49BAC"),
                navigation_item("Preferences", ft.Icons.TUNE_OUTLINED),
                navigation_item("History", ft.Icons.HISTORY_OUTLINED),
                ft.Container(expand=True),
                ft.Divider(color=BORDER),
                navigation_item("About", ft.Icons.INFO_OUTLINE),
                ft.Container(
                    border_radius=10,
                    padding=ft.Padding.symmetric(horizontal=12, vertical=10),
                    ink=True,
                    on_click=lambda e: page.run_task(open_github, e),
                    content=ft.Row(
                        spacing=12,
                        controls=[
                            ft.Icon(
                                ft.Icons.STAR_BORDER_ROUNDED,
                                size=18,
                                color=PURPLE,
                            ),
                            ft.Text("Star Us"),
                        ],
                    ),
                ),
                ft.Row(
                    spacing=6,
                    controls=[
                        ft.Icon(ft.Icons.CHECK_CIRCLE_OUTLINE, size=13, color=SUCCESS),
                        ft.Text("Settings are local", size=10, color=MUTED),
                    ],
                ),
            ],
        ),
    )

    def restart_prepaste(e):
        root_dir = Path(__file__).parent.parent

        notification_exe = root_dir / "build_notification" / "prepaste.exe"
        notif_windows_exe = (
            root_dir / "build_notif_windows" / "prepaste_win_notification.exe"
        )

        # Close either possible background application first.
        # Give the notification and dummy builds different .exe names.
        for process_name in ("prepaste.exe", "prepaste_dummy.exe"):
            subprocess.run(
                ["taskkill", "/F", "/IM", process_name, "/T"],
                capture_output=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )

        time.sleep(0.5)

        config = load_settings()  # Same settings file used by the switch.
        show_flet_notification = config.get("show_flet_notification", False)

        # True → actual Flet notification app
        # False → dummy app
        exe_path = notif_windows_exe if show_flet_notification else notification_exe

        if not exe_path.is_file():
            print(f"Program not found: {exe_path}")
            return

        try:
            subprocess.Popen(
                [str(exe_path)],
                cwd=str(exe_path.parent),
                creationflags=(
                    getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                    | getattr(subprocess, "DETACHED_PROCESS", 0)
                ),
            )
            print(f"Started: {exe_path.name}")
        except Exception as exc:
            print(f"Failed to launch: {exc}")

    page.add(
        ft.Row(
            expand=True,
            spacing=0,
            controls=[
                sidebar,
                ft.Container(
                    expand=True,
                    padding=ft.Padding.only(left=38, top=30, right=38, bottom=18),
                    content=ft.Column(
                        expand=True,
                        controls=[
                            content,
                            ft.Row(
                                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                controls=[
                                    save_note,
                                    ft.FilledButton(
                                        "Restart PrePaste",
                                        icon=ft.Icons.REFRESH_ROUNDED,
                                        style=ft.ButtonStyle(
                                            bgcolor=PURPLE, color=ft.Colors.WHITE
                                        ),
                                        on_click=restart_prepaste,
                                    ),
                                ],
                            ),
                        ],
                    ),
                ),
            ],
        )
    )
    show_page("Protection")


if __name__ == "__main__":
    ft.run(main)
