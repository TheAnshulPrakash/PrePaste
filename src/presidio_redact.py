"""Report lines containing personally identifiable information with Presidio.

Install dependencies first:
    pip install -r requirements.txt
    python -m spacy download en_core_web_lg

Example:
    python presidio_redact.py "Email alex@example.com or call +1 555-123-4567."
"""

from __future__ import annotations

import argparse
import re
import sys

from config_store import add_history_entry, load_settings

# These are heuristic signatures, not proof that a value is an active credential.
# They are registered with Presidio, so PII and credential matches are produced by
# the same `analyzer.analyze()` call for every line.
API_KEY_PATTERNS: dict[str, re.Pattern[str]] = {
    "OpenAI API key": re.compile(r"(?:sk-[A-Za-z0-9]{48}|sk-proj-[A-Za-z0-9_-]+)"),
    "Anthropic API key": re.compile(r"sk-ant-api03-[A-Za-z0-9_-]{90,100}"),
    "Hugging Face token": re.compile(r"hf_[A-Za-z0-9]{34}"),
    "GitHub personal access token": re.compile(r"ghp_[A-Za-z0-9]{36}"),
    "Google API key": re.compile(r"AIza[0-9A-Za-z_-]{35}"),
    "Google OAuth token": re.compile(r"ya29\.[0-9A-Za-z_-]+"),
    "AWS access key ID": re.compile(
        r"(?:AKIA|ASIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA)[A-Z0-9]{16}"
    ),
    "Stripe secret key": re.compile(r"[rs]k_(?:test|live)_[0-9A-Za-z]{24}"),
    "Slack token": re.compile(r"xox[baprs]-[0-9A-Za-z]{10,48}"),
    "MongoDB connection URI": re.compile(r"mongodb(?:\+srv)?://[^\s]+:[^\s]+@[^\s]+"),
    "Supabase JWT": re.compile(
        r"ey[A-Za-z0-9_-]{30,}\.[A-Za-z0-9_-]{30,}\.[A-Za-z0-9_-]{30,}"
    ),
}


def build_analyzer(settings: dict | None = None):
    """Create one analyzer using the selected PrePaste model and detectors."""
    try:
        from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer
        from presidio_analyzer.nlp_engine import NlpEngineProvider
    except ImportError as error:
        raise RuntimeError(
            "Microsoft Presidio is not installed. Run: pip install -r requirements.txt"
        ) from error

    settings = settings or load_settings()
    provider = NlpEngineProvider(
        nlp_configuration={
            "nlp_engine_name": "spacy",
            "models": [
                {
                    "lang_code": settings.get("language", "en"),
                    "model_name": settings.get("model", "en_core_web_lg"),
                }
            ],
        }
    )
    analyzer = AnalyzerEngine(
        nlp_engine=provider.create_engine(),
        supported_languages=[settings.get("language", "en")],
    )
    for entity_type, pattern in API_KEY_PATTERNS.items():
        # PatternRecognizer runs a regular expression; it does not invoke NLP.
        analyzer.registry.add_recognizer(
            PatternRecognizer(
                supported_entity=entity_type,
                patterns=[Pattern(entity_type, pattern.pattern, 1.0)],
            )
        )
    return analyzer


def find_sensitive_lines(text: str) -> list[tuple[int, list[str], str]]:
    """Return line number, detected PII/credential types, and text for each match."""
    settings = load_settings()
    analyzer = build_analyzer(settings)
    selected_entities = [
        entity for entity, enabled in settings["entities"].items() if enabled
    ]
    selected_credentials = [
        name for name, enabled in settings["credential_types"].items() if enabled
    ]
    sensitive_lines = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        findings = analyzer.analyze(
            text=line,
            language=settings.get("language", "en"),
            entities=[*selected_entities, *selected_credentials],
            score_threshold=float(settings.get("confidence_threshold", 0.5)),
        )
        finding_types = sorted({finding.entity_type for finding in findings})

        if finding_types:
            sensitive_lines.append((line_number, finding_types, line))
    return sensitive_lines


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Find PII in English text, line by line."
    )
    parser.add_argument(
        "text", nargs="?", help="Text to inspect. Reads standard input when omitted."
    )
    args = parser.parse_args()

    text = args.text if args.text is not None else sys.stdin.read()
    if not text.strip():
        parser.error("provide text as an argument or through standard input")

    try:
        matches = find_sensitive_lines(text)
    except RuntimeError as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1) from error

    history_findings = [
        {"entity_type": entity_type}
        for _, entity_types, _ in matches
        for entity_type in entity_types
    ]
    add_history_entry(history_findings, len(text), source="Command-line scan")

    if not matches:
        print("No sensitive information found.")
        return

    for line_number, entity_types, line in matches:
        print(f"Line {line_number} ({', '.join(entity_types)}): {line}")


if __name__ == "__main__":
    main()
