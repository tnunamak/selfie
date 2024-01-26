from datetime import datetime, timezone
import os
import shutil
from typing import Optional, List

import humanize

from selfie.config import default_storage_root, default_db_name, default_local_model
from selfie.data_processing.generators.chat_training_data import (
    ChatTrainingDataGenerator,
)
from selfie.data_processing.types import ShareGPTMessage
from selfie.data_index.document_types import Document, ScoredDocument
from selfie.data_index.importance_scorer import ImportanceScorer
from selfie.data_index.recency_scorer import RecencyScorer
from selfie.data_index.relevance_scorer import RelevanceScorer
from txtai.embeddings import Embeddings
import logging

from txtai.pipeline import LLM

logger = logging.getLogger(__name__)

default_importance = 0.3

llm = LLM(
    path=default_local_model,
    method="llama.cpp",
    n_ctx=8192,
    n_gpu_layers=-1,
)


class DataIndex:
    def __init__(self, character_name, storage_path: str = default_storage_root, use_local_llm=True, completion=None):
        logger.info("Initializing DataIndex")
        self.storage_path = os.path.join(storage_path, "index")

        async def completion_async(prompt):
            return llm(prompt)

        self.completion = completion or completion_async

        self.character_name = character_name
        self.embeddings = Embeddings(
            path="sentence-transformers/all-MiniLM-L6-v2",
            # TODO: may not work on Windows
            # https://docs.sqlalchemy.org/en/20/core/engines.html#sqlite
            content=f"sqlite:///{os.path.join(storage_path, default_db_name)}"
        )
        self.token_used = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }
        self.gpt3_call_count = 0
        self.importance_scorer = ImportanceScorer(
            score_weight=1, use_local_llm=use_local_llm
        )
        self.recency_scorer = RecencyScorer(score_weight=1)
        self.relevance_scorer = RelevanceScorer(score_weight=1)

        if os.path.exists(os.path.join(self.storage_path, "embeddings")):
            self.embeddings.load(self.storage_path)
        else:
            logger.info(
                "Embeddings file not found, starting with a new embeddings index."
            )

    @staticmethod
    def map_share_gpt_data(
        conversation: List[ShareGPTMessage], source: str = "Unknown", source_document_id: int = None
    ) -> List[Document]:
        chunks = ChatTrainingDataGenerator.group_messages_into_chunks(
            conversation, overlap=1, max_messages=8, max_characters=0
        )
        documents = []
        for i, conv in enumerate(chunks):
            if any("REDACTED" in msg.value for msg in conv):
                continue
            last_user = ""
            formatted_conversation = "\n".join(
                f"\n{(last_user := msg.from_user)}:\n{msg.value}"
                if msg.from_user != last_user
                else f"{msg.value}"
                for msg in conv
            ).strip()

            document = Document(
                content=formatted_conversation,
                timestamp=conv[0].timestamp,
                source=source,
            )

            if source_document_id:
                document.source_document_id = source_document_id

            documents.append(document)
        return documents

    @staticmethod
    def _calculate_retrieval_score(
        recency_score,
        relevance_score,
        importance_score=None,
        importance_weight=1,
        recency_weight=1,
        relevance_weight=1,
    ):
        if importance_score is None:
            importance_score = default_importance
        return (
            (importance_score * importance_weight)
            + (recency_score * recency_weight)
            + (relevance_score * relevance_weight)
        ) / (importance_weight + recency_weight + relevance_weight)

    async def _summarize_documents(
        self, character_name: str, documents: List[Document], context, model
    ):
        logger.info(f"Summarizing {len(documents)} documents")

        if model is None:
            model = "gpt-3.5-turbo"
        if len(documents) == 0:
            return None
        document_summary = "\n\n".join(
            [
                f"{humanize.naturaltime(datetime.now(timezone.utc) - document.timestamp)}\n{document.content}"
                for document in documents
            ]
        )

        if character_name:
            prompt = f'### Instruction:\nYou are {character_name}. Below are conversation fragments from your recent memories. You are gathering your thoughts in preparation of writing a response for "{context}". In a sentence, concisely tell yourself what you can conclude about this topic from your memories, especially as it relates to you personally.\n\n### Input:\nStart of memories:\n{document_summary}\nEnd of memories.\n\n### Concise response:\n{character_name}:\nBased on the given conversation fragments, it can be concluded that '
        else:
            prompt = f'### Instruction:\nBelow are conversation fragments from an unknown person. You are gathering your thoughts in preparation of writing a response for "{context}". In a sentence, concisely answer what you can conclude about this topic from the memories.\n\n### Input:\nStart of memories:\n{document_summary}\nEnd of memories.\n\n### Concise response:\nYou:\nBased on the given conversation fragments, it can be concluded that '

        logger.debug(f"Model: {model}")
        logger.debug(f"Prompt: {prompt}")

        # TODO: truncate the prompt to fit the context window
        if model == "local":
            return await self.completion(prompt)
        else:
            from litellm import completion

            openai_response = completion(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
            )
            return openai_response.choices[0].message.content

    def map_document(self, document: Document, extract_importance=True):
        return {
            **({"id": document.id} if document.id is not None else {}),
            "timestamp": document.timestamp.replace(tzinfo=timezone.utc).isoformat(),
            "text": document.content,
            "source": document.source,
            **(
                {
                    "importance": document.importance
                    if document.importance is not None  # Only calculate importance if it's not already set
                    else self.importance_scorer.calculate_score(document)

                } if extract_importance else {}
            ),
            "created_timestamp": document.created_timestamp.replace(tzinfo=timezone.utc).isoformat(),
            "updated_timestamp": document.updated_timestamp.replace(tzinfo=timezone.utc).isoformat(),
            **({"source_document_id": document.source_document_id} if document.source_document_id is not None else {})
        }

    async def index(self, documents: List[Document], extract_importance=True, upsert=False):
        logger.info(f"Indexing {len(documents)} documents")

        documents = [
            await self.find_existing_document(document) or document for document in documents
        ] if upsert else documents

        with_importance = [
            self.map_document(document, extract_importance) for document in documents
        ]
        self.embeddings.upsert(with_importance)
        self.embeddings.save(self.storage_path)

        return with_importance
        # TODO: return document with ID, if possible

    async def recall(
        self,
        topic: str,
        topic_context=None,
        character_name: Optional[str] = None,
        limit=5,
        importance_weight=0,
        recency_weight=1,
        relevance_weight=1,
        include_summary=True,
        local_llm=True,
        min_score=0.4,
    ):
        if min_score is None:
            min_score = 0.4

        if not os.path.exists(self.storage_path):
            return {"documents": [], "summary": "No documents found."}
        self.embeddings.load(self.storage_path)

        query = f"SELECT score, id, timestamp, text, importance, source, updated_timestamp, source_document_id FROM txtai WHERE similar(:topic)"
        results = self.embeddings.search(
            query, limit=limit, parameters={"topic": topic}
        )
        documents_list: List[ScoredDocument] = []
        for result in results:
            document = Document(
                content=result["text"],
                timestamp=result["timestamp"],
                importance=result["importance"],
                source=result["source"],
                updated_timestamp=result["updated_timestamp"],
                source_document_id=result["source_document_id"],
            )
            relevance_score = self.relevance_scorer.calculate_score(
                document, result["score"]
            )
            recency_score = self.recency_scorer.calculate_score(document)
            importance_score = document.importance
            retrieval_score = self._calculate_retrieval_score(
                recency_score,
                relevance_score,
                importance_score,
                importance_weight,
                recency_weight,
                relevance_weight,
            )
            documents_list.append(
                ScoredDocument(
                    **document.model_dump(),
                    score=retrieval_score,
                    relevance=relevance_score,
                    recency=recency_score,
                )
            )

        documents_list = [m for m in documents_list if m.score > min_score]
        if len(documents_list) == 0:
            return {"documents": [], "summary": "No documents found.", "mean_score": 0}

        documents_list.sort(key=lambda x: x.score, reverse=True)
        short_documents_list = documents_list[:limit]
        summary = (
            await self._summarize_documents(
                character_name,
                short_documents_list,
                topic_context if topic_context else topic,
                ("local" if local_llm else None),
            )
            if include_summary
            else None
        )
        return {"documents": short_documents_list, "summary": summary, "mean_score": sum([m.score for m in short_documents_list]) / len(short_documents_list)}

    # TODO: Fix this
    def delete_all(self):
        logger.info("Deleting all documents")
        if os.path.exists(self.storage_path):
            shutil.rmtree(self.storage_path)
            logger.info(f"Deleted storage path: {self.storage_path}")
            self.embeddings.index(documents=[])
        else:
            logger.info("Storage path not found, nothing to delete.")

    def delete_document(self, document_id):
        self.embeddings.delete([document_id])
        self.embeddings.save(self.storage_path)
        # TODO: determine whether anything was actually deleted

    def update_document(self, document_id, updated_document, extract_importance=True):
        self.embeddings.upsert(
            [(document_id, self.map_document(updated_document, extract_importance))]
        )
        self.embeddings.save(self.storage_path)

    def get_document_count(self):
        if not os.path.exists(self.storage_path):
            return 0

        self.embeddings.load(self.storage_path)
        result = self.embeddings.search("SELECT count(*) FROM txtai")
        return result[0]["count(*)"]

    async def get_document(self, document_id):
        if not os.path.exists(self.storage_path):
            return None  # TODO: raise exception
        self.embeddings.load(self.storage_path)
        query = f"SELECT id, timestamp, text, importance, source, updated_timestamp, source_document_id source FROM txtai WHERE id = {document_id}"
        result = self.embeddings.search(query)
        return result[0] if result else None

    async def find_existing_document(self, document: Document):
        if not os.path.exists(self.storage_path):
            return None
        self.embeddings.load(self.storage_path)
        query = f"SELECT id, timestamp, text, importance, source, created_timestamp, updated_timestamp, source_document_id FROM txtai WHERE text = :text AND timestamp = :timestamp AND source = :source AND source_document_id = :source_document_id"
        result = self.embeddings.search(
            query,
            parameters={
                "text": document.content,
                "timestamp": document.timestamp.isoformat(),
                "source": document.source,
                "source_document_id": document.source_document_id,
            },
        )
        if len(result) > 1:
            logger.warning(f"Found {len(result)} documents matching {document})")
        if len(result) > 0:
            logger.debug(f"Found an existing document matching")

            # TODO: This is kinda horrible
            result[0]['content'] = result[0]['text']
            del result[0]['text']
            result[0]['id'] = int(result[0]['id'])
            result[0]['source_document_id'] = int(result[0]['source_document_id'])

        return Document(**result[0]) if result else None

    async def get_documents(self, offset=0, limit=10):
        if not os.path.exists(self.storage_path):
            return []
        self.embeddings.load(self.storage_path)
        query = f"SELECT id, timestamp, text, importance, source, updated_timestamp, source_document_id FROM txtai ORDER BY timestamp DESC LIMIT {limit} OFFSET {offset}"
        return self.embeddings.search(query)
