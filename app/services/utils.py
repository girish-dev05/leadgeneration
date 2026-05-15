import re
from typing import Optional

import phonenumbers

EMAIL_REGEX = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')


def normalize_phone(raw_phone: Optional[str], default_region: str = 'IN') -> Optional[str]:
    if not raw_phone:
        return None
    try:
        parsed = phonenumbers.parse(raw_phone, default_region)
        if not phonenumbers.is_possible_number(parsed):
            return None
        return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    except phonenumbers.NumberParseException:
        return None


def extract_email(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    match = EMAIL_REGEX.search(text)
    return match.group(0).lower() if match else None


def normalize_email(email: Optional[str]) -> Optional[str]:
    if not email:
        return None
    cleaned = email.strip().lower()
    return cleaned if '@' in cleaned else None
