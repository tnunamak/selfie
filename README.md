# Selfie

Selfie personalizes text generation, augmenting both local and hosted Large Language Models (LLMs) with your personal data. Selfie exposes an OpenAI-compatible API that wraps the LLM of your choice, and automatically injects relevant context into each text generation request.

## Features

* Dedicated chat message loader that supports WhatsApp and Google Takeout exports.
* Load data using any [LlamaHub loader](https://llamahub.ai/?tab=loaders) (goal, partial support is currently available).
* Drop your data into any tool compatible with an OpenAI API:
  * `/api/v1/memory/completions` behaves like `/api/v1/completions` plus context from your data.
  * `/api/v1/memory/chat_completions` behaves like `/api/v1/chat_completions` plus context from your data.
* API endpoints for directly querying loaded data.
* Vanilla text generation APIs, if you just want a convenient interface for switching between models.

## Usage

In the future, pre-built executables will be available. For now, you can run selfie with Python:

1. `poetry shell`
2. `poetry install`
3. `python -m selfie`

This starts a local web server at http://localhost:8181.

### Recipe: Importing Chat Messages

1. Open http://localhost:8181/docs
2. Find `POST /api/v1/memories/chat-processor`
3. Upload one or more exported chat log files.
4. Copy, paste, and edit the example parser_configs JSON. Include one configuration object in the list for each file you upload.

![chat-processor.png](selfie/images/chat-processor.png)

Setting `extract_importance` to `true` will give you better query results, but usually causes the import to take a while.

### Recipe: Connecting with SillyTavern

1. Install and run [SillyTavern](https://github.com/SillyTavern/SillyTavern).
2. Configure a custom chat completion source as  `http://localhost:8181/v1/memory`. You can customize the model by setting API parameters for `method` and `model` in Additional Parameters.
![silly-tavern-api.png](selfie/images/silly-tavern-api.png)
3. Create a character, customize the text generation settings, etc.
4. Chat with your character to see that it is aware of your data:![silly-tavern-chat.png](selfie/images/silly-tavern-chat.png)

## Augmenting Local Models

Selfie uses [txtai](https://neuml.github.io/txtai) to download local models and run them with [llama.cpp](https://github.com/ggerganov/llama.cpp). In completion requests, specify the `llama.cpp` method, or leave it off as the default, and ensure that your model is defined correctly, as a local path or HuggingFace model, according to [txtai's documentation](https://neuml.github.io/txtai/models).

```json
"method": "llama.cpp"
"model": "~/models/dolphin-2.6-mistral-7b-dpo.Q5_K_M.gguf"
```
or
```json
"method": "llama.cpp"
"model": "TheBloke/dolphin-2.6-mistral-7B-dpo-GGUF/dolphin-2.6-mistral-7b-dpo.Q5_K_M.gguf"
```

## Augmenting Hosted Models

Selfie uses [txtai](https://neuml.github.io/txtai) to connect to hosted models with [litellm](https://litellm.vercel.app). In completion requests, specify the `litellm` method and ensure that your model is prefixed correctly according to [litellm's documentation for your provider](https://docs.litellm.ai/docs/providers).

```json
"method": "litellm",
"model": "replicate/llama-2-70b-chat:2796ee9483c3fd7aa2e171d38f4ca12251a30609463dcfd4cd76703f22e96cdf",
```

In general, you need an API key for your provided loaded into your environment. A quick way to do that is to specify it when you start the server:
`REPLICATE_API_KEY=replicatekey python -m selfie`.

## Building an Executable

Build an executable for your platform with `pyinstaller selfie.spec --noconfirm`.

Start the built service with `./dist/selfie/selfie`.
