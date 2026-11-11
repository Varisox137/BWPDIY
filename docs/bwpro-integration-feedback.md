# BWPro 集成改进建议

## 1. 气绝倒计时支持数值 0

当前 `render_entity` 的 `state.defeated_countdown` 只接受正整数或 `"infinity"`。BWPro 在“气绝倒计时 1→0、随后复活”的视觉事件中需要短暂显示数字 0；直接传入会触发参数校验失败并退回文字色块。

建议允许非负整数 `0`，与现有普通 `countdown=0` 的语义保持一致，并补充原生渲染回归。BWPro 在上游支持前会在该过渡帧保留上一张有效小卡，等待复活事件再更新。

## 2. 修正集成文档中的战力/乏力资源路径

`docs/integration.md` 仍写对局小卡战力/乏力读取 `icons/`，但当前 `render/entity.py` 已使用 `stats/combat_power.png` 与 `stats/weak.png` 大图标；文本内嵌 `#zl`/`#fl` 才继续使用 `icons/` 小图。

建议更新集成文档，避免调用方预置错误尺寸的资源。
