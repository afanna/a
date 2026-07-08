"""Rule engine layer: 27 rules across 6 dimensions.

Import all rule modules to trigger @register_rule decorators.
"""

# Import all rule modules to register them
from card_scorer.rules import (
    color,
    consistency,
    hierarchy,
    information,
    layout,
    structure,
)

__all__ = [
    "color",
    "consistency",
    "hierarchy",
    "information",
    "layout",
    "structure",
]
