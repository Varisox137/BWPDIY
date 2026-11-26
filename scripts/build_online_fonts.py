# /// script
# requires-python = ">=3.12"
# dependencies = ["fonttools==4.69.1", "pillow>=11.0"]
# ///
from io import BytesIO
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from fontTools import subset
from fontTools.ttLib import TTFont
from PIL import ImageFont

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "assets" / "fonts"
TARGET = ROOT / "prototype" / "pyodide" / "runtime-fonts.zip"
COVERAGE_TARGET = ROOT / "prototype" / "pyodide" / "runtime-fonts.json"
SAMPLES = ("山风贯通，[[觉醒]]≥1。#ll", "阴阳师百闻牌：力量/生命 +3/-1", "《「测试」》——……∞")
# 这些字参与 FreeType CJK 蓝色区域计算，缺少时会改变其他字的小字号栅格化。
CJK_BLUE = (
    "他们你來們到和地对對就席我时時會来為能舰說说这這齊|军同已愿既星是景民照现現理用置要軍那配里開雷露面顾"
    "个为人他以们你來個們到和大对對就我时時有来為要說说|主些因它想意理生當看着置者自著裡过还进進過道還里面"
    "些们你來們到和她将將就年得情最样樣理能說说这這通|即吗吧听呢品响嗎师師收断斷明眼間间际陈限除陳随際隨"
    "事前學将將情想或政斯新样樣民沒没然特现現球第經谁起|例別别制动動吗嗎增指明朝期构物确种調调費费那都間间"
)


def gb2312_characters():
    characters = set(chr(value) for value in range(0x20, 0x7F))
    for first in range(0xA1, 0xF8):
        for second in range(0xA1, 0xFF):
            try:
                characters.add(bytes((first, second)).decode("gb2312"))
            except UnicodeDecodeError:
                pass
    return characters


def build_font(path):
    font = TTFont(path)
    original_cmap = font.getBestCmap()
    characters = gb2312_characters() | set(CJK_BLUE) | {
        chr(codepoint) for codepoint in original_cmap
        if codepoint < 0x2E80 or 0x3000 <= codepoint <= 0x303F
        or 0xFF00 <= codepoint <= 0xFFEF
    }
    options = subset.Options()
    options.name_IDs = ["*"]
    options.name_legacy = True
    options.name_languages = ["*"]
    options.notdef_glyph = True
    options.notdef_outline = True
    options.recommended_glyphs = True
    subsetter = subset.Subsetter(options=options)
    subsetter.populate(text="".join(sorted(characters)))
    subsetter.subset(font)
    output = BytesIO()
    font.recalcTimestamp = False
    font.save(output)
    data = output.getvalue()

    reduced_cmap = TTFont(BytesIO(data)).getBestCmap()
    missing = (set(characters) & {chr(codepoint) for codepoint in original_cmap}) - {
        chr(codepoint) for codepoint in reduced_cmap
    }
    if missing:
        raise RuntimeError(f"{path.name} 子集丢失字符：{sorted(missing)[:12]}")

    comparisons = 0
    for size in (12, 24, 48, 97):
        original = ImageFont.truetype(str(path), size)
        reduced = ImageFont.truetype(BytesIO(data), size)
        for text in (*sorted(characters), *SAMPLES):
            original_mask, original_offset = original.getmask2(text)
            reduced_mask, reduced_offset = reduced.getmask2(text)
            if (original.getbbox(text) != reduced.getbbox(text)
                    or original.getlength(text) != reduced.getlength(text)
                    or original_offset != reduced_offset
                    or bytes(original_mask) != bytes(reduced_mask)):
                raise RuntimeError(f"{path.name} 子集渲染不一致：{size}px {text!r}")
            comparisons += 1
    return data, "".join(chr(codepoint) for codepoint in sorted(reduced_cmap)), comparisons


def main():
    built = {}
    coverages = {}
    for path in sorted(SOURCE.glob("*.ttf")):
        data, coverage, comparisons = build_font(path)
        built[path.name] = data
        coverages[path.name] = coverage
        print(f"{path.name}：{path.stat().st_size} → {len(data)} 字节；"
              f"{len(coverage)} 字符；{comparisons} 次渲染一致")
    if set(built) != {"方正北魏楷书.ttf", "田氏颜体大字库2.0.ttf"}:
        raise RuntimeError("在线字体包必须恰好包含两套正式字体")

    temporary = TARGET.with_suffix(".zip.tmp")
    coverage_temporary = COVERAGE_TARGET.with_suffix(".json.tmp")
    try:
        with ZipFile(temporary, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
            for name, data in sorted(built.items()):
                info = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = ZIP_DEFLATED
                info.external_attr = 0o600 << 16
                archive.writestr(info, data, compress_type=ZIP_DEFLATED, compresslevel=9)
        coverage_temporary.write_text(json.dumps(coverages, ensure_ascii=False, sort_keys=True),
                                      encoding="utf-8")
        temporary.replace(TARGET)
        coverage_temporary.replace(COVERAGE_TARGET)
    finally:
        if temporary.exists():
            temporary.unlink()
        if coverage_temporary.exists():
            coverage_temporary.unlink()
    print(f"已生成 {TARGET.relative_to(ROOT)}：{TARGET.stat().st_size} 字节")


if __name__ == "__main__":
    main()
