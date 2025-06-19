import streamlit as st
from app.services.ask_gpt import ask_local_gpt


def run_gpt_tab():
    st.header("💬 GPT Expense Assistant")

    user_input = st.text_area("Ask a question about your expenses:")
    if st.button("Submit") and user_input.strip():
        with st.spinner("Thinking..."):
            response = ask_local_gpt(user_input)
        st.markdown("**Response:**")
        st.write(response)
