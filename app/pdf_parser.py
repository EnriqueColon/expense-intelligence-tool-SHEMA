import fitz
import re
import pandas as pd

_SKIP_WORDS = {
    # Statement / financial terms
    'ACCOUNT', 'SUMMARY', 'STATEMENT', 'CLOSING', 'CREDIT', 'PAYMENT',
    'BALANCE', 'TOTAL', 'MINIMUM', 'NEW', 'PREVIOUS', 'TRANSACTIONS',
    'DATE', 'DESCRIPTION', 'AMOUNT', 'PURCHASES', 'FEES', 'INTEREST',
    'ADJUSTMENTS', 'ACTIVITY', 'DETAILS', 'DUE', 'BILLING', 'PERIOD',
    'OPENING', 'AVAILABLE', 'CASH', 'ADVANCE', 'FOREIGN', 'CONTINUED',
    'PAGE', 'IMPORTANT', 'NOTICE', 'INFORMATION',
    # Rewards / loyalty
    'REWARDS', 'POINTS', 'EARNED', 'EARN', 'MILES', 'BONUS', 'CASHBACK',
    # Business entity words that appear in section headers
    'SOFTWARE', 'SERVICES', 'SERVICE', 'GROUP', 'MANAGEMENT', 'SYSTEMS',
    'SOLUTIONS', 'TECHNOLOGIES', 'TECHNOLOGY', 'INC', 'LLC', 'CORP',
    'LIMITED', 'DIRECT', 'ONLINE', 'DIGITAL', 'GLOBAL', 'NATIONAL',
    'INTERNATIONAL', 'ENTERPRISES', 'ASSOCIATES', 'PARTNERS', 'CONSULTING',
    'HOLDINGS', 'STORAGE', 'PROPERTIES', 'REALTY', 'FINANCIAL',
    # Card / bank terms that appear as section headings in statements
    'CARD', 'BANK', 'CITI', 'CITIBANK', 'CITIBUSINESS', 'VISA', 'MASTERCARD',
    'AMEX', 'DISCOVER', 'CHASE', 'WELLS', 'FARGO', 'CAPITAL', 'SAPPHIRE',
    'PREFERRED', 'PLATINUM', 'SIGNATURE', 'BUSINESS', 'CORPORATE', 'DEBIT',
}


def _is_cardholder_line(line: str) -> bool:
    """
    Return True only if line looks like a personal cardholder name.
    Accepts both ALL-CAPS ("CARLOS RIVERA") and Title Case ("Carlos Rivera").
    Requirements: 2-3 words, each 2-20 alpha chars, each with a vowel,
    none matching known financial/business/card keywords.
    """
    words = line.strip().split()
    if len(words) < 2 or len(words) > 3:
        return False
    # Every word must be purely alphabetic, 2-20 chars, all-caps OR title-case
    for w in words:
        if not re.match(r'^[A-Za-z]{2,20}$', w):
            return False
        if not (w.isupper() or w.istitle()):
            return False
    # Every word must contain at least one vowel
    if not all(re.search(r'[AEIOUaeiou]', w) for w in words):
        return False
    # No word should be a known financial/business/card term
    if any(w.upper() in _SKIP_WORDS for w in words):
        return False
    return True


def parse_pdf_text(uploaded_file):
    pdf_lines = []
    with fitz.open(stream=uploaded_file.read(), filetype="pdf") as doc:
        for page in doc:
            text = page.get_text()
            pdf_lines.extend(text.split("\n"))
    return pdf_lines


def extract_transactions_from_text(lines):
    transactions = []
    current_cardholder = "Primary"
    i = 0

    while i < len(lines) - 2:
        line_1 = lines[i].strip()
        line_2 = lines[i + 1].strip()
        line_3 = lines[i + 2].strip()

        # Detect cardholder section header (e.g. "JOHN DOE" or "Carlos Rivera")
        if _is_cardholder_line(line_1):
            current_cardholder = line_1.strip().title()
            i += 1
            continue

        # Payment transaction (3-line pattern)
        if (
            len(line_1) >= 4 and line_1[:2].isdigit() and
            "PAYMENT" in line_2.upper() and
            ("minus$" in line_3 or "-$" in line_3 or line_3.startswith("-"))
        ):
            amount = (
                line_3.replace("minus$", "-")
                      .replace("$", "")
                      .replace(",", "")
                      .strip()
            )
            transactions.append({
                "Sale Date": line_1,
                "Post Date": line_1,
                "Description": line_2,
                "Amount": amount,
                "Cardholder": current_cardholder
            })
            i += 3
            continue

        # Purchase transaction (4-line pattern)
        if i < len(lines) - 3:
            line_4 = lines[i + 3].strip()
            if (
                len(line_1) >= 4 and line_1[:2].isdigit() and
                len(line_2) >= 4 and line_2[:2].isdigit() and
                "$" in line_4
            ):
                amount = (
                    line_4.replace("$", "")
                          .replace(",", "")
                          .strip()
                )
                transactions.append({
                    "Sale Date": line_1,
                    "Post Date": line_2,
                    "Description": line_3,
                    "Amount": amount,
                    "Cardholder": current_cardholder
                })
                i += 4
                continue

        i += 1

    return pd.DataFrame(transactions)
