import fitz
import re
import pandas as pd

# Words that appear in all-caps in statements but are NOT cardholder names
_SKIP_WORDS = {
    'ACCOUNT', 'SUMMARY', 'STATEMENT', 'CLOSING', 'CREDIT', 'PAYMENT',
    'BALANCE', 'TOTAL', 'MINIMUM', 'NEW', 'PREVIOUS', 'TRANSACTIONS',
    'DATE', 'DESCRIPTION', 'AMOUNT', 'PURCHASES', 'FEES', 'INTEREST',
    'ADJUSTMENTS', 'REWARDS', 'POINTS', 'ACTIVITY', 'DETAILS', 'DUE',
    'BILLING', 'PERIOD', 'OPENING', 'AVAILABLE', 'CASH', 'ADVANCE',
    'FOREIGN', 'CONTINUED', 'PAGE', 'IMPORTANT', 'NOTICE', 'INFORMATION'
}


def _is_cardholder_line(line: str) -> bool:
    """Return True if line looks like an all-caps cardholder name (2-4 words)."""
    words = line.strip().split()
    if len(words) < 2 or len(words) > 4:
        return False
    if not all(re.match(r'^[A-Z]+$', w) for w in words):
        return False
    if any(w in _SKIP_WORDS for w in words):
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

        # Detect cardholder section header (e.g. "JOHN DOE", "CARLOS RIVERA")
        if _is_cardholder_line(line_1):
            current_cardholder = line_1.title()
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
