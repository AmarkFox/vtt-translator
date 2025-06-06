"""
VTT字幕翻译系统
"""

from vtt_translator.vtt_translator_core import VttTranslator
from vtt_translator.vtt_translator_manager import VttTranslatorManager
from vtt_translator.vtt_translator_config import load_config, save_config
from vtt_translator.vtt_translator_utils import setup_logger

__version__ = '1.0.0'