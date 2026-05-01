import sys
import os
import io
import base64
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
SECRET_KEY    = os.environ.get("SECRET_KEY", "shema-intelligence-secret-2025")
APP_USERNAME  = os.environ.get("APP_USERNAME", "admin")
APP_PASSWORD  = os.environ.get("APP_PASSWORD", "shema2025")
GITHUB_TOKEN  = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO   = os.environ.get("GITHUB_REPO", "EnriqueColon/expense-intelligence-tool-SHEMA")
ALGORITHM     = "HS256"
TOKEN_HOURS   = 8

# --- App ---
app = FastAPI(title="SHEMA Expense Intelligence Tool")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

# --- Model ---
MODEL_PATH = os.path.join(BASE_DIR, "model", "expense_classifier.pkl")
try:
    pipeline = joblib.load(MODEL_PATH)
    print("[INFO] Model loaded successfully")
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

# --- GitHub helper ---
def commit_model_to_github(model_bytes: bytes) -> dict:
    if not GITHUB_TOKEN:
        return {"success": False, "reason": "GITHUB_TOKEN not configured"}
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/model/expense_classifier.pkl"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    existing = http_requests.get(url, headers=headers)
    payload = {
        "message": f"Retrain model via dashboard ({datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')})",
        "content": base64.b64encode(model_bytes).decode(),
        "branch": "main"
    }
    if existing.status_code == 200:
        payload["sha"] = existing.json().get("sha")
    r = http_requests.put(url, headers=headers, json=payload)
    if r.status_code in (200, 201):
        commit_url = r.json().get("commit", {}).get("html_url", "")
        return {"success": True, "commit_url": commit_url}
    return {"success": False, "reason": r.text[:200]}

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
    df = df[df["Category"].astype(str).str.strip().isin(["", "Unclassified"]) == False]
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
    github_result = commit_model_to_github(model_buffer.getvalue())
    return {
        "success": True,
        "samples": len(df),
        "categories": sorted(y.unique().tolist()),
        "retrained_by": username,
        "github": github_result
    }

@app.get("/api/health")
def health():
    return {"status": "ok", "model_loaded": pipeline is not None}
