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


_STD_PURCHASES = re.compile(
    r'^standard purchases(\s*$|,|\s+cont)', re.IGNORECASE
)


def _prescan_cardholders(lines):
    """
    Pass 1: scan the entire document to find every cardholder section.

    For each line that looks like a personal name, search forward up to
    60 lines for a bare "Standard Purchases" header (no dollar amount on
    the same line).  Record the line index AFTER that header as the section
    start — that is where the cardholder's transactions begin.

    Returns a list of (section_start_line, name_title) sorted by position.
    The wide 60-line window handles Citi's two-column interleaving, which
    can inject the AAdvantage miles block AND the Cardholder Summary table
    between the name header and "Standard Purchases".
    """
    sections = []
    seen = set()
    for i, raw in enumerate(lines):
        line = raw.strip()
        if not _is_cardholder_line(line):
            continue
        name_title = line.title()
        if name_title in seen:
            continue
        for j in range(i + 1, min(i + 61, len(lines))):
            if _STD_PURCHASES.match(lines[j].strip()):
                sections.append((j + 1, name_title))
                seen.add(name_title)
                break
    return sorted(sections, key=lambda x: x[0])


def extract_transactions_from_text(lines):
    """
    Pass 2: parse transactions, using pre-scanned cardholder checkpoints
    to assign each transaction to the correct cardholder.

    Transactions that appear before the first detected cardholder section
    (e.g. account-level ONLINE PAYMENT entries at the top of the statement)
    are attributed to the first confirmed cardholder rather than "Primary",
    since on a multi-cardholder business card all charges belong to someone.
    """
    sections = _prescan_cardholders(lines)
    confirmed_cardholders = {name for _, name in sections}

    # Default cardholder for transactions that appear BEFORE the first checkpoint.
    #
    # In Citi's two-column layout PyMuPDF extracts the left column (transactions)
    # before the right column (cardholder summary).  That means the section
    # confirmation for the first cardholder's transactions lands AFTER those
    # transactions in the extracted text stream.
    #
    # The cardholder summary always lists the "next-page" cardholder first and
    # the "same-page" (pre-summary) cardholder last.  So sections[-1] is the
    # cardholder whose transactions appear before all checkpoints.
    default_cardholder = sections[-1][1] if sections else "Primary"
    current_cardholder = default_cardholder

    # Checkpoint pointer — advance through sections as we walk the lines.
    chk_idx = 0

    transactions = []
    i = 0

    while i < len(lines) - 2:

        # Advance checkpoint: switch cardholder when we reach a section start.
        while chk_idx < len(sections) and i >= sections[chk_idx][0]:
            current_cardholder = sections[chk_idx][1]
            chk_idx += 1

        line_1 = lines[i].strip()
        line_2 = lines[i + 1].strip()
        line_3 = lines[i + 2].strip()

        # Page-continuation: the name reappears (no new "Standard Purchases"
        # header) — switch cardholder immediately.
        if _is_cardholder_line(line_1):
            name_title = line_1.title()
            if name_title in confirmed_cardholders:
                current_cardholder = name_title
                i += 1
                continue

        # Payment transaction (3-line: date / description / amount)
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
                "Cardholder": current_cardholder,
            })
            i += 3
            continue

        # Purchase transaction (4-line: sale date / post date / desc / amount)
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
                    "Cardholder": current_cardholder,
                })
                i += 4
                continue

        i += 1

    return pd.DataFrame(transactions)
