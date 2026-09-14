import argparse
from config_parser import load_config
from image_processor import process_card_image

def main():
    # 解析命令行参数
    parser=argparse.ArgumentParser(description='阴阳师百闻牌DIY卡牌生成器')
    parser.add_argument('-c', '--config', help='配置文件路径',
                        required=False, default='./config.json')
    args=parser.parse_args()
    
    # 加载配置并处理图像
    config=load_config(args.config)
    process_card_image(config)

if __name__ == '__main__':
    main()