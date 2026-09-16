"""渲染核心库：纯 PIL，对外主入口 render_card。"""

__all__ = ["render_card"]


def __getattr__(name: str):
    if name == "render_card":
        from bwpdiy.render.pipeline import render_card

        return render_card
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
