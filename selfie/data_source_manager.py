from datetime import datetime

from llama_index.node_parser import SentenceSplitter
from peewee import (
    Model,
    SqliteDatabase,
    CharField,
    TextField,
    ForeignKeyField,
    AutoField,
    DoesNotExist,
)
import json
import importlib
from typing import List, Dict, Any, Optional

from selfie.memory_index.memory_types import Memory
from selfie.memory_index.__init__ import MemoryIndex

# Database setup
db = SqliteDatabase("data_sources.db")


# Database Models
class BaseModel(Model):
    class Meta:
        database = db


class DataSource(BaseModel):
    id = AutoField()
    name = CharField()
    loader_module = CharField()
    config = TextField()


class Document(BaseModel):
    id = AutoField()
    source = ForeignKeyField(DataSource, backref="documents")
    metadata = TextField()


db.connect()
db.create_tables([DataSource, Document])


class DataSourceManager:
    def add_data_source(
        self,
        name: str,
        loader_module: str,
        constructor_args: List[Any],
        constructor_kwargs: Dict[str, Any],
        load_data_args: List[Any],
        load_data_kwargs: Dict[str, Any],
    ) -> int:
        config = {
            "constructor_args": constructor_args,
            "constructor_kwargs": constructor_kwargs,
            "load_data_args": load_data_args,
            "load_data_kwargs": load_data_kwargs,
        }
        return DataSource.create(
            name=name, loader_module=loader_module, config=json.dumps(config)
        )

    def remove_data_source(self, source_id: int):
        DataSource.get_by_id(source_id).delete_instance()

    def scan_data_sources(self, source_ids: List[int]) -> Dict[str, Any]:
        changes = {}
        for source_id in source_ids:
            data_source = DataSource.get_by_id(source_id)
            documents = self._fetch_documents(
                data_source.loader_module, json.loads(data_source.config)
            )
            print(documents)
            for doc in documents:
                document, created = Document.get_or_create(
                    source=data_source, defaults={"metadata": json.dumps(doc.metadata)}
                )
                changes[document.id] = "Created" if created else "Updated"
        return changes

    def _fetch_documents(self, loader_module: str, config: Dict[str, Any]) -> List[Any]:
        module_name, class_name = loader_module.rsplit(".", 1)
        module = importlib.import_module(module_name)
        loader_class = getattr(module, class_name)
        loader = loader_class(
            *config["constructor_args"], **config["constructor_kwargs"]
        )
        return loader.load_data(*config["load_data_args"], **config["load_data_kwargs"])

    def _get_unique_key(self, doc, unique_key_path: str):
        keys = unique_key_path.split(".")
        value = doc
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key, None)
            else:
                value = getattr(value, key, None)
        return value

    def index_documents(self, data_source: DataSource):
        print("Indexing documents")

        # Ensure that the data source is in the database
        self.scan_data_sources([data_source.id])

        loader_module = data_source.loader_module

        documents = self._fetch_documents(loader_module, json.loads(data_source.config))
        memories = self._process_documents_to_memories(documents, loader_module)

        memory_stream = MemoryIndex("n/a")
        memory_stream.memorize(memories, extract_importance=False)

        # TODO: record the last time this data source was indexed

        return {"message": f"{len(documents)} documents indexed successfully"}

    def _process_documents_to_memories(self, documents, source):
        text_parser = SentenceSplitter(chunk_size=1024)
        memories = []

        for doc in documents:
            text_chunks = text_parser.split_text(doc.text)
            for text_chunk in text_chunks:
                timestamp = self._extract_timestamp(doc)
                memory = Memory(content=text_chunk, source=source, timestamp=timestamp)
                memories.append(memory)

        return memories

    @staticmethod
    def _extract_timestamp(doc):
        last_modified = doc.metadata.get("last_modified")
        if last_modified:
            return datetime.strptime(last_modified, "%Y-%m-%d")
        return datetime.now()

    @staticmethod
    def get_data_source(source_id: int):
        try:
            return DataSource.get_by_id(source_id)
        except DoesNotExist:
            return {"error": "Data source not found"}
        except Exception as e:
            return {"error": str(e)}

    def get_data_sources(self):
        return [
            {
                "name": source.name,
                "id": source.id,
                "loader_module": source.loader_module,
                "config": json.loads(source.config),
            }
            for source in DataSource.select()
        ]

    def get_documents(self, source_id: Optional[int] = None):
        if source_id:
            documents = Document.select().where(Document.source_id == source_id)
        else:
            documents = Document.select()

        return [
            {"id": doc.id, "metadata": json.loads(doc.metadata)} for doc in documents
        ]  # Example usage


if __name__ == "__main__":
    manager = DataSourceManager()

    # # Adding a SimpleWebPageReader data source
    # constructor_args_web = []
    # constructor_kwargs_web = {"html_to_text": True}
    # load_data_args_web = []
    # load_data_kwargs_web = {"urls": ["http://paulgraham.com/worked.html"]}
    # source_id_web = manager.add_data_source("llama_index.readers.SimpleWebPageReader", constructor_args_web, constructor_kwargs_web, load_data_args_web, load_data_kwargs_web, "metadata.url").id
    #
    # # Adding a SimpleDirectoryReader data source
    # constructor_args_dir = []
    # constructor_kwargs_dir = {"input_dir": "/home/tnunamak/Downloads/tim_misc_text", "recursive": True, "num_files_limit": 5}
    # load_data_args_dir = []
    # load_data_kwargs_dir = {}
    # source_id_dir = manager.add_data_source("llama_index.readers.SimpleDirectoryReader", constructor_args_dir, constructor_kwargs_dir, load_data_args_dir, load_data_kwargs_dir, "metadata.file_path").id

    # Scanning data sources
    # changes_web = manager.scan_data_sources([source_id_web])
    # changes_dir = manager.scan_data_sources([source_id_dir])
    # print("Web Changes:", changes_web)
    # print("Directory Changes:", changes_dir)

    # for data_source in DataSource.select():
    #     manager.index_documents(data_source)
    # print(data_source.id, data_source.loader_module, data_source.config)

    # source_id = -1  # Example source ID
    # result = manager.index_documents(source_id)
    # print(result)

    # Cleanup
    # manager.remove_data_source(source_id_web)
    # manager.remove_data_source(source_id_dir)
