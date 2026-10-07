import flet as ft
from .constants import (
    PRIMARY,
    INK,
    MUTED,
    BORDER,
    CARD,
    ICON_BG,
)


def title(eyebrow: str, heading: str, copy: str) -> ft.Control:
    return ft.Column(
        spacing=4,
        controls=[
            ft.Text(
                eyebrow.upper(), size=10, weight=ft.FontWeight.W_700, color=PRIMARY
            ),
            ft.Text(heading, size=28, weight=ft.FontWeight.BOLD, color=INK),
            ft.Text(copy, size=13, color=MUTED),
        ],
    )


def card(*controls: ft.Control, padding: int = 18) -> ft.Container:
    return ft.Container(
        bgcolor=CARD,
        border=ft.Border.all(1, BORDER),
        border_radius=14,
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
    state: dict,
    key: str,
    label: str,
    description: str,
    bucket: str,
    persist,
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
                    bgcolor=ICON_BG,
                    content=ft.Icon(icon, size=17, color=PRIMARY),
                ),
                ft.Column(
                    expand=True,
                    spacing=1,
                    controls=[
                        ft.Text(
                            label,
                            size=13,
                            weight=ft.FontWeight.W_600,
                            color=INK,
                        ),
                        ft.Text(
                            description,
                            size=10,
                            color=MUTED,
                        ),
                    ],
                ),
                ft.Switch(
                    value=bool(state[bucket].get(key, False)),
                    active_color=PRIMARY,
                    on_change=on_change,
                ),
            ],
        ),
    )
