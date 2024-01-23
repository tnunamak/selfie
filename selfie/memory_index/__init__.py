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
from selfie.memory_index.memory_types import Memory, ScoredMemory
from selfie.memory_index.importance_scorer import ImportanceScorer
from selfie.memory_index.recency_scorer import RecencyScorer
from selfie.memory_index.relevance_scorer import RelevanceScorer
from txtai.embeddings import Embeddings
import logging

from txtai.pipeline import LLM

logger = logging.getLogger(__name__)

default_importance = 0.3


class MemoryIndex:
    def __init__(self, character_name, storage_path: str = default_storage_root, use_local_llm=True, completion_fn=None):
        logger.info("Initializing MemoryIndex")
        self.storage_path = os.path.join(storage_path, "index")
        self.completion_fn = completion_fn

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
    ) -> List[Memory]:
        chunks = ChatTrainingDataGenerator.group_messages_into_chunks(
            conversation, overlap=1, max_messages=8, max_characters=0
        )
        memories = []
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

            memory = Memory(
                content=formatted_conversation,
                timestamp=conv[0].timestamp,
                source=source,
            )

            if source_document_id:
                memory.source_document_id = source_document_id

            memories.append(memory)
        return memories

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

    async def _summarize_memories(
        self, character_name: str, memories: List[Memory], question, model
    ):
        logger.info(f"Summarizing {len(memories)} memories")

        if model is None:
            model = "gpt-3.5-turbo"
        if len(memories) == 0:
            return None
        memory_summary = "\n\n".join(
            [
                f"{humanize.naturaltime(datetime.now(timezone.utc) - memory.timestamp)}\n{memory.content}"
                for memory in memories
            ]
        )

        if character_name:
            prompt = f'### Instruction:\nYou are {character_name}. Below are conversation fragments from your recent memories. You are gathering your thoughts in preparation of responding to the message "{question}". In a sentence, concisely tell yourself what you can conclude about this topic from your memories, especially as it relates to you personally.\n\n### Input:\nStart of memories:\n{memory_summary}\nEnd of memories.\n\n### Concise response:\n{character_name}:\n'
        else:
            prompt = f'### Instruction:\nBelow are conversation fragments from an unknown person. You are gathering your thoughts in preparation of responding to the message "{question}". In a sentence, concisely answer what you can conclude about this topic from the memories.\n\n### Input:\nStart of memories:\n{memory_summary}\nEnd of memories.\n\n### Concise response:\nYou:\n'

        logger.info(f"Model: {model}")
        logger.info(f"Prompt: {prompt}")

        # TODO: truncate the prompt to fit the context window
        if model == "local":
            return await self.completion_fn(prompt)
        else:
            from litellm import completion

            openai_response = completion(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
            )
            return openai_response.choices[0].message.content

    def map_memory(self, memory: Memory, extract_importance=True):
        return {
            **({"id": memory.id} if memory.id is not None else {}),
            "timestamp": memory.timestamp.replace(tzinfo=timezone.utc).isoformat(),
            "text": memory.content,
            "source": memory.source,
            **(
                {
                    "importance": memory.importance
                    if memory.importance is not None  # Only calculate importance if it's not already set
                    else self.importance_scorer.calculate_score(memory)

                } if extract_importance else {}
            ),
            "created_timestamp": memory.created_timestamp.replace(tzinfo=timezone.utc).isoformat(),
            "updated_timestamp": memory.updated_timestamp.replace(tzinfo=timezone.utc).isoformat(),
            **({"source_document_id": memory.source_document_id} if memory.source_document_id is not None else {})
        }

    async def memorize(self, memories: List[Memory], extract_importance=True, upsert=False):
        logger.info(f"Memorizing {len(memories)} memories")

        memories = [
            await self.find_existing_memory(memory) or memory for memory in memories
        ] if upsert else memories

        with_importance = [
            self.map_memory(memory, extract_importance) for memory in memories
        ]
        self.embeddings.upsert(with_importance)
        self.embeddings.save(self.storage_path)

        return with_importance
        # TODO: return memory with ID, if possible

    async def recall(
        self,
        topic,
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
            return {"memories": [], "summary": "No memories found."}
        self.embeddings.load(self.storage_path)

        query = f"SELECT score, id, timestamp, text, importance, source, updated_timestamp, source_document_id FROM txtai WHERE similar(:topic)"
        results = self.embeddings.search(
            query, limit=limit, parameters={"topic": topic}
        )
        memories_list: List[ScoredMemory] = []
        for result in results:
            memory = Memory(
                content=result["text"],
                timestamp=result["timestamp"],
                importance=result["importance"],
                source=result["source"],
                updated_timestamp=result["updated_timestamp"],
                source_document_id=result["source_document_id"],
            )
            relevance_score = self.relevance_scorer.calculate_score(
                memory, result["score"]
            )
            recency_score = self.recency_scorer.calculate_score(memory)
            importance_score = memory.importance
            retrieval_score = self._calculate_retrieval_score(
                recency_score,
                relevance_score,
                importance_score,
                importance_weight,
                recency_weight,
                relevance_weight,
            )
            memories_list.append(
                ScoredMemory(
                    **memory.model_dump(),
                    score=retrieval_score,
                    relevance=relevance_score,
                    recency=recency_score,
                )
            )

        memories_list = [m for m in memories_list if m.score > min_score]
        if len(memories_list) == 0:
            return {"memories": [], "summary": "No memories found.", "mean_score": 0}

        memories_list.sort(key=lambda x: x.score, reverse=True)
        short_memories_list = memories_list[:limit]
        summary = (
            await self._summarize_memories(
                character_name,
                short_memories_list,
                topic,
                ("local" if local_llm else None),
            )
            if include_summary
            else None
        )
        return {"memories": short_memories_list, "summary": summary, "mean_score": sum([m.score for m in short_memories_list]) / len(short_memories_list)}

    # TODO: Fix this
    def delete_all(self):
        logger.info("Deleting all memories")
        if os.path.exists(self.storage_path):
            shutil.rmtree(self.storage_path)
            logger.info(f"Deleted storage path: {self.storage_path}")
            self.embeddings.index(documents=[])
        else:
            logger.info("Storage path not found, nothing to delete.")

    def delete_memory(self, memory_id):
        self.embeddings.delete([memory_id])
        self.embeddings.save(self.storage_path)
        # TODO: determine whether anything was actually deleted

    def update_memory(self, memory_id, updated_memory, extract_importance=True):
        self.embeddings.upsert(
            [(memory_id, self.map_memory(updated_memory, extract_importance))]
        )
        self.embeddings.save(self.storage_path)

    def get_memory_count(self):
        if not os.path.exists(self.storage_path):
            return 0

        self.embeddings.load(self.storage_path)
        result = self.embeddings.search("SELECT count(*) FROM txtai")
        return result[0]["count(*)"]

    async def get_memory(self, memory_id):
        if not os.path.exists(self.storage_path):
            return None  # TODO: raise exception
        self.embeddings.load(self.storage_path)
        query = f"SELECT id, timestamp, text, importance, source, updated_timestamp, source_document_id source FROM txtai WHERE id = {memory_id}"
        result = self.embeddings.search(query)
        return result[0] if result else None

    async def find_existing_memory(self, memory: Memory):
        if not os.path.exists(self.storage_path):
            return None
        self.embeddings.load(self.storage_path)
        query = f"SELECT id, timestamp, text, importance, source, created_timestamp, updated_timestamp, source_document_id FROM txtai WHERE text = :text AND timestamp = :timestamp AND source = :source AND source_document_id = :source_document_id"
        result = self.embeddings.search(
            query,
            parameters={
                "text": memory.content,
                "timestamp": memory.timestamp.isoformat(),
                "source": memory.source,
                "source_document_id": memory.source_document_id,
            },
        )
        if len(result) > 1:
            logger.warning(f"Found {len(result)} memories matching {memory})")
        if len(result) > 0:
            logger.debug(f"Found an existing memory matching")

            # TODO: This is kinda horrible
            result[0]['content'] = result[0]['text']
            del result[0]['text']
            result[0]['id'] = int(result[0]['id'])
            result[0]['source_document_id'] = int(result[0]['source_document_id'])

        return Memory(**result[0]) if result else None

    async def get_memories(self, offset=0, limit=10):
        if not os.path.exists(self.storage_path):
            return []
        self.embeddings.load(self.storage_path)
        query = f"SELECT id, timestamp, text, importance, source, updated_timestamp, source_document_id FROM txtai ORDER BY timestamp DESC LIMIT {limit} OFFSET {offset}"
        return self.embeddings.search(query)
