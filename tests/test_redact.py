"""Leak tests: PII must be redacted anywhere in a long document, in English and German."""

from nopii_mcp.redact import detect_language, redact

FILLER_EN = "The quarterly report covers revenue, costs and the outlook for the next period. " * 3
FILLER_DE = "Der Quartalsbericht behandelt Umsatz, Kosten und den Ausblick auf die nächste Periode. " * 3


def long_document(filler: str, secret: str, at: int = 150, paragraphs: int = 200) -> str:
    """Many paragraphs of filler with one PII sentence far past any model window."""
    parts = [filler] * paragraphs
    parts[at] = secret
    return "\n\n".join(parts)


def test_english_pii_deep_in_long_document():
    secret = "Please contact Margaret Thornton at margaret.thornton@example.com or +44 20 7946 0958."
    out = redact(long_document(FILLER_EN, secret))
    for value in ("Margaret", "Thornton", "margaret.thornton@example.com", "7946 0958"):
        assert value not in out
    assert "<PERSON_1>" in out


def test_german_pii_deep_in_long_document():
    secret = (
        "Bitte wenden Sie sich an Herrn Jürgen Hoffmann, Telefon +49 30 23125 456, IBAN DE89 3704 0044 0532 0130 00."
    )
    out = redact(long_document(FILLER_DE, secret))
    for value in ("Jürgen", "Hoffmann", "23125 456", "DE89 3704"):
        assert value not in out


def test_same_value_same_placeholder():
    out = redact("John Miller signed the contract. Later, John Miller sent it to Sarah Connor.")
    assert out.count("<PERSON_1>") == 2
    assert "<PERSON_2>" in out


def test_detect_language():
    assert detect_language(FILLER_EN) == "en"
    assert detect_language(FILLER_DE) == "de"


def test_urls_are_redacted_without_breaking_emails():
    out = redact("Profile: https://www.linkedin.com/in/anna-schmidt-4711 and email anna@example.com")
    assert "linkedin" not in out and "anna@example.com" not in out
    assert "<URL_1>" in out and "<EMAIL_ADDRESS_1>" in out
