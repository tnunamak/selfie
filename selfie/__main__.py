import uvicorn
import webbrowser
from selfie.server import app


@app.on_event("startup")
def open_browser():
    webbrowser.open("http://localhost:8181/docs")


# uvicorn.run("local:app", host="0.0.0.0", port=8181, reload=True)
uvicorn.run(app, host="0.0.0.0", port=8181)

# import io
# import os
# import sys
# import argparse
# import asyncio
# from typing import List
# from fastapi import UploadFile
#
# from selfie.data_processing.parsers.chat import ChatFileParser
# from selfie.data_processing.parsers.chat.chat_file_parsing_helper import (
#     ChatFileParserConfig,
#     get_files_with_full_configs,
# )
# from selfie.memory_stream.txtai import TxtaiMemoryStream
# import logging
#
#
# def convert_to_uploadfile(chat_file_path):
#     with open(chat_file_path, "rb") as chat_file:
#         contents = chat_file.read()
#         upload_file = UploadFile(filename=chat_file_path, file=io.BytesIO(contents))
#     return upload_file
#
#
# async def process_chat_files(
#         character_id: str, file_paths: List[str], main_speaker, format
# ):
#     chat_parser = ChatFileParser()
#     parser_configs = [
#                          ChatFileParserConfig(main_speaker=main_speaker, format=format.upper())
#                      ] * len(file_paths)
#
#     upload_files = [convert_to_uploadfile(path) for path in file_paths]
#     files_with_settings = get_files_with_full_configs(upload_files, parser_configs)
#
#     memories = []
#     new_memory_count = 0
#     for file_with_settings in files_with_settings:
#         file_data = chat_parser.parse_file(
#             file_with_settings["file"],
#             file_with_settings["config"].format,
#             file_with_settings["config"].speaker_aliases,
#         )
#         mapped_memories = TxtaiMemoryStream.map_share_gpt_data(
#             file_data.conversations, file_with_settings["file"].split("/")[-1]
#         )
#         file_memories = TxtaiMemoryStream(character_id).memorize(mapped_memories)
#         new_memory_count += len(file_memories)
#         memories.extend(file_memories)
#
#     return {
#         "success": True,
#         "num_memories": len(memories),
#         "num_new_memories": new_memory_count,
#     }
#
#
# async def main():
#     parser = argparse.ArgumentParser(description="Txtai Memory Stream CLI")
#
#     parser.add_argument("--character-id", type=str, help="Character ID")
#     parser.add_argument(
#         "--action",
#         choices=["count", "recall", "upload", "delete-all"],
#         help="Action to perform",
#     )
#     parser.add_argument("--topic", type=str, help="Topic for recall action")
#     parser.add_argument(
#         "--page", type=int, default=0, help="Page number for pagination"
#     )
#     parser.add_argument(
#         "--page-size", type=int, default=10, help="Number of items per page"
#     )
#     parser.add_argument("--openai-api-key", type=str, help="OpenAI API key")
#     parser.add_argument(
#         "--local-llm",
#         action="store_true",
#         default=False,
#         help="Use local LLM for summarization",
#     )
#     parser.add_argument(
#         "--debug", action="store_true", default=False, help="Enable debug logging"
#     )
#     parser.add_argument("--files", type=str, nargs="+", help="File(s) to process")
#     parser.add_argument("--files-main-speaker", type=str, help="Main speaker name")
#     parser.add_argument(
#         "--files-format", type=str, help='Chat file format (e.g., "whatsapp")'
#     )
#
#     args = parser.parse_args()
#
#     if args.debug:
#         logging.basicConfig(level=logging.DEBUG)
#         logging.getLogger("services.memory_stream.txtai").setLevel(logging.DEBUG)
#     else:
#         logging.getLogger("httpx").setLevel(logging.CRITICAL)
#         logging.getLogger("services.memory_stream.txtai").setLevel(logging.CRITICAL)
#         logging.getLogger("numexpr.utils").setLevel(logging.CRITICAL)
#         logging.getLogger("faiss.loader").setLevel(logging.CRITICAL)
#
#     if args.openai_api_key:
#         os.environ["OPENAI_API_KEY"] = args.openai_api_key
#
#     if not args.local_llm and os.environ.get("OPENAI_API_KEY", None) is None:
#         print(
#             "Use a --local-llm, or provide the OPENAI_API_KEY environment variable or argument (--openai-api-key)"
#         )
#         return
#
#     txtai_stream = TxtaiMemoryStream(args.character_id)
#
#     if args.action == "delete-all":
#         confirm = input("Are you sure you want to delete all memories? (yes/no): ")
#         if confirm.lower() == "yes":
#             txtai_stream.delete_all()
#             print("All memories have been deleted.")
#         else:
#             print("Operation cancelled.")
#             sys.exit()
#     elif args.action == "upload":
#         print(
#             await process_chat_files(
#                 args.character_id,
#                 args.files,
#                 args.files_main_speaker,
#                 args.files_format,
#             )
#         )
#     elif args.action == "count":
#         print(f"Total memories: {txtai_stream.get_memory_count()}")
#     elif args.action == "recall":
#         if not args.topic:
#             print("Topic is required for recall action")
#             return
#         recall_result = await txtai_stream.recall(args.topic, local_llm=args.local_llm)
#         print(recall_result.get("summary"))
#
#
# asyncio.run(main())
