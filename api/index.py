import sys
import os
import io

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

import joblib
import pandas as pd
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.pdf_parser import parse_pdf_text, extract_transactions_from_text

app = FastAPI(title="SHEMA Expense Intelligence Tool")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

MODEL_PATH = os.path.join(BASE_DIR, "model", "expense_classifier.pkl")

try:
    pipeline = joblib.load(MODEL_PATH)
except Exception as e:
    pipeline = None
    print(f"[WARNING] Could not load model: {e}")


@app.get("/")
def root():
    return FileResponse(os.path.join(BASE_DIR, "index.html"))


@app.post("/api/upload")
async def upload_pdf(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    contents = await file.read()

    try:
        lines = parse_pdf_text(io.BytesIO(contents))
        df = extract_transactions_from_text(lines)

        if df.empty:
            return {"transactions": [], "count": 0}

        if pipeline is not None:
            X = df[["Description", "Amount"]].copy()
            X["Amount"] = pd.to_numeric(X["Amount"], errors="coerce").fillna(0)
            df["Category"] = pipeline.predict(X)
        else:
            df["Category"] = "Unclassified"

        records = df.fillna("").to_dict(orient="records")
        return {"transactions": records, "count": len(records)}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/health")
def health():
    return {"status": "ok", "model_loaded": pipeline is not None}
