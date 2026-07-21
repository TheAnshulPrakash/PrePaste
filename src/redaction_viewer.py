r"""Standalone side-by-side viewer for saved PrePaste redactions.

The viewer reads %LOCALAPPDATA%\PrePaste\history.json and the small pointer
file %LOCALAPPDATA%\PrePaste\viewer_selection.json.  The pointer is simply:

    {"id": "the-redaction-id-to-open"}

Use config_store.select_redaction_for_viewer(record_id) in the producing app
to write that pointer atomically before launching this script.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import flet as ft

from config_store import history_path, viewer_selection_path

PURPLE = "#7357E8"
INK = "#252033"
MUTED = "#756E82"
CANVAS = "#F7F5FC"
CARD = "#FFFFFF"
BORDER = "#E8E3F1"
ALERT = "#D94E64"
ALERT_SOFT = "#FFF4F5"
SUCCESS = "#23A56A"


def _read_json(path: Path) -> tuple[Any | None, str | None]:
    """Read JSON without letting a missing or half-written file crash the UI."""
    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file), None
    except FileNotFoundError:
        return None, "missing"
    except json.JSONDecodeError:
        return None, "invalid JSON"
    except OSError:
        return None, "unreadable"


def _clean_line_numbers(value: Any) -> list[int]:
    if not isinstance(value, list):
        return []
    result: set[int] = set()
    for line in value:
        try:
            number = int(line)
        except (TypeError, ValueError):
            continue
        if number > 0:
            result.add(number)
    return sorted(result)


def load_redactions() -> tuple[list[dict[str, Any]], str | None]:
    raw, error = _read_json(history_path())
    if error:
        return [], error
    if not isinstance(raw, list):
        return [], "history is not a JSON list"

    records: list[dict[str, Any]] = []
    for candidate in raw:
        if not isinstance(candidate, dict):
            continue
        record_id = candidate.get("id")
        original = candidate.get("original_text")
        redacted = candidate.get("redacted_text")
        if not isinstance(record_id, str) or not record_id.strip():
            continue
        if not isinstance(original, str) or not isinstance(redacted, str):
            continue
        records.append(
            {
                **candidate,
                "id": record_id.strip(),
                "line_numbers": _clean_line_numbers(candidate.get("line_numbers")),
            }
        )
    return records, None


def load_selected_id() -> tuple[str | None, str | None]:
    """Support both {"id": "..."} and a bare JSON string for convenience."""
    raw, error = _read_json(viewer_selection_path())
    if error:
        return None, error
    if isinstance(raw, str) and raw.strip():
        return raw.strip(), None
    if isinstance(raw, dict):
        value = raw.get("id", raw.get("redaction_id"))
        if isinstance(value, str) and value.strip():
            return value.strip(), None
    return None, "missing id"


def resolve_record() -> tuple[dict[str, Any] | None, str, str | None]:
    """Resolve the pointer, with a safe fallback to the newest usable record."""
    records, history_error = load_redactions()
    if history_error:
        return None, "", f"Could not load history: {history_error}."
    if not records:
        return None, "", "No valid redaction records were found."

    selected_id, selection_error = load_selected_id()
    if selected_id:
        for record in records:
            if record["id"] == selected_id:
                return record, "Selected redaction", None
        fallback_note = "Selected ID was not found"
    else:
        fallback_note = (
            "No usable selection file" if selection_error else "No selected ID"
        )

    newest = max(records, key=lambda record: str(record.get("timestamp", "")))
    return (
        newest,
        "Most recent redaction",
        f"{fallback_note}; showing the newest valid record instead.",
    )


def main(page: ft.Page) -> None:
    page.title = "PrePaste Redaction Viewer"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.bgcolor = CANVAS
    page.padding = 20
    page.window.width = 1420
    page.window.height = 900
    page.window.min_width = 980
    page.window.min_height = 640

    root = ft.Column(expand=True, spacing=14)

    def notify(message: str, color: str = INK) -> None:
        page.snack_bar = ft.SnackBar(ft.Text(message), bgcolor=color, open=True)
        page.update()

    async def copy_text(text: str, label: str) -> None:
        try:
            await ft.Clipboard().set(text)
        except Exception:
            notify(f"Could not copy {label.lower()}.", ALERT)
            return
        notify(f"{label} copied")

    def build_empty_state(message: str) -> list[ft.Control]:
        return [
            ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                controls=[
                    ft.Column(
                        spacing=2,
                        controls=[
                            ft.Text(
                                "Redaction viewer",
                                size=24,
                                weight=ft.FontWeight.BOLD,
                                color=INK,
                            ),
                            ft.Text(
                                "A focused, local review window for one saved redaction.",
                                size=12,
                                color=MUTED,
                            ),
                        ],
                    ),
                    ft.IconButton(
                        ft.Icons.REFRESH_ROUNDED,
                        tooltip="Reload files",
                        on_click=lambda e: reload_view(),
                    ),
                ],
            ),
            ft.Container(
                expand=True,
                alignment=ft.Alignment.CENTER,
                bgcolor=CARD,
                border=ft.Border.all(1, BORDER),
                border_radius=18,
                content=ft.Column(
                    tight=True,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=8,
                    controls=[
                        ft.Icon(ft.Icons.FOLDER_OFF_OUTLINED, size=44, color="#B2AABD"),
                        ft.Text(
                            "Nothing to review yet",
                            size=17,
                            weight=ft.FontWeight.W_700,
                            color=INK,
                        ),
                        ft.Text(
                            message,
                            size=12,
                            color=MUTED,
                            text_align=ft.TextAlign.CENTER,
                        ),
                        ft.Text(
                            f"History: {history_path()}",
                            size=10,
                            color=MUTED,
                            selectable=True,
                        ),
                        ft.Text(
                            f"Selection: {viewer_selection_path()}",
                            size=10,
                            color=MUTED,
                            selectable=True,
                        ),
                    ],
                ),
            ),
        ]

    def make_comparison(
        original: str, redacted: str, flagged_lines: set[int]
    ) -> ft.Control:
        """Render both texts in one scrollable surface so they never drift."""

        async def copy_original(e: ft.ControlEvent) -> None:
            await copy_text(original, "Original")

        async def copy_redacted(e: ft.ControlEvent) -> None:
            await copy_text(redacted, "Redacted")

        def pane_header(
            label: str, accent: str, on_copy: ft.ControlEventHandler
        ) -> ft.Control:
            return ft.Container(
                expand=True,
                padding=ft.Padding.symmetric(horizontal=14, vertical=10),
                bgcolor="#F9F7FD",
                content=ft.Row(
                    controls=[
                        ft.Container(
                            width=8, height=8, border_radius=4, bgcolor=accent
                        ),
                        ft.Text(
                            label,
                            expand=True,
                            size=12,
                            weight=ft.FontWeight.W_700,
                            color=INK,
                        ),
                        ft.IconButton(
                            ft.Icons.CONTENT_COPY_OUTLINED,
                            icon_size=17,
                            tooltip=f"Copy {label.lower()}",
                            on_click=on_copy,
                        ),
                    ],
                ),
            )

        def line_cell(number: int, line: str, flagged: bool) -> ft.Control:
            return ft.Container(
                expand=True,
                bgcolor=ALERT_SOFT if flagged else None,
                padding=ft.Padding.only(right=9),
                content=ft.Row(
                    spacing=0,
                    vertical_alignment=ft.CrossAxisAlignment.START,
                    controls=[
                        ft.Container(
                            width=17,
                            padding=ft.Padding.only(top=5),
                            alignment=ft.Alignment.TOP_CENTER,
                            content=(
                                ft.Icon(ft.Icons.CIRCLE, size=7, color=ALERT)
                                if flagged
                                else None
                            ),
                        ),
                        ft.Container(
                            width=42,
                            padding=ft.Padding.only(top=1, right=9),
                            alignment=ft.Alignment.TOP_RIGHT,
                            content=ft.Text(
                                str(number),
                                size=11,
                                color="#A49BAC",
                                font_family="Consolas",
                            ),
                        ),
                        ft.Container(
                            expand=True,
                            padding=ft.Padding.only(left=10, top=1, bottom=1),
                            border=ft.Border.only(left=ft.BorderSide(1, BORDER)),
                            content=ft.Text(
                                line if line else " ",
                                size=12,
                                color=INK,
                                font_family="Consolas",
                                selectable=True,
                            ),
                        ),
                    ],
                ),
            )

        original_lines = original.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        redacted_lines = redacted.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        total_lines = max(len(original_lines), len(redacted_lines))
        rows: list[ft.Control] = []
        for number in range(1, total_lines + 1):
            original_line = (
                original_lines[number - 1] if number <= len(original_lines) else ""
            )
            redacted_line = (
                redacted_lines[number - 1] if number <= len(redacted_lines) else ""
            )
            rows.append(
                ft.Row(
                    spacing=0,
                    vertical_alignment=ft.CrossAxisAlignment.START,
                    controls=[
                        line_cell(number, original_line, number in flagged_lines),
                        ft.Container(width=1, bgcolor=BORDER),
                        line_cell(number, redacted_line, number in flagged_lines),
                    ],
                )
            )

        return ft.Container(
            expand=True,
            bgcolor=CARD,
            border=ft.Border.all(1, BORDER),
            border_radius=16,
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            content=ft.Column(
                expand=True,
                spacing=0,
                controls=[
                    ft.Row(
                        spacing=0,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            pane_header("Original", ALERT, copy_original),
                            ft.Container(width=1, bgcolor=BORDER),
                            pane_header("Redacted", SUCCESS, copy_redacted),
                        ],
                    ),
                    ft.Container(height=1, bgcolor=BORDER),
                    ft.ListView(
                        expand=True,
                        spacing=0,
                        padding=ft.Padding.symmetric(horizontal=8, vertical=10),
                        controls=rows,
                    ),
                ],
            ),
        )

    def build_view(
        record: dict[str, Any], mode: str, fallback_note: str | None
    ) -> list[ft.Control]:
        original = str(record["original_text"])
        redacted = str(record["redacted_text"])
        flagged_lines = set(record["line_numbers"])
        file_name = str(
            record.get("file_name") or record.get("source") or "Clipboard redaction"
        )
        timestamp = str(record.get("timestamp") or "Unknown time")
        count = len(flagged_lines)

        header_controls: list[ft.Control] = [
            ft.Column(
                expand=True,
                spacing=2,
                controls=[
                    ft.Row(
                        spacing=8,
                        controls=[
                            ft.Icon(
                                ft.Icons.DESCRIPTION_OUTLINED, color=PURPLE, size=20
                            ),
                            ft.Text(
                                file_name, size=24, weight=ft.FontWeight.BOLD, color=INK
                            ),
                        ],
                    ),
                    ft.Text(
                        f"{mode}  •  {timestamp}  •  {count} flagged line{'s' if count != 1 else ''}",
                        size=12,
                        color=MUTED,
                    ),
                ],
            ),
            ft.IconButton(
                ft.Icons.REFRESH_ROUNDED,
                tooltip="Reload history and selection",
                on_click=lambda e: reload_view(),
            ),
        ]
        controls: list[ft.Control] = [ft.Row(controls=header_controls)]
        if fallback_note:
            controls.append(
                ft.Container(
                    padding=ft.Padding.symmetric(horizontal=12, vertical=8),
                    bgcolor="#FFF8E8",
                    border_radius=10,
                    content=ft.Row(
                        spacing=8,
                        controls=[
                            ft.Icon(ft.Icons.INFO_OUTLINE, size=16, color="#A77616"),
                            ft.Text(fallback_note, size=11, color="#725411"),
                        ],
                    ),
                )
            )
        controls.extend(
            [
                ft.Container(
                    padding=ft.Padding.symmetric(horizontal=12, vertical=8),
                    bgcolor=ALERT_SOFT,
                    border_radius=10,
                    content=ft.Row(
                        spacing=8,
                        controls=[
                            ft.Icon(ft.Icons.CIRCLE, size=8, color=ALERT),
                            ft.Text(
                                "Red dots mark lines where sensitive content was detected.",
                                size=11,
                                color="#8D3C4C",
                            ),
                        ],
                    ),
                ),
                make_comparison(original, redacted, flagged_lines),
                ft.Text(
                    f"Record ID: {record['id']}",
                    size=10,
                    color="#A49BAC",
                    selectable=True,
                ),
            ]
        )
        return controls

    def reload_view() -> None:
        record, mode, message = resolve_record()
        root.controls = (
            build_empty_state(message or "No history is available.")
            if record is None
            else build_view(record, mode, message)
        )
        page.update()

    page.add(root)
    reload_view()


if __name__ == "__main__":
    # Port 0 asks Windows for a fresh local port; it avoids sharing the port
    # already used by the Settings Flet process.
    ft.run(main, port=0)
