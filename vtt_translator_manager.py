"""
调度管理模块，负责批量文件的处理流程
"""

import os
import time
import random
import logging
from datetime import datetime

from vtt_translator.vtt_translator_core import VttTranslator
from vtt_translator.vtt_translator_utils import setup_logger, get_file_logger, move_file, ensure_dir
from vtt_translator.vtt_translator_config import load_config

class VttTranslatorManager:
    def __init__(self, config_path=None):
        """
        初始化翻译管理器
        
        Args:
            config_path: 配置文件路径，如果为None则加载默认配置
        """
        # 加载配置
        self.config = load_config(config_path)
        
        # 确保目录存在
        ensure_dir(self.config['input_dir'])
        ensure_dir(self.config['output_dir'])
        ensure_dir(self.config['done_dir'])
        ensure_dir(self.config['log_dir'])
        
        # 设置日志记录器
        self.logger = setup_logger(self.config['log_dir'], f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
        
    def find_vtt_files(self, input_dir=None):
        """
        查找VTT文件
        
        Args:
            input_dir: 输入目录，如果为None则使用配置中的输入目录
            
        Returns:
            vtt_files: VTT文件列表
        """
        if input_dir is None:
            input_dir = self.config['input_dir']
        
        vtt_files = []
        for file in os.listdir(input_dir):
            if file.endswith(".vtt") and not file.endswith("-zh.vtt") and not file.endswith("_zh.vtt"):
                # 排除已经处理过的文件
                if os.path.exists(os.path.join(self.config['done_dir'], file)):
                    continue
                
                # 排除已经有对应中文翻译的文件
                base_name = os.path.splitext(file)[0]
                if os.path.exists(os.path.join(self.config['output_dir'], f"{base_name}-zh.vtt")):
                    continue
                
                vtt_files.append(os.path.join(input_dir, file))
        
        return sorted(vtt_files)
    
    def process_file(self, input_file):
        """
        处理单个VTT文件
        
        Args:
            input_file: 输入文件路径
            
        Returns:
            bool: 处理是否成功
        """
        # 获取文件名
        file_name = os.path.basename(input_file)
        base_name = os.path.splitext(file_name)[0]
        
        # 构建输出文件路径
        output_file = os.path.join(self.config['output_dir'], f"{base_name}-zh.vtt")
        
        # 获取文件专用日志记录器
        file_logger = get_file_logger(self.config['log_dir'], input_file)
        
        # 记录开始处理
        self.logger.info(f"开始处理文件: {file_name}")
        start_time = time.time()
        
        try:
            # 创建翻译器
            translator = VttTranslator(self.config, file_logger)
            
            # 翻译文件
            success = translator.translate_vtt(input_file, output_file)
            
            # 记录处理结果
            end_time = time.time()
            duration = end_time - start_time
            
            if success:
                self.logger.info(f"文件 {file_name} 处理成功，耗时: {duration:.2f} 秒")
                
                # 移动原文件到done目录
                move_file(input_file, self.config['done_dir'])
                
                return True
            else:
                self.logger.error(f"文件 {file_name} 处理失败，耗时: {duration:.2f} 秒")
                return False
                
        except Exception as e:
            self.logger.error(f"处理文件 {file_name} 时出错: {str(e)}")
            return False
    
    def batch_process(self, start_index=0, end_index=None):
        """
        批量处理VTT文件
        
        Args:
            start_index: 起始索引
            end_index: 结束索引，如果为None则处理所有文件
            
        Returns:
            success_count: 成功处理的文件数量
            total_count: 总文件数量
        """
        # 查找VTT文件
        vtt_files = self.find_vtt_files()
        
        if not vtt_files:
            self.logger.info("没有找到需要处理的VTT文件")
            return 0, 0
        
        # 确定处理范围
        if end_index is None or end_index > len(vtt_files):
            end_index = len(vtt_files)
        
        selected_files = vtt_files[start_index:end_index]
        
        if not selected_files:
            self.logger.info(f"指定范围 [{start_index}:{end_index}] 内没有找到需要处理的VTT文件")
            return 0, 0
        
        # 记录开始批处理
        self.logger.info(f"开始批量处理 {len(selected_files)} 个文件")
        for i, file in enumerate(selected_files):
            self.logger.info(f"{i+1}. {os.path.basename(file)}")
        
        # 处理每个文件
        success_count = 0
        for i, file in enumerate(selected_files):
            # 处理文件
            if self.process_file(file):
                success_count += 1
            
            # 如果不是最后一个文件，随机休眠
            if i < len(selected_files) - 1:
                sleep_time = random.randint(
                    self.config.get('min_sleep_time', 180),
                    self.config.get('max_sleep_time', 300)
                )
                self.logger.info(f"休息 {sleep_time} 秒后继续处理下一个文件...")
                time.sleep(sleep_time)
        
        # 记录批处理结束
        self.logger.info(f"批量处理完成，成功: {success_count}/{len(selected_files)}")
        
        return success_count, len(selected_files)