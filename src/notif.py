import ctypes
from pathlib import Path
import subprocess
import flet as ft

import file


import asyncio
import time
import threading

import clipboard_observer

from clipboard_observer import pii_detected
from blinker import signal
import pyperclip
from config_store import select_redaction_for_viewer

WINDOW_WIDTH = 400
WINDOW_HEIGHT = 80

GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_FRAMECHANGED = 0x0020


async def main(page: ft.Page):

    page.title = "PrePaste"
    page.window.skip_task_bar = True
    page.window.title_bar_hidden = True
    page.window.frameless = True
    page.window.always_on_top = True
    page.window.width = WINDOW_WIDTH
    page.window.height = WINDOW_HEIGHT
    page.bgcolor = ft.Colors.TRANSPARENT
    page.window.bgcolor = ft.Colors.TRANSPARENT
    page.padding = 0

    # page.update()

    user32 = ctypes.windll.user32
    paused_until = 0.0

    physical_screen_width = user32.GetSystemMetrics(0)
    dpi = user32.GetDpiForSystem() or 96
    screen_width = round(physical_screen_width * 96 / dpi)
    config = file.load_config()

    page.window.top = max(0, config["top_margin"] - 4)
    page.window.left = max(0, screen_width - WINDOW_WIDTH - config["right_margin"])
    page.window.always_on_top = config["always_on_top"]

    user32 = ctypes.windll.user32
    hwnd = user32.FindWindowW(None, "PrePaste")
    if hwnd:
        style = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
        style = (style | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW
        user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, style)
        user32.SetWindowPos(
            hwnd,
            0,
            0,
            0,
            0,
            0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED,
        )

    current_clipboard_text = ""
    current_redaction_id = None

    is_hovering = False
    current_timer_id = 0
    is_showing_list = False

    def handle_hover(e):
        nonlocal is_hovering, current_timer_id
        is_hovering = str(e.data).lower() == "true"
        current_timer_id += 1

        if is_hovering:
            bar.opacity = 1
            page.update()
        else:
            page.run_task(auto_hide, current_timer_id)

    def sensitive_button_hover(e):
        page.window.width = WINDOW_WIDTH + 50 if e.data == "true" else WINDOW_WIDTH
        page.window.left = screen_width - page.window.width - config["right_margin"]
        page.update()

    def show_lists(e):
        nonlocal is_showing_list
        is_showing_list = not is_showing_list

        if is_showing_list:
            page.window.height = 300
            action_list.visible = True
            expand_button.icon = ft.Icons.EXPAND_LESS_ROUNDED
        else:
            page.window.height = WINDOW_HEIGHT
            action_list.visible = False
            expand_button.icon = ft.Icons.EXPAND_MORE_ROUNDED
        page.update()

    expand_button = ft.IconButton(
        width=36,
        height=36,
        bgcolor="#F4F2F8",
        icon=ft.Icons.EXPAND_MORE_ROUNDED,
        on_click=show_lists,
        icon_color="#242424",
    )

    async def rewrite_clicked(e):
        nonlocal current_redaction_id

        set_bar_state("success")

        bar.update()
        current_redaction_id = clipboard_observer.redact_clipboard()
        # await dim_and_hide(page)

    def deactivate_for_five_minutes(e):
        nonlocal paused_until, current_timer_id, is_showing_list

        paused_until = time.monotonic() + 300
        current_timer_id += 1  # Cancels any active auto-hide timer.

        is_showing_list = False
        action_list.visible = False
        page.window.height = WINDOW_HEIGHT
        expand_button.icon = ft.Icons.EXPAND_MORE_ROUNDED
        set_bar_state("active")
        page.update()

    # A beautifully compact top bar for the name and close button
    def open_settings(e):
        root_dir = Path(__file__).parent.parent
        exe_name = "prepaste.exe"
        exe_path = root_dir / "build_settings" / exe_name

        # 1. Check if file exists (Your original check)
        if not exe_path.is_file():
            print("hbuu here")
            print("Selection saved, but prepaste.exe was not found")
            return

        # 2. Close existing instances
        print(f"Closing any open instances of {exe_name}...")
        try:
            # /F (force) /IM (image name) /T (kill child processes)
            subprocess.run(
                ["taskkill", "/F", "/IM", exe_name, "/T"],
                capture_output=True,
                # Prevents a black cmd window from flashing during the kill command
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )

            # Wait a fraction of a second for Windows to release file locks
            time.sleep(0.5)
        except Exception as e:
            print(f"Warning during taskkill: {e}")
        print("Starting fresh instance...")
        try:
            process = subprocess.Popen(
                [str(exe_path)],
                cwd=str(exe_path.parent),
                creationflags=(
                    getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                    | getattr(subprocess, "DETACHED_PROCESS", 0)
                ),
            )
            print("Executable launched!")
            return process
        except Exception as e:
            print(f"Failed to launch: {e}")
            return None

    menu_button = ft.PopupMenuButton(
        bgcolor=ft.Colors.WHITE,
        icon=ft.Icons.MENU,
        icon_size=14,
        icon_color="#999999",
        width=24,
        height=24,
        tooltip="Menu",
        style=ft.ButtonStyle(
            padding=0,
        ),
        items=[
            ft.PopupMenuItem(
                content=ft.Text(
                    "Open settings", style=ft.TextStyle(size=11, color=ft.Colors.BLACK)
                ),
                on_click=open_settings,
                height=16,
            ),
            ft.PopupMenuItem(
                content=ft.Text(
                    "Deactivate for 5 minutes",
                    style=ft.TextStyle(size=11, color=ft.Colors.BLACK),
                ),
                on_click=deactivate_for_five_minutes,
                height=16,
            ),
        ],
    )
    top_bar = ft.Container(
        width=WINDOW_WIDTH,
        padding=ft.Padding(left=12, top=0, right=8, bottom=0),
        content=ft.Row(
            controls=[
                ft.Text(
                    "PREPASTE",
                    size=9,
                    weight=ft.FontWeight.BOLD,
                    color="#999999",
                ),
                ft.Container(expand=True),
                menu_button,
                ft.IconButton(
                    icon=ft.Icons.CLOSE_ROUNDED,
                    icon_size=14,
                    width=24,
                    height=24,
                    style=ft.ButtonStyle(
                        padding=0
                    ),  # Removes default Flet button padding
                    icon_color="#999999",
                    hover_color="#E0E0E0",
                    # Safely bind the close button to your hide function
                    on_click=lambda e: page.run_task(dim_and_hide, page),
                ),
            ],
        ),
    )
    hide_sensitive_button = ft.Container(
        width=82,
        height=38,
        border_radius=12,
        bgcolor="#FFF0F2",
        border=ft.Border.all(1, "#8066E9"),
        padding=ft.Padding(left=2, top=3, right=7, bottom=3),
        ink=True,
        on_hover=sensitive_button_hover,
        on_click=rewrite_clicked,
        animate=500,
        content=ft.Row(
            spacing=5,
            tight=True,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Icon(
                    ft.Icons.VISIBILITY_OFF_ROUNDED,
                    size=15,
                    color="#D94E64",
                ),
                ft.Container(
                    width=1,
                    height=20,
                    bgcolor="#EFC1C9",
                ),
                ft.Column(
                    spacing=0,
                    tight=True,
                    alignment=ft.MainAxisAlignment.CENTER,
                    controls=[
                        ft.Text(
                            "Hide",
                            size=9,
                            weight=ft.FontWeight.W_700,
                            color="#8E3344",
                            no_wrap=True,
                        ),
                        ft.Text(
                            "Sensitive",
                            size=9,
                            weight=ft.FontWeight.W_700,
                            color="#8E3344",
                            no_wrap=True,
                        ),
                    ],
                ),
            ],
        ),
    )

    bar_all_good = ft.Row(
        spacing=10,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[
            ft.Container(
                border_radius=5,
                content=ft.Image("PrePaste.png", width=32, height=32),
            ),
            ft.Column(
                expand=True,
                spacing=1,
                alignment=ft.MainAxisAlignment.CENTER,
                controls=[
                    ft.Text(
                        "Activated ",
                        size=13,
                        weight=ft.FontWeight.W_600,
                        color="#A964E7",
                    ),
                    ft.Text(
                        "PrePaste is checking before you paste.",
                        size=10,
                        color="#77747E",
                        no_wrap=True,
                    ),
                ],
            ),
        ],
    )

    bar_leak_identified = ft.Row(
        spacing=10,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[
            ft.Container(
                border_radius=5,
                content=ft.Icon(
                    icon=ft.Icons.WARNING_AMBER_ROUNDED,
                    size=28,
                    color=ft.Colors.RED_ACCENT,
                ),
            ),
            ft.Column(
                expand=True,
                spacing=1,
                alignment=ft.MainAxisAlignment.CENTER,
                controls=[
                    ft.Text(
                        "Warning",
                        size=13,
                        weight=ft.FontWeight.W_600,
                        color="#1C1B20",
                    ),
                    ft.Text(
                        "This paste could leak sensitive information.",
                        size=10,
                        color="#77747E",
                        no_wrap=True,
                    ),
                ],
            ),
            hide_sensitive_button,
            expand_button,
        ],
    )

    def open_current_redaction(e):
        print("coming here")
        if not current_redaction_id:
            print("shit happened")
            return

        try:
            select_redaction_for_viewer(current_redaction_id)
        except Exception as exc:
            print(f"Could not select redaction: {exc}")
            return

        root_dir = Path(__file__).resolve().parent.parent
        exe_path = root_dir / "build_viewer" / "prepaste.exe"

        if not exe_path.is_file():
            print(f"Viewer not found: {exe_path}")
            return

        subprocess.Popen(
            [str(exe_path)],
            cwd=str(exe_path.parent),
            creationflags=(
                getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                | getattr(subprocess, "DETACHED_PROCESS", 0)
            ),
        )

    bar_redacted_success = ft.Row(
        spacing=10,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[
            ft.Container(
                border_radius=5,
                content=ft.Icon(
                    icon=ft.Icons.CHECK_CIRCLE_OUTLINE_ROUNDED,
                    size=28,
                    color=ft.Colors.GREEN_ACCENT,
                ),
            ),
            ft.Column(
                expand=True,
                spacing=1,
                alignment=ft.MainAxisAlignment.CENTER,
                controls=[
                    ft.Text(
                        "Success",
                        size=13,
                        weight=ft.FontWeight.W_600,
                        color="#72DEA8",
                    ),
                    ft.Text(
                        "Clipboard is redacted",
                        size=10,
                        color="#141414",
                        no_wrap=True,
                    ),
                ],
            ),
            ft.Container(
                border_radius=5,
                content=ft.IconButton(
                    icon=ft.Icons.VISIBILITY_ROUNDED,
                    icon_size=20,
                    icon_color=ft.Colors.GREEN_ACCENT,
                    tooltip="Review redaction",
                    width=28,
                    height=28,
                    style=ft.ButtonStyle(padding=0),
                    on_click=open_current_redaction,
                ),
            ),
        ],
    )

    def set_bar_state(state: str):
        if state == "active":
            bar.content = bar_all_good
            bar.border = ft.Border.all(2, "#9A66E9")  # Green for active
        elif state == "warning":
            bar.content = bar_leak_identified
            bar.border = ft.Border.all(2, ft.Colors.RED_ACCENT)  # Red for warning
        elif state == "success":
            bar.content = bar_redacted_success
            bar.border = ft.Border.all(2, "#72DEA8")  # Green for redacted

        if bar.page:
            bar.update()

    bar = ft.Container(
        width=WINDOW_WIDTH,
        height=50,
        border=ft.Border.all(1, ft.Colors.RED_ACCENT),
        border_radius=25,
        bgcolor=ft.Colors.WHITE,
        animate_opacity=700,
        on_hover=handle_hover,
        padding=ft.Padding(left=16, right=7),
        shadow=ft.BoxShadow(
            blur_radius=18,
            spread_radius=0,
            color=ft.Colors.with_opacity(0.13, ft.Colors.BLACK),
            offset=ft.Offset(0, 5),
        ),
        content=bar_all_good,
    )

    def create_leak_item(match):
        entity_label = match["entity_type"].replace("_", " ").title()
        confidence = match["confidence"]

        # Yellow for <= 85%; red above 85%.
        status_color = "#F2B84B" if confidence <= 85 else "#F05268"

        return ft.Container(
            width=320,
            height=62,
            border_radius=15,
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            padding=ft.Padding(left=12, top=6, right=12, bottom=6),
            # Glass effect
            bgcolor=ft.Colors.with_opacity(0.70, ft.Colors.WHITE),
            blur=18,
            border=ft.Border.all(
                1,
                ft.Colors.with_opacity(0.55, ft.Colors.WHITE),
            ),
            shadow=ft.BoxShadow(
                blur_radius=16,
                spread_radius=0,
                color=ft.Colors.with_opacity(0.12, ft.Colors.BLACK),
                offset=ft.Offset(0, 5),
            ),
            data=match,
            content=ft.Row(
                spacing=9,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Container(
                        width=28,
                        height=28,
                        border_radius=9,
                        bgcolor=ft.Colors.with_opacity(0.20, status_color),
                        alignment=ft.Alignment.CENTER,
                        content=ft.Icon(
                            ft.Icons.WARNING_AMBER_ROUNDED,
                            size=16,
                            color=status_color,
                        ),
                    ),
                    ft.Column(
                        expand=True,
                        spacing=0,
                        alignment=ft.MainAxisAlignment.CENTER,
                        controls=[
                            ft.Text(
                                match["text"],
                                size=12,
                                weight=ft.FontWeight.W_600,
                                color="#29252E",
                                max_lines=1,
                                overflow=ft.TextOverflow.ELLIPSIS,
                            ),
                            ft.Text(
                                f'Line {match["line"]}  •  {confidence}% confidence',
                                size=9,
                                color="#716B77",
                                max_lines=1,
                            ),
                            ft.Text(
                                entity_label,
                                size=8,
                                weight=ft.FontWeight.W_600,
                                color="#9C5362",
                                max_lines=1,
                            ),
                        ],
                    ),
                    ft.Icon(
                        ft.Icons.CIRCLE,
                        size=13,
                        color=status_color,
                    ),
                ],
            ),
        )

    list_view = ft.ListView(expand=True, spacing=4, padding=10, controls=[])

    action_list = ft.Container(
        animate_opacity=400,
        on_hover=handle_hover,
        height=200,
        content=list_view,
        visible=False,
    )

    notification_box = ft.Container(
        border_radius=25,
        content=ft.Column(
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=2,
            controls=[
                top_bar,
                bar,
                action_list,
            ],
        ),
        animate_size=400,
        animate_opacity=400,
    )

    page.add(
        ft.Column(
            controls=[notification_box],
        )
    )

    async def dim_and_hide(page: ft.Page):
        bar.opacity = 0
        page.update()
        await asyncio.sleep(0.7)
        page.window.visible = False
        page.update()

    async def auto_hide(timer_id):

        for _ in range(100):
            if current_timer_id != timer_id:
                return
            await asyncio.sleep(0.1)

        notification_box.opacity = 0

        bar.opacity = 0
        page.update()

        await asyncio.sleep(0.7)

        if current_timer_id != timer_id:
            return

        page.window.visible = False

        page.update()

        if is_hovering:
            bar.opacity = 1
            page.update()
            page.run_task(auto_hide, timer_id)
            return

        page.window.visible = False
        page.update()

    async def show_timed_notification():
        nonlocal current_timer_id
        current_timer_id += 1

        page.window.visible = True
        notification_box.opacity = 1
        bar.opacity = 0
        page.update()

        await asyncio.sleep(0.02)

        bar.opacity = 1
        page.update()

        if not is_hovering:
            page.run_task(auto_hide, current_timer_id)

    async def process_new_clipboard(full_text, detected_entities, no_of_entities):
        nonlocal current_clipboard_text, is_showing_list

        matches = list(detected_entities or [])
        has_leak = no_of_entities > 0 and bool(matches)

        # Clean clipboard content must not show, resize, or update the notification.
        if not has_leak:
            return

        current_clipboard_text = full_text
        page.window.focused = False
        is_showing_list = False
        action_list.visible = False
        page.window.height = WINDOW_HEIGHT
        expand_button.icon = ft.Icons.EXPAND_MORE_ROUNDED

        list_view.controls.clear()
        for match in matches:
            list_view.controls.append(create_leak_item(match))

        set_bar_state("warning")
        page.update()
        await show_timed_notification()

    def listener(sender, **kwargs):
        if time.monotonic() < paused_until:
            return

        detected_entities = kwargs.get("detected_entities", [])
        no_of_entities = int(kwargs.get("no_of_entities") or 0)

        if no_of_entities <= 0 or not detected_entities:
            return

        page.run_task(
            process_new_clipboard,
            kwargs.get("full_text", ""),
            detected_entities,
            no_of_entities,
        )

    # Connect to blinker signal
    pii_detected.connect(listener, weak=False)

    page.window.visible = False
    page.update()
    await page.window.wait_until_ready_to_show()

    # Show the “Activated” acknowledgement once when the app starts.
    await show_timed_notification()

    # Start listening only after the UI and signal listener are ready.
    threading.Thread(
        target=clipboard_observer.run,
        daemon=True,
        name="clipboard-observer",
    ).start()


ft.run(main, view=ft.AppView.FLET_APP_HIDDEN, assets_dir="assets/")
