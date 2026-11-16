"""memvault: save the AI conversations you care about into a local, searchable SQLite vault."""

from .vault import Conversation, Hit, Message, Vault

__all__ = ["Conversation", "Hit", "Message", "Vault"]
__version__ = "0.1.0"
