"""KineType – waterfall / rapid-flash kinetic typography without After Effects.

Public API::

    from kinetype import RenderConfig, Renderer, load_script, assign_timeline

    cfg = RenderConfig()                       # or load_config("meme-punch")
    chunks = load_script("script.txt", cfg)
    duration = assign_timeline(chunks, cfg, target=12.0)
    renderer = Renderer(cfg)
    renderer.write(renderer.prepare(chunks, duration), "out.mp4")
"""

from .config import DEFAULT_PRESET, PRESETS, RenderConfig, load_config, parse_color
from .renderer import Program, Renderer
from .script import Chunk, Key, assign_timeline, chunks_from_text, load_script

__version__ = "0.1.0"
__all__ = [
    "Chunk",
    "DEFAULT_PRESET",
    "Key",
    "PRESETS",
    "Program",
    "RenderConfig",
    "Renderer",
    "assign_timeline",
    "chunks_from_text",
    "load_config",
    "load_script",
    "parse_color",
    "__version__",
]
