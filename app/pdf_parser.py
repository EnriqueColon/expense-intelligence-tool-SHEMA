import fitz  # PyMuPDF
import pandas as pd
import re

def parse_pdf_text(uploaded_file):
    pdf_lines = []
    with fitz.open(stream=uploaded_file.read(), filetype="pdf") as doc:
        for page in doc:
            text = page.get_text()
            lines = text.split("\n")
            pdf_lines.extend(lines)
    return pdf_lines


def clean_amount(amount_str):
    try:
        cleaned = (
            amount_str.replace("minus$", "-")
                      .replace("(", "-")
                      .replace(")", "")
                      .replace("$", "")
                      .replace(",", "")
                      .strip()
        )
        return float(cleaned)
    except Exception as e:
        print(f"[ERROR] Failed to parse amount '{amount_str}': {e}")
        return 0.0


def classify_transaction(description, amount_str, override=None):
    if override:
        return override

    amount = clean_amount(amount_str)

    if amount < 0:
        return "Credit"

    if any(k in description.lower() for k in ["fee", "interest", "advance", "charge", "penalty", "late", "finance"]):
        return "Debt"

    return "Purchase"


def extract_transactions_from_text(lines):
    transactions = []
    current_cardholder = "General Account"
    in_payments_section = False
    i = 0

    def is_date(s):
        return bool(re.match(r"\d{2}/\d{2}", s.strip()))

    while i < len(lines):
        line = lines[i].strip()

        if "Payments, Credits and Adjustments" in line:
            in_payments_section = True
            current_cardholder = "General Account"
            i += 1
            continue
        elif "LAURO R SERRANO" in line:
            current_cardholder = "Lauro R Serrano"
            in_payments_section = False
            i += 1
            continue
        elif "CARLOS RIVERA" in line:
            current_cardholder = "Carlos Rivera"
            in_payments_section = False
            i += 1
            continue

        if in_payments_section and i + 2 < len(lines):
            date_line = lines[i].strip()
            desc_line = lines[i + 1].strip()
            amount_line = lines[i + 2].strip()

            if is_date(date_line) and "payment" in desc_line.lower() and "minus$" in amount_line.lower():
                sale_date = date_line
                description = desc_line
                amount = amount_line.lower().replace("minus$", "-").replace("$", "").replace(",", "").strip()

                transactions.append({
                    "Sale Date": sale_date,
                    "Post Date": sale_date,
                    "Description": description,
                    "Amount": amount,
                    "Cardholder": "General Account",
                    "Transaction Type": "Credit"
                })

                print(f"[DEBUG] ✅ Online payment parsed: {sale_date} | {description} | {amount}")
                i += 3
                continue

        if in_payments_section:
            print(f"[DEBUG] Checking line for refund credit: {line}")
            parts = re.split(r"\s{2,}|\t", line)
            if len(parts) >= 4 and is_date(parts[0]) and is_date(parts[1]) and re.search(r"-?\$[\d,]+\.\d{2}", parts[-1]):
                sale_date = parts[0]
                post_date = parts[1]
                amount_str = parts[-1]
                description = " ".join(parts[2:-1])

                transactions.append({
                    "Sale Date": sale_date,
                    "Post Date": post_date,
                    "Description": description.strip(),
                    "Amount": amount_str.replace("$", "").replace(",", "").replace("minus$", "-"),
                    "Cardholder": "General Account",
                    "Transaction Type": "Credit"
                })

                print(f"[DEBUG] ✅ Refund credit parsed: {sale_date} | {description.strip()} | {amount_str}")
                i += 1
                continue

        if in_payments_section and i + 3 < len(lines):
            date1 = lines[i].strip()
            date2 = lines[i + 1].strip()
            desc = lines[i + 2].strip()
            amount_line = lines[i + 3].strip()

            if is_date(date1) and is_date(date2) and re.search(r"-?\$[\d,]+\.\d{2}", amount_line):
                amount_str = amount_line.replace("minus$", "-").replace("$", "").replace(",", "").strip()

                transactions.append({
                    "Sale Date": date1,
                    "Post Date": date2,
                    "Description": desc,
                    "Amount": amount_str,
                    "Cardholder": "General Account",
                    "Transaction Type": "Credit"
                })

                print(f"[DEBUG] ✅ 4-line refund credit parsed: {date1} | {desc} | {amount_str}")
                i += 4
                continue

        if not in_payments_section and i + 3 < len(lines) and is_date(lines[i]) and is_date(lines[i + 1]):
            sale_date = lines[i].strip()
            post_date = lines[i + 1].strip()
            description_lines = []
            j = i + 2

            while j < len(lines):
                amount_match = re.search(r"\$[\d,]+\.\d{2}", lines[j])
                if amount_match:
                    amount_str = amount_match.group()
                    break
                description_lines.append(lines[j].strip())
                j += 1
            else:
                i += 1
                continue

            description = " ".join(description_lines).strip()
            txn_type = classify_transaction(description, amount_str)

            transactions.append({
                "Sale Date": sale_date,
                "Post Date": post_date,
                "Description": description,
                "Amount": amount_str.replace("$", "").replace(",", ""),
                "Cardholder": current_cardholder,
                "Transaction Type": txn_type
            })

            i = j + 1
            continue

        i += 1

    return pd.DataFrame(transactions)


def parse_pdf(uploaded_file):
    lines = parse_pdf_text(uploaded_file)
    df = extract_transactions_from_text(lines)

    df["Amount_float"] = df["Amount"].astype(float)
    suspect_df = df[(df["Transaction Type"] == "Purchase") & (df["Amount_float"] < 0)]

    if not suspect_df.empty:
        print("\n[WARNING] Possible mislabeled purchases that are negative:")
        print(suspect_df[["Sale Date", "Description", "Amount", "Transaction Type"]])

    return df.drop(columns=["Amount_float"])
