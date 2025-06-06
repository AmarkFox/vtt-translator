"""
主程序入口，提供命令行接口
"""

import os
import sys
import argparse

from vtt_translator.vtt_translator_core import VttTranslator
from vtt_translator.vtt_translator_manager import VttTranslatorManager
from vtt_translator.vtt_translator_utils import setup_logger
from vtt_translator.vtt_translator_config import load_config, save_config, DEFAULT_CONFIG

def parse_args():
    """
    解析命令行参数
    
    Returns:
        args: 解析后的参数
    """
    parser = argparse.ArgumentParser(description='VTT字幕翻译工具')
    
    # 子命令
    subparsers = parser.add_subparsers(dest='command', help='子命令')
    
    # 单文件翻译命令
    translate_parser = subparsers.add_parser('translate', help='翻译单个VTT文件')
    translate_parser.add_argument('input', help='输入VTT文件路径')
    translate_parser.add_argument('output', help='输出VTT文件路径')
    translate_parser.add_argument('--config', help='配置文件路径')
    
    # 批量翻译命令
    batch_parser = subparsers.add_parser('batch', help='批量翻译VTT文件')
    batch_parser.add_argument('--start', type=int, default=0, help='起始索引')
    batch_parser.add_argument('--end', type=int, help='结束索引')
    batch_parser.add_argument('--input-dir', help='输入目录')
    batch_parser.add_argument('--output-dir', help='输出目录')
    batch_parser.add_argument('--done-dir', help='处理完成目录')
    batch_parser.add_argument('--config', help='配置文件路径')
    
    # 生成配置文件命令
    config_parser = subparsers.add_parser('config', help='生成配置文件')
    config_parser.add_argument('output', help='配置文件输出路径')
    
    return parser.parse_args()

def main():
    """
    主函数
    """
    args = parse_args()
    
    if args.command == 'translate':
        # 单文件翻译
        config = load_config(args.config)
        logger = setup_logger(config['log_dir'])
        
        translator = VttTranslator(config, logger)
        success = translator.translate_vtt(args.input, args.output)
        
        if success:
            print(f"翻译成功，输出文件: {args.output}")
            return 0
        else:
            print("翻译失败")
            return 1
    
    elif args.command == 'batch':
        # 批量翻译
        config = load_config(args.config)
        
        # 更新配置
        if args.input_dir:
            config['input_dir'] = args.input_dir
        if args.output_dir:
            config['output_dir'] = args.output_dir
        if args.done_dir:
            config['done_dir'] = args.done_dir
        
        # 创建管理器
        manager = VttTranslatorManager(config)
        
        # 批量处理
        success_count, total_count = manager.batch_process(args.start, args.end)
        
        if success_count == total_count:
            print(f"批量翻译完成，成功: {success_count}/{total_count}")
            return 0
        else:
            print(f"批量翻译部分完成，成功: {success_count}/{total_count}")
            return 1
    
    elif args.command == 'config':
        # 生成配置文件
        success = save_config(DEFAULT_CONFIG, args.output)
        
        if success:
            print(f"配置文件已生成: {args.output}")
            return 0
        else:
            print("配置文件生成失败")
            return 1
    
    else:
        # 没有指定命令，显示帮助
        print("请指定子命令，使用 -h 查看帮助")
        return 1

if __name__ == '__main__':
    sys.exit(main())