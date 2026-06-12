"""RFQ detection using keyword matching and fuzzy matching."""
from rapidfuzz import fuzz
from config.settings import RFQ_KEYWORDS, FUZZY_MATCH_THRESHOLD


def is_rfq_email(subject: str, body: str) -> bool:
    """Check if email is RFQ-related via exact keyword or fuzzy match."""
    text = f"{subject} {body}".lower()

    # Exact keyword match
    for kw in RFQ_KEYWORDS:
        if kw in text:
            return True

    # Fuzzy match on subject (most indicative)
    subject_lower = subject.lower()
    for kw in RFQ_KEYWORDS:
        if fuzz.partial_ratio(kw, subject_lower) >= FUZZY_MATCH_THRESHOLD:
            return True

    return False
