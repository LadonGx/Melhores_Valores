class StoreBlockedError(Exception):
    """Raised by a search scraper when the target store served an anti-bot/auth wall."""

    def __init__(self, category: str):
        self.category = category
        super().__init__(f"Store blocked: {category}")
