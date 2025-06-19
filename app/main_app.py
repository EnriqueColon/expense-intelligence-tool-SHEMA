import streamlit as st
from upload_review import run_upload_interface

# === App Entry Point ===
def main():
    st.set_page_config(page_title="Expense Classifier GPT", layout="wide")
    st.sidebar.title("Navigation")
    selection = st.sidebar.radio("Go to", ["📥 Upload & Review"])

    if selection == "📥 Upload & Review":
        run_upload_interface()


if __name__ == "__main__":
    main()
