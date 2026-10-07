import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from ui.notification.notification_bar import NotificationBar
from ui.notification.themes import DEFAULT_MENU_ITEMS

if __name__ == "__main__":
    app = QApplication(sys.argv)

    bar = NotificationBar.starting(menu_items=DEFAULT_MENU_ITEMS)
    bar.show_animated()

    def on_ready():

        bar.set_state(
            status="risky",
            title="PrePaste is ready",
            message="Clipboard protection is active.",
            loading=False,
            secondary_text="Dismiss",
            duration=10000,
        )

    QTimer.singleShot(2000, on_ready)

    bar.primary_clicked.connect(lambda: print("primary ->", bar.selected_option()))
    bar.secondary_clicked.connect(lambda: print("secondary"))
    bar.option_selected.connect(lambda text: print("selected:", text))
    bar.disable_requested.connect(lambda m: print(f"disable notifications for {m} min"))
    bar.settings_requested.connect(lambda: print("open settings"))

    sys.exit(app.exec())
