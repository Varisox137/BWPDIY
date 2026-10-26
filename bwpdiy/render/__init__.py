"""渲染核心库：纯 PIL，对外主入口 render_card 与 render_entity。"""

__all__ = ["entity_eligible", "render_card", "render_entity", "validate_entity_state"]


def __getattr__(name: str):
    if name == "render_card":
        from bwpdiy.render.pipeline import render_card

        return render_card
    if name in ("entity_eligible", "render_entity", "validate_entity_state"):
        from bwpdiy.render import entity

        return getattr(entity, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
