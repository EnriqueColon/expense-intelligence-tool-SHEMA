# ROLLBACK — Change Ledger

Every committed change to the tool, newest first, with the files it touched and the
command to undo it. Add an entry here for each commit at the end of every session.

**Last updated:** 2026-08-18
**Current HEAD:** the documentation commit described in the 2026-08-18 section below. A
commit cannot contain its own hash, so that one entry carries its SHA from the next update.

---

## How To Roll Back

Undo one commit while keeping history intact (preferred — safe on shared branches):

```bash
git revert <sha>
```

Undo a range of commits, oldest-first so the patches apply cleanly:

```bash
git revert --no-commit <oldest-sha>^..<newest-sha>
git commit -m "Revert <feature>"
```

Inspect a commit before reverting it:

```bash
git show <sha> --stat
```

Restore a single file to its state at a given commit:

```bash
git checkout <sha> -- path/to/file
```

### Before Rolling Back — Read This

- **Database migrations do not revert.** Schema changes live inside `init_db()` in
  `api/index.py`. Reverting the code removes the `CREATE`/`ALTER` statement but leaves the
  column in place, which is usually harmless. Reverting a commit that ran a data-rewriting
  `UPDATE` (for example the category normalisation in `2c57b4e`) does **not** restore the
  old values — those need a manual fix or a database restore.
- **Model artefacts do not revert.** The model in Vercel Blob Storage is whatever was last
  retrained. If a rollback changes the pipeline definition in `_fit_and_save_pipeline()`,
  retrain from the Dashboard afterwards so the stored model matches the code.
- **Verify after any rollback** by checking `/api/health`, then uploading a known-good
  statement PDF and confirming the transaction count and cardholder attribution.

---

## Change Log

### 2026-08-18 — Download Report, startup fix, and documentation

| SHA | Change | Files | Revert |
|---|---|---|---|
| _(this entry's own commit)_ | Add SESSION.md, ROLLBACK.md, CONFLUENCE.md, the session-docs rule, and ignore `.venv/` / `.DS_Store` | `SESSION.md`, `ROLLBACK.md`, `CONFLUENCE.md`, `.cursor/rules/session-docs.mdc`, `.gitignore` | Safe to revert — documentation only, no runtime effect |
| `8ac5dd1` | Add Download Report: formula-driven Excel export of the dashboard | `app/report.py`, `app/vendors.py`, `scripts/verify_report.py`, `api/index.py`, `index.html`, `static/app.js`, `static/style.css`, `requirements.txt` | `git revert 8ac5dd1` |
| `0d1e6e3` | Fix `init_db` so a fresh database initialises | `api/index.py` | do not revert |

`0d1e6e3` is marked do-not-revert because reverting it restores a state in which a
deployment against an empty database silently creates no tables at all. It changes nothing
for an existing install — the reordered `UPDATE` is a no-op once the tables exist.

`8ac5dd1` adds `openpyxl` to `requirements.txt` and extracts `build_dashboard_filters()`,
which `/api/dashboard` now depends on. Reverting removes both cleanly, but note that the
report only reconciles to the dashboard while the two share that filter builder, and while
`app/vendors.py` stays in step with `normalizeVendor()` in `static/app.js`.

Verified before commit: 54 seeded transactions across three statement periods and three
cardholders, downloaded through a real browser, reconciled exactly to the on-screen totals
both unfiltered ($11,955.89) and filtered to one cardholder ($5,325.30), with all 42 vendor
names matching and zero formula errors.

### 2026-05-13 — Category management

| SHA | Change | Files | Revert |
|---|---|---|---|
| `c33953d` | Add delete category action with warning popup to Manage Categories tab | `index.html`, `static/app.js` | `git revert c33953d` |
| `717be0b` | Show all categories in Monthly Spending Trend dropdown, not just those present in data | `static/app.js` | `git revert 717be0b` |
| `657a243` | Add Telephone/Internet/Web category and the Manage Categories tab | `index.html`, `static/app.js`, `api/index.py` | `git revert 657a243` |

Reverting `657a243` removes the Categories tab entirely and drops `Telephone/Internet/Web`
from the category list. Any transactions already saved under that label remain in the
database with a category that no longer appears in the dropdown.

### 2026-05-11 — Analytics correctness

| SHA | Change | Files | Revert |
|---|---|---|---|
| `2c57b4e` | Normalise category labels; fix split "Dues & Subscriptions" and other variants | `api/index.py`, `static/app.js` | `git revert 2c57b4e` |
| `c7f8b74` | Consolidate migration into `init_db()`, surface API errors in the UI | `api/index.py`, `static/app.js` | `git revert c7f8b74` |
| `a5048b9` | Chart analytics by statement billing period instead of upload date | `api/index.py`, `app/pdf_parser.py`, `static/app.js` | `git revert a5048b9` |

`2c57b4e` introduced `_CATEGORY_MAP` and a one-way `UPDATE` that rewrote existing rows to
canonical labels. Reverting the code will not un-merge those rows.

`a5048b9` added the `statement_period` column and backfilled it from `created_at`.
Reverting returns every chart to grouping by upload month, which will visibly shift
historical data.

### 2026-05-08 — Dashboard filtering and UI redesign

| SHA | Change | Files | Revert |
|---|---|---|---|
| `6a5985d` | Add cardholder filter to the dashboard | `api/index.py`, `index.html`, `static/app.js` | `git revert 6a5985d` |
| `ae4c82f` | Redesign UI as a sidebar shell matching reference tool patterns | `index.html`, `static/style.css`, `static/app.js` | `git revert ae4c82f` |

`ae4c82f` is a full layout rewrite. Reverting it conflicts with every later frontend
commit; restore the pre-redesign UI only by checking out that tree, not by reverting.

### 2026-05-05 — Cardholder detection rewrite, dashboard, retraining

| SHA | Change | Files | Revert |
|---|---|---|---|
| `be238cd` | Guard the page-continuation trigger with `chk_idx > 0` | `app/pdf_parser.py` | `git revert be238cd` |
| `e4f6b83` | Use `sections[-1]` as the pre-checkpoint default cardholder | `app/pdf_parser.py` | `git revert e4f6b83` |
| `daae18b` | Rewrite cardholder detection as a two-pass approach | `app/pdf_parser.py` | `git revert daae18b` |
| `f8f960d` | Add database-powered model retraining to the Dashboard tab | `api/index.py`, `index.html`, `static/app.js` | `git revert f8f960d` |
| `91c2c55` | Add cardholder rename to the saved batch detail view | `api/index.py`, `static/app.js` | `git revert 91c2c55` |
| `3635a0a` | Add cardholder rename UI for correcting undetected names | `index.html`, `static/app.js` | `git revert 3635a0a` |
| `ee457a2` | Fix vendor table cutoff, add per-vendor filter dropdown | `index.html`, `static/app.js` | `git revert ee457a2` |
| `1ac9234` | Add date range filters to the Dashboard tab | `api/index.py`, `index.html`, `static/app.js` | `git revert 1ac9234` |
| `66acd86` | Add persistent Dashboard tab backed by all saved data | `api/index.py`, `index.html`, `static/app.js` | `git revert 66acd86` |
| `323ece1` | Remove net spend card, add custom date range filter to history chart | `index.html`, `static/app.js` | `git revert 323ece1` |

The three parser commits `daae18b`, `e4f6b83`, and `be238cd` are a single logical fix
applied in sequence. Revert them together, oldest-first, or first-cardholder attribution
will regress:

```bash
git revert --no-commit daae18b^..be238cd
```

### 2026-05-02 — Persistence and bulk upload

| SHA | Change | Files | Revert |
|---|---|---|---|
| `e10f34a` | Fix cardholder detection: drop date-break from lookahead, extend to 25 lines | `app/pdf_parser.py` | `git revert e10f34a` |
| `cf74d9b` | Add monthly line chart, category filter, and bulk PDF upload | `index.html`, `static/app.js`, `api/index.py` | `git revert cf74d9b` |
| `1cc434b` | Add transaction persistence, history view, and cardholder detection fixes | `api/index.py`, `app/pdf_parser.py`, `index.html`, `static/app.js` | `git revert 1cc434b` |

`1cc434b` created the `transaction_batches` and `transactions` tables. Reverting removes
the save and history routes but leaves both tables and all saved data intact in Postgres.

### 2026-05-01 — Platform migration and initial cardholder support

| SHA | Change | Files | Revert |
|---|---|---|---|
| `a72935c` | Fix Lauro cardholder detection: look ahead past interleaved PDF columns | `app/pdf_parser.py` | `git revert a72935c` |
| `49bde2a` | Fix cardholder detection for Citi multi-cardholder statements | `app/pdf_parser.py` | `git revert 49bde2a` |
| `a766c37` | Detect Title Case cardholder names, not just ALL-CAPS | `app/pdf_parser.py` | `git revert a766c37` |
| `21a8ebc` | Prevent card/bank section headers being detected as cardholder names | `app/pdf_parser.py` | `git revert 21a8ebc` |
| `4c78667` | Fix cardholder detection and normalise vendor names in analysis | `app/pdf_parser.py`, `static/app.js` | `git revert 4c78667` |
| `875f16f` | Add cardholder extraction from PDF and the vendor analysis section | `app/pdf_parser.py`, `index.html`, `static/app.js` | `git revert 875f16f` |
| `428b0e3` | Replace GitHub token with Vercel Blob Storage for model persistence | `api/index.py`, `requirements.txt` | `git revert 428b0e3` |
| `f87ecb3` | Add login, analytics dashboard, user tracking, and model retrain | `api/index.py`, `login.html`, `static/login.js`, `index.html`, `static/app.js` | `git revert f87ecb3` |
| `3cffd81` | Pin `scikit-learn==1.6.1` to match the model training version | `requirements.txt` | do not revert |
| `33b6e5c` | Serve everything through FastAPI: static files, HTML, and API | `api/index.py`, `vercel.json` | `git revert 33b6e5c` |
| `22fd1c2` | Fix entrypoint: use `api/index.py`, cover all rewrite path variants | `api/index.py`, `vercel.json` | `git revert 22fd1c2` |
| `8e9b206` | Rename `api/index.py` to `api/upload.py`, drop rewrite | `api/`, `vercel.json` | superseded by `22fd1c2` |
| `19a2120` | Remove `functions` block from `vercel.json` causing unmatched pattern error | `vercel.json` | do not revert |
| `ae7da54` | Revamp: replace Streamlit with FastAPI + HTML/JS frontend for Vercel | repository-wide | do not revert |

`3cffd81`, `19a2120`, and `ae7da54` are marked do-not-revert because each one fixes a
condition that breaks deployment outright. Unpinning scikit-learn breaks unpickling of the
bundled model; restoring the `functions` block breaks the Vercel build; reverting `ae7da54`
returns the project to Streamlit, which cannot run on the current hosting setup.

`8e9b206` was superseded four commits later by `22fd1c2`. Reverting it in isolation
reintroduces the routing bug it was trying to fix.

### 2025-06-19 — Original Streamlit scaffold

| SHA | Change | Files | Revert |
|---|---|---|---|
| `efd8524` | Update expense classifier pipeline and upload interface | `app/`, `model/` | historical |
| `061bdc1` | Fix import path for `pdf_parser` module | `app/` | historical |
| `f48c5d4` | Initial secure scaffold with Streamlit GPT-ready structure | repository-wide | historical |
| `4633598` | Create README.md | `README.md` | historical |

Pre-migration history. These commits describe an architecture the project no longer uses
and are not revertable in any meaningful sense.

---

## Uncommitted Work

Everything from the 2026-08-18 sessions is committed except the documentation itself, which
is going in as the commit described at the top of the change log. Nothing has been pushed —
`origin` is untouched, so the deployed application is still running `c33953d` until someone
pushes.

Deliberately left untracked:

- `billflow/` — Next.js 16 / React 19 / Tailwind 4 scaffold from `create-next-app`.
  Contains no application code beyond the default template page. Not deployed, not
  referenced by the FastAPI app. Removing the directory has no effect on the tool. Still
  awaiting a decision on whether it is a live effort.
- `.venv/` — local virtual environment built from `requirements.txt` for running the report
  verification script. Now ignored by git; safe to delete and rebuild at any time.
