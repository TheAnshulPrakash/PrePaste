from __future__ import annotations

from datetime import datetime
from pathlib import Path
import subprocess
import time
import flet as ft

from config_store import (
    load_settings,
    save_settings,
)
from .views import (
    protection_view,
    credentials_view,
    preferences_view,
    history_view,
    about_view,
)

from .constants import (
    PRIMARY,
    INK,
    MUTED,
    BORDER,
    CARD,
    ICON_BG,
    CANVAS,
    LOGO_IMAGE,
    SUCCESS,
)

views = {
    "Protection": protection_view,
    "API keys": credentials_view,
    "Preferences": preferences_view,
    "History": history_view,
    "About": about_view,
}


def main(page: ft.Page) -> None:
    page.title = "PrePaste Settings"
    page.theme_mode = ft.ThemeMode.DARK
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

    def show_page(name: str) -> None:
        nonlocal current_page
        current_page = name
        content.controls = views[name](
            state,
            persist,
            show_page,
            notify,
        )
        for label, button in nav_buttons.items():
            selected = label == name
            button.bgcolor = "#1B1F25" if selected else None
            nav_labels[label].color = PRIMARY if selected else MUTED
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
                controls=[ft.Icon(icon, size=18, color=PRIMARY), label_control],
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
                            content=ft.Image(
                                LOGO_IMAGE, color=PRIMARY, width=41, height=41
                            ),
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
                                color=PRIMARY,
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
        for process_name in ("prepaste.exe", "prepaste_dummy.exe"):
            subprocess.run(
                ["taskkill", "/F", "/IM", process_name, "/T"],
                capture_output=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )

        time.sleep(0.5)

        config = load_settings()
        show_flet_notification = config.get("show_flet_notification", False)

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
                                            bgcolor=PRIMARY, color=ft.Colors.WHITE
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
