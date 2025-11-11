"""Slack API integration module.

This module contains all Slack-related functionality:
- Data extraction (users, channels, messages, files)
- Message and file sending
- Real-time event streaming via Socket Mode
- Reaction management
"""

from .client import SlackClient
from .extractor.coordinator import ExtractionCoordinator
from .sender.message_sender import MessageSender
from .sender.file_sender import FileSender
from .sender.reaction_manager import ReactionManager
from .realtime.socket_client import SocketModeClient
from .realtime.event_handlers import EventHandlers

__all__ = [
    'SlackClient',
    'ExtractionCoordinator',
    'MessageSender',
    'FileSender',
    'ReactionManager',
    'SocketModeClient',
    'EventHandlers',
]
