# app/embedder.py

import os
import pandas as pd
from sentence_transformers import SentenceTransformer
import faiss
import pickle

DATA_DIR = "data/parsed_approved"
VECTOR_DIR = "data/vector_store"
MODEL_NAME = "all-MiniLM-L6-v2"

def embed_data():
    model = SentenceTransformer(MODEL_NAME)
    texts = []
    metadata = []

    for filename in os.listdir(DATA_DIR):
        if filename.endswith(".csv"):
            df = pd.read_csv(os.path.join(DATA_DIR, filename))
            for idx, row in df.iterrows():
                desc = str(row["Description"])
                amount = str(row["Amount"])
                cardholder = str(row["Cardholder"])
                tx_type = str(row["Transaction Type"])
                full_text = f"{desc} | ${amount} | {cardholder} | {tx_type}"
                texts.append(full_text)
                metadata.append({
                    "file": filename,
                    "row": idx,
                    "description": desc,
                    "amount": amount,
                    "type": tx_type
                })

    embeddings = model.encode(texts, show_progress_bar=True)
    dim = embeddings.shape[1]

    index = faiss.IndexFlatL2(dim)
    index.add(embeddings)

    faiss.write_index(index, os.path.join(VECTOR_DIR, "faiss_index.index"))
    with open(os.path.join(VECTOR_DIR, "metadata.pkl"), "wb") as f:
        pickle.dump(metadata, f)

    print(f"[INFO] ✅ Embedded {len(texts)} records.")
