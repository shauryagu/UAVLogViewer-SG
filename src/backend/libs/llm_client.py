import os
from openai import OpenAI

def get_baseten_client():
    return OpenAI(
        api_key=os.environ.get("BASETEN_API_KEY"),
        base_url="https://inference.baseten.co/v1"
    )

def chat_with_llm(messages, model="meta-llama/Llama-4-Scout-17B-16E-Instruct", **kwargs):
    """
    Send a chat completion request to Baseten's OpenAI-compatible API and stream the response.
    Args:
        messages: List of dicts with 'role' and 'content'.
        model: Model slug (default: Llama-4-Scout).
        kwargs: Additional OpenAI parameters.
    Returns:
        The full streamed response as a string.
    """
    client = get_baseten_client()
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        stop=[],
        stream=True,
        stream_options={
            "include_usage": True,
            "continuous_usage_stats": True
        },
        top_p=1,
        max_tokens=1000,
        temperature=1,
        presence_penalty=0,
        frequency_penalty=0,
        **kwargs
    )
    result = ""
    for chunk in response:
        if chunk.choices and chunk.choices[0].delta.content is not None:
            result += chunk.choices[0].delta.content
    return result 