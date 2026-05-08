"""VTT subtitle translation package."""

from .config import Config
from .translator import VttTranslator
from .manager import VttTranslatorManager

__version__ = "2.0.0"
__all__ = ["Config", "VttTranslator", "VttTranslatorManager"]
