"""
核心翻译模块，负责单个VTT文件的翻译处理
"""

import re
import boto3
import json
import time
import logging
from botocore.exceptions import ClientError

from vtt_translator.vtt_translator_config import load_config

class VttTranslator:
    def __init__(self, config=None, logger=None):
        """
        初始化翻译器
        
        Args:
            config: 配置字典，如果为None则加载默认配置
            logger: 日志记录器，如果为None则使用默认记录器
        """
        self.config = config if config else load_config()
        self.logger = logger if logger else logging.getLogger(__name__)
        
    def translate_vtt(self, input_file, output_file):
        """
        翻译VTT文件
        
        Args:
            input_file: 输入VTT文件路径
            output_file: 输出VTT文件路径
            
        Returns:
            bool: 翻译是否成功
        """
        try:
            self.logger.info(f"开始翻译文件: {input_file}")
            
            # 解析VTT文件
            subtitles = self._parse_vtt(input_file)
            self.logger.info(f"解析出 {len(subtitles)} 条字幕")
            
            # 将字幕分组为语义单元
            groups = self._group_subtitles(subtitles)
            self.logger.info(f"将{len(subtitles)}条字幕分组为{len(groups)}个语义单元")
            
            # 翻译每个组
            for i, group in enumerate(groups):
                original_text = ' '.join(group['texts'])
                self.logger.info(f"翻译组 {i+1}/{len(groups)}, 包含 {len(group['timestamps'])} 条字幕")
                
                # 根据组的完整性选择翻译方法
                if group['complete']:
                    # 完整句子，直接翻译
                    group['translated_text'] = self._translate_text(original_text)
                else:
                    # 不完整句子，提供上下文
                    group_index = groups.index(group)
                    prev_text = ' '.join(groups[group_index-1]['texts']) if group_index > 0 else ""
                    next_text = ' '.join(groups[group_index+1]['texts']) if group_index < len(groups) - 1 else ""
                    
                    context = f"前文：{prev_text}\n后文：{next_text}"
                    group['translated_text'] = self._translate_text(original_text, context)
            
            # 生成翻译后的VTT文件
            self._generate_output_vtt(groups, output_file)
            
            self.logger.info(f"翻译完成，输出文件: {output_file}")
            return True
            
        except Exception as e:
            self.logger.error(f"翻译过程中出错: {str(e)}")
            return False
    
    def _parse_vtt(self, vtt_file_path):
        """
        解析VTT文件，返回时间戳和文本内容的列表
        
        Args:
            vtt_file_path: VTT文件路径
            
        Returns:
            subtitles: 字幕列表
        """
        with open(vtt_file_path, 'r', encoding='utf-8') as file:
            content = file.read()
        
        # 跳过WEBVTT头部
        if content.startswith('WEBVTT'):
            content = content.split('WEBVTT', 1)[1].strip()
        
        # 使用正则表达式匹配时间戳和文本，处理可能存在的行号
        pattern = r'(?:\d+\n)?(\d{2}:\d{2}:\d{2}\.\d{3} --> \d{2}:\d{2}:\d{2}\.\d{3})\n([\s\S]*?)(?=\n\n(?:\d+\n)?\d{2}:\d{2}:\d{2}\.\d{3}|$)'
        matches = re.findall(pattern, content)
        
        subtitles = []
        for timestamp, text in matches:
            # 解析时间戳，计算持续时间
            start_time, end_time = timestamp.split(' --> ')
            duration = self._calculate_duration(start_time, end_time)
            
            subtitles.append({
                'timestamp': timestamp,
                'text': text.strip(),
                'start_time': start_time,
                'end_time': end_time,
                'duration': duration
            })
        
        return subtitles
    
    def _calculate_duration(self, start_time, end_time):
        """
        计算时间戳的持续时间（秒）
        
        Args:
            start_time: 开始时间
            end_time: 结束时间
            
        Returns:
            duration: 持续时间（秒）
        """
        def time_to_seconds(time_str):
            h, m, s = time_str.split(':')
            return int(h) * 3600 + int(m) * 60 + float(s)
        
        return time_to_seconds(end_time) - time_to_seconds(start_time)
    
    def _group_subtitles(self, subtitles):
        """
        将字幕分组为语义单元
        
        Args:
            subtitles: 字幕列表
            
        Returns:
            groups: 分组后的字幕
        """
        groups = []
        current_group = {
            'timestamps': [],
            'texts': [],
            'durations': [],
            'complete': False
        }
        
        for i, subtitle in enumerate(subtitles):
            text = subtitle['text'].strip()
            
            # 跳过空文本
            if not text:
                continue
            
            # 检查是否应该开始新组
            if not current_group['texts'] or text[0].isupper():
                # 保存当前组（如果不为空）
                if current_group['texts']:
                    # 检查当前组是否是完整句子
                    combined_text = ' '.join(current_group['texts'])
                    current_group['complete'] = combined_text[-1] in ['.', '?', '!']
                    groups.append(current_group)
                    
                    # 创建新组
                    current_group = {
                        'timestamps': [],
                        'texts': [],
                        'durations': [],
                        'complete': False
                    }
            
            # 添加当前字幕到组
            current_group['timestamps'].append(subtitle['timestamp'])
            current_group['texts'].append(text)
            current_group['durations'].append(subtitle['duration'])
            
            # 检查是否是最后一个字幕或当前字幕结束一个完整句子
            if i == len(subtitles) - 1 or text[-1] in ['.', '?', '!']:
                current_group['complete'] = text[-1] in ['.', '?', '!']
                groups.append(current_group)
                current_group = {
                    'timestamps': [],
                    'texts': [],
                    'durations': [],
                    'complete': False
                }
        
        # 添加最后一个组（如果有）
        if current_group['texts']:
            groups.append(current_group)
        
        return groups
    
    def _translate_text(self, text, context=None):
        """
        使用AWS Bedrock的Claude模型翻译文本
        
        Args:
            text: 要翻译的文本
            context: 上下文信息，如果有的话
            
        Returns:
            translated_text: 翻译后的文本
        """
        max_retries = self.config.get('max_retries', 5)
        retry_delay = self.config.get('retry_delay', 2)
        api_sleep_time = self.config.get('api_sleep_time', 5)
        
        bedrock_runtime = boto3.client(
            service_name='bedrock-runtime',
            region_name=self.config.get('aws_region', 'us-west-2')
        )
        
        # 构建提示
        if context:
            prompt = f"""请将以下英文文本翻译成中文。这是一个视频字幕的一部分。
上下文：{context}
要翻译的文本：{text}
请只返回翻译后的中文文本，不要包含任何解释或原文。翻译时请保持自然流畅的中文表达。"""
        else:
            prompt = f"""请将以下英文文本翻译成中文。这是一个视频字幕的一部分。
要翻译的文本：{text}
请只返回翻译后的中文文本，不要包含任何解释或原文。翻译时请保持自然流畅的中文表达。"""
        
        # 添加重试机制
        retries = 0
        while retries <= max_retries:
            try:
                # 调用Claude模型
                response = bedrock_runtime.invoke_model(
                    modelId=self.config.get('model_id', 'us.anthropic.claude-3-7-sonnet-20250219-v1:0'),
                    body=json.dumps({
                        "anthropic_version": "bedrock-2023-05-31",
                        "max_tokens": 1000,
                        "messages": [
                            {
                                "role": "user",
                                "content": prompt
                            }
                        ]
                    })
                )
                
                response_body = json.loads(response['body'].read().decode('utf-8'))
                translated_text = response_body['content'][0]['text']
                
                # 每次API调用后休眠，避免限流
                time.sleep(api_sleep_time)
                
                return translated_text
                
            except ClientError as e:
                if e.response['Error']['Code'] == 'ThrottlingException' and retries < max_retries:
                    # 如果是限流错误且未达到最大重试次数，则等待后重试
                    wait_time = retry_delay * (2 ** retries)  # 指数退避策略
                    self.logger.warning(f"API限流，等待{wait_time}秒后重试...")
                    time.sleep(wait_time)
                    retries += 1
                else:
                    # 其他错误或已达到最大重试次数，则抛出异常
                    raise
    
    def _distribute_translation(self, translated_text, timestamps_count, durations=None):
        """
        将翻译结果分配到多个时间戳
        
        Args:
            translated_text: 翻译后的文本
            timestamps_count: 时间戳数量
            durations: 持续时间列表
            
        Returns:
            parts: 分配后的文本列表
        """
        if timestamps_count <= 1:
            return [translated_text]
        
        # 如果提供了持续时间，使用加权分配
        if durations:
            total_duration = sum(durations)
            parts = []
            
            # 计算每个时间戳应分配的文本长度比例
            text_length = len(translated_text)
            start_pos = 0
            
            for i, duration in enumerate(durations):
                # 计算当前时间戳应分配的文本长度
                weight = duration / total_duration
                chars_count = int(text_length * weight)
                
                if i == timestamps_count - 1:  # 最后一个部分
                    end_pos = text_length
                else:
                    end_pos = min(start_pos + chars_count, text_length)
                    
                    # 尝试在标点符号处分割
                    if end_pos < text_length:
                        # 向后查找最近的标点符号
                        for j in range(min(end_pos + 10, text_length - 1), start_pos, -1):
                            if translated_text[j] in ['，', '。', '！', '？', '；']:
                                end_pos = j + 1
                                break
                
                part = translated_text[start_pos:end_pos].strip()
                parts.append(part if part else "...")
                start_pos = end_pos
            
            return parts
        
        # 尝试按句号分割
        if '。' in translated_text:
            chinese_sentences = translated_text.split('。')
            # 移除空字符串并添加句号
            chinese_sentences = [s + '。' if s.strip() else '...' for s in chinese_sentences]
            chinese_sentences = [s for s in chinese_sentences if s]
            
            # 如果句子数量与时间戳数量相同，直接返回
            if len(chinese_sentences) == timestamps_count:
                return chinese_sentences
            
            # 如果句子数量多于时间戳数量，合并一些句子
            if len(chinese_sentences) > timestamps_count:
                merged_sentences = []
                sentences_per_timestamp = len(chinese_sentences) // timestamps_count
                remainder = len(chinese_sentences) % timestamps_count
                
                start_idx = 0
                for i in range(timestamps_count):
                    # 分配额外的句子给前几个时间戳
                    extra = 1 if i < remainder else 0
                    end_idx = start_idx + sentences_per_timestamp + extra
                    
                    merged = ''.join(chinese_sentences[start_idx:end_idx])
                    merged_sentences.append(merged if merged else "...")
                    start_idx = end_idx
                
                return merged_sentences
        
        # 如果句子分割不理想，尝试按逗号分割
        if '，' in translated_text:
            parts = translated_text.split('，')
            # 移除空字符串并添加逗号
            parts = [s + '，' if s.strip() else '...' for s in parts]
            parts = [s for s in parts if s]
            
            # 如果分割后的部分数量与时间戳数量相同，直接返回
            if len(parts) == timestamps_count:
                return parts
            
            # 如果部分数量多于时间戳数量，合并一些部分
            if len(parts) > timestamps_count:
                merged_parts = []
                parts_per_timestamp = len(parts) // timestamps_count
                remainder = len(parts) % timestamps_count
                
                start_idx = 0
                for i in range(timestamps_count):
                    # 分配额外的部分给前几个时间戳
                    extra = 1 if i < remainder else 0
                    end_idx = start_idx + parts_per_timestamp + extra
                    
                    merged = ''.join(parts[start_idx:end_idx])
                    merged_parts.append(merged if merged else "...")
                    start_idx = end_idx
                
                return merged_parts
        
        # 如果以上方法都不理想，按字符平均分配
        chars_per_timestamp = max(1, len(translated_text) // timestamps_count)
        result = []
        
        for i in range(timestamps_count):
            start = i * chars_per_timestamp
            end = (i + 1) * chars_per_timestamp if i < timestamps_count - 1 else len(translated_text)
            
            # 尝试在标点符号处分割
            if i < timestamps_count - 1 and end < len(translated_text):
                # 向后查找最近的标点符号
                for j in range(min(end + 10, len(translated_text) - 1), end - 1, -1):
                    if translated_text[j] in ['，', '。', '！', '？', '；']:
                        end = j + 1
                        break
            
            part = translated_text[start:end].strip()
            result.append(part if part else "...")
        
        return result
    
    def _generate_output_vtt(self, groups, output_file):
        """
        生成翻译后的VTT文件
        
        Args:
            groups: 分组后的字幕
            output_file: 输出文件路径
        """
        with open(output_file, 'w', encoding='utf-8') as file:
            file.write('WEBVTT\n\n')
            
            # 将翻译结果映射回原始时间戳
            for group in groups:
                # 如果组只有一个时间戳，直接使用翻译结果
                if len(group['timestamps']) == 1:
                    file.write(f"{group['timestamps'][0]}\n")
                    file.write(f"{group['translated_text']}\n\n")
                else:
                    # 对于多个时间戳的组，需要分配翻译结果
                    parts = self._distribute_translation(
                        group['translated_text'], 
                        len(group['timestamps']),
                        group['durations']
                    )
                    
                    for i, timestamp in enumerate(group['timestamps']):
                        file.write(f"{timestamp}\n")
                        file.write(f"{parts[i]}\n\n")