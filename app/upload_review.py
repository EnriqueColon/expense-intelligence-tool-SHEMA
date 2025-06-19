import streamlit as st
import pandas as pd
import os
from datetime import datetime
from pdf_parser import parse_pdf  


def save_dataframe(df, folder):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"parsed_{timestamp}.csv"
    output_path = os.path.join(folder, filename)
    df.to_csv(output_path, index=False)
    return output_path


def run_upload_interface():
    st.title("📥 PDF Upload and Expense Review")

    uploaded_file = st.file_uploader("Upload a PDF bank statement", type=["pdf"])

    if uploaded_file is not None:
        try:
            df = parse_pdf(uploaded_file)
            st.success("✅ PDF parsed successfully!")
            st.dataframe(df)

            approval = st.radio("Do you want to approve and save this data?", ("No", "Yes"))

            if approval == "Yes":
                saved_path = save_dataframe(df, "data/parsed_approved")
                st.success(f"✅ Data approved and saved to: {saved_path}")
            else:
                saved_path = save_dataframe(df, "data/parsed_pending")
                st.warning(f"⚠️ Data not approved. Saved to: {saved_path}")

        except Exception as e:
            st.error(f"❌ Error while parsing PDF: {e}")
