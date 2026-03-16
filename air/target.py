from dataclasses import dataclass
from typing import Literal


@dataclass
class ReviewTarget:
    kind: Literal["commit", "mr"]
    ref: str  # commit SHA 或 MR IID
