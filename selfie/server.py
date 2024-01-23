import os
import json
import litellm
from fastapi import FastAPI, HTTPException, File, Form, UploadFile, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from huggingface_hub import scan_cache_dir
from litellm import ModelResponse as LitellmCompletionResponse
from litellm.utils import _generate_id
from llama_cpp import (
    CreateCompletionResponse as LlamaCppCompletionResponse,
    CreateChatCompletionResponse as LlamaCppChatCompletionResponse,
)
from pydantic import BaseModel
from typing import List, Optional, Dict, Any, Union, Literal, ClassVar

from starlette.middleware.cors import CORSMiddleware
from txtai.pipeline import LLM, GenerationFactory
from sse_starlette.sse import EventSourceResponse

from selfie.config import default_local_model, default_local_gpu_model
from selfie.data_processing.parsers.chat import ChatFileParser
from selfie.data_processing.parsers.chat.chat_file_parsing_helper import (
    get_files_with_configs,
    delete_uploaded_files,
)
from selfie.data_manager import DataManager
from selfie.memory_index.memory_types import Memory
from selfie.memory_index.__init__ import MemoryIndex

import logging
logger = logging.getLogger(__name__)

litellm.drop_params = True

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

current_file_dir = os.path.dirname(os.path.realpath(__file__))
static_files_dir = os.path.join(current_file_dir, "web")

app.mount("/static", StaticFiles(directory=static_files_dir), name="static")


# TODO: Simplify this based on library types (txtai, litellm, openai)
class Message(BaseModel):
    role: str
    content: str


class FunctionCall(BaseModel):
    name: str
    parameters: Optional[Dict[str, Any]] = None


class Tool(BaseModel):
    type: str
    function: Optional[FunctionCall] = None

class BaseCompletionRequest(BaseModel):
    method: Optional[Literal["litellm", "llama.cpp", "transformers"]] = None
    model: Optional[str] = None
    frequency_penalty: Optional[float] = 0.0
    logit_bias: Optional[Dict[int, float]] = None
    # logprobs: Optional[bool] = False
    max_tokens: Optional[int] = None
    # n: Optional[int] = 1
    presence_penalty: Optional[float] = 0.0
    response_format: Optional[Dict[str, str]] = None
    seed: Optional[int] = None
    stop: Optional[Union[str, List[str]]] = None
    stream: Optional[bool] = False
    temperature: Optional[float] = 1.0
    top_p: Optional[float] = 1.0
    tools: Optional[List[Tool]] = None
    tool_choice: Optional[Union[str, Dict[str, Any]]] = None
    # user: Optional[str] = None
    api_base: Optional[str] = None
    api_key: Optional[str] = None

    custom_params: ClassVar[List[str]] = ["method", "api_base", "api_key"]

    def openai_params(self):
        return {
            k: v
            for k, v in self.model_dump().items()
            if k not in BaseCompletionRequest.custom_params and v is not None
        }

class ChatCompletionRequest(BaseCompletionRequest):
    messages: List[Message]


class CompletionRequest(BaseCompletionRequest):
    prompt: Union[str, List[str]]
    # best_of: Optional[int] = None
    echo: Optional[bool] = None
    logprobs: Optional[int] = None
    # n: Optional[int] = None
    suffix: Optional[str] = None


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: Optional[str]
    choices: List[Dict[str, Any]]
    usage: Dict[str, int]


@app.get("/", response_class=HTMLResponse)
async def serve_index_html():
    # Construct the full path to 'index.html'
    index_html_path = os.path.join(static_files_dir, "index.html")
    with open(index_html_path, "r") as f:
        return HTMLResponse(content=f.read())


@app.get("/v1/memory/v1/models")
@app.get("/v1/models")
async def get_models():
    hf_cache_info = scan_cache_dir()
    models = []

    for repo in hf_cache_info.repos:
        for revision in repo.revisions:
            gguf_files = [file for file in revision.files if file.file_name.endswith('.gguf')]
            if gguf_files:
                for gguf_file in gguf_files:
                    models.append({
                        "id": f"{repo.repo_id}/{gguf_file.file_name}",
                        "object": "model",
                        "created": gguf_file.blob_last_modified,
                        "owned_by": "user"
                    })
            else:
                models.append({
                    "id": repo.repo_id,
                    "object": "model",
                    "created": min(file.last_modified for file in repo.revisions),
                    "owned_by": "user"
                })

    return {
        "object": "list",
        "data": models
    }


async def completion(
    request: CompletionRequest | ChatCompletionRequest, use_memory: bool = False
) -> LlamaCppCompletionResponse | LlamaCppChatCompletionResponse | LitellmCompletionResponse | EventSourceResponse:
    chat_mode = isinstance(request, ChatCompletionRequest)

    if request.method is None and request.model:
        method = GenerationFactory.method(request.model, request.method)
    elif request.method is None:
        method = 'llama.cpp'
    else:
        method = request.method

    if use_memory:
        async def simple_completion(prompt):
            simple_result = await completion(CompletionRequest(
                api_base=request.api_base,
                api_key=request.api_key,
                method=method,
                model=request.model,
                prompt=prompt,
                max_tokens=512,
            ), use_memory=False)

            # Depending on the method used, could be simple_result['choices'][0]['text'] (simple_result as a dict)
            # or simple_result.choices[0].message.content
            if isinstance(simple_result, dict):
                return simple_result["choices"][0]["text"]
            else:
                return simple_result.choices[0].message.content

        memory_stream = MemoryIndex("n/a", completion_fn=simple_completion)
        if chat_mode:
            last_user_message = next(
                (
                    message
                    for message in reversed(request.messages)
                    if message.role == "user"
                ),
                None,
            )
            memories = await memory_stream.recall(last_user_message.content)
            # Find the first system message and insert the memory summary at the end. If there isn't one,
            # insert a new system message at the beginning.
            system_message = f"[System note: The AI recalls that: {memories['summary']}]"
            system_msgs = [m for m in request.messages if m.role == "system"]
            if system_msgs:
                system_msgs[0].content += f"\n\n{system_message}"
            else:
                request.messages.insert(0, Message(role="system", content=system_message))
        else:
            memories = await memory_stream.recall(request.prompt)
            request.prompt = f"[Recalled from memory: {memories['summary']}]\n\n{request.prompt}"

    open_ai_params = request.openai_params()

    if method == "llama.cpp":
        model = request.model or default_local_model
        logger.info(f"Using model {model}")
        llm = LLM(
            # verbose=True,
            path=model,
            method="llama.cpp",
            n_ctx=8192,
            n_gpu_layers=-1,
        ).generator.llm

        completion_fn = (
            llm.create_chat_completion if chat_mode else llm.create_completion
        )

        result = completion_fn(**open_ai_params)

        if request.stream:
            return EventSourceResponse({"data": json.dumps(item)} for item in result)
    elif method == "litellm":
        logger.info(f"Using model {request.model or 'litellm default'}")
        if not chat_mode:
            open_ai_params["messages"] = [{"content": open_ai_params["prompt"], "role": "user"}]
            del open_ai_params["prompt"]

        if "temperature" in open_ai_params and open_ai_params["temperature"] == 0.0:
            open_ai_params["temperature"] = 0.0000001

        # open_ai_params["instruction_template"] = "Mistral" # TODO: Investigate why the Mistral template isn't auto-selected

        result = litellm.completion(**open_ai_params)
        if request.stream:
            return EventSourceResponse(
                {"data": json.dumps(item.model_dump())} for item in result
            )
    elif method == "transformers":  # TODO: Check GPU support
        # # TODO: TL;DR this seems like way too much. Look for another library.
        # model = request.model or default_local_gpu_model
        # logger.info(f"Using model {model}")
        #
        # import torch
        # import transformers
        #
        # device = "cuda:0" if torch.cuda.is_available() else "cpu"
        #
        # from transformers import TextStreamer
        #
        # llm = LLM(
        #     path=model,
        #     method="transformers",
        #     device_map="auto",
        #     **({
        #         'quantization_config': transformers.GPTQConfig(bits=4, use_exllama=False)
        #     } if device is "cpu" else {})
        # )
        #
        # tokenizer = llm.generator.llm.pipeline.tokenizer
        #
        # # TODO: needs work
        # def transform_openai_params(open_ai_params: Dict[str, Any]) -> Dict[str, Any]:
        #     filtered_params = {key: value for key, value in open_ai_params.items()
        #                        if key not in
        #                        ['model', 'prompt', 'stream', 'logit_bias', 'max_tokens']} # TODO not ideal
        #     if chat_mode:
        #         filtered_params['text'] = tokenizer.apply_chat_template(request.messages, tokenize=False, add_generation_prompt=True)
        #         del filtered_params['messages']
        #     else:
        #         filtered_params['text'] = request.prompt
        #
        #     del filtered_params['frequency_penalty']
        #     del filtered_params['presence_penalty']
        #
        #     if request.stream:
        #         filtered_params['streamer'] = TextStreamer(tokenizer, skip_prompt=True)
        #
        #     return filtered_params
        #
        # id = _generate_id()
        # created = round(datetime.now().timestamp())
        # transformed_openai_params = transform_openai_params(open_ai_params)
        #
        # def make_response(text: str, finish_reason: str = None):
        #     prompt_tokens = tokenizer(transformed_openai_params['text'], return_tensors='pt')['input_ids'].size(1)
        #     completion_tokens = tokenizer(text, return_tensors='pt')['input_ids'].size(1)
        #
        #     return {
        #         'id': id,
        #         'object': 'chat.completion' if chat_mode else 'text_completion',
        #         'model': model,
        #         'created': created,
        #         'choices': [
        #             {
        #                 **({
        #                        "message": {
        #                            "content": text,
        #                            "role": "assistant"
        #                        }
        #                    } if chat_mode else {
        #                     "text": text,
        #                 }),
        #                 "index": 0,
        #                 "logprobs": None,
        #                 "finish_reason": finish_reason
        #             }
        #         ],
        #         'usage': {'prompt_tokens': prompt_tokens, 'completion_tokens': completion_tokens, 'total_tokens': prompt_tokens + completion_tokens}
        #     }
        #
        # generation = llm(**transformed_openai_params)
        # # print(f'Generation: {generation}')
        # if request.stream:
        #     return EventSourceResponse(
        #         (*({"data": json.dumps(make_response(item))} for item in generation),
        #           {"data": json.dumps(make_response("", finish_reason="stop"))})
        #     )
        #
        # result = make_response(generation, "stop")

        # # TODO: Make error response OpenAI-compatible
        raise HTTPException(status_code=501, detail="Method not yet implemented")
    else:
        raise HTTPException(status_code=400, detail="Invalid method")

    return result


@app.post("/v1/chat/completions")
async def create_chat_completion(
    request: ChatCompletionRequest,
) -> LlamaCppChatCompletionResponse | LitellmCompletionResponse:
    return await completion(request)


# TODO can StreamingResponse's schema be defined?
@app.post("/v1/completions")
async def create_completion(
    request: CompletionRequest,
) -> LlamaCppCompletionResponse | LitellmCompletionResponse:
    return await completion(request)


@app.post("/v1/memory/v1/chat/completions")
async def create_memory_chat_completion(
    request: ChatCompletionRequest,
) -> LlamaCppChatCompletionResponse | LitellmCompletionResponse:
    return await completion(request, use_memory=True)


@app.post("/v1/memory/v1/completions")
async def create_memory_completion(
    request: CompletionRequest,
) -> LlamaCppCompletionResponse | LitellmCompletionResponse:
    return await completion(request, use_memory=True)

@app.get("/v1/memories")
async def get_memories(offset: int = 0, limit: int = 10):
    return await MemoryIndex("n/a").get_memories(offset=offset, limit=limit)


@app.get("/v1/memories/summary")
async def get_memory_summary(topic: str, limit: Optional[int] = 5, min_score: Optional[float] = None):
    result = await MemoryIndex("n/a").recall(topic, limit=limit, min_score=min_score)
    return {
        "summary": result["summary"],
        "score": result["mean_score"],
        "memories": result["memories"],
    }


@app.post("/v1/memories")
async def create_memory(memory: Memory):
    memory_stream = MemoryIndex("n/a")
    return (await memory_stream.memorize([memory]))[0]


@app.get("/v1/memories/{memory_id}")
async def get_memory(memory_id: int):
    return await MemoryIndex("n/a").get_memory(memory_id)


@app.put("/v1/memories/{memory_id}")
async def update_memory(memory_id: int, memory: Memory):
    MemoryIndex("n/a").update_memory(memory_id, memory)
    return {"message": "Memory updated successfully"}


@app.delete("/v1/memories/{memory_id}")
async def delete_memory(memory_id: int):
    # Sometimes self.embeddings.save() errors on "database is locked", bricks it
    # raise HTTPException(status_code=501, detail="Not implemented")
    MemoryIndex("n/a").delete_memory(memory_id)
    return {"message": "Memory deleted successfully"}


@app.delete("/v1/memories")
async def delete_memories():
    MemoryIndex("n/a").delete_all()
    return {"message": "All memories deleted successfully"}


from llama_index.node_parser.text import SentenceSplitter
from datetime import datetime, timezone
import importlib


class DataLoaderRequest(BaseModel):
    name: Optional[str]
    loader_module: str
    constructor_args: Optional[List[Any]] = []
    constructor_kwargs: Optional[Dict[str, Any]] = {}
    load_data_args: Optional[List[Any]] = []
    load_data_kwargs: Optional[Dict[str, Any]] = {}


@app.post("/v1/memories/llama-hub-loader")
async def load_data(request: DataLoaderRequest):
    # TODO: extract document metadata from request?

    # Adapted from:
    # https://docs.llamaindex.ai/en/stable/examples/low_level/oss_ingestion_retrieval.html#build-an-ingestion-pipeline-from-scratch
    module_name, class_name = request.loader_module.rsplit(".", 1)
    module = importlib.import_module(module_name)
    loader_class = getattr(module, class_name)

    loader = loader_class(*request.constructor_args, **request.constructor_kwargs)

    documents = loader.load_data(*request.load_data_args, **request.load_data_kwargs)

    print(documents)

    text_parser = SentenceSplitter(
        chunk_size=1024,
        # separator=" ",
    )

    text_chunks = []
    # maintain relationship with source doc index, to help inject doc metadata in (3)
    doc_idxs = []
    for doc_idx, doc in enumerate(documents):
        cur_text_chunks = text_parser.split_text(doc.text)
        text_chunks.extend(cur_text_chunks)
        doc_idxs.extend([doc_idx] * len(cur_text_chunks))

    memories = []
    for idx, text_chunk in enumerate(text_chunks):
        src_doc = documents[doc_idxs[idx]]
        memory = Memory(
            content=text_chunk,
            source=request.loader_module,
            # importance=0.0,
            # timestamp=datetime.strptime(src_doc.metadata['last_modified'], "%Y-%m-%d"),
            # use last_modified if available, otherwise use current time
            timestamp=datetime.strptime(src_doc.metadata["last_modified"], "%Y-%m-%d")
            if "last_modified" in src_doc.metadata
            else datetime.now(),
        )

        memories.append(memory)

    return {"memories": await MemoryIndex("n/a").memorize(memories, extract_importance=False)}


@app.post("/v1/data-sources")
async def add_data_source(request: DataLoaderRequest):
    source_id = DataManager().add_data_source(
        request.name,
        request.loader_module,
        request.constructor_args,
        request.constructor_kwargs,
        request.load_data_args,
        request.load_data_kwargs,
    )
    return {"source_id": source_id}


@app.delete("/v1/data-sources/{source_id}")
async def delete_data_source(source_id: int):
    DataManager().remove_data_source(source_id)
    return {"message": "Data source removed successfully"}


@app.post("/v1/data-sources/{source_id}/scan")
async def scan_data_sources(source_id: int):
    return DataManager().scan_data_sources([source_id])


@app.post("/v1/data-sources/{source_id}/index")
async def index_data_source(source_id: int):
    manager = DataManager()
    data_source = manager.get_data_source(source_id)
    if isinstance(data_source, dict) and "error" in data_source:
        raise HTTPException(status_code=404, detail=data_source["error"])
    return await manager.index_documents(data_source)


class IndexDocumentsRequest(BaseModel):
    is_chat: bool = False
    document_ids: List[str] = []


@app.post("/v1/documents/index")
async def index_document(request: IndexDocumentsRequest):
    is_chat = request.is_chat
    document_ids = request.document_ids

    manager = DataManager()
    parser = ChatFileParser()

    # TODO: figure out what to do about this
    speaker_aliases = {}

    return [
        await manager.index_document(manager.get_document(document_id),
                               lambda document: MemoryIndex.map_share_gpt_data(
                                   parser.parse_document(
                                       document.text,
                                       None,
                                       speaker_aliases,
                                       False,
                                       document.id
                                   ).conversations,
                                   document.source.name,
                                   document.id
                               ) if is_chat else None)
        for document_id in document_ids
    ]


@app.get("/v1/data-sources")
async def get_data_sources():
    return DataManager().get_data_sources()


@app.get("/v1/documents")
async def get_documents(source_id: Optional[int] = None):
    return DataManager().get_documents(source_id)


@app.post("/v1/memories/chat-processor")
async def process_chat_files(
    character_name: str,
    files: List[UploadFile] = File(..., description="Upload chat files here."),
    parser_configs: str = Form(
        "[]",
        description="JSON string of parser configurations. Format can be whatsapp, google, discord. Example: "
        + '[{"main_speaker": "Alice", "format": "whatsapp", '
        + '"speaker_aliases": {"alicex": "Alice", "bobby": "Bob"}}]',
    ),
    extract_importance: bool = False,
):
    parser = ChatFileParser()
    memory_index = MemoryIndex(character_name)

    files_with_settings = get_files_with_configs(files, parser_configs)

    memories = []
    new_memory_count = 0
    for file_with_settings in files_with_settings:
        file_data = parser.parse_file(
            file_with_settings["file"],
            file_with_settings["config"].format,
            file_with_settings["config"].speaker_aliases,
        )

        mapped_memories = MemoryIndex.map_share_gpt_data(
            file_data.conversations, file_with_settings["file"].split("/")[-1]
        )

        file_memories = await memory_index.memorize(mapped_memories, extract_importance)
        new_memory_count += len(file_memories)
        memories.extend(file_memories)

    delete_uploaded_files(files_with_settings)

    return {
        "success": True,
        "num_memories": len(memories),
        "num_new_memories": new_memory_count,
    }


# @app.delete("/v1/documents/{document-id}")
# async def delete_data_source(document_id: int):
#     DataSourceManager().remove_document(document_id)
#     return {"message": "Document removed successfully"}
