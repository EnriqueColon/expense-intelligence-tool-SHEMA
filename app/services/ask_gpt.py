import requests

def ask_local_gpt(prompt: str, history: list = None) -> str:
    """
    Sends a prompt to the locally running Mistral model via Ollama and returns the response.

    Args:
        prompt (str): The input prompt for the LLM.
        history (list): Optional conversation history (not used in this simple example).

    Returns:
        str: The LLM's response.
    """
    url = "http://localhost:11434/api/generate"
    headers = {"Content-Type": "application/json"}
    data = {
        "model": "llama3",
        "prompt": prompt,
        "stream": False
    }

    try:
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        result = response.json()
        return result.get("response", "").strip()
    except requests.RequestException as e:
        return f"[Error communicating with local model: {e}]"
