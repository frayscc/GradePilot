from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.data.calibration import Region


@dataclass(frozen=True)
class VisualSignature:
    samples: tuple[int, ...]

    def difference_ratio(self, other: "VisualSignature", *, channel_threshold: int = 16) -> float:
        if len(self.samples) != len(other.samples) or not self.samples:
            return 1.0
        changed = sum(abs(left - right) >= channel_threshold for left, right in zip(self.samples, other.samples))
        return changed / len(self.samples)


class ScreenCapture:
    def grab(self, region: Region, output: Path) -> Path:
        import mss
        import mss.tools

        output.parent.mkdir(parents=True, exist_ok=True)
        with mss.mss() as screen:
            shot = screen.grab({"left": region.x, "top": region.y, "width": region.width, "height": region.height})
            mss.tools.to_png(shot.rgb, shot.size, output=str(output))
        return output

    def signature(self, region: Region, *, grid: int = 16) -> VisualSignature:
        import mss

        with mss.mss() as screen:
            shot = screen.grab({"left": region.x, "top": region.y, "width": region.width, "height": region.height})
        rgb = shot.rgb
        width, height = shot.size
        samples: list[int] = []
        for row in range(grid):
            y = min(height - 1, (row * height) // grid)
            for column in range(grid):
                x = min(width - 1, (column * width) // grid)
                offset = (y * width + x) * 3
                samples.extend(channel // 8 * 8 for channel in rgb[offset:offset + 3])
        return VisualSignature(tuple(samples))
