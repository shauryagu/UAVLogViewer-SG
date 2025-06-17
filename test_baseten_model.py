import requests
import json

resp = requests.post(
    "https://model-7qrz950w.api.baseten.co/development/predict", # Make sure this URL is for your new deployment
    headers={"Authorization": "Api-Key wGbBIwJ0.mrN88VQHhXlUf8I6IXfydZ4fgxYR0RLF"},
    json={
        "prompt": "Explain the difference between MAVLink and Dataflash logs in 2-3 sentences."
    },
    stream=True
)

print("Status Code:", resp.status_code)
for chunk in resp.iter_content(chunk_size=None):
    if chunk:
        try:
            # The response chunks for streaming are typically bytes that need decoding
            print(chunk.decode('utf-8'), end="", flush=True)
        except json.JSONDecodeError:
            # If a chunk is not valid JSON, print its raw content
            print(chunk.decode('utf-8'), end="", flush=True)

print() # for a final newline