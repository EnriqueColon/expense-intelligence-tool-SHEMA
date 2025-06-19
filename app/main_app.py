import streamlit as st
from app.upload_review import run_upload_interface
from app.interface.gpt_tab import run_gpt_tab

def main():
    st.set_page_config(page_title="Expense Classifier", layout="wide")

    tabs = {
        "Upload & Review": run_upload_interface,
        "GPT Assistant": run_gpt_tab,
    }

    selected_tab = st.sidebar.radio("Navigation", list(tabs.keys()))
    tabs[selected_tab]()


if __name__ == "__main__":
    main()
