from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
import subprocess
import time
import flet as ft
import sys
import platform
import psutil


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

from constants import (
    PRIMARY,
    INK,
    MUTED,
    BORDER,
    CARD,
    CANVAS,
    LOGO_IMAGE,
    SUCCESS,
    MUTED_SOFT,
)

views = {
    "Protection": protection_view,
    "API keys": credentials_view,
    "Preferences": preferences_view,
    "History": history_view,
    "About": about_view,
}

SYSTEM = platform.system()  # "Windows", "Darwin", "Linux"
IS_FROZEN = getattr(sys, "frozen", False)
EXE_SUFFIX = ".exe" if SYSTEM == "Windows" else ""

ROOT_DIR = (
    Path(sys.executable).parent if IS_FROZEN else Path(__file__).parent.parent.parent
)

PREPASTE_EXE = ROOT_DIR / "dist" / f"prepaste{EXE_SUFFIX}"
PREPASTE_SCRIPT = ROOT_DIR / "main.py"


def _is_prepaste(proc: psutil.Process) -> bool:
    name = (proc.info["name"] or "").lower().removesuffix(".exe")
    if IS_FROZEN:
        return name == "prepaste"

    if not name.startswith("python"):
        return False
    cwd = Path(proc.cwd())
    for arg in proc.info["cmdline"] or []:
        if (
            Path(arg).name == "main.py"
            and (cwd / arg).resolve() == PREPASTE_SCRIPT.resolve()
        ):
            return True
    return False


def _stop_prepaste() -> None:
    own_pid = os.getpid()
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            if proc.info["pid"] == own_pid or not _is_prepaste(proc):
                continue
            for child in proc.children(recursive=True):
                child.kill()
            proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue


def _launch_command() -> tuple[list[str], Path] | None:
    if IS_FROZEN:
        if SYSTEM == "Darwin":
            app_bundle = PREPASTE_EXE.with_suffix(".app")
            if app_bundle.exists():
                return ["open", "-n", str(app_bundle)], app_bundle.parent
        if not PREPASTE_EXE.is_file():
            print(f"Program not found: {PREPASTE_EXE}")
            return None
        return [str(PREPASTE_EXE)], PREPASTE_EXE.parent

    if not PREPASTE_SCRIPT.is_file():
        print(f"Script not found: {PREPASTE_SCRIPT}")
        return None

    python = Path(sys.executable)
    if SYSTEM == "Windows":
        pythonw = python.with_name("pythonw.exe")  # no console window
        if pythonw.exists():
            python = pythonw
    return [str(python), str(PREPASTE_SCRIPT)], PREPASTE_SCRIPT.parent


def _spawn_detached(cmd: list[str], cwd: Path) -> None:
    kwargs: dict = {"cwd": str(cwd)}
    if SYSTEM == "Windows":
        kwargs["creationflags"] = getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0
        ) | getattr(subprocess, "DETACHED_PROCESS", 0)
    else:
        kwargs["start_new_session"] = True
        kwargs["stdin"] = subprocess.DEVNULL
        kwargs["stdout"] = subprocess.DEVNULL
        kwargs["stderr"] = subprocess.DEVNULL
    subprocess.Popen(cmd, **kwargs)


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
    save_note = ft.Text(" ", size=11, color=MUTED)

    def notify(message: str) -> None:
        page.snack_bar = ft.SnackBar(ft.Text(message), bgcolor=INK, open=True)
        page.update()

    def persist(message: str = "Saved") -> None:
        save_settings(state)
        save_note.value = "Restart to apply changes"
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
                            ft.Text("Star Us ♡"),
                        ],
                    ),
                ),
            ],
        ),
    )

    def restart_prepaste(e):
        _stop_prepaste()
        time.sleep(0.5)

        launch = _launch_command()
        if launch is None:
            notify("Could not find PrePaste to restart")
            return

        cmd, cwd = launch
        try:
            _spawn_detached(cmd, cwd)
            save_note.value = " "
            save_note.update()
        except Exception as exc:
            notify(f"Failed to launch: {exc}")

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
                                            bgcolor=PRIMARY, color=CANVAS
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
