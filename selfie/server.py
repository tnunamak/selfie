import os
import json
import litellm
from fastapi import FastAPI, HTTPException, File, Form, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from litellm import ModelResponse as LitellmCompletionResponse
from llama_cpp import (
    CreateCompletionResponse as LlamaCppCompletionResponse,
    CreateChatCompletionResponse as LlamaCppChatCompletionResponse,
)
from pydantic import BaseModel
from typing import List, Optional, Dict, Any, Union, Literal

from starlette.middleware.cors import CORSMiddleware
from txtai.pipeline import LLM
from sse_starlette.sse import EventSourceResponse

from selfie.data_processing.parsers.chat import ChatFileParser
from selfie.data_processing.parsers.chat.chat_file_parsing_helper import (
    get_files_with_configs,
    delete_uploaded_files,
)
from selfie.data_source_manager import DataSourceManager
from selfie.memory_index.memory_types import Memory
from selfie.memory_index.__init__ import MemoryIndex

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


class ChatCompletionRequest(BaseModel):
    method: Literal["litellm", "llama.cpp", "transformers"] = "llama.cpp"
    # model: str = "TheBloke/Mistral-7B-OpenOrca-GGUF/mistral-7b-openorca.Q4_K_M.gguf"
    model: str = "TheBloke/dolphin-2.6-mistral-7B-dpo-GGUF/dolphin-2.6-mistral-7b-dpo.Q5_K_M.gguf"
    messages: List[Message]
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


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[Dict[str, Any]]
    usage: Dict[str, int]


class CompletionRequest(BaseModel):
    method: Literal["litellm", "llama.cpp", "transformers"] = "llama.cpp"
    model: str = "TheBloke/dolphin-2.6-mistral-7B-dpo-GGUF/dolphin-2.6-mistral-7b-dpo.Q5_K_M.gguf"
    prompt: Union[str, List[str]]
    # best_of: Optional[int] = None
    echo: Optional[bool] = None
    frequency_penalty: Optional[float] = None
    logit_bias: Optional[Dict[int, float]] = None
    logprobs: Optional[int] = None
    max_tokens: Optional[int] = None
    # n: Optional[int] = None
    presence_penalty: Optional[float] = None
    seed: Optional[int] = None
    stop: Optional[Union[str, List[str]]] = None
    stream: Optional[bool] = None
    suffix: Optional[str] = None
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    # user: Optional[str] = None


@app.get("/", response_class=HTMLResponse)
async def serve_index_html():
    # Construct the full path to 'index.html'
    index_html_path = os.path.join(static_files_dir, "index.html")
    with open(index_html_path, "r") as f:
        return HTMLResponse(content=f.read())


async def completion(
    request: CompletionRequest | ChatCompletionRequest, use_memory: bool = False
) -> LlamaCppCompletionResponse | LlamaCppChatCompletionResponse | LitellmCompletionResponse | EventSourceResponse:
    chat_mode = isinstance(request, ChatCompletionRequest)

    if use_memory:
        memory_stream = MemoryIndex("n/a")
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
            last_message = request.messages[-1]
            # if last_message.role == "system":
            #     last_message.content = f"{last_message.content}\n[Recalled from memory: {memories['summary']}]"
            # else:
            #     request.messages.append(Message(role="system", content=f"[Recalled from memory: {memories['summary']}]"))
            request.messages.append(
                Message(
                    role="assistant", content=f"[Thinks to self: {memories['summary']}]"
                )
            )
            print(request.messages)
        else:
            memories = await memory_stream.recall(request.prompt)
            memory_string = f"[Recalled from memory: {memories['summary']}]"
            new_prompt = f"{memory_string}\n\n{request.prompt}"
            print(new_prompt)
            request.prompt = new_prompt

    # TODO: support transformers method (txtai)
    custom_params = ["method"]
    open_ai_params = {
        k: v
        for k, v in request.model_dump().items()
        if k not in custom_params and v is not None
    }

    if request.method == "llama.cpp":
        model = (
            request.model
            or "TheBloke/dolphin-2.6-mistral-7B-dpo-GGUF/dolphin-2.6-mistral-7b-dpo.Q5_K_M.gguf"
        )
        # "TheBloke/Mistral-7B-OpenOrca-GGUF/mistral-7b-openorca.Q4_K_M.gguf"
        llm = LLM(
            path=model, method="llama.cpp", n_ctx=8192, n_gpu_layers=-1
        ).generator.llm

        completion_fn = (
            llm.create_chat_completion if chat_mode else llm.create_completion
        )

        result = completion_fn(**open_ai_params)

        if request.stream:
            return EventSourceResponse({"data": json.dumps(item)} for item in result)
    elif request.method == "transformers":
        # TODO: Make error response OpenAI-compatible
        raise HTTPException(status_code=501, detail="Method not yet implemented")
    elif request.method == "litellm":
        result = litellm.completion(**open_ai_params)
        if request.stream:
            return EventSourceResponse(
                {"data": json.dumps(item.model_dump())} for item in result
            )
    else:
        raise HTTPException(status_code=400, detail="Invalid method")

    # TODO: return StreamingResponse here instead
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


@app.post("/v1/memory/chat/completions")
async def create_completion(
    request: ChatCompletionRequest,
) -> LlamaCppCompletionResponse | LitellmCompletionResponse:
    return await completion(request, use_memory=True)


@app.post("/v1/memory/completions")
async def create_completion(
    request: CompletionRequest,
) -> LlamaCppCompletionResponse | LitellmCompletionResponse:
    return await completion(request, use_memory=True)


@app.get("/v1/memories")
async def get_memories(offset: int = 0, limit: int = 10):
    return await MemoryIndex("n/a").get_memories(offset=offset, limit=limit)


@app.get("/v1/memories/summary")
async def get_memory_summary(topic: str):
    return {
        "summary": (
            await MemoryIndex("n/a").recall(topic, limit=3, include_summary=True)
        )["summary"]
    }


@app.post("/v1/memories")
async def create_memory(memory: Memory):
    memory_stream = MemoryIndex("n/a")
    return memory_stream.memorize([memory])[0]


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
from datetime import datetime
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

    return {"memories": MemoryIndex("n/a").memorize(memories, extract_importance=False)}


@app.post("/v1/data-sources")
async def add_data_source(request: DataLoaderRequest):
    source_id = DataSourceManager().add_data_source(
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
    DataSourceManager().remove_data_source(source_id)
    return {"message": "Data source removed successfully"}


@app.post("/v1/data-sources/{source_id}/scan")
async def scan_data_sources(source_id: int):
    return DataSourceManager().scan_data_sources([source_id])


@app.post("/v1/data-sources/{source_id}/index")
async def index_data_source(source_id: int):
    manager = DataSourceManager()
    data_source = manager.get_data_source(source_id)
    if isinstance(data_source, dict) and "error" in data_source:
        raise HTTPException(status_code=404, detail=data_source["error"])
    return manager.index_documents(data_source)


@app.get("/v1/data-sources")
async def get_data_sources():
    return DataSourceManager().get_data_sources()


@app.get("/v1/documents")
async def get_documents(source_id: Optional[int] = None):
    return DataSourceManager().get_documents(source_id)


@app.post("/api/v1/memories/chat-processor")
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

        file_memories = memory_index.memorize(mapped_memories, extract_importance)
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
