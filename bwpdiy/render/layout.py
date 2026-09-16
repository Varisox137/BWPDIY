"""卡面布局常量（画布 512×512）。区域为 (x0, y0, x1, y1)。"""

CANVAS_SIZE = (512, 512)

# 等级标（三层叠加，同一中心点）
LEVEL_POS = (120, 65)
LEVEL_BASE_SIZE = (72, 72)
LEVEL_STAR_SIZE = (60, 60)
LEVEL_NUM_SIZE = (40, 40)

# 稀有度标：右上角，与等级标对称
RARITY_POS = (392, 65)
RARITY_SIZE = (48, 48)

# 派系标（式神）：顶部中央
FACTION_POS = (256, 40)
FACTION_SIZE = (40, 40)

# 数值标：底部左右角（式神力量/生命；战斗加成；幻境耐久居中）
STAT_LEFT_POS = (145, 478)
STAT_RIGHT_POS = (367, 478)
STAT_CENTER_POS = (256, 478)
STAT_FONT_SIZE = 30

# 文本区
NAME_BOX = (130, 340, 382, 382)
DESC_BOX = (130, 388, 382, 495)
NAME_FONT_RANGE = (36, 16)   # (最大, 最小)
DESC_FONT_RANGE = (22, 12)
TEXT_FILL = (60, 45, 30, 255)        # 深棕（羊皮纸底色上）
