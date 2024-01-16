from datetime import datetime
from typing import Dict, Any

from selfie.data_processing.parsers.chat.base import JsonBasedChatParser, TextBasedChatParser
from selfie.data_processing.types import ShareGPTConversation


# Generated with Google Takeout
class GoogleMessagesParser(JsonBasedChatParser):
    def extract_conversations(self, data: Dict[str, Any]) -> ShareGPTConversation:
        """
        Extract conversations from parsed Google Takeout JSON data.

        Args:
            data (Dict[str, Any]): The parsed JSON data should have a structure like:
                        {
                            "uuid_1": {"SenderId": "Alice", "Message": "Hello", "Timestamp": "2021-01-01 12:00:00", "Attachment count": "0"},
                            "uuid_2": {"SenderId": "Bob", "Message": "Hi", "Timestamp": "2021-01-01 12:01:00", "Attachment count": "0"}
                        }

        Returns:
            Dict: A dictionary containing the parsed chat data.
                  Example structure:
                  {
                      "conversations": [
                          {"from": "Alice", "value": "Hello", "timestamp": "2021-01-01T12:00:00Z"},
                          {"from": "Bob", "value": "Hi", "timestamp": "2021-01-01T12:01:00Z"}
                      ]
                  }
        """
        parsed_data = []
        for message_id, message_data in data.items():
            if message_id == "footer":
                continue  # Skip the footer if it exists
            from_user = message_data["SenderId"]
            value = message_data["Message"]
            timestamp_str = message_data["Timestamp"]
            timestamp_iso = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=self.timezone).isoformat()

            parsed_data.append({
                "from": from_user,
                "value": value,
                "timestamp": timestamp_iso
            })

        return ShareGPTConversation(conversations=parsed_data)


# TODO: Why are these duplicated?
class GoogleTakeoutParser(TextBasedChatParser):
    def extract_conversations(self, data: Dict[str, Any]) -> ShareGPTConversation:
        """
        Extract conversations from parsed Google Takeout JSON data.

        Args:
            data (Dict[str, Any]): The parsed JSON data should have a structure like:
                        {
                            "uuid_1": {"SenderId": "Alice", "Message": "Hello", "Timestamp": "2021-01-01 12:00:00", "Attachment count": "0"},
                            "uuid_2": {"SenderId": "Bob", "Message": "Hi", "Timestamp": "2021-01-01 12:01:00", "Attachment count": "0"}
                        }

        Returns:
            Dict: A dictionary containing the parsed chat data.
                  Example structure:
                  {
                      "conversations": [
                          {"from": "Alice", "value": "Hello", "timestamp": "2021-01-01T12:00:00Z"},
                          {"from": "Bob", "value": "Hi", "timestamp": "2021-01-01T12:01:00Z"}
                      ]
                  }
        """
        parsed_data = []
        for message_id, message_data in data.items():
            if message_id == "footer":
                continue  # Skip the footer if it exists
            from_user = message_data["SenderId"]
            value = message_data["Message"]
            timestamp_str = message_data["Timestamp"]
            timestamp_iso = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=self.timezone).isoformat()

            parsed_data.append({
                "from": from_user,
                "value": value,
                "timestamp": timestamp_iso
            })

        return ShareGPTConversation(conversations=parsed_data)
