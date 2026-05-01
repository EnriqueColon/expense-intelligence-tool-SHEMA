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
    # Section sub-headers
    'STANDARD', 'CHARGES', 'CREDITS',
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
    Return True if line looks like a personal cardholder name.
    Accepts both ALL-CAPS and Title Case, with optional middle initial:
      "CARLOS RIVERA", "Carlos Rivera", "LAURO R SERRANO"
    Rules for each name word (first / last / middle if not an initial):
      - 3-20 alphabetic characters
      - All-caps or title-case (not mixed)
      - Contains at least one vowel
      - Not in the financial/card/business skip list
    Middle initial: single uppercase letter in position 1 of a 3-word name.
    """
    words = line.strip().split()
    if len(words) < 2 or len(words) > 3:
        return False

    name_words = []
    for idx, w in enumerate(words):
        # Single uppercase letter in the middle slot → valid middle initial
        if idx == 1 and len(words) == 3 and re.match(r'^[A-Z]$', w):
            continue
        if not re.match(r'^[A-Za-z]{3,20}$', w):
            return False
        if not (w.isupper() or w.istitle()):
            return False
        name_words.append(w)

    if len(name_words) < 2:
        return False

    if not all(re.search(r'[AEIOUaeiou]', w) for w in name_words):
        return False

    if any(w.upper() in _SKIP_WORDS for w in name_words):
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

        # Detect named cardholder transaction section.
        # Citi PDFs use a two-column layout; PyMuPDF interleaves right-column
        # blocks (AAdvantage miles section) between the section name header and
        # "Standard Purchases", so they are not always adjacent lines.
        # Strategy: look ahead up to 10 lines for the exact text
        # "Standard Purchases" (stops at the first MM/DD date so we don't
        # accidentally match the CARDHOLDER SUMMARY table, and requires an
        # exact match so "Standard Purchases, Cont'd" on page 3 is ignored).
        if _is_cardholder_line(line_1):
            found_at = -1
            for j in range(i + 1, min(i + 11, len(lines))):
                s = lines[j].strip()
                if re.match(r'^standard purchases\s*$', s, re.IGNORECASE):
                    found_at = j
                    break
                if re.match(r'^\d{2}/\d{2}', s):
                    break  # hit a transaction date — stop searching
            if found_at >= 0:
                current_cardholder = line_1.strip().title()
                i = found_at + 1
                continue

        # Payment transaction (3-line pattern: date / description / amount)
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

        # Purchase transaction (4-line pattern: sale date / post date / desc / amount)
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
