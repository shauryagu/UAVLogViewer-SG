"""
The `Model` class is an interface between the ML model that you're packaging and the model
server that you're running it on.

The main methods to implement here are:
* `load`: runs exactly once when the model server is spun up or patched and loads the
   model onto the model server. Include any logic for initializing your model, such
   as downloading model weights and loading the model into memory.
* `predict`: runs every time the model server is called. Include any logic for model
  inference and return the model output.

See https://truss.baseten.co/quickstart for more.
"""

from threading import Thread
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, TextIteratorStreamer, GenerationConfig
import os

class Model:
    def __init__(self, **kwargs):
        self._secrets = kwargs["secrets"]
        self._model = None
        self._tokenizer = None

    def load(self):
        model_name = "mistralai/Mistral-7B-Instruct-v0.2"
        hf_token = self._secrets["hf_access_token"]
        print("[DEBUG] Hugging Face token loaded from secrets:", bool(hf_token))
        print("[DEBUG] Starting to load tokenizer and model from Hugging Face...")
        try:
            self._tokenizer = AutoTokenizer.from_pretrained(model_name, token=hf_token, use_fast=False)
            print("[DEBUG] Tokenizer loaded successfully.")
            self._model = AutoModelForCausalLM.from_pretrained(
                model_name,
                torch_dtype=torch.float16,
                device_map="auto",
                load_in_8bit=True,
                token=hf_token
            )
            print("[DEBUG] Model loaded successfully.")
        except Exception as e:
            print("[ERROR] Exception during model/tokenizer loading:", e)
            raise

    def predict(self, request: dict):
        stream = request.pop("stream", True)
        prompt = request.pop("prompt")
        
        # Note: Mistral's instruction format is `[INST] {prompt} [/INST]`
        formatted_prompt = f"[INST] {prompt} [/INST]"

        input_ids = self._tokenizer(formatted_prompt, return_tensors="pt").input_ids.to("cuda")

        generation_args = {
            "max_new_tokens": request.get("max_new_tokens", 1024),
            "temperature": request.get("temperature", 0.7),
            "top_p": request.get("top_p", 0.95),
            "do_sample": True,
            "pad_token_id": self._tokenizer.eos_token_id,
        }

        if stream:
            return self.stream(input_ids, generation_args)

        with torch.no_grad():
            output = self._model.generate(inputs=input_ids, **generation_args)
            return self._tokenizer.decode(output[0], skip_special_tokens=True)

    def stream(self, input_ids: list, generation_args: dict):
        streamer = TextIteratorStreamer(self._tokenizer, skip_prompt=True, skip_special_tokens=True)

        generation_config = GenerationConfig(**generation_args)
        generation_kwargs = {
            "input_ids": input_ids,
            "generation_config": generation_config,
            "streamer": streamer,
        }

        with torch.no_grad():
            thread = Thread(target=self._model.generate, kwargs=generation_kwargs)
            thread.start()

            def inner():
                for text in streamer:
                    yield text
                thread.join()

        return inner()
