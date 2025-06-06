#!/usr/bin/env python3
"""
示例：翻译单个VTT文件
"""

from vtt_translator import VttTranslator

# 创建翻译器
translator = VttTranslator()

# 翻译文件
input_file = "../vtt/01. Introduction: Systems vs. Applications.vtt"
output_file = "../vtt/zh/01. Introduction: Systems vs. Applications-zh.vtt"

translator.translate_vtt(input_file, output_file)
