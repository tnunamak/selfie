import os
import re
import sys
from enum import unique, Enum
from typing import Dict
import yaml

from selfie.data_processing.parsers.chat.discord import DiscordParser
from selfie.data_processing.parsers.chat.whatsapp import WhatsAppParser
from selfie.data_processing.parsers.chat.google import GoogleMessagesParser
from selfie.data_processing.types import ShareGPTConversation, ShareGPTMessage


# TODO: Clean this up
# Check if we are running in a PyInstaller bundle
if getattr(sys, "frozen", False):
    # If so, the base path is the path to the _MEIPASS folder
    base_path = sys._MEIPASS
    blacklist_file_path = os.path.join(
        base_path, "selfie/data_processing/parsers/chat/blacklist_patterns.yaml"
    )
else:
    # If not, the base path is the root of your project
    base_path = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    blacklist_file_path = os.path.join(
        base_path, "parsers/chat/blacklist_patterns.yaml"
    )
# current_dir = os.path.dirname(os.path.abspath(__file__))
# blacklist_file_path = os.path.join(current_dir, "blacklist_patterns.yaml")

with open(blacklist_file_path, "r") as f:
    default_blacklist_patterns = yaml.safe_load(f)
    default_blacklist_patterns = [
        pattern.strip() for pattern in default_blacklist_patterns
    ]


@unique
class Parser(Enum):
    WHATSAPP = WhatsAppParser
    DISCORD = DiscordParser
    GOOGLE_MESSAGES = GoogleMessagesParser


class ChatFileParser:
    @staticmethod
    def mask_text(text: str, mask: bool) -> str:
        return "*" * len(text) if mask else text

    def __init__(self, blacklist_patterns=None, rewrite_placeholder: str = "REDACTED"):
        self.parser_cache = {}
        self.blacklist_patterns = [
            re.compile(pattern, re.IGNORECASE)
            for pattern in default_blacklist_patterns + (blacklist_patterns or [])
        ]
        self.rewrite_placeholder = rewrite_placeholder

    def select_parser(self, parser_type: str):
        if parser_type not in self.parser_cache:
            self.parser_cache[parser_type] = Parser[parser_type.upper()].value()
        return self.parser_cache[parser_type]

    def is_blacklisted(self, line: str) -> bool:
        messages = line.split("\n")
        return any(
            any(pattern.search(message) for pattern in self.blacklist_patterns)
            for message in messages
        )

    def rewrite_blacklisted(self, text: str) -> str:
        if self.is_blacklisted(text):
            # logger.trace(f"Rewriting blacklisted text: {text}")
            return self.rewrite_placeholder
        return text

    def parse_file(
        self,
        input_file: str,
        parser_type: str,
        rename_speakers: Dict[str, str] = None,
        mask: bool = False,
    ) -> ShareGPTConversation:
        rename_speakers = rename_speakers or {}
        parser_instance = self.select_parser(parser_type)

        with open(input_file, "r", encoding="utf-8") as file:
            raw_lines = file.readlines()

        parsed_data = parser_instance.parse_chat(raw_lines)

        # Check if there are any conversations in the parsed data
        if not parsed_data.conversations:
            return ShareGPTConversation(conversations=[])

        # Process each message in the conversations
        processed_conversations = [
            ShareGPTMessage.model_validate(
                {
                    "from": rename_speakers.get(msg.from_user, msg.from_user),
                    "value": self.mask_text(self.rewrite_blacklisted(msg.value), mask),
                    "timestamp": msg.timestamp.isoformat(),
                }
            )
            for msg in parsed_data.conversations
        ]

        return ShareGPTConversation(conversations=processed_conversations)
