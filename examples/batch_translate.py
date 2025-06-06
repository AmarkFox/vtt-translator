#!/usr/bin/env python3
"""
示例：批量翻译VTT文件
"""

from vtt_translator import VttTranslatorManager

# 创建管理器
manager = VttTranslatorManager()

# 批量处理前10个文件
manager.batch_process(0, 10)
