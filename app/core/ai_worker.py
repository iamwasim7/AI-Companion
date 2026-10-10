"""Qt worker for keeping AI requests off the application UI thread."""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QThread, Signal

from app.core.ai_service import AIService, AIServiceError
from app.core.logger import get_logger
from app.core.session import ChatMessage

logger = get_logger("ai.worker")


class AIRequestWorker(QThread):
    succeeded = Signal(str)
    failed = Signal(str)

    def __init__(self, service: AIService, messages: Sequence[ChatMessage], model: str) -> None:
        super().__init__()
        self._service = service
        self._messages = list(messages)
        self._model = model

    def run(self) -> None:
        try:
            reply = self._service.reply(self._messages, self._model)
        except AIServiceError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:
            logger.exception("Unexpected AI worker failure: %s", type(exc).__name__)
            self.failed.emit("The AI request could not be completed. Please try again.")
        else:
            self.succeeded.emit(reply)
