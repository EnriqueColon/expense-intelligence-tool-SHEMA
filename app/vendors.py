"""Vendor-name normalisation.

Python port of ``normalizeVendor`` / ``VENDOR_MAP`` in ``static/app.js``.  The
dashboard derives vendor names client-side from the raw statement description;
the Excel report has to apply the identical rules so its Vendor Analysis sheet
reconciles to the vendor table on screen.

Keep this file and the JavaScript implementation in sync — if a brand rule is
added to one, add it to the other.
"""

import re

# Ordered brand rules — first match wins, mirroring the JS array order.
VENDOR_MAP = [
    (re.compile(r"amzn|amazon", re.I),               "Amazon"),
    (re.compile(r"upwork", re.I),                    "Upwork"),
    (re.compile(r"godaddy", re.I),                   "GoDaddy"),
    (re.compile(r"intuit|quickbooks|turbotax", re.I), "Intuit / QuickBooks"),
    (re.compile(r"at&t|att\.com", re.I),             "AT&T"),
    (re.compile(r"google", re.I),                    "Google"),
    (re.compile(r"microsoft|msft", re.I),            "Microsoft"),
    (re.compile(r"apple\.com|apple store", re.I),    "Apple"),
    (re.compile(r"dropbox", re.I),                   "Dropbox"),
    (re.compile(r"zoom", re.I),                      "Zoom"),
    (re.compile(r"slack", re.I),                     "Slack"),
    (re.compile(r"adobe", re.I),                     "Adobe"),
    (re.compile(r"shopify", re.I),                   "Shopify"),
    (re.compile(r"paypal", re.I),                    "PayPal"),
    (re.compile(r"stripe", re.I),                    "Stripe"),
    (re.compile(r"square", re.I),                    "Square"),
    (re.compile(r"uber\s?eats|ubereats", re.I),      "Uber Eats"),
    (re.compile(r"\buber\b", re.I),                  "Uber"),
    (re.compile(r"lyft", re.I),                      "Lyft"),
    (re.compile(r"doordash", re.I),                  "DoorDash"),
    (re.compile(r"grubhub", re.I),                   "Grubhub"),
    (re.compile(r"fedex", re.I),                     "FedEx"),
    (re.compile(r"usps", re.I),                      "USPS"),
    (re.compile(r"\bups\b", re.I),                   "UPS"),
    (re.compile(r"dhl", re.I),                       "DHL"),
    (re.compile(r"verizon", re.I),                   "Verizon"),
    (re.compile(r"t-mobile|tmobile", re.I),          "T-Mobile"),
    (re.compile(r"comcast|xfinity", re.I),           "Comcast / Xfinity"),
    (re.compile(r"notion", re.I),                    "Notion"),
    (re.compile(r"canva", re.I),                     "Canva"),
    (re.compile(r"mailchimp", re.I),                 "Mailchimp"),
    (re.compile(r"hubspot", re.I),                   "HubSpot"),
    (re.compile(r"salesforce", re.I),                "Salesforce"),
    (re.compile(r"docusign", re.I),                  "DocuSign"),
    (re.compile(r"propstream", re.I),                "PropStream"),
    (re.compile(r"costar", re.I),                    "CoStar"),
    (re.compile(r"openai", re.I),                    "OpenAI"),
    (re.compile(r"chatgpt", re.I),                   "ChatGPT"),
]

_TRAILING_STAR   = re.compile(r"\*.*$")
_LONG_NUMBER     = re.compile(r"[\s-]?\d[\d\s-]{6,}\d")
_TRAILING_STATE  = re.compile(r"\s+[A-Z]{2}$")
_URL             = re.compile(r"https?://\S+", re.I)
_DOMAIN          = re.compile(r"\w+\.(com|net|org|io|co)\b", re.I)

# Excel treats * ? ~ as wildcards inside SUMIF/COUNTIF criteria.  A vendor label
# containing one would silently match the wrong rows, so strip them from the
# canonical label — the same value is written to the Detail sheet and used as
# the criteria, keeping both sides consistent.
_WILDCARDS = re.compile(r"[*?~]")


def wildcard_safe(value: str) -> str:
    """Strip Excel criteria wildcards and collapse whitespace."""
    return re.sub(r"\s+", " ", _WILDCARDS.sub(" ", value or "")).strip()


def normalize_vendor(description: str) -> str:
    """Collapse a raw statement description down to a vendor name.

    Mirrors ``normalizeVendor`` in ``static/app.js``: brand rules first, then
    strip processor suffixes, long reference numbers, trailing state codes and
    URLs, and finally keep at most the first three words.
    """
    s = (description or "").strip()

    for pattern, name in VENDOR_MAP:
        if pattern.search(s):
            return name

    s = _TRAILING_STAR.sub("", s).strip()
    s = _LONG_NUMBER.sub("", s).strip()
    s = _TRAILING_STATE.sub("", s).strip()
    s = _URL.sub("", s).strip()
    s = _DOMAIN.sub("", s).strip()

    words = [w for w in re.split(r"\s+", s) if w][:3]
    return wildcard_safe(" ".join(words)) or "Unknown"
