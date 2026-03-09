"""
Multi-Robot Task Allocation - Nearest Robot First algorithm.

Score formula (lower = better):
  distance_score = distance_to_zone / max_distance    # normalized [0, 1]
  battery_score  = (100 - battery_level) / 100        # normalized [0, 1]
  score = w_dist * distance_score + w_bat * battery_score
          (default: w_dist=0.6, w_bat=0.4)

Only robots with battery > 20% and status = idle are candidates.
"""
import math
import logging
from typing import Optional

from src.models.mission import RobotCandidate

logger = logging.getLogger(__name__)

MIN_BATTERY_PCT = 20.0
W_DISTANCE = 0.6
W_BATTERY = 0.4


def score_robot(
    robot: RobotCandidate,
    zone_x: float,
    zone_y: float,
    max_distance: float,
) -> float:
    distance = math.sqrt(
        (robot.position_x - zone_x) ** 2 + (robot.position_y - zone_y) ** 2
    )
    distance_score = min(distance / max_distance, 1.0) if max_distance > 0 else 0.0
    battery_score = (100.0 - robot.battery_level) / 100.0
    return W_DISTANCE * distance_score + W_BATTERY * battery_score


def allocate(
    candidates: list[RobotCandidate],
    zone_x: float,
    zone_y: float,
) -> Optional[str]:
    """Return robot_id of the best candidate, or None if no candidates available."""
    eligible = [
        r for r in candidates
        if r.status == "idle" and r.battery_level >= MIN_BATTERY_PCT
    ]

    if not eligible:
        logger.warning("No eligible robots for task allocation")
        return None

    # Compute max distance for normalization
    distances = [
        math.sqrt((r.position_x - zone_x) ** 2 + (r.position_y - zone_y) ** 2)
        for r in eligible
    ]
    max_dist = max(distances) if distances else 1.0

    scored = sorted(
        eligible,
        key=lambda r: score_robot(r, zone_x, zone_y, max_dist),
    )
    best = scored[0]
    logger.info(
        f"Allocated robot={best.robot_id} "
        f"(battery={best.battery_level:.0f}%, "
        f"score={score_robot(best, zone_x, zone_y, max_dist):.3f})"
    )
    return best.robot_id
