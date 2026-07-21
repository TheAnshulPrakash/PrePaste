import os
import re
import sys
import time
from presidio_anonymizer import AnonymizerEngine
import pyperclip
from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer
from presidio_analyzer.nlp_engine import NlpEngineProvider
from blinker import signal
from config_store import add_redaction_history_entry, load_settings

print("Loading smaller Presidio model...")

# 1. Define the signal
pii_detected = signal("pii_detected")

if getattr(sys, "frozen", False):
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_DIR, "en_core_web_sm-3.8.0")
configuration = {
    "nlp_engine_name": "spacy",
    "models": [{"lang_code": "en", "model_name": MODEL_PATH}],
}

provider = NlpEngineProvider(nlp_configuration=configuration)
nlp_engine = provider.create_engine()

analyzer = AnalyzerEngine(
    nlp_engine=nlp_engine,
    supported_languages=["en"],
)

SETTINGS = load_settings()
anonymizer = AnonymizerEngine()

CONFIDENCE_THRESHOLD = float(SETTINGS.get("confidence_threshold", 0.5))
SCAN_CLIPBOARD = bool(SETTINGS.get("scan_clipboard", True))
REDACT_ON_REQUEST = bool(SETTINGS.get("redact_on_request", True))
SHOW_DESKTOP_ALERTS = bool(SETTINGS.get("show_desktop_alerts", True))

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
    "Google_API": re.compile(r"AIza[0-9A-Za-z-_]{35}"),
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


def get_allowed_entities() -> set[str]:
    enabled_pii = {
        name for name, enabled in SETTINGS.get("entities", {}).items() if enabled
    }

    enabled_credentials = {
        CREDENTIAL_SETTING_TO_ENTITY[name]
        for name, enabled in SETTINGS.get("credential_types", {}).items()
        if enabled and name in CREDENTIAL_SETTING_TO_ENTITY
    }

    return enabled_pii | enabled_credentials


ALLOWED_ENTITIES = get_allowed_entities()

for api_name, regex_pattern in API_PATTERNS.items():

    entity_name = api_name.upper()

    # Add it to our allowed list so the script knows to process it
    ALLOWED_ENTITIES.add(entity_name)

    # Create the Presidio Recognizer (score 1.0 means 100% confidence on regex match)
    pattern = Pattern(
        name=f"{api_name}_pattern", regex=regex_pattern.pattern, score=1.0
    )
    recognizer = PatternRecognizer(supported_entity=entity_name, patterns=[pattern])

    # Add it to the main analyzer
    analyzer.registry.add_recognizer(recognizer)


def redact_clipboard():
    """Reads the current clipboard, anonymizes it, and writes it back."""
    try:
        text = pyperclip.paste()
        if not text.strip():
            return

        results = analyzer.analyze(text=text, language="en")

        # Filter for only ALLOWED_ENTITIES
        filtered_results = [
            res
            for res in results
            if res.score > 0.50 and res.entity_type in ALLOWED_ENTITIES
        ]

        if filtered_results:
            anonymized_result = anonymizer.anonymize(
                text=text, analyzer_results=filtered_results
            )
            # Write the safe text back to the clipboard
            pyperclip.copy(anonymized_result.text)
            line_numbers = sorted(
                {text.count("\n", 0, result.start) + 1 for result in filtered_results}
            )

            history_id = add_redaction_history_entry(
                original_text=text,
                redacted_text=anonymized_result.text,
                line_numbers=line_numbers,
            )
            print("Clipboard successfully redacted!")
            return history_id
    except Exception as e:
        print(f"Failed to redact clipboard: {e}")
        return None


# 4. Connect the function to the signal


def scan_for_pii(text):
    print(ALLOWED_ENTITIES)
    lines = text.splitlines()

    # Store our formatted results here
    detected_pii_list = []

    for line_number, line_text in enumerate(lines, start=1):
        if not line_text.strip():
            continue

        results = analyzer.analyze(text=line_text, language="en")

        for result in results:
            if (
                result.score <= CONFIDENCE_THRESHOLD
                or result.entity_type not in ALLOWED_ENTITIES
            ):

                continue

            extracted_pii = line_text[result.start : result.end]
            score_percent = int(result.score * 100)
            pii_info = f"Line {line_number}: {result.entity_type} ({score_percent}% '{extracted_pii}')"
            detected_pii_list.append(
                {
                    "line": line_number,
                    "entity_type": result.entity_type,
                    "confidence": int(result.score * 100),
                    "text": extracted_pii,
                }
            )

            print(f"Found: {pii_info} | Text: '{extracted_pii}'")

            # Signal to notif

    pii_detected.send(
        "clipboard_observer",
        full_text=text,
        detected_entities=detected_pii_list,
        no_of_entities=len(detected_pii_list),
    )


def on_clipboard_change(text):
    print("\n--- Clipboard Changed: Starting PII Scan ---\n")
    scan_for_pii(text)
    print("\n--- Scan Complete ---\n")


def run():
    last_text = pyperclip.paste()
    print("Monitoring clipboard for changes... Press Ctrl+C to stop.")

    while True:
        time.sleep(0.2)

        try:
            # Try to read the clipboard
            text = pyperclip.paste()
        except pyperclip.PyperclipException:
            # If the clipboard is temporarily locked by Windows or another app,
            # ignore the error and wait for the next loop to try again.
            continue
        except Exception as e:
            # Catching general exceptions just in case so the thread doesn't die
            continue

        if text != last_text:
            last_text = text
            on_clipboard_change(text)


# if __name__ == "__main__":
#     run()
