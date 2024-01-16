from datetime import datetime
from typing import List, Dict, Union, Any
import re

from selfie.data_processing.parsers.chat.base import TextBasedChatParser
from selfie.data_processing.types import ShareGPTMessage


class WhatsAppParser(TextBasedChatParser):
    SUPPORTED_FORMATS = [
        {
            'regex': r"\[(?P<timestamp>\d{1,2}/\d{1,2}/\d{2,4}, \d{1,2}:\d{2}:\d{2} (AM|PM))\] (?P<from>.+?): (?P<value>.+)",
            'timestamp_format': "%m/%d/%y, %I:%M:%S %p"
        },
        # Output format from vana-fine-tuning, probably not needed.
        {
            'regex': r"(?P<timestamp>\d{1,2}/\d{1,2}/\d{2}, \d{1,2}:\d{2} (AM|PM)) - (?P<from>.+?): (?P<value>.+)",
            'timestamp_format': "%m/%d/%y, %I:%M %p"
        },
        # Output format from vana-fine-tuning, probably not needed.
        {
            'regex': r"(?P<timestamp>\d{1,2}/\d{1,2}/\d{2}, \d{1,2}:\d{2}(AM|PM)) - (?P<from>.+?): (?P<value>.+)",
            'timestamp_format': "%m/%d/%y, %I:%M%p"
        },
    ]

    def parse_message(self, raw_message: List[str]) -> ShareGPTMessage:
        """
        Parse a single WhatsApp message from a list of lines that make up that message.

        Args:
            raw_message (List[str]): List of lines belonging to the same message.
                                     e.g., ["[1/1/21, 12:00 AM] Alice: Hi", "How are you?"]

        Returns:
            Dict[str, str]: A dictionary representing the parsed message.
                            Example structure:
                            {
                                "from": "Alice",
                                "value": "Hi\nHow are you?",
                                "timestamp": "2021-01-01T12:00:00Z"
                            }
        """

        full_message = "\n".join(raw_message)
        for format in self.SUPPORTED_FORMATS:
            match = re.match(format['regex'], full_message, flags=re.DOTALL)
            if match:
                groups = match.groupdict()
                timestamp_dt = datetime.strptime(groups['timestamp'], format['timestamp_format']).replace(tzinfo=self.timezone)
                groups['timestamp'] = timestamp_dt.isoformat()
                return ShareGPTMessage.model_validate(groups)
