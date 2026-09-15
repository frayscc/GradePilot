from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Region:
    left: int
    top: int
    width: int
    height: int

    def __post_init__(self) -> None:
        if min(self.left, self.top) < 0 or self.width <= 0 or self.height <= 0:
            raise ValueError("capture region coordinates must be non-negative and dimensions positive")


def capture_region(region: Region, output: Path) -> Path:
    import mss
    import mss.tools

    output.parent.mkdir(parents=True, exist_ok=True)
    with mss.mss() as screen:
        shot = screen.grab({"left": region.left, "top": region.top, "width": region.width, "height": region.height})
        mss.tools.to_png(shot.rgb, shot.size, output=str(output))
    return output
