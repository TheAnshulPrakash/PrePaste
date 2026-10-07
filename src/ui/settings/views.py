from __future__ import annotations

from datetime import datetime
from pathlib import Path
import subprocess

import flet as ft

from config_store import (
    CREDENTIAL_TYPES,
    PII_ENTITIES,
    clear_history,
    data_directory,
    history_path,
    load_history,
    select_redaction_for_viewer,
    settings_path,
)

from .constants import (
    PRIMARY,
    INK,
    MUTED,
    BORDER,
    ENTITY_DETAILS,
    CREDENTIAL_DETAILS,
)
from .components import card, section_header, title, toggle_row


def protection_view(state: dict, persist, refresh, notify) -> list[ft.Control]:
    enabled = sum(bool(value) for value in state["entities"].values())

    personal_controls = [
        section_header(
            "Personal data",
            f"{enabled} of {len(PII_ENTITIES)} detectors enabled",
        ),
        ft.Divider(height=1, color=BORDER),
    ]

    personal_controls.extend(
        toggle_row(
            state=state,
            key=key,
            label=ENTITY_DETAILS[key][0],
            description=ENTITY_DETAILS[key][1],
            bucket="entities",
            persist=persist,
            icon=ft.Icons.PERSON_OUTLINE,
        )
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


def credentials_view(state: dict, persist, refresh, notify) -> list[ft.Control]:
    enabled = sum(bool(value) for value in state["credential_types"].values())
    all_enabled = enabled == len(CREDENTIAL_TYPES)

    def set_all(e: ft.ControlEvent) -> None:
        for key in state["credential_types"]:
            state["credential_types"][key] = bool(e.control.value)

        persist("All credential detectors updated")
        refresh("API keys")

    controls = [
        section_header(
            "Credential patterns",
            f"{enabled} of {len(CREDENTIAL_TYPES)} patterns enabled",
            ft.Switch(
                value=all_enabled,
                active_color=PRIMARY,
                on_change=set_all,
            ),
        ),
        ft.Divider(height=1, color=BORDER),
    ]

    controls.extend(
        toggle_row(
            state=state,
            key=key,
            label=CREDENTIAL_DETAILS[key][0],
            description=CREDENTIAL_DETAILS[key][1],
            bucket="credential_types",
            persist=persist,
            icon=ft.Icons.KEY_OUTLINED,
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


def preferences_view(state: dict, persist, refresh, notify) -> list[ft.Control]:
    model_options = [
        ft.dropdown.Option(
            "en_core_web_sm",
            "Small — quicker, lower memory",
        ),
    ]

    def model_changed(e: ft.ControlEvent) -> None:
        state["model"] = e.control.value
        persist("Language model saved")

    def threshold_changed(e: ft.ControlEvent) -> None:
        state["confidence_threshold"] = int(e.control.value) / 100
        threshold_label.value = f"{int(e.control.value)}% confidence"
        threshold_label.update()
        persist("Confidence threshold saved")

    def simple_toggle(
        key: str,
        label: str,
        description: str,
    ) -> ft.Control:
        def changed(e: ft.ControlEvent) -> None:
            state[key] = bool(e.control.value)
            persist("Preference saved")

        return ft.Switch(
            label=label,
            value=bool(state.get(key)),
            active_color=PRIMARY,
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
        color=PRIMARY,
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
                focused_border_color=PRIMARY,
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
                active_color=PRIMARY,
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
                    ft.dropdown.Option(
                        str(limit),
                        f"{limit} scans",
                    )
                    for limit in (25, 50, 100, 250)
                ],
                border_color=BORDER,
                focused_border_color=PRIMARY,
                on_text_change=history_limit_changed,
            ),
        ),
    ]


def history_view(state: dict, persist, refresh, notify) -> list[ft.Control]:
    entries = load_history()

    def open_in_viewer(entry: dict) -> None:
        record_id = entry.get("id")

        if not isinstance(record_id, str) or not record_id.strip():
            notify("This history record cannot be opened")
            return

        try:
            select_redaction_for_viewer(record_id)
        except Exception:
            notify("Could not select this redaction for review")
            return

        root_dir = Path(__file__).parent.parent.parent
        exe_path = root_dir / "build_viewer" / "prepaste.exe"

        if not exe_path.is_file():
            notify("Selection saved, but the redaction viewer was not found")
            return

        try:
            subprocess.Popen(
                [str(exe_path)],
                cwd=str(exe_path.parent),
                creationflags=(
                    getattr(
                        subprocess,
                        "CREATE_NEW_PROCESS_GROUP",
                        0,
                    )
                    | getattr(
                        subprocess,
                        "DETACHED_PROCESS",
                        0,
                    )
                ),
            )
        except Exception:
            notify("Could not open the redaction viewer")

    def delete_all(e: ft.ControlEvent) -> None:
        clear_history()
        notify("History deleted")
        refresh("History")

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

    rows: list[ft.Control] = [
        header,
        ft.Divider(height=1, color=BORDER),
    ]

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
                    str(entry["timestamp"]).replace(
                        "Z",
                        "+00:00",
                    )
                )
                .astimezone()
                .strftime("%d %b, %I:%M %p")
            )
        except (KeyError, ValueError):
            happened = "Unknown time"

        line_numbers = entry.get("line_numbers", [])
        line_label = ", ".join(str(line) for line in line_numbers) or "—"

        count = (
            len(line_numbers) if line_numbers else int(entry.get("finding_count", 0))
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
                    ft.Icons.PRIVACY_TIP_OUTLINED,
                    color="#D7546A",
                    size=17,
                ),
            ),
            ft.Column(
                expand=True,
                spacing=1,
                controls=description_controls,
            ),
            ft.Column(
                horizontal_alignment=ft.CrossAxisAlignment.END,
                spacing=1,
                controls=[
                    ft.Text(
                        happened,
                        size=10,
                        color=MUTED,
                    ),
                    ft.Text(
                        str(entry.get("source", "Scan")),
                        size=9,
                        color=PRIMARY,
                    ),
                ],
            ),
        ]

        if can_open:
            row_controls.append(
                ft.Icon(
                    ft.Icons.CHEVRON_RIGHT,
                    color="#B2AABD",
                    size=18,
                )
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
                content=ft.Row(
                    controls=row_controls,
                ),
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


def about_view(state: dict, persist, refresh, notify) -> list[ft.Control]:
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
                            ft.Icons.SHIELD_OUTLINED,
                            size=27,
                            color=PRIMARY,
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
                "PrePaste checks clipboard text locally using Microsoft "
                "Presidio and optional, format-based credential detectors. "
                "It warns you before a paste may expose personal data or "
                "secrets to online forums or LLMs.",
                size=13,
                color=INK,
            ),
            ft.Text(
                "Privacy promise",
                size=14,
                weight=ft.FontWeight.W_700,
                color=INK,
            ),
            ft.Text(
                "Your copied text is processed on your computer. When "
                "history is enabled, each redaction stores the full "
                "original and redacted text only in this Windows user's "
                "local history file.",
                size=12,
                color=MUTED,
            ),
            ft.Text(
                "If you like this project, consider giving it a star ⭐",
                size=12,
                color=MUTED,
            ),
            ft.Text(
                "Found a bug? Have a feature request? I'd love to hear "
                "from you 😊\nPlease open an issue on GitHub.",
                size=12,
                color=MUTED,
            ),
        ),
        card(
            section_header(
                "Local files",
                "These files belong only to the current user.",
            ),
            ft.Text(
                f"Settings: {settings_path()}",
                size=11,
                color=INK,
                selectable=True,
            ),
            ft.Text(
                f"History: {history_path()}",
                size=11,
                color=INK,
                selectable=True,
            ),
            ft.Text(
                "Version 1.0 ● Beaver",
                size=11,
                color=MUTED,
            ),
        ),
    ]
