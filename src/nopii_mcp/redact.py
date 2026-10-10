"""Detect PII in English or German markdown and replace it with numbered placeholders.

Presidio does the work: its pattern recognizers catch structured values (emails,
phones, IBANs, cards, IPs, URLs), and its GLiNER recognizer catches contextual ones
(names, addresses, IDs). Presidio splits long text into chunks for GLiNER itself.
"""

from functools import cache

from lingua import Language, LanguageDetectorBuilder
from presidio_analyzer import AnalyzerEngine, RecognizerRegistry
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_analyzer.predefined_recognizers import (
    CreditCardRecognizer,
    EmailRecognizer,
    GLiNERRecognizer,
    IbanRecognizer,
    IpRecognizer,
    PhoneRecognizer,
    UrlRecognizer,
)
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

LANGUAGES = {Language.ENGLISH: "en", Language.GERMAN: "de"}
SPACY_MODELS = {"en": "en_core_web_sm", "de": "de_core_news_sm"}
PHONE_REGIONS = ("DE", "AT", "CH", "GB", "US")
GLINER_MODEL = "urchade/gliner_multi_pii-v1"
GLINER_THRESHOLD = 0.5

# GLiNER label (what the model is asked to find) -> placeholder type.
GLINER_LABELS = {
    "person": "PERSON",
    "email": "EMAIL_ADDRESS",
    "phone number": "PHONE_NUMBER",
    "address": "ADDRESS",
    "ip address": "IP_ADDRESS",
    "national id number": "NATIONAL_ID",
    "passport number": "PASSPORT",
    "credit card number": "CREDIT_CARD",
    "bank account number": "BANK_ACCOUNT",
    "date of birth": "DATE_OF_BIRTH",
    "api key": "SECRET",
}
ENTITIES = sorted(set(GLINER_LABELS.values()) | {"IBAN_CODE", "URL"})


class _SharedGliner(GLiNERRecognizer):
    """One GLiNER model in memory, shared by the English and German recognizers."""

    _model = None

    def load(self) -> None:
        if _SharedGliner._model is None:
            super().load()
            _SharedGliner._model = self.gliner
        self.gliner = _SharedGliner._model


@cache
def _engines() -> tuple[AnalyzerEngine, AnonymizerEngine]:
    nlp = NlpEngineProvider(
        nlp_configuration={
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": k, "model_name": v} for k, v in SPACY_MODELS.items()],
        }
    ).create_engine()
    for model in nlp.nlp.values():
        model.max_length = 50_000_000  # spaCy only tokenizes here; GLiNER does the NER

    registry = RecognizerRegistry(supported_languages=list(SPACY_MODELS))
    for lang in SPACY_MODELS:
        registry.add_recognizer(EmailRecognizer(supported_language=lang))
        registry.add_recognizer(PhoneRecognizer(supported_language=lang, supported_regions=PHONE_REGIONS))
        registry.add_recognizer(IbanRecognizer(supported_language=lang))
        registry.add_recognizer(CreditCardRecognizer(supported_language=lang))
        registry.add_recognizer(IpRecognizer(supported_language=lang))
        registry.add_recognizer(UrlRecognizer(supported_language=lang))  # all URLs, public ones too
        registry.add_recognizer(
            _SharedGliner(
                supported_language=lang,
                model_name=GLINER_MODEL,
                entity_mapping=GLINER_LABELS,
                threshold=GLINER_THRESHOLD,
            )
        )

    analyzer = AnalyzerEngine(nlp_engine=nlp, registry=registry, supported_languages=list(SPACY_MODELS))
    return analyzer, AnonymizerEngine()


@cache
def _detector():
    return LanguageDetectorBuilder.from_languages(*LANGUAGES).build()


def detect_language(text: str) -> str:
    """Return "en" or "de" for the text (English when unsure)."""
    return LANGUAGES.get(_detector().detect_language_of(text[:20_000]), "en")


def redact(text: str) -> str:
    """Replace every PII value with a placeholder like <PERSON_1>.

    Numbering is per document: the same value always gets the same placeholder.
    """
    if not text.strip():
        return text
    analyzer, anonymizer = _engines()
    results = analyzer.analyze(text=text, language=detect_language(text), entities=ENTITIES)

    # Number values in reading order, so <PERSON_1> is the first person mentioned.
    numbers: dict[tuple[str, str], int] = {}
    for r in sorted(results, key=lambda r: r.start):
        key = (r.entity_type, text[r.start : r.end])
        numbers.setdefault(key, sum(1 for t, _ in numbers if t == r.entity_type) + 1)

    def placeholder(entity_type: str):
        def replace(value: str) -> str:
            key = (entity_type, value)
            n = numbers.setdefault(key, sum(1 for t, _ in numbers if t == entity_type) + 1)
            return f"<{entity_type}_{n}>"

        return replace

    operators = {e: OperatorConfig("custom", {"lambda": placeholder(e)}) for e in ENTITIES}
    return anonymizer.anonymize(text=text, analyzer_results=results, operators=operators).text


def warm_up() -> None:
    """Load all models now, so the first real request isn't slow."""
    redact("Warm-up text written by Max Mustermann.")
