from typing import Dict, Any

from selfie.data_processing.parsers.chat.base import JsonBasedChatParser
from selfie.data_processing.types import ShareGPTConversation


# TODO: This is a hypothetical parser for Discord data. It's not tested.
class DiscordParser(JsonBasedChatParser):
    def extract_conversations(self, data: Any) -> ShareGPTConversation:
        """
        Extract conversations from parsed Discord JSON data.

        Args:
            data (Any): The parsed JSON data should have a structure like:
                        {
                            "messages": [
                                {"author": {"name": "Alice"}, "content": "Hi", "timestamp": "2021-01-01T12:00:00Z"},
                                {"author": {"name": "Bob"}, "content": "Hello", "timestamp": "2021-01-01T12:01:00Z"}
                            ]
                        }

        Returns:
            Dict: A dictionary containing the parsed chat data.
                  Example structure:
                  {
                      "conversations": [
                          {"from": "Alice", "value": "Hi", "timestamp": "2021-01-01T12:00:00Z"},
                          {"from": "Bob", "value": "Hello", "timestamp": "2021-01-01T12:01:00Z"}
                      ]
                  }
        """
        return ShareGPTConversation(conversations=[{"from": msg['author']['name'], "value": msg['content'], "timestamp": msg['timestamp']} for msg in data['messages']])
