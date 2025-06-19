import os
import joblib
import pandas as pd

# Load the trained pipeline model
model_path = os.path.join("models", "expense_classifier.pkl")

try:
    model = joblib.load(model_path)
except FileNotFoundError:
    raise FileNotFoundError(f"❌ Could not find the model at {model_path}. Make sure it exists and is correctly named.")

def predict_expense_categories(df: pd.DataFrame):
    """
    Predicts expense categories using the trained pipeline.
    Input must contain a 'Description' column.
    Returns a list of predicted labels.
    """
    if "Description" not in df.columns:
        raise ValueError("❌ The input DataFrame must contain a 'Description' column.")

    try:
        X = df["Description"].astype(str)
        predictions = model.predict(X)
        print(f"[DEBUG] Prediction count: {len(predictions)}")
        return predictions
    except Exception as e:
        print(f"[ERROR] Failed during prediction: {e}")
        raise
