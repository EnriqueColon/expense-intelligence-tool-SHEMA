import sys
import os
import io
import requests as http_requests
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

import joblib
import pandas as pd
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
SECRET_KEY   = os.environ.get("SECRET_KEY", "shema-intelligence-secret-2025")
APP_USERNAME = os.environ.get("APP_USERNAME", "admin")
APP_PASSWORD = os.environ.get("APP_PASSWORD", "shema2025")
BLOB_TOKEN   = os.environ.get("BLOB_READ_WRITE_TOKEN", "")
ALGORITHM    = "HS256"
TOKEN_HOURS  = 8

# --- App ---
app = FastAPI(title="SHEMA Expense Intelligence Tool")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

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
        {"sub": body.username, "exp": datetime.utcnow() + timedelta(hours=TOKEN_HOURS)},
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

@app.post("/api/retrain")
async def retrain_model(body: RetrainRequest, username: str = Depends(verify_token)):
    global pipeline
    if not body.transactions:
        raise HTTPException(status_code=400, detail="No transactions provided.")
    df = pd.DataFrame(body.transactions)
    df["Amount"] = pd.to_numeric(df.get("Amount", 0), errors="coerce").fillna(0)
    df = df.dropna(subset=["Description", "Category"])
    df = df[df["Description"].astype(str).str.strip() != ""]
    df = df[~df["Category"].astype(str).str.strip().isin(["", "Unclassified"])]
    if len(df) < 5:
        raise HTTPException(status_code=400, detail="Need at least 5 labeled transactions to retrain.")
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

    return {
        "success": True,
        "samples": len(df),
        "categories": sorted(y.unique().tolist()),
        "retrained_by": username,
        "persisted": saved
    }

@app.get("/api/health")
def health():
    return {"status": "ok", "model_loaded": pipeline is not None, "blob_configured": bool(BLOB_TOKEN)}
