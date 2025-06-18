import os
import requests
import json
from typing import List, Dict, Generator

class LLMClient:
    def __init__(self):
        self.api_url = os.environ.get("BASETEN_LLM_API_URL")
        self.api_key = os.environ.get("BASETEN_API_KEY")
        self.model = os.environ.get("BASETEN_LLM_MODEL", "mistralai/Mistral-7B-Instruct-v0.3")
        if not self.api_url or not self.api_key:
            raise ValueError("BASETEN_LLM_API_URL and BASETEN_API_KEY must be set in environment variables.")

    def stream_chat_response(self, messages: List[Dict], max_tokens: int = 512, temperature: float = 0.6) -> Generator[str, None, None]:
        # Convert messages to a single prompt string for Baseten format
        prompt = self._messages_to_prompt(messages)
        
        payload = {
            "model": self.model,
            "stream": True,
            "prompt": prompt,
            "max_tokens": max_tokens,
            "temperature": temperature
        }
        headers = {"Authorization": f"Api-Key {self.api_key}"}
        try:
            resp = requests.post(
                self.api_url,
                headers=headers,
                json=payload,
                stream=True,
                timeout=60
            )
            resp.raise_for_status()
            
            for line in resp.iter_lines():
                if not line:
                    continue
                    
                line_str = line.decode('utf-8').strip()
                
                # Skip empty lines and non-data lines
                if not line_str or not line_str.startswith("data: "):
                    continue
                    
                # Extract JSON after "data: "
                json_str = line_str[6:].strip()  # Remove "data: " prefix
                
                # Check for termination
                if json_str == "[DONE]":
                    break
                    
                try:
                    data = json.loads(json_str)
                    # Extract text from Baseten's OpenAI-compatible format
                    if 'choices' in data and data['choices'] and 'text' in data['choices'][0]:
                        text_chunk = data['choices'][0]['text']
                        if text_chunk:  # Only yield non-empty chunks
                            yield text_chunk
                except json.JSONDecodeError:
                    continue
        except Exception as e:
            yield f"[LLM Error: {str(e)}]"
    
    def _messages_to_prompt(self, messages: List[Dict]) -> str:
        """Convert OpenAI-style messages to a single prompt string."""
        prompt_parts = []
        for message in messages:
            role = message.get('role', 'user')
            content = message.get('content', '')
            if role == 'system':
                prompt_parts.append(f"System: {content}")
            elif role == 'user':
                prompt_parts.append(f"User: {content}")
            elif role == 'assistant':
                prompt_parts.append(f"Assistant: {content}")
        return "\n".join(prompt_parts) + "\nAssistant:"

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
        messages=messages, # not sure if this should be messages or prompt
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