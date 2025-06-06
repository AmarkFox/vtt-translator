"""
工具函数模块，提供日志记录和文件操作等通用功能
"""

import os
import logging
import shutil
from datetime import datetime

def setup_logger(log_dir, file_name=None):
    """
    设置日志记录器
    
    Args:
        log_dir: 日志目录
        file_name: 日志文件名，如果为None则使用时间戳生成
        
    Returns:
        logger: 配置好的日志记录器
    """
    # 确保日志目录存在
    os.makedirs(log_dir, exist_ok=True)
    
    # 如果没有提供文件名，使用时间戳生成
    if file_name is None:
        file_name = f"translation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    
    log_path = os.path.join(log_dir, file_name)
    
    # 创建日志记录器
    logger = logging.getLogger(file_name)
    logger.setLevel(logging.INFO)
    
    # 防止重复添加处理器
    if not logger.handlers:
        # 文件处理器
        file_handler = logging.FileHandler(log_path, encoding='utf-8')
        file_handler.setLevel(logging.INFO)
        
        # 控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        
        # 设置日志格式
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', 
                                      datefmt='%Y-%m-%d %H:%M:%S')
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        # 添加处理器
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
    
    return logger

def get_file_logger(log_dir, input_file):
    """
    为特定文件创建日志记录器
    
    Args:
        log_dir: 日志目录
        input_file: 输入文件路径
        
    Returns:
        logger: 配置好的日志记录器
    """
    # 从文件路径中提取文件名
    file_name = os.path.basename(input_file)
    base_name = os.path.splitext(file_name)[0]
    
    # 创建日志文件名
    log_file = f"{base_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    
    return setup_logger(log_dir, log_file)

def move_file(source_path, target_dir):
    """
    移动文件到目标目录
    
    Args:
        source_path: 源文件路径
        target_dir: 目标目录
        
    Returns:
        target_path: 移动后的文件路径
    """
    # 确保目标目录存在
    os.makedirs(target_dir, exist_ok=True)
    
    # 获取文件名
    file_name = os.path.basename(source_path)
    
    # 构建目标路径
    target_path = os.path.join(target_dir, file_name)
    
    # 移动文件
    shutil.move(source_path, target_path)
    
    return target_path

def ensure_dir(directory):
    """
    确保目录存在，如果不存在则创建
    
    Args:
        directory: 目录路径
    """
    if not os.path.exists(directory):
        os.makedirs(directory)