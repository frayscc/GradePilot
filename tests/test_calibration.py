from pathlib import Path

import pytest

from app.core.calibration_store import load_calibration, save_calibration
from app.data.calibration import CalibrationError, CalibrationProfile, Point, Region


def test_region_from_reversed_corners() -> None:
    assert Region.from_corners(Point(30, 40), Point(10, 15)) == Region(10, 15, 20, 25)


def test_zero_sized_region_is_rejected() -> None:
    with pytest.raises(CalibrationError):
        Region.from_corners(Point(10, 10), Point(10, 20))


def test_calibration_round_trip(tmp_path: Path) -> None:
    profile = CalibrationProfile(
        Region(58, 166, 1316, 500), Point(1510, 424), Point(1554, 475), Point(410, 107)
    )
    path = tmp_path / "task.calibration.json"
    save_calibration(profile, path)
    assert load_calibration(path) == profile


def test_calibration_rejects_unknown_fields() -> None:
    with pytest.raises(CalibrationError):
        CalibrationProfile.from_dict(
            {
                "answer_region": {"x": 0, "y": 0, "width": 10, "height": 10},
                "score_input": {"x": 1, "y": 1},
                "submit_button": {"x": 2, "y": 2},
                "unsafe": True,
            }
        )
