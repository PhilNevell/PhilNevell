import hmac
import hashlib
import re
from dataclasses import dataclass
from typing import Dict, List, Tuple

PII_PATTERNS = {
    "EMAIL_ADDRESS": re.compile(r"[a-zA-Z0-9_.+\-]+@[a-zA-Z0-9\-]+\.[a-zA-Z0-9\-.]+"),
    "PHONE_NUMBER": re.compile(r"(?:(?:\+?\d{1,3}[\s.-]?)?(?:\(\d{2,4}\)[\s.-]?|\d{2,4}[\s.-])?\d{3,4}[\s.-]?\d{3,4})"),
    "IP_ADDRESS": re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d?\d)(?:\.|$)){4}\b"),
    "CREDIT_CARD": re.compile(r"\b(?:\d[ -]*?){13,19}\b"),
    "SSN": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "DATE": re.compile(r"\b(?:\d{1,2}[\-/]\d{1,2}[\-/]\d{2,4}|\d{4}[\-/]\d{1,2}[\-/]\d{1,2})\b"),
}


@dataclass
class Anonymizer:
    secret_key: str

    def _stable_token(self, entity_type: str, value: str) -> str:
        mac = hmac.new(self.secret_key.encode("utf-8"), (entity_type + "::" + value).encode("utf-8"), hashlib.sha256)
        token = mac.hexdigest()[:16]
        return f"<{entity_type}:{token}>"

    def anonymize(self, text: str) -> Tuple[str, List[Dict]]:
        if not text:
            return text, []
        entities_out: List[Dict] = []
        replaced_segments: List[Tuple[int, int, str]] = []

        for entity_type, pattern in PII_PATTERNS.items():
            for match in pattern.finditer(text):
                start, end = match.start(), match.end()
                value = text[start:end]
                token = self._stable_token(entity_type, value)
                replaced_segments.append((start, end, token))
                entities_out.append({
                    "type": entity_type,
                    "start": start,
                    "end": end,
                })

        # Apply replacements from end to start to keep indices valid
        replaced_segments.sort(key=lambda x: x[0], reverse=True)
        anonymized_text = text
        for start, end, token in replaced_segments:
            anonymized_text = anonymized_text[:start] + token + anonymized_text[end:]

        # Sort entities by start for readability
        entities_out.sort(key=lambda e: e["start"]) 
        return anonymized_text, entities_out