import streamlit as st

st.set_page_config(page_title="Secure Expense Classifier", layout="wide")
st.title("🧾 Secure PDF Expense Uploader (AI-Enhanced)")

st.markdown("""
This is the upgraded version of your expense classification tool with:
- 🔐 Secure architecture
- 🧠 GPT support (coming soon)
- ✅ Manual approval before data is saved
""")

st.subheader("Step 1: Upload your bank/credit card statement (PDF)")
uploaded_file = st.file_uploader("Drag and drop a PDF", type=["pdf"])

if uploaded_file:
    st.success("File received. Parsing & categorization will go here...")
