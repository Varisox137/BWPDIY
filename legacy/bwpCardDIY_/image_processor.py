from PIL import Image, ImageFilter, ImageOps
import os

def process_card_image(params: dict):
    # 加载卡图和牌框
    image=Image.open(params['image_path']).convert('RGBA')
    frame=Image.open(f'./basics/frames/{params["type"]}_f_{params["frame_type"]}.png').convert('RGBA')

    # 缩放卡图
    image_resized=image.resize(frame.size, resample=Image.LANCZOS)

    # 加载蒙版
    imask=Image.open(f'./basics/masks/{params["type"]}_im.png').convert('L')

    # 平滑蒙版
    imask_smoothed=imask.filter(ImageFilter.GaussianBlur(radius=1))
    fmask_smoothed=ImageOps.invert(imask_smoothed) # 反转卡图蒙版即得到牌框蒙版
    
    # 应用蒙版
    image_masked=image_resized.copy()
    image_masked.putalpha(imask_smoothed)
    frame_masked=frame.copy()
    frame_masked.putalpha(fmask_smoothed)

    # 叠加合成
    image_comp=Image.alpha_composite(image_masked, frame_masked)
    
    # 创建目录并保存
    os.makedirs('./output', exist_ok=True)
    image_comp.save(f'./output/{params["name"]}.png')

if __name__ == '__main__':
    # 示例参数
    process_card_image(params={
        'card_name': 'test',
        'card_type': 'xz_s',
        'frame_type': 'cg',
        'card_image': './test_image.png',
    })
