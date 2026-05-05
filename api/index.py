import sys
import os
import io
import requests as http_requests
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

import joblib
import pandas as pd
import psycopg2
import psycopg2.extras
from fastapi import FastAPI, UploadFile, File, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from jose import JWTError, jwt
from sklearn.pipeline import Pipeline
from sklearn.ensemble import RandomForestClassifier
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer
from app.pdf_parser import parse_pdf_text, extract_transactions_from_text

# --- Config ---
SECRET_KEY    = os.environ.get("SECRET_KEY", "shema-intelligence-secret-2025")
APP_USERNAME  = os.environ.get("APP_USERNAME", "admin")
APP_PASSWORD  = os.environ.get("APP_PASSWORD", "shema2025")
BLOB_TOKEN    = os.environ.get("BLOB_READ_WRITE_TOKEN", "")
DATABASE_URL  = os.environ.get("POSTGRES_URL", "")
ALGORITHM     = "HS256"
TOKEN_HOURS   = 8

# --- App ---
app = FastAPI(title="SHEMA Expense Intelligence Tool")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

# --- Database ---
def get_db():
    if not DATABASE_URL:
        raise HTTPException(status_code=503, detail="Database not configured. Set the DATABASE_URL environment variable.")
    return psycopg2.connect(DATABASE_URL)

def _serialize(row: dict) -> dict:
    out = {}
    for k, v in row.items():
        if isinstance(v, Decimal):
            out[k] = float(v)
        elif hasattr(v, 'isoformat'):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out

def init_db():
    if not DATABASE_URL:
        print("[DB] DATABASE_URL not set — skipping table init")
        return
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS transaction_batches (
                id               SERIAL PRIMARY KEY,
                uploaded_by      VARCHAR(255) NOT NULL,
                filename         VARCHAR(255) DEFAULT '',
                created_at       TIMESTAMPTZ  DEFAULT NOW(),
                transaction_count INTEGER     DEFAULT 0
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id           SERIAL PRIMARY KEY,
                batch_id     INTEGER REFERENCES transaction_batches(id) ON DELETE CASCADE,
                sale_date    VARCHAR(10)   DEFAULT '',
                post_date    VARCHAR(10)   DEFAULT '',
                description  TEXT          DEFAULT '',
                amount       NUMERIC(12,2) DEFAULT 0,
                category     VARCHAR(100)  DEFAULT 'Unclassified',
                cardholder   VARCHAR(255)  DEFAULT 'Primary',
                processed_by VARCHAR(255)  DEFAULT '',
                notes        TEXT          DEFAULT '',
                created_at   TIMESTAMPTZ   DEFAULT NOW(),
                updated_at   TIMESTAMPTZ   DEFAULT NOW()
            )
        """)
        conn.commit()
        cur.close()
        conn.close()
        print("[DB] Tables ready")
    except Exception as e:
        print(f"[DB] Init failed: {e}")

init_db()

# --- Blob Storage helpers ---
BLOB_FILENAME = "expense_classifier.pkl"

def load_model_from_blob():
    if not BLOB_TOKEN:
        return None
    try:
        r = http_requests.get(
            "https://blob.vercel-storage.com",
            headers={"Authorization": f"Bearer {BLOB_TOKEN}"},
            params={"prefix": BLOB_FILENAME, "limit": 1},
            timeout=10
        )
        if r.status_code != 200:
            return None
        blobs = r.json().get("blobs", [])
        if not blobs:
            return None
        model_r = http_requests.get(blobs[0]["downloadUrl"], timeout=30)
        if model_r.status_code == 200:
            return joblib.load(io.BytesIO(model_r.content))
    except Exception as e:
        print(f"[BLOB] Load failed: {e}")
    return None

def save_model_to_blob(model_bytes: bytes) -> bool:
    if not BLOB_TOKEN:
        return False
    try:
        r = http_requests.put(
            f"https://blob.vercel-storage.com/{BLOB_FILENAME}",
            headers={
                "Authorization": f"Bearer {BLOB_TOKEN}",
                "Content-Type": "application/octet-stream",
                "x-add-random-suffix": "0"
            },
            data=model_bytes,
            timeout=30
        )
        return r.status_code in (200, 201)
    except Exception as e:
        print(f"[BLOB] Save failed: {e}")
        return False

# --- Model (try Blob first, fall back to bundled file) ---
MODEL_PATH = os.path.join(BASE_DIR, "model", "expense_classifier.pkl")
pipeline = load_model_from_blob()
if pipeline:
    print("[INFO] Model loaded from Vercel Blob")
else:
    try:
        pipeline = joblib.load(MODEL_PATH)
        print("[INFO] Model loaded from bundled file")
    except Exception as e:
        pipeline = None
        print(f"[ERROR] Could not load model: {e}")

# --- Auth ---
security = HTTPBearer()

class LoginRequest(BaseModel):
    username: str
    password: str

class RetrainRequest(BaseModel):
    transactions: list

class SaveTransactionsRequest(BaseModel):
    filename: str = ""
    transactions: list

class UpdateTransactionRequest(BaseModel):
    category: Optional[str] = None
    notes: Optional[str] = None

class RenameCardholderRequest(BaseModel):
    old_name: str
    new_name: str

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if not username:
            raise HTTPException(status_code=401, detail="Invalid token")
        return username
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

# --- Routes ---
@app.get("/")
def root():
    return FileResponse(os.path.join(BASE_DIR, "index.html"))

@app.get("/login")
def login_page():
    return FileResponse(os.path.join(BASE_DIR, "login.html"))

@app.post("/api/login")
def login(body: LoginRequest):
    if body.username != APP_USERNAME or body.password != APP_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = jwt.encode(
        {"sub": body.username, "exp": datetime.now(timezone.utc) + timedelta(hours=TOKEN_HOURS)},
        SECRET_KEY, algorithm=ALGORITHM
    )
    return {"token": token, "username": body.username}

@app.post("/api/upload")
async def upload_pdf(file: UploadFile = File(...), username: str = Depends(verify_token)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")
    contents = await file.read()
    try:
        lines = parse_pdf_text(io.BytesIO(contents))
        df = extract_transactions_from_text(lines)
        if df.empty:
            return {"transactions": [], "count": 0, "username": username}
        if pipeline is not None:
            X = df[["Description", "Amount"]].copy()
            X["Amount"] = pd.to_numeric(X["Amount"], errors="coerce").fillna(0)
            df["Category"] = pipeline.predict(X)
        else:
            df["Category"] = "Unclassified"
        df["Processed By"] = username
        if "Cardholder" not in df.columns:
            df["Cardholder"] = "Primary"
        records = df.fillna("").to_dict(orient="records")
        return {"transactions": records, "count": len(records), "username": username}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def _fit_and_save_pipeline(df: pd.DataFrame) -> tuple:
    """Train a new pipeline on df (must have Description, Amount, Category columns).
    Returns (new_pipeline, persisted: bool)."""
    global pipeline
    X = df[["Description", "Amount"]]
    y = df["Category"]
    text_pipe = Pipeline([("tfidf", TfidfVectorizer(stop_words="english"))])
    num_pipe  = Pipeline([("imputer", SimpleImputer(strategy="mean")), ("scaler", StandardScaler())])
    preprocessor = ColumnTransformer([
        ("desc", text_pipe, "Description"),
        ("amt",  num_pipe,  ["Amount"])
    ])
    new_pipeline = Pipeline([
        ("preprocessor", preprocessor),
        ("classifier", RandomForestClassifier(n_estimators=100, random_state=42))
    ])
    new_pipeline.fit(X, y)
    pipeline = new_pipeline
    model_buffer = io.BytesIO()
    joblib.dump(new_pipeline, model_buffer)
    saved = save_model_to_blob(model_buffer.getvalue())
    return new_pipeline, saved

@app.post("/api/retrain")
async def retrain_model(body: RetrainRequest, username: str = Depends(verify_token)):
    if not body.transactions:
        raise HTTPException(status_code=400, detail="No transactions provided.")
    df = pd.DataFrame(body.transactions)
    df["Amount"] = pd.to_numeric(df.get("Amount", 0), errors="coerce").fillna(0)
    df = df.dropna(subset=["Description", "Category"])
    df = df[df["Description"].astype(str).str.strip() != ""]
    df = df[~df["Category"].astype(str).str.strip().isin(["", "Unclassified"])]
    if len(df) < 5:
        raise HTTPException(status_code=400, detail="Need at least 5 labeled transactions to retrain.")
    _, saved = _fit_and_save_pipeline(df)
    y = df["Category"]
    return {
        "success": True,
        "samples": len(df),
        "categories": sorted(y.unique().tolist()),
        "retrained_by": username,
        "persisted": saved
    }

@app.post("/api/retrain/database")
def retrain_from_database(username: str = Depends(verify_token)):
    conn = get_db()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT description AS "Description",
                   amount::float AS "Amount",
                   category AS "Category"
            FROM transactions
            WHERE amount > 0
              AND description != ''
              AND category NOT IN ('Unclassified', '')
        """)
        rows = [dict(r) for r in cur.fetchall()]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

    if not rows:
        raise HTTPException(status_code=400, detail="No labeled transactions found in the database.")
    df = pd.DataFrame(rows)
    df["Amount"] = pd.to_numeric(df["Amount"], errors="coerce").fillna(0)
    df = df.dropna(subset=["Description", "Category"])
    df = df[df["Description"].astype(str).str.strip() != ""]
    df = df[~df["Category"].astype(str).str.strip().isin(["", "Unclassified"])]
    if len(df) < 5:
        raise HTTPException(status_code=400, detail=f"Need at least 5 labeled transactions (found {len(df)}).")
    _, saved = _fit_and_save_pipeline(df)
    y = df["Category"]
    return {
        "success": True,
        "samples": len(df),
        "categories": sorted(y.unique().tolist()),
        "retrained_by": username,
        "persisted": saved
    }

# --- Transaction persistence ---

@app.post("/api/transactions/save")
def save_transactions(body: SaveTransactionsRequest, username: str = Depends(verify_token)):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO transaction_batches (uploaded_by, filename, transaction_count) VALUES (%s, %s, %s) RETURNING id",
            (username, body.filename, len(body.transactions))
        )
        batch_id = cur.fetchone()[0]
        for txn in body.transactions:
            cur.execute(
                """INSERT INTO transactions
                   (batch_id, sale_date, post_date, description, amount, category, cardholder, processed_by)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    batch_id,
                    str(txn.get("Sale Date", "")),
                    str(txn.get("Post Date", "")),
                    str(txn.get("Description", "")),
                    float(txn.get("Amount", 0) or 0),
                    str(txn.get("Category", "Unclassified")),
                    str(txn.get("Cardholder", "Primary")),
                    str(txn.get("Processed By", username)),
                )
            )
        conn.commit()
        return {"success": True, "batch_id": batch_id, "count": len(body.transactions)}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@app.get("/api/transactions/history")
def get_history(username: str = Depends(verify_token)):
    conn = get_db()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "SELECT id, uploaded_by, filename, created_at, transaction_count FROM transaction_batches ORDER BY created_at DESC LIMIT 100"
        )
        rows = [_serialize(dict(r)) for r in cur.fetchall()]
        return {"batches": rows}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@app.get("/api/transactions/batch/{batch_id}")
def get_batch(batch_id: int, username: str = Depends(verify_token)):
    conn = get_db()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            """SELECT id, sale_date, post_date, description, amount, category,
                      cardholder, processed_by, notes, created_at, updated_at
               FROM transactions WHERE batch_id = %s ORDER BY id""",
            (batch_id,)
        )
        rows = [_serialize(dict(r)) for r in cur.fetchall()]
        return {"transactions": rows}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@app.patch("/api/transactions/{transaction_id}")
def update_transaction(
    transaction_id: int,
    body: UpdateTransactionRequest,
    username: str = Depends(verify_token)
):
    fields, values = [], []
    if body.category is not None:
        fields.append("category = %s")
        values.append(body.category)
    if body.notes is not None:
        fields.append("notes = %s")
        values.append(body.notes)
    if not fields:
        raise HTTPException(status_code=400, detail="Nothing to update.")
    fields.append("updated_at = NOW()")
    values.append(transaction_id)
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(f"UPDATE transactions SET {', '.join(fields)} WHERE id = %s", values)
        conn.commit()
        return {"success": True}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@app.patch("/api/transactions/batch/{batch_id}/rename-cardholder")
def rename_cardholder_in_batch(
    batch_id: int,
    body: RenameCardholderRequest,
    username: str = Depends(verify_token)
):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE transactions SET cardholder = %s, updated_at = NOW() WHERE batch_id = %s AND cardholder = %s",
            (body.new_name, batch_id, body.old_name)
        )
        count = cur.rowcount
        conn.commit()
        return {"success": True, "updated": count}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@app.delete("/api/transactions/batch/{batch_id}")
def delete_batch(batch_id: int, username: str = Depends(verify_token)):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM transaction_batches WHERE id = %s", (batch_id,))
        conn.commit()
        return {"success": True}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@app.get("/api/transactions/analytics")
def get_analytics(username: str = Depends(verify_token)):
    conn = get_db()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT
                TO_CHAR(tb.created_at, 'YYYY-MM') AS month,
                t.category,
                ROUND(SUM(t.amount)::numeric, 2)::float AS total
            FROM transactions t
            JOIN transaction_batches tb ON t.batch_id = tb.id
            WHERE t.amount > 0
            GROUP BY TO_CHAR(tb.created_at, 'YYYY-MM'), t.category
            ORDER BY month, t.category
        """)
        return {"data": [dict(r) for r in cur.fetchall()]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@app.get("/api/dashboard")
def get_dashboard(
    username: str = Depends(verify_token),
    start: Optional[str] = None,
    end:   Optional[str] = None,
):
    conn = get_db()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        date_clauses, date_params = [], []
        if start:
            date_clauses.append("TO_CHAR(tb.created_at, 'YYYY-MM') >= %s")
            date_params.append(start)
        if end:
            date_clauses.append("TO_CHAR(tb.created_at, 'YYYY-MM') <= %s")
            date_params.append(end)
        where = ("AND " + " AND ".join(date_clauses)) if date_clauses else ""

        cur.execute(f"""
            SELECT
                COUNT(t.id)::int                                                               AS total_transactions,
                COUNT(DISTINCT t.batch_id)::int                                                AS total_batches,
                ROUND(SUM(CASE WHEN t.amount > 0 THEN t.amount ELSE 0 END)::numeric, 2)::float AS total_charges,
                ROUND(SUM(CASE WHEN t.amount < 0 THEN ABS(t.amount) ELSE 0 END)::numeric, 2)::float AS total_credits,
                TO_CHAR(MIN(tb.created_at), 'YYYY-MM') AS min_month,
                TO_CHAR(MAX(tb.created_at), 'YYYY-MM') AS max_month
            FROM transactions t
            JOIN transaction_batches tb ON t.batch_id = tb.id
            WHERE 1=1 {where}
        """, date_params)
        stats = dict(cur.fetchone())

        cur.execute(f"""
            SELECT t.category, ROUND(SUM(t.amount)::numeric, 2)::float AS total
            FROM transactions t
            JOIN transaction_batches tb ON t.batch_id = tb.id
            WHERE t.amount > 0 {where}
            GROUP BY t.category
            ORDER BY total DESC
        """, date_params)
        categories = [dict(r) for r in cur.fetchall()]

        cur.execute(f"""
            SELECT t.description, ROUND(SUM(t.amount)::numeric, 2)::float AS total, COUNT(*)::int AS count
            FROM transactions t
            JOIN transaction_batches tb ON t.batch_id = tb.id
            WHERE t.amount > 0 {where}
            GROUP BY t.description
            ORDER BY total DESC
            LIMIT 500
        """, date_params)
        vendors = [dict(r) for r in cur.fetchall()]

        # Global count of labeled transactions available for model training
        cur.execute("""
            SELECT COUNT(*)::int AS labeled_transactions
            FROM transactions
            WHERE amount > 0 AND description != '' AND category NOT IN ('Unclassified', '')
        """)
        labeled = cur.fetchone()["labeled_transactions"]

        return {"stats": stats, "categories": categories, "vendors": vendors, "labeled_transactions": labeled}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "model_loaded": pipeline is not None,
        "blob_configured": bool(BLOB_TOKEN),
        "db_configured": bool(DATABASE_URL)
    }
