# main.py
import os
import re
import sys
import time
import signal as py_signal

from PySide6.QtCore import QThread, QTimer, Signal
from PySide6.QtWidgets import QApplication

from ui.notification.notification_bar import NotificationBar
from ui.notification.themes import DEFAULT_MENU_ITEMS

if getattr(sys, "frozen", False):
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_DIR, "en_core_web_sm-3.8.0")

CREDENTIAL_SETTING_TO_ENTITY = {
    "OpenAI API key": "OPENAI",
    "Anthropic API key": "ANTHROPIC",
    "Hugging Face token": "HUGGINGFACE",
    "GitHub personal access token": "GITHUB_PAT",
    "Google API key": "GOOGLE_API",
    "Google OAuth token": "GOOGLE_OAUTH",
    "AWS access key ID": "AWS_ACCESS_KEY",
    "Stripe secret key": "STRIPE",
    "Slack token": "SLACK",
    "MongoDB connection URI": "MONGODB_URI",
    "Supabase JWT": "SUPABASE_JWT",
}

API_PATTERNS = {
    "OpenAI": re.compile(r"(?:sk-[a-zA-Z0-9]{48}|sk-proj-[a-zA-Z0-9_-]+)"),
    "Anthropic": re.compile(r"sk-ant-api03-[a-zA-Z0-9\-_]{90,100}"),
    "HuggingFace": re.compile(r"hf_[a-zA-Z0-9]{34}"),
    "GitHub_PAT": re.compile(r"ghp_[a-zA-Z0-9]{36}"),
    "Google_API": re.compile(r"AIza[0-9A-Za-z\-_]{35}"),
    "Google_OAuth": re.compile(r"ya29\.[0-9A-Za-z\-_]+"),
    "AWS_Access_Key": re.compile(
        r"(?:AKIA|ASIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA)[A-Z0-9]{16}"
    ),
    "Stripe": re.compile(r"[rs]k_(?:test|live)_[0-9a-zA-Z]{24}"),
    "Slack": re.compile(r"xox[baprs]-[0-9a-zA-Z]{10,48}"),
    "MongoDB_URI": re.compile(r"mongodb(?:\+srv)?:\/\/[^\s]+:[^\s]+@[^\s]+"),
    "Supabase_JWT": re.compile(
        r"ey[A-Za-z0-9_-]{30,}\.[A-Za-z0-9_-]{30,}\.[A-Za-z0-9_-]{30,}"
    ),
}


class PiiWorker(QThread):
    """Loads Presidio, then monitors the clipboard. Never touches the UI directly."""

    ready = Signal()
    pii_found = Signal(list, str)
    redacted = Signal(int)
    failed = Signal(str)

    def __init__(self):
        super().__init__()
        self._running = True
        self._redact_requested = False

    def stop(self):
        self._running = False

    def request_redact(self):
        self._redact_requested = True

    def _load_engine(self):

        import pyperclip
        from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer
        from presidio_analyzer.nlp_engine import NlpEngineProvider
        from presidio_anonymizer import AnonymizerEngine
        from config_store import add_redaction_history_entry, load_settings

        self.pyperclip = pyperclip
        self.add_history = add_redaction_history_entry

        nlp_engine = NlpEngineProvider(
            nlp_configuration={
                "nlp_engine_name": "spacy",
                "models": [{"lang_code": "en", "model_name": MODEL_PATH}],
            }
        ).create_engine()

        self.analyzer = AnalyzerEngine(
            nlp_engine=nlp_engine, supported_languages=["en"]
        )
        self.anonymizer = AnonymizerEngine()

        settings = load_settings()
        self.threshold = float(settings.get("confidence_threshold", 0.5))

        allowed = {n for n, on in settings.get("entities", {}).items() if on}
        allowed |= {
            CREDENTIAL_SETTING_TO_ENTITY[n]
            for n, on in settings.get("credential_types", {}).items()
            if on and n in CREDENTIAL_SETTING_TO_ENTITY
        }

        for api_name, rx in API_PATTERNS.items():
            entity = api_name.upper()
            allowed.add(entity)
            self.analyzer.registry.add_recognizer(
                PatternRecognizer(
                    supported_entity=entity,
                    patterns=[
                        Pattern(name=f"{api_name}_pattern", regex=rx.pattern, score=1.0)
                    ],
                )
            )
        self.allowed = allowed

    def _scan(self, text):
        found = []
        for line_no, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            for r in self.analyzer.analyze(text=line, language="en"):
                if r.score <= self.threshold or r.entity_type not in self.allowed:
                    continue
                found.append(
                    {
                        "line": line_no,
                        "entity_type": r.entity_type,
                        "confidence": int(r.score * 100),
                        "text": line[r.start : r.end],
                    }
                )
                print(f"Found: Line {line_no}: {r.entity_type} ({int(r.score*100)}%)")
        return found

    def _redact(self, text):
        results = [
            r
            for r in self.analyzer.analyze(text=text, language="en")
            if r.score > self.threshold and r.entity_type in self.allowed
        ]
        if not results:
            return None, text
        out = self.anonymizer.anonymize(text=text, analyzer_results=results).text
        self.pyperclip.copy(out)
        lines = sorted({text.count("\n", 0, r.start) + 1 for r in results})
        hid = self.add_history(
            original_text=text, redacted_text=out, line_numbers=lines
        )
        return hid, out

    def run(self):
        try:
            self._load_engine()
        except Exception as e:
            self.failed.emit(str(e))
            return

        print("Monitoring clipboard for changes... Press Ctrl+C to stop.")
        self.ready.emit()

        try:
            last_text = self.pyperclip.paste()
        except Exception:
            last_text = ""

        while self._running:
            time.sleep(0.2)
            try:
                text = self.pyperclip.paste()
            except Exception:
                continue

            if self._redact_requested:
                self._redact_requested = False
                hid, new_text = self._redact(last_text)
                last_text = new_text
                self.redacted.emit(hid or 0)
                continue

            if text != last_text:
                last_text = text
                print("\n--- Clipboard Changed: Starting PII Scan ---\n")
                found = self._scan(text)
                print("\n--- Scan Complete ---\n")
                if found:
                    self.pii_found.emit(found, text)


def main():
    print("Loading smaller Presidio model...")
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # hiding the bar must not quit the app

    worker = PiiWorker()

    bar = NotificationBar.starting(menu_items=DEFAULT_MENU_ITEMS)
    bar.show_animated()

    # Connect once. The bar is never recreated.
    bar.primary_clicked.connect(worker.request_redact)
    bar.secondary_clicked.connect(lambda: print("secondary"))
    bar.option_selected.connect(lambda t: print("selected:", t))
    bar.disable_requested.connect(lambda m: print(f"disable notifications for {m} min"))
    bar.settings_requested.connect(lambda: print("open settings"))

    def on_ready():
        bar.present(
            status="ready",
            title="PrePaste is ready",
            message="Clipboard protection is active.",
            secondary_text="Dismiss",
            duration=10000,
        )

    def on_pii(entities, _text):
        kinds = ", ".join(sorted({e["entity_type"] for e in entities}))
        bar.present(
            status="warning",
            title="Sensitive data detected",
            message=f"{len(entities)} item(s): {kinds}",
            primary_text="Redact",
            secondary_text="Dismiss",
            duration=10000,
        )

    def on_redacted(_hid):
        bar.present(
            status="valid",
            title="Clipboard redacted",
            message="Sensitive data was replaced.",
            secondary_text="Dismiss",
            duration=5000,
        )

    def on_failed(msg):
        print(f"Failed to start PrePaste: {msg}")
        bar.present(
            status="warning",
            title="PrePaste failed to start",
            message=msg[:120],
            secondary_text="Dismiss",
            duration=10000,
        )

    worker.ready.connect(on_ready)
    worker.pii_found.connect(on_pii)
    worker.redacted.connect(on_redacted)
    worker.failed.connect(on_failed)

    py_signal.signal(py_signal.SIGINT, lambda *_: app.quit())
    tick = QTimer()
    tick.start(200)
    tick.timeout.connect(lambda: None)

    app.aboutToQuit.connect(lambda: (worker.stop(), worker.wait(2000)))

    worker.start()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
