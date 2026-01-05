from telegram import Bot

from src.utils.logging import get_logger, log_error, log_event


class TelegramMessenger:
    def __init__(self, token: str | None, chat_id: str | None, logger=None):
        self.enabled = bool(token and chat_id)
        self.chat_id = chat_id
        self.bot = Bot(token) if self.enabled else None
        self.logger = logger or get_logger("app")
        if not self.enabled:
            log_event(self.logger, "messaging_disabled", reason="missing_token_or_chat_id")

    def send(self, payload: dict):
        if not self.enabled:
            return
        message = self._format(payload)
        try:
            self.bot.send_message(chat_id=self.chat_id, text=message)
        except Exception as exc:  # noqa: BLE001
            log_error(self.logger, "telegram_send", exc)

    def _format(self, payload: dict) -> str:
        lines = [
            f"[{payload['template']}] {payload['setup']} | score {payload['score']}",
            payload["contract"],
            f"premium ${payload['premium_total']:,} | contracts {payload['contracts_total']}",
            f"aggression {payload['aggression']} | vol/oi {payload['vol_oi']:.2f}",
            f"why: {', '.join(payload['why'])}",
        ]
        if payload.get("tags"):
            lines.append(f"tags: {', '.join(payload['tags'])}")
        return "\n".join(lines)
