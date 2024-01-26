from typing import Optional, List

from fastapi import APIRouter
from pydantic import BaseModel

from selfie.data_manager import DataManager
from selfie.data_processing.parsers.chat import ChatFileParser
from selfie.memory_index import MemoryIndex

router = APIRouter()


class IndexDocumentsRequest(BaseModel):
    is_chat: bool = False
    document_ids: List[str] = []


@router.get("/v1/documents")
async def get_documents(source_id: Optional[int] = None):
    return DataManager().get_documents(source_id)


@router.post("/v1/documents/index")
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


# @app.delete("/v1/documents/{document-id}")
# async def delete_data_source(document_id: int):
#     DataSourceManager().remove_document(document_id)
#     return {"message": "Document removed successfully"}
