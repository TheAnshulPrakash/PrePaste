from __future__ import annotations

from datetime import datetime
from pathlib import Path
import subprocess
import sys

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

from constants import (
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
            "What should PrePaste protect?",
            "Choose the information types that should trigger a warning before you paste.",
        ),
        card(*controls),
    ]


def preferences_view(state: dict, persist, refresh, notify) -> list[ft.Control]:
    model_options = [
        ft.DropdownOption(
            key="en_core_web_sm",
            text="Small — quicker, lower memory",
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
                "Choose an appropriate language model",
            ),
            ft.Dropdown(
                value=state["model"],
                options=model_options,
                border_color=BORDER,
                focused_border_color=PRIMARY,
                on_select=model_changed,
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
                divisions=7,
                value=int(float(state["confidence_threshold"]) * 100),
                active_color=PRIMARY,
                on_change=threshold_changed,
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


def viewer_command(record_id: str) -> tuple[list[str], str] | None:
    ui_dir = Path(
        __file__
    ).parent.parent  # adjust if your file sits at a different depth
    project_root = ui_dir.parent
    exe_path = ui_dir / "viewer" / "redaction_viewer.exe"
    script_path = ui_dir / "viewer" / "redaction_viewer.py"

    if getattr(sys, "frozen", False):
        if exe_path.is_file():
            return [str(exe_path), "--id", record_id], str(exe_path.parent)
        return None

    if script_path.is_file():
        py = Path(sys.executable)
        pyw = py.with_name("pythonw.exe")
        interpreter = str(pyw if pyw.is_file() else py)
        return (
            [interpreter, "-m", "ui.viewer.redaction_viewer", "--id", record_id],
            str(project_root),
        )
    if exe_path.is_file():
        return [str(exe_path), "--id", record_id], str(exe_path.parent)
    return None


def history_view(state: dict, persist, refresh, notify) -> list[ft.Control]:
    entries = load_history()

    def open_in_viewer(entry: dict) -> None:
        record_id = entry.get("id")

        if not isinstance(record_id, str) or not record_id.strip():
            notify("This history record cannot be opened")
            return

        launch = viewer_command(record_id.strip())
        if launch is None:
            notify("The redaction viewer was not found")
            return

        command, cwd = launch
        print("CMD:", command, "CWD:", cwd)  # remove once working

        try:
            subprocess.Popen(
                command,
                cwd=cwd,
                creationflags=(
                    getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                    | getattr(subprocess, "CREATE_NO_WINDOW", 0)
                ),
            )
        except Exception as ex:
            print("Launch failed:", repr(ex))
            notify(f"Could not open the redaction viewer: {ex}")

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
    github_url = "https://github.com/TheAnshulPrakash/PrePaste/#prepaste"
    url_launcher = ft.UrlLauncher()
    url = ft.TextField(label="URL to open", value=github_url, expand=True)

    async def launch_default():
        await url_launcher.launch_url(url.value)

    return [
        card(
            ft.Column(
                spacing=12,
                controls=[
                    section_header(
                        "About PrePaste",
                        "A safer way to copy and paste.",
                    ),
                    ft.Text(
                        "PrePaste is a free, open-source clipboard privacy tool "
                        "designed to help prevent accidental exposure of "
                        "personal information and sensitive data.",
                        size=13,
                        color=INK,
                    ),
                    ft.Text(
                        "It monitors copied text for potentially sensitive "
                        "information, including passwords, API keys, and "
                        "personal details, helping you review and redact "
                        "content before sharing it.",
                        size=12,
                        color=MUTED,
                    ),
                ],
            ),
        ),
        card(
            ft.Column(
                spacing=12,
                controls=[
                    section_header(
                        "Privacy First",
                        "Your clipboard. Your control.",
                    ),
                    ft.Row(
                        spacing=10,
                        vertical_alignment=ft.CrossAxisAlignment.START,
                        controls=[
                            ft.Icon(
                                ft.Icons.LOCK_OUTLINE,
                                color=PRIMARY,
                                size=20,
                            ),
                            ft.Column(
                                spacing=4,
                                expand=True,
                                controls=[
                                    ft.Text(
                                        "Local processing",
                                        size=12,
                                        weight=ft.FontWeight.W_600,
                                        color=INK,
                                    ),
                                    ft.Text(
                                        "Clipboard content is analyzed directly "
                                        "on your device, without sending it "
                                        "to external detection services.",
                                        size=11,
                                        color=MUTED,
                                    ),
                                ],
                            ),
                        ],
                    ),
                    ft.Row(
                        spacing=10,
                        vertical_alignment=ft.CrossAxisAlignment.START,
                        controls=[
                            ft.Icon(
                                ft.Icons.HISTORY,
                                color=PRIMARY,
                                size=20,
                            ),
                            ft.Column(
                                spacing=4,
                                expand=True,
                                controls=[
                                    ft.Text(
                                        "Optional local history",
                                        size=12,
                                        weight=ft.FontWeight.W_600,
                                        color=INK,
                                    ),
                                    ft.Text(
                                        "When enabled, redaction history is "
                                        "stored locally under your Windows "
                                        "user profile.",
                                        size=11,
                                        color=MUTED,
                                    ),
                                ],
                            ),
                        ],
                    ),
                ],
            ),
        ),
        card(
            ft.Column(
                spacing=12,
                controls=[
                    section_header(
                        "Local Storage",
                        "Your data stays with you.",
                    ),
                    ft.Text(
                        "PrePaste stores application preferences and optional "
                        "redaction history locally under the current user.",
                        size=12,
                        color=MUTED,
                    ),
                    ft.Text(
                        "Settings",
                        size=12,
                        weight=ft.FontWeight.W_600,
                        color=INK,
                    ),
                    ft.Text(
                        str(settings_path()),
                        size=11,
                        color=MUTED,
                        selectable=True,
                    ),
                    ft.Divider(height=1),
                    ft.Text(
                        "History",
                        size=12,
                        weight=ft.FontWeight.W_600,
                        color=INK,
                    ),
                    ft.Text(
                        str(history_path()),
                        size=11,
                        color=MUTED,
                        selectable=True,
                    ),
                ],
            ),
        ),
        card(
            ft.Column(
                spacing=12,
                controls=[
                    section_header(
                        "Support PrePaste",
                        "Free, open source, and community-driven.",
                    ),
                    ft.Text(
                        "PrePaste is free to use and open source. "
                        "Our goal is to make everyday copy-and-paste "
                        "safer and more privacy-conscious for everyone.",
                        size=12,
                        color=INK,
                    ),
                    ft.Text(
                        "If you find PrePaste useful, you can support "
                        "the project by starring it on GitHub, sharing "
                        "it with others, or contributing ideas, "
                        "bug reports, code, and tests.",
                        size=12,
                        color=MUTED,
                    ),
                    ft.Divider(height=1),
                    ft.Row(
                        spacing=10,
                        vertical_alignment=ft.CrossAxisAlignment.START,
                        controls=[
                            ft.Icon(
                                ft.Icons.FAVORITE_BORDER,
                                color=PRIMARY,
                                size=20,
                            ),
                            ft.Column(
                                spacing=5,
                                expand=True,
                                controls=[
                                    ft.Text(
                                        "Support the maintainers",
                                        size=12,
                                        weight=ft.FontWeight.W_600,
                                        color=INK,
                                    ),
                                    ft.Text(
                                        "Individuals and companies who "
                                        "believe in the project can also "
                                        "support its maintainers through "
                                        "GitHub Sponsors. Sponsorship helps "
                                        "sustain development, maintenance, "
                                        "and future improvements.",
                                        size=12,
                                        color=MUTED,
                                    ),
                                ],
                            ),
                        ],
                    ),
                    ft.Text(
                        "Every star, share, contribution, and sponsorship "
                        "helps keep this open-source initiative growing. "
                        "Thank you for being part of it.",
                        size=11,
                        italic=True,
                        color=MUTED,
                    ),
                    ft.FilledButton(
                        "Explore on GitHub",
                        icon=ft.Icons.OPEN_IN_NEW,
                        bgcolor=PRIMARY,
                        on_click=launch_default,
                    ),
                ],
            ),
        ),
        ft.Container(
            alignment=ft.Alignment.CENTER,
            padding=ft.Padding.symmetric(
                vertical=16,
                horizontal=8,
            ),
            content=ft.Column(
                spacing=5,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Text(
                        "PrePaste  ·  v1.0.0  ·  Beaver-edition",
                        size=11,
                        weight=ft.FontWeight.W_600,
                        color=INK,
                    ),
                    ft.Text(
                        "Apache-2.0 license",
                        size=10,
                        color=MUTED,
                        text_align=ft.TextAlign.CENTER,
                    ),
                ],
            ),
        ),
    ]
