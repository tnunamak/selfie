from typing import Optional, List

from fastapi import APIRouter, UploadFile, File, Form

from selfie.api.data_sources import DataLoaderRequest
from selfie.data_processing.parsers.chat import ChatFileParser
from selfie.data_processing.parsers.chat.chat_file_parsing_helper import get_files_with_configs, delete_uploaded_files
from selfie.memory_index import MemoryIndex
from selfie.memory_index.memory_types import Memory

from llama_index.node_parser.text import SentenceSplitter
from datetime import datetime
import importlib

router = APIRouter()


@router.get("/v1/memories")
async def get_memories(offset: int = 0, limit: int = 10):
    return await MemoryIndex("n/a").get_memories(offset=offset, limit=limit)


@router.get("/v1/memories/summary")
async def get_memory_summary(topic: str, limit: Optional[int] = 5, min_score: Optional[float] = None):
    result = await MemoryIndex("n/a").recall(topic, limit=limit, min_score=min_score)
    return {
        "summary": result["summary"],
        "score": result["mean_score"],
        "memories": result["memories"],
    }


@router.post("/v1/memories")
async def create_memory(memory: Memory):
    memory_stream = MemoryIndex("n/a")
    return (await memory_stream.memorize([memory]))[0]


@router.get("/v1/memories/{memory_id}")
async def get_memory(memory_id: int):
    return await MemoryIndex("n/a").get_memory(memory_id)


@router.put("/v1/memories/{memory_id}")
async def update_memory(memory_id: int, memory: Memory):
    MemoryIndex("n/a").update_memory(memory_id, memory)
    return {"message": "Memory updated successfully"}


@router.delete("/v1/memories/{memory_id}")
async def delete_memory(memory_id: int):
    # Sometimes self.embeddings.save() errors on "database is locked", bricks it
    # raise HTTPException(status_code=501, detail="Not implemented")
    MemoryIndex("n/a").delete_memory(memory_id)
    return {"message": "Memory deleted successfully"}


@router.delete("/v1/memories")
async def delete_memories():
    MemoryIndex("n/a").delete_all()
    return {"message": "All memories deleted successfully"}


@router.post("/v1/memories/llama-hub-loader")
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


@router.post("/v1/memories/chat-processor")
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
