"""Base integration interfaces."""

from typing import Any


class BaseIntegrationClient:
    """Base class for all external integration clients."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass
