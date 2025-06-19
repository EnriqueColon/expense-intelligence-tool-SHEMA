import os
import pandas as pd
import streamlit as st
from app.pdf_parser import parse_pdf
from app.services.expense_classifier import predict_expense_categories

def run_upload_interface():
    st.title("Upload & Review Expenses")

    uploaded_file = st.file_uploader("Drag and drop file here", type=["pdf"])
    if uploaded_file:
        file_path = os.path.join("data", "raw_uploads", uploaded_file.name)
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "wb") as f:
            f.write(uploaded_file.read())
        st.success(f"Uploaded file saved to {file_path}")

        try:
            # Parse transactions
            df = parse_pdf(open(file_path, "rb"))

            # Predict categories
            try:
                predictions = predict_expense_categories(df)
                df["Predicted_Category"] = predictions
            except Exception as e:
                st.error(f"Failed to categorize transactions: {e}")
                return

            # Editable table
            edited_df = st.data_editor(df, num_rows="dynamic", use_container_width=True)

            # Download CSV
            csv = edited_df.to_csv(index=False).encode("utf-8")
            st.download_button(
                label="Download CSV",
                data=csv,
                file_name=f"parsed_{uploaded_file.name.replace('.pdf', '.csv')}",
                mime="text/csv"
            )

            # Approve button
            if st.button("Approve and Save"):
                approved_path = os.path.join("data", "approved", uploaded_file.name.replace(".pdf", ".csv"))
                os.makedirs(os.path.dirname(approved_path), exist_ok=True)
                edited_df.to_csv(approved_path, index=False)
                st.success(f"✅ Approved data saved to: {approved_path}")

        except Exception as e:
            st.error(f"Failed to parse PDF: {e}")
