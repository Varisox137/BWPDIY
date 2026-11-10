"""从 assets/psd_export/ 再生成其管理的 PSD 基础资源（英文命名）。

用法（Windows Git Bash，cwd=仓库根）：
    PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe scripts/import_psd_assets.py
    PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe scripts/import_psd_assets.py --sample-colors

frames/rarity/factions 先清空重建；levels/stats/icons 只覆盖本脚本管理的文件，
保留后续加入的八色勾玉、状态组件、逐条目派系图标和其他新资源。numbers/badges
不由本脚本管理；旧 signs、协战专用稀有度和无编号/墨染派系小标不再生成。
legacy 归档（assets/legacy/）由本脚本生成的内容只有 rarity/N.png 与 factions/ 复制回。

牌框预处理统一：裁 alpha bbox → 等比缩放至高 512 → 居中贴到 512×512 透明画布。
稀有度整带取左半部分 alpha bbox 裁出左端单枚花标。
levels/stats/icons 原尺寸直拷。
"""

import argparse
import shutil
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
PSD = ASSETS / "psd_export"
LEGACY = ASSETS / "legacy"

FRAME_SIZE = 512

# 框品映射：PSD 中文名 → 英文框品
VARIANTS = {"基础": "norm", "琉璃光境": "blue", "百炼": "red", "墨染": "black"}
# 类型映射：PSD 卡框目录 → 英文类型
FRAME_TYPES = {
    "卡框-基础_形态": "form",
    "卡框-战斗": "combat",
    "卡框-法术": "spell",
    "卡框-幻境": "field",
}

LEVELS = {
    "勾玉/勾玉-底框.png": "base.png",
    "勾玉/一勾玉.png": "level_1_yellow.png",
    "勾玉/二勾玉.png": "level_2_yellow.png",
    "勾玉/三勾玉.png": "level_3_yellow.png",
}

STATS = {
    # 力量/生命全类型共用同一资源（PSD 中各类型重复，取基础_形态版）
    "基础_形态-数值/基础_形态-攻击.png": "power.png",
    "基础_形态-数值/基础_形态-生命.png": "health.png",
    "战斗-数值/战斗-护甲.png": "shield.png",
    "战斗-数值/战斗-破甲.png": "combat_fragile_1.png",
    "战斗-数值/战斗-破甲1.png": "combat_fragile_2.png",
    "幻境-数值/幻境.png": "intensity.png",
}

SYMBOL_DIR = "☆【符号】攻击生命等（新增战力、乏力标识）"
ICONS = {
    f"{SYMBOL_DIR}/攻击.png": "power.png",
    f"{SYMBOL_DIR}/生命.png": "health.png",
    f"{SYMBOL_DIR}/护甲.png": "shield.png",
    f"{SYMBOL_DIR}/破甲.png": "fragile.png",
    f"{SYMBOL_DIR}/能量.png": "energy.png",
    f"{SYMBOL_DIR}/幻境.png": "intensity.png",
    "☆新增战力、乏力标识（如需使用请自行调整尺寸）/战力.png": "combat_power.png",
    "☆新增战力、乏力标识（如需使用请自行调整尺寸）/乏力.png": "weak.png",
}

# 稀有度整带 → 目标文件名（裁左端单枚花标）
RARITY_BANDS = {
    "罕贵度/R.png": "R.png",
    "罕贵度/SR.png": "SR.png",
    "罕贵度/SSR.png": "SSR.png",
    "罕贵度/R 琉璃光境.png": "R_blue.png",
    "罕贵度/SR 琉璃光境.png": "SR_blue.png",
    "罕贵度/SSR 琉璃光境.png": "SSR_blue.png",
    "罕贵度/R 百炼.png": "R_red.png",
    "罕贵度/SR 百炼.png": "SR_red.png",
    "罕贵度/SSR 百炼.png": "SSR_red.png",
}

# 取色：框品目录 → (英文框品, 取样文件 → 用途)
TEXT_DIRS = {"文字-基础": "norm", "文字-琉璃光境": "blue", "文字-墨染": "black", "文字-百炼": "red"}
TEXT_SAMPLES = {"卡名.png": "卡名", "描述.png": "描述", "式神-战斗.png": "脚注"}


def _reset_dir(path: Path) -> Path:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)
    return path


def _fit_frame(src: Path, dst: Path) -> tuple[int, int]:
    """裁 alpha bbox → 等比缩放至高 512 → 居中贴 512×512 透明画布。返回内容尺寸。"""
    im = Image.open(src).convert("RGBA")
    bbox = im.getbbox()
    if bbox:
        im = im.crop(bbox)
    ratio = FRAME_SIZE / im.height
    w = round(im.width * ratio)
    im = im.resize((w, FRAME_SIZE), Image.LANCZOS)
    canvas = Image.new("RGBA", (FRAME_SIZE, FRAME_SIZE), (0, 0, 0, 0))
    canvas.paste(im, ((FRAME_SIZE - w) // 2, 0), im)
    canvas.save(dst)
    return w, FRAME_SIZE


def _crop_left_emblem(src: Path, dst: Path) -> tuple[int, int]:
    """罕贵度整带（两端花标、中间透明）裁左端单枚花标：左半部分 alpha bbox。"""
    im = Image.open(src).convert("RGBA")
    left = im.crop((0, 0, im.width // 2, im.height))
    bbox = left.getbbox()
    if not bbox:
        raise ValueError(f"整带左半无内容: {src}")
    emblem = left.crop(bbox)
    emblem.save(dst)
    return emblem.size


def import_frames() -> list[str]:
    out = _reset_dir(ASSETS / "frames")
    logs = []
    for cn_type, en_type in FRAME_TYPES.items():
        for cn_var, en_var in VARIANTS.items():
            src = PSD / cn_type / f"{cn_var}.png"
            size = _fit_frame(src, out / f"{en_type}_{en_var}.png")
            logs.append(f"frames/{en_type}_{en_var}.png 内容 {size[0]}x{size[1]}")
    size = _fit_frame(PSD / "协战" / "协战牌框.png", out / "reinforce_norm.png")
    logs.append(f"frames/reinforce_norm.png 内容 {size[0]}x{size[1]}")
    return logs


def extract_evolve_circle(source: Path, target: Path) -> None:
    """提取旧觉醒图中央圆盘，保留原画布以维持与新星叠加的固有比例。"""
    with Image.open(source) as opened:
        src = opened.convert("RGBA")
    scale = 4
    mask = Image.new("L", (src.width * scale, src.height * scale), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse(tuple(v * scale for v in (21, 21, 78, 78)), fill=255)
    mask = mask.resize(src.size, Image.LANCZOS)
    src.putalpha(ImageChops.multiply(src.getchannel("A"), mask))
    src.save(target)


def import_levels(out: Path | None = None) -> list[str]:
    if out is None:
        out = ASSETS / "levels"
    out.mkdir(parents=True, exist_ok=True)
    for src_rel, name in LEVELS.items():
        shutil.copy2(PSD / src_rel, out / name)
    extract_evolve_circle(PSD / "勾玉/底框-觉醒.png", out / "evolve_circle.png")
    return [f"levels/{name}" for name in LEVELS.values()] + ["levels/evolve_circle.png"]


def import_rarity() -> list[str]:
    out = _reset_dir(ASSETS / "rarity")
    logs = []
    for src_rel, name in RARITY_BANDS.items():
        w, h = _crop_left_emblem(PSD / src_rel, out / name)
        logs.append(f"rarity/{name} {w}x{h}")
    shutil.copy2(LEGACY / "rarity" / "N.png", out / "N.png")
    logs.append("rarity/N.png（legacy 复制回）")
    return logs


def import_factions() -> list[str]:
    out = _reset_dir(ASSETS / "factions")
    logs = []
    for color in ("red", "green", "blue", "purple"):
        for style in (1, 2, 3):
            name = f"{color}_{style}.png"
            shutil.copy2(LEGACY / "factions" / name, out / name)
            logs.append(f"factions/{name}")
    return logs


def import_stats() -> list[str]:
    out = ASSETS / "stats"
    out.mkdir(parents=True, exist_ok=True)
    for src_rel, name in STATS.items():
        shutil.copy2(PSD / src_rel, out / name)
    return [f"stats/{name}" for name in STATS.values()]


def import_icons() -> list[str]:
    out = ASSETS / "icons"
    out.mkdir(parents=True, exist_ok=True)
    logs = [f"icons/{name}" for name in ICONS.values()]
    for src_rel, name in ICONS.items():
        shutil.copy2(PSD / src_rel, out / name)
    return logs


def _dominant_rgb(path: Path, alpha_min: int = 200, colors: int = 6) -> tuple[int, int, int]:
    """取不透明像素量化后的主色。"""
    im = Image.open(path).convert("RGBA")
    raw = im.tobytes()
    opaque = [(raw[i], raw[i + 1], raw[i + 2]) for i in range(0, len(raw), 4) if raw[i + 3] >= alpha_min]
    if not opaque:
        raise ValueError(f"无不透明像素: {path}")
    flat = Image.new("RGB", (len(opaque), 1))
    flat.putdata(opaque)
    q = flat.quantize(colors=colors)
    counts = sorted(q.getcolors(), reverse=True)  # [(count, palette_idx)]
    palette = q.getpalette()
    idx = counts[0][1]
    return palette[idx * 3], palette[idx * 3 + 1], palette[idx * 3 + 2]


def sample_colors() -> list[str]:
    lines = []
    for cn_dir, en_var in TEXT_DIRS.items():
        for filename, usage in TEXT_SAMPLES.items():
            r, g, b = _dominant_rgb(PSD / cn_dir / filename)
            lines.append(f"{en_var} {usage}: rgb({r}, {g}, {b})")
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample-colors", action="store_true", help="仅取色输出建议 RGB，不生成资产")
    args = parser.parse_args()

    if args.sample_colors:
        for line in sample_colors():
            print(line)
        return 0

    logs = []
    logs += import_frames()
    logs += import_levels()
    logs += import_rarity()
    logs += import_factions()
    logs += import_stats()
    logs += import_icons()
    for line in logs:
        print(line)
    print(f"共生成 {len(logs)} 个文件")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
