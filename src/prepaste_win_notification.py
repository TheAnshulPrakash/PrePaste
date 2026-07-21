import os
import sys
import time
import threading
import subprocess
from pathlib import Path
from win11toast import toast
from blinker import signal

# Import your redaction and viewer functions
from clipboard_observer import redact_clipboard
import clipboard_observer
from config_store import select_redaction_for_viewer

pii_detected = signal("pii_detected")

# Global state for pausing notifications
paused_until = 0.0
if getattr(sys, "frozen", False):
    # 1. ASSETS_DIR: Where the temporary files (Icon.png) are extracted
    ASSETS_DIR = Path(sys._MEIPASS)
    # 2. PROJECT_ROOT: Where the .exe physically lives.
    # sys.executable is usually in the "dist" folder, so we use .parent.parent to go up to the main PrePaste folder.
    PROJECT_ROOT = Path(sys.executable).parent.parent
else:
    # Normal Python script mode
    ASSETS_DIR = Path(__file__).resolve().parent
    PROJECT_ROOT = ASSETS_DIR.parent
ICON_PATH = str(ASSETS_DIR / "assets" / "Icon.png")
SUCCESS_ICON = "https://raw.githubusercontent.com/microsoft/FluentUI-System-Icons/main/assets/Checkmark%20Circle/SVG/ic_fluent_checkmark_circle_24_filled.svg"
WARNING_ICON = "https://raw.githubusercontent.com/microsoft/FluentUI-System-Icons/main/assets/Warning/SVG/ic_fluent_warning_24_filled.svg"


def show_startup_toast():
    """Confirmation that PrePaste has started monitoring."""
    toast(
        "PrePaste Activated",
        "PrePaste is checking before you paste.",
        icon=ICON_PATH if os.path.exists(ICON_PATH) else None,
        app_id="PrePaste",
        duration="short",
    )


def open_viewer(redaction_id):
    """Launches the viewer application for a specific redaction."""
    try:
        select_redaction_for_viewer(redaction_id)

        exe_path = PROJECT_ROOT / "build_viewer" / "prepaste.exe"
        if exe_path.is_file():
            subprocess.Popen(
                [str(exe_path)],
                cwd=str(exe_path.parent),
                creationflags=(
                    getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                    | getattr(subprocess, "DETACHED_PROCESS", 0)
                ),
            )
        else:
            print(f"Viewer not found at: {exe_path}")
    except Exception as exc:
        print(f"Could not open viewer: {exc}")


def open_settings():
    """Launches the settings application."""
    try:
        exe_path = PROJECT_ROOT / "build_settings" / "prepaste.exe"

        # Kill existing instances first to prevent duplicates
        subprocess.run(
            ["taskkill", "/F", "/IM", "prepaste.exe", "/T"],
            capture_output=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        time.sleep(0.5)

        if exe_path.is_file():
            subprocess.Popen(
                [str(exe_path)],
                cwd=str(exe_path.parent),
                creationflags=(
                    getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                    | getattr(subprocess, "DETACHED_PROCESS", 0)
                ),
            )
        else:
            print(f"Settings exe not found at: {exe_path}")
    except Exception as exc:
        print(f"Could not open settings: {exc}")


def handle_leak_notification(detected_entities):
    """
    Displays the native Windows toast notification for leaks.
    """
    global paused_until

    # Format the expanding details into a clean multiline string
    leak_details = []
    for match in detected_entities:
        entity_name = match["entity_type"].replace("_", " ").title()
        line = match["line"]
        conf = match["confidence"]
        leak_details.append(f"• Line {line}: {entity_name} ({conf}%)")

    formatted_body = "Sensitive data detected!\n" + "\n".join(leak_details)

    print("Showing leak notification...")

    # Block thread waiting for user action.
    # Swiping it away natively handles the "Ignore" action.
    result = toast(
        "PrePaste: Warning!",
        formatted_body,
        icon=ICON_PATH if os.path.exists(ICON_PATH) else WARNING_ICON,
        buttons=["Hide Sensitive", "Settings", "Pause 5m"],
        app_id="PrePaste",
        duration="long",
    )

    print(f"Toast interaction result: {result}")

    # Safely check if the result is a dictionary (button clicked) and not a tuple (timeout/swipe)
    if isinstance(result, dict) and "arguments" in result:
        choice = str(result["arguments"])

        if "Hide Sensitive" in choice:
            print(
                "User clicked 'Hide Sensitive'. Waiting 0.5s for Windows to release clipboard lock..."
            )
            time.sleep(0.5)

            print("Triggering redact_clipboard()...")
            redaction_id = redact_clipboard()

            if redaction_id:
                # Success Confirmation Toast
                success_result = toast(
                    "PrePaste: Success",
                    "Clipboard was successfully redacted and is safe to paste.",
                    icon=SUCCESS_ICON,
                    buttons=["Review Redaction", "Dismiss"],
                    app_id="PrePaste",
                )

                # Safely check success toast interaction
                if isinstance(success_result, dict) and "Review Redaction" in str(
                    success_result.get("arguments", "")
                ):
                    print("Opening viewer...")
                    open_viewer(redaction_id)

        elif "Settings" in choice:
            print("Opening PrePaste Settings...")
            open_settings()

        elif "Pause 5m" in choice:
            print("Pausing PrePaste for 5 minutes.")
            paused_until = time.monotonic() + 300
            toast(
                "PrePaste Paused",
                "Notifications and redactions disabled for 5 minutes.",
                icon=ICON_PATH if os.path.exists(ICON_PATH) else None,
                app_id="PrePaste",
                duration="short",
            )


def _listener(sender, **kwargs):
    """Receives the signal and spawns a thread for the notification."""
    global paused_until

    if time.monotonic() < paused_until:
        return

    detected_entities = kwargs.get("detected_entities", [])
    no_of_entities = int(kwargs.get("no_of_entities") or 0)

    if no_of_entities > 0 and detected_entities:
        threading.Thread(
            target=handle_leak_notification, args=(detected_entities,), daemon=True
        ).start()


def init_notifier():
    """Call this function once when your app starts to connect the signal."""
    pii_detected.connect(_listener, weak=False)
    print("Native Windows notifications enabled and listening.")
    show_startup_toast()


if __name__ == "__main__":
    # 1. Start the notification listener
    init_notifier()

    # 2. Run your clipboard observer loop
    clipboard_observer.run()
