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


class Model:
    def __init__(self, **kwargs):
        # vLLM handles model loading and inference; no custom logic needed
        pass

    def load(self):
        # vLLM loads the model via the docker_server start_command
        pass

    def predict(self, model_input):
        # vLLM handles inference via the OpenAI-compatible API endpoint
        return model_input
