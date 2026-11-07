"""All Reelspan tools with one client and shared settings."""

from __future__ import annotations

from typing import List, Optional

from langchain_core.tools import BaseTool, BaseToolkit
from pydantic import ConfigDict, Field
from reelspan import Reelspan

from .tools import READ_TOOLS, WRITE_TOOLS


class ReelspanToolkit(BaseToolkit):
    """Reelspan tools for an agent.

    >>> toolkit = ReelspanToolkit(profile="acme", read_only=False)
    >>> tools = toolkit.get_tools()
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    client: Reelspan = Field(default_factory=Reelspan)
    """Defaults to a client reading REELSPAN_API_KEY."""
    profile: Optional[str] = None
    """Pin every tool to one profile."""
    platforms: Optional[List[str]] = None
    """Only these networks can be posted to."""
    read_only: bool = False
    """Only tools that read: no posting, retrying or cancelling."""
    wait: bool = True
    """Wait for each network's result after posting."""

    def get_tools(self) -> List[BaseTool]:
        classes = READ_TOOLS if self.read_only else READ_TOOLS + WRITE_TOOLS
        return [cls(client=self.client, profile=self.profile, allowed_platforms=self.platforms, wait=self.wait) for cls in classes]
