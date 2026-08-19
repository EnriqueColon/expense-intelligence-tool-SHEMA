# SHEMA Expense Intelligence Tool — Product & Developer Documentation

> Living reference document. Update the relevant section whenever behaviour, stack,
> or maintenance procedure changes. See `SESSION.md` for work logs and
> `ROLLBACK.md` for the commit-level change ledger.

**Last updated:** 2026-08-18
**Repository:** `expense-classifier-gpt` locally; pushed to two GitHub remotes (see Git Remotes)
**Production host:** Vercel, project **`expense-intelligence-tool-shema`**, on the Safe Harbor
Vercel account. Live at `https://expense-intelligence-tool-shema.vercel.app`.
**Not production:** the Vercel project `expense-classifier-gpt` is a stale copy on a personal
account — no environment variables, no database, no active Git integration, last deployed
2026-05. Do not mistake it for the live system.

---

## Part 1 — What The Tool Does

### Purpose

The tool turns credit-card statement PDFs into categorised, queryable expense data.
An accountant or bookkeeper uploads one or more statements, the tool extracts every
transaction, predicts an expense category for each one using a trained machine-learning
model, and lets the user correct anything that is wrong before saving it to a database.
Saved data feeds a dashboard and analytics views that show spend over time, by category,
by vendor, and by cardholder.

The problem it solves: manually keying statement lines into accounting software is slow
and error-prone, especially for business cards with multiple cardholders where each
person's charges need to be attributed correctly.

### Who Uses It

A single shared login protects the whole application. Every user authenticates with the
same credentials, and their username is stamped onto each transaction they process
(`processed_by`) and each saved batch (`uploaded_by`).

### The Four Screens

The interface is a single page with a left sidebar containing four tabs.

**Upload** is where work starts. The user drags in one or more PDF statements, or clicks
to browse. Each file is sent to the server, parsed, and classified. The results appear as
an editable table: every row shows sale date, post date, description, amount, cardholder,
and a category dropdown. The user fixes any mis-categorised rows, optionally renames a
cardholder that the parser labelled generically, then either downloads a CSV or saves the
batch to the database. Two supporting panels sit below the table: a Cardholders summary
showing each person's transaction count and total, and a Vendor Analysis section that
groups charges by normalised vendor name.

**Dashboard** aggregates every transaction ever saved. Summary cards show total
transactions, batches, charges, and credits. Charts break spend down by category and by
vendor. Two filters narrow the view: a date range expressed in statement months, and a
cardholder selector. A retrain panel here reports how many labelled transactions exist in
the database and lets the user retrain the classification model against all of them. A
**Download Report** button in the header exports the current view as a formula-driven Excel
workbook, described below.

**History** lists saved batches newest-first, showing filename, uploader, date, statement
period, and transaction count. Clicking a batch opens its transactions, where categories
and free-text notes can be edited inline, cardholders renamed, and the batch exported to
CSV or deleted. The statement period of a batch can also be corrected here if the parser
detected it wrongly. A Monthly Spending Trend chart above the list plots category totals
over time, with a dropdown to isolate a single category.

**Categories** manages the category list used by every dropdown in the app. Categories can
be added, renamed, or deleted. Because changing this list affects how future transactions
are classified and how existing data lines up, a confirmation modal warns the user before
any change is applied.

### How Classification Works

The classifier is a scikit-learn pipeline. Transaction descriptions are vectorised with
TF-IDF (English stop words removed) and the amount is imputed and standard-scaled; both
feature streams are joined by a `ColumnTransformer` and fed into a `RandomForestClassifier`
with 100 trees. Predictions come back as category labels, which are then passed through a
normalisation map so that historical variants such as "Dues and Subscriptions" and
"Dues & Subscriptions" collapse into one canonical label.

The model improves through retraining. The user corrects categories in the UI, saves those
transactions, and then triggers a retrain — either against the rows currently on screen or
against every labelled transaction in the database. Retraining fits a fresh pipeline,
replaces the in-memory model, and uploads the serialised model to Vercel Blob Storage so it
survives redeploys and is picked up by other serverless instances. A minimum of five
labelled transactions is required for either retrain path.

### How the Excel Report Works

The Download Report button produces a six-sheet `.xlsx` analysis workbook that reflects
whatever filters are applied to the Dashboard at the moment it is clicked. It is a live
snapshot of the current view: the button sends the same start month, end month, and
cardholder to `/api/report`, which resolves rows through the same filter builder the
dashboard uses, so the workbook reconciles to the figures on screen.

The workbook's defining property is that it is **formula-driven**. The last sheet,
Transaction Detail, lists every transaction that makes up the report and is the single
source of truth. Every figure on every other sheet is a live spreadsheet formula pointing
back at it — `SUMIFS` and `COUNTIFS` for aggregates, direct cell references such as
`='Transaction Detail'!$I$42` for row-level lookups. Nothing is a hardcoded computed value,
so editing or deleting a row in Detail recalculates the whole workbook. That means an
accountant can strike a disputed charge and watch every total, percentage, and chart move.

The sheets, in order:

| Sheet | Contents |
|---|---|
| Executive Summary | Branded cover, report parameters, key metrics, monthly breakdown by cardholder, and a prior-period comparison |
| Category Analysis | Count, total, average, and share of total per category, with a bar chart |
| Vendor Analysis | The same per vendor, plus collapsible per-vendor drill-downs and a top-10 chart |
| Monthly Trend | Month totals with a line chart, and a top-6 category pivot with a stacked column chart |
| Top 25 Transactions | Largest transactions by absolute amount, every cell referencing Detail |
| Transaction Detail | Every transaction, frozen header and autofilter — the source all formulas target |

Three behaviours are deliberate and worth knowing. Headline totals count **charges only**
(`amount > 0`), matching the dashboard's category and vendor tables; credits and payments
still appear in full on the Detail sheet and are reported separately as Credits & Payments
and Net Activity. Monthly grouping keys off **statement period**, not transaction date, for
the same reason the dashboard charts do — and because statement period is always populated,
which transaction dates are not. The **prior-period total is a static value**, because those
transactions fall outside the report's Detail sheet and therefore cannot be a formula; the
variance figures beside it are formulas referencing the live current total.

Because the cells contain formulas with no cached results, the workbook sets
`fullCalcOnLoad`, which makes Excel, Google Sheets, and LibreOffice compute everything the
moment the file opens. A preview tool that only reads cached values will show blanks.

### How Cardholder Attribution Works

Business card statements list transactions grouped under each cardholder's name, but PDF
text extraction does not preserve that visual grouping reliably. Citi statements in
particular use a two-column layout where PyMuPDF emits the left column (transactions)
before the right column (cardholder summary), so a cardholder's name can appear in the
extracted text *after* their own transactions.

The parser handles this in two passes. The first pass scans the whole document for lines
that look like personal names, and for each one searches forward up to 60 lines for a bare
"Standard Purchases" header. The line after that header marks where that cardholder's
transactions begin. The second pass walks the document line by line, advancing through
those checkpoints and stamping the current cardholder onto each transaction it finds.
Transactions appearing before the first checkpoint are attributed to `sections[-1]` — the
last detected section — because in Citi's layout that is the cardholder whose transactions
were emitted early. If no cardholder can be detected at all, transactions fall back to
`Primary`, and the user can rename that from the UI.

Name detection is deliberately conservative. A candidate line must be two or three words,
each 3–20 alphabetic characters, consistently all-caps or title-case, containing at least
one vowel, and absent from a skip list of roughly 80 financial, card-brand, and generic
business terms. A single uppercase letter in the middle slot is accepted as a middle initial.

### How Dates And Statement Periods Work

Statement PDFs print transaction dates as `MM/DD` with no year. The parser looks for the
billing-period header (for example `06/12/24-07/09/24`) and uses it to attach the correct
four-digit year to every transaction, handling the case where a period spans a calendar-year
boundary. The billing-end month becomes the batch's `statement_period` in `YYYY-MM` form.

This matters for analytics. All time-series grouping keys off `statement_period` rather than
upload date, so a statement uploaded in August but covering June spend is charted under June.
Where `statement_period` is missing, queries fall back to the upload month via
`COALESCE(tb.statement_period, TO_CHAR(tb.created_at, 'YYYY-MM'))`.

---

## Part 2 — Developer Guide

### Stack

| Layer | Technology |
|---|---|
| Web framework | FastAPI, served as a single Vercel serverless function |
| PDF extraction | PyMuPDF (`fitz`) |
| Data handling | pandas |
| Machine learning | scikit-learn, pinned to `1.6.1` |
| Model serialisation | joblib |
| Excel generation | openpyxl |
| Model storage | Vercel Blob Storage, with a bundled `.pkl` as fallback |
| Database | PostgreSQL via `psycopg2-binary` (Vercel Postgres) |
| Auth | JWT (HS256) via `python-jose`, bearer token in `localStorage` |
| Frontend | Static HTML, vanilla JavaScript, CSS — no build step |
| Charts | Chart.js 4.4.0 from CDN |
| Hosting | Vercel |

The scikit-learn pin is load-bearing. The bundled `model/expense_classifier.pkl` was
serialised with 1.6.1, and unpickling under a different minor version can fail or silently
misbehave. Do not bump it without retraining and re-uploading the model.

### Repository Layout

```
api/index.py              FastAPI app — all routes, auth, DB access, model lifecycle
app/pdf_parser.py         PDF text extraction, cardholder detection, transaction parsing
app/report.py             Formula-driven Excel workbook builder
app/vendors.py            Vendor-name normalisation (Python port of the frontend rules)
model/expense_classifier.pkl  Fallback classifier bundled with the deployment
index.html                Main single-page application
login.html                Login screen
static/app.js             All frontend logic (~1,200 lines)
static/login.js           Login form handling and token storage
static/style.css          Styling for the sidebar shell and all views
scripts/verify_report.py  Recalculates a generated workbook and asserts it ties out
requirements.txt          Python dependencies
billflow/                 Next.js 16 scaffold — exploratory rewrite, not deployed
```

`api/index.py` inserts the repository root onto `sys.path` at import time so that
`from app.pdf_parser import ...` resolves inside Vercel's function bundle. Keep that
prelude intact when editing the file.

### Environment Variables

| Variable | Required | Purpose |
|---|---|---|
| `POSTGRES_URL` | Yes for persistence | Postgres connection string. Without it, all DB routes return 503. **The name is `POSTGRES_URL`** — the 503 message says "set the `DATABASE_URL` environment variable", but that is the internal Python variable name and setting it will have no effect |
| `BLOB_READ_WRITE_TOKEN` | Yes for model persistence | Vercel Blob token. Without it, retrained models are lost on redeploy |
| `SECRET_KEY` | Yes in production | JWT signing key |
| `APP_USERNAME` | Yes in production | Login username |
| `APP_PASSWORD` | Yes in production | Login password |

All five have insecure development defaults hard-coded in `api/index.py`. Setting real
values in the Vercel project environment is a deployment requirement, not an option.

### Database Schema

`transaction_batches` — one row per saved upload: `id`, `uploaded_by`, `filename`,
`created_at`, `transaction_count`, `statement_period`.

`transactions` — one row per line item: `id`, `batch_id` (cascade delete), `sale_date`,
`post_date`, `description`, `amount` (`NUMERIC(12,2)`), `category`, `cardholder`,
`processed_by`, `notes`, `created_at`, `updated_at`.

Migrations live inside `init_db()`, which runs at module import. It uses
`CREATE TABLE IF NOT EXISTS` and `ADD COLUMN IF NOT EXISTS`, backfills
`statement_period` from `created_at` where null, and rewrites any category values that
match a known variant to their canonical label. Every statement in `init_db()` must be
idempotent, because it re-runs on every cold start.

### API Routes

All routes except `/`, `/login`, `/api/login`, and `/api/health` require a bearer token.

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/login` | Exchange credentials for an 8-hour JWT |
| POST | `/api/upload` | Parse and classify a PDF, returns transactions plus statement period |
| POST | `/api/retrain` | Retrain from a posted transaction list |
| POST | `/api/retrain/database` | Retrain from all labelled rows in the database |
| POST | `/api/transactions/save` | Persist a batch and its transactions |
| GET | `/api/transactions/history` | List the 100 most recent batches |
| GET | `/api/transactions/batch/{id}` | Fetch one batch's transactions |
| PATCH | `/api/transactions/{id}` | Update a transaction's category or notes |
| PATCH | `/api/transactions/batch/{id}/rename-cardholder` | Rename a cardholder within a batch |
| PATCH | `/api/transactions/batch/{id}/statement-period` | Correct a batch's statement period |
| DELETE | `/api/transactions/batch/{id}` | Delete a batch and cascade its transactions |
| GET | `/api/transactions/analytics` | Monthly totals grouped by category |
| GET | `/api/dashboard` | Aggregated stats, categories, vendors, cardholders; accepts `start`, `end`, `cardholder` |
| GET | `/api/report` | Formula-driven `.xlsx` workbook for the current view; accepts `start`, `end`, `cardholder`, `period_label` |
| GET | `/api/health` | Reports model, blob, and database configuration status |

### Running Locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export POSTGRES_URL="postgres://..."
export BLOB_READ_WRITE_TOKEN="vercel_blob_rw_..."
export SECRET_KEY="local-dev-key"
uvicorn api.index:app --reload --port 8000
```

Open `http://localhost:8000/login`. Without `POSTGRES_URL` the upload and classification
flow still works end to end; only the save, history, dashboard, and analytics routes fail
with a 503.

Deployment is `git push` to `main` on the Safe Harbor remote, which the
`expense-intelligence-tool-shema` Vercel project builds automatically. `/api/health` is the
first thing to check after a deploy; it should return 200 with `db_configured: true`.

### Routing — Why There Is No `vercel.json`

The project deliberately has **no `vercel.json`**. Vercel detects the FastAPI application in
`api/index.py` as a backend framework and routes all traffic to the ASGI app natively, with the
original request path preserved.

There used to be a catch-all rewrite, `/(.*)` → `/api/index`. **Do not reintroduce it.** Vercel
changed the semantics of internal rewrites so that the application now receives the *rewritten
destination* path rather than the original one. With that rewrite in place every request reaches
FastAPI as the literal path `/api/index`, matches no route, and the entire site — pages, API,
and static assets alike — returns `{"detail":"Not Found"}`. The app is healthy, the build
succeeds, and there is no traceback, which makes it a genuinely confusing failure. It took
production down on 2026-08-18.

The trap is that the change is invisible until a rebuild. A deployment built under an older
Vercel CLI keeps working indefinitely; the breakage only appears when something triggers a fresh
build, at which point the *trigger* looks like the cause. Watch for this warning in build logs:

```
WARNING! Internal rewrites in backend framework projects now route requests using the
rewritten destination path.
```

### Verifying A Deployment

Page loads are not sufficient — the failure mode above serves a working-looking 404. Probe the
routes directly, because the status codes distinguish "route missing" from "route present":

```bash
u=https://expense-intelligence-tool-shema.vercel.app
curl -s -o /dev/null -w '%{http_code}\n' $u/            # expect 200
curl -s $u/api/health                                   # expect 200, db_configured: true
curl -s -o /dev/null -w '%{http_code}\n' $u/static/style.css   # expect 200 — proves the mount
curl -s -o /dev/null -w '%{http_code}\n' $u/api/dashboard      # expect 401, not 404
curl -s -o /dev/null -w '%{http_code}\n' $u/api/report         # expect 401, not 404
```

**401 means the route exists and is demanding a token — that is a pass.** A 404 on
`/api/dashboard` or `/api/report` means the deployed bundle does not contain that route, either
because routing is broken or because an older build is being served.

### Rolling Back A Bad Deployment

Vercel dashboard → project → **Deployments** → three-dot menu on the last known-good deployment
→ **Instant Rollback**. This repoints the production alias at an existing build in seconds. It
changes neither git nor the database.

Two caveats learned the hard way. A rollback **pins** production, so later pushes may build
without being promoted — check whether production actually moved, rather than assuming. And
because a rollback restores an *older build*, the running code will no longer match `main`;
`/api/report` returning 404 is a quick way to detect that drift.

### There Is No Staging Environment

The only project that auto-deploys is production. Until that changes, test anything risky with a
**preview deployment**: push a branch other than `main` to the Safe Harbor remote and Vercel
builds it at its own URL, leaving production untouched. This is how the routing fix above was
validated before it was merged.

### Git Remotes

This repository is pushed to **two GitHub accounts**, maintained as mirrors by hand:

| Remote | Repository | Account |
|---|---|---|
| `origin` | `RSronin09/expense-classifier-gpt` | personal (`enriquec012@outlook.com`) |
| `enriquecolon` | `EnriqueColon/expense-intelligence-tool-SHEMA` | Safe Harbor (`mktinfo@safeharborequity.com`) |

Nothing enforces that both stay in step. A push to one only will leave the other silently
behind — this happened on 2026-08-18, when three commits reached `origin` and the Safe Harbor
repository stayed three commits back until someone noticed. Push to both, every time:

```bash
git push origin main && git push enriquecolon main
```

Commits are authored from the **global** git config (`RSronin09 <enriquec012@outlook.com>`);
there is no repository-local identity override, so commits carry the personal identity
regardless of which remote they land on.

> **Credential warning.** The `enriquecolon` remote URL has historically carried a GitHub
> personal access token embedded in it (`https://user:ghp_...@github.com/...`). That stores
> the secret in plaintext in `.git/config` and leaks it through ordinary commands such as
> `git remote -v`. Do not reintroduce this pattern — use SSH or a git credential helper. If
> you find a token in a remote URL, revoke it at github.com/settings/tokens and re-point the
> remote.

### Maintenance Playbook

**Adding a category.** Add the label to the `CATEGORIES` array in `static/app.js`. If it
replaces or merges with an older wording, add every old variant to `_CATEGORY_MAP` in
`api/index.py` mapping to the new canonical label — `init_db()` will rewrite existing rows
on the next cold start. Users can also add categories at runtime through the Categories
tab, but those are stored in `localStorage` per browser and do not affect the server-side
normalisation map.

**Changing the model.** Modify `_fit_and_save_pipeline()` in `api/index.py`, which is the
single place both retrain routes build their pipeline. After changing features or
hyperparameters, retrain through the Dashboard so a compatible model is written to Blob
Storage; otherwise the bundled `.pkl` and the new code will disagree.

**Supporting a new statement format.** The parser is tuned to Citi's layout. Extending it
means working in `app/pdf_parser.py`: `_is_cardholder_line` and `_SKIP_WORDS` for name
detection, `_STD_PURCHASES` and `_prescan_cardholders` for section boundaries, and the
three- and four-line pattern matchers in `extract_transactions_from_text` for transaction
shapes. Test by dumping `parse_pdf_text()` output for a sample statement and reading the
raw line stream before adjusting any heuristic — the layout assumptions matter more than
the regexes.

**Changing the schema.** Add the change to `init_db()` as an idempotent statement. There is
no migration framework and no down-migration path, so destructive changes need a manual
backup first.

**Changing the report.** Everything lives in `app/report.py`, one `_write_*` function per
sheet. The rules that keep it correct: write formula strings, never computed values; quote
sheet names containing spaces in every reference (`'Transaction Detail'!$I$3:$I$859`); keep
every `SUMIF`/`SUMIFS` range spanning identical rows; and normalise any value used as a
criteria so it cannot be blank or contain the Excel wildcards `* ? ~`. The Executive Summary
KPI cells sit at fixed addresses that other sheets reference, so the `EXEC_*` row constants
and the block layout must stay in step — `_write_parameters` asserts this and will fail loudly
if they drift. Charts skip hidden cells by default, so any chart pointing at the hidden helper
columns needs `visible_cells_only = False`.

After any change run `python scripts/verify_report.py`. It builds a workbook from synthetic
records, recalculates it with headless LibreOffice, and asserts that the Executive Summary,
Category, Vendor, Monthly Trend, and monthly-breakdown totals all agree with the sum of the
Detail sheet, that drill-down and Top-N references resolve, and that no cell holds a formula
error. It also recalculates four edge cases including a set with no charges at all.

**Changing vendor rules.** `normalize_vendor()` in `app/vendors.py` is a port of
`normalizeVendor()` in `static/app.js`, and the report's vendor figures only reconcile to the
dashboard while the two agree. Add brand rules to both, in the same order.

**Frontend changes.** There is no build step or bundler. Edit `static/app.js` directly and
hard-refresh; Vercel serves it as a static asset. State lives in module-level variables at
the top of the file, and every view re-renders through its own `render*` function.

### Known Constraints

- Single shared credential set; there is no per-user account system or role separation.
- Category edits made in the Categories tab are per-browser `localStorage`, not shared
  server state.
- Vendor analysis normalisation is heuristic string matching, so vendor grouping is
  approximate.
- The parser targets Citi business card statements; other issuers are untested.
- Cold starts pay the cost of `init_db()` plus a Blob model fetch.
- Report cells are formulas with no cached values, so they read as blank until a spreadsheet
  application recalculates. Excel, Google Sheets, and LibreOffice do this on open; simple
  preview tools may not.
- The report's collapsible vendor drill-downs use native Excel outline grouping, which works
  in Excel and Google Sheets but is ignored by Apple Numbers, where the rows simply appear
  expanded.
- Vendor rules are duplicated between `app/vendors.py` and `static/app.js` and must be kept
  in sync by hand.
- The report is generated synchronously in the request; very large filter ranges will make
  the download slow and could approach the serverless function timeout.
- `billflow/` is an untracked Next.js scaffold with no application code yet; it is not part
  of the deployed product.
- The repository has two GitHub remotes kept in sync manually, so they can and do drift. See
  Git Remotes above before pushing or reverting.
- Adding a `vercel.json` catch-all rewrite to `/api/index` breaks every route on the next
  rebuild. See Routing above.
- A rebuild can break production even when no application code changed, because Vercel platform
  behaviour changes take effect only when a project is rebuilt. Long gaps between deploys make
  this more likely, not less.
- There is no staging environment; production is the only auto-deploying project. Use branch
  preview deployments to test.
- Production can silently run code older than `main` following an Instant Rollback, since a
  rollback pins the production alias.
