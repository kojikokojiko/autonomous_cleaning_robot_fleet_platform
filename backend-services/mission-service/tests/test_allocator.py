"""
テスト仕様書: ロボット割り当てアルゴリズム (allocator.py)
==========================================================

[日本語]
このファイルは mission-service のロボット割り当てアルゴリズムのテスト仕様書です。
アルゴリズムの仕様を「実行可能なドキュメント」として定義します。

スコア計算式:
  distance_score = distance / max_distance      # 0〜1 に正規化
  battery_score  = (100 - battery_level) / 100  # 0〜1 に正規化
  score          = 0.6 × distance_score + 0.4 × battery_score
  ※ スコアが小さいほど優先度が高い

選定条件:
  - status == "idle"
  - battery_level >= 20%

[English]
This file is the test specification for the robot allocation algorithm in mission-service.
Algorithm behavior is documented as executable tests.

Score formula:
  distance_score = distance / max_distance      # normalized [0, 1]
  battery_score  = (100 - battery_level) / 100  # normalized [0, 1]
  score          = 0.6 × distance_score + 0.4 × battery_score
  * Lower score = higher priority

Eligibility:
  - status == "idle"
  - battery_level >= 20%
"""
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.dto.mission import RobotCandidate
from src.services.allocator import MIN_BATTERY_PCT, W_BATTERY, W_DISTANCE, allocate, score_robot

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_robot(
    robot_id: str,
    battery: float = 80.0,
    x: float = 0.0,
    y: float = 0.0,
    status: str = "idle",
) -> RobotCandidate:
    """テスト用ロボット候補を生成するヘルパー関数 / Helper to create a RobotCandidate for tests."""
    return RobotCandidate(
        robot_id=robot_id,
        battery_level=battery,
        position_x=x,
        position_y=y,
        status=status,
    )


# ---------------------------------------------------------------------------
# score_robot のテスト / Tests for score_robot()
# ---------------------------------------------------------------------------

class TestScoreRobot:
    """
    [日本語] score_robot() 関数のテスト
    個々のロボットに対するスコア計算が仕様通りであることを検証する。

    [English] Tests for score_robot()
    Verifies that per-robot score calculation follows the specification.
    """

    def test_perfect_score_robot_at_zone_full_battery(self):
        """
        [日本語] ゾーン直上・バッテリー100% のロボットは最小スコア (0.0) になる。
        距離=0 → distance_score=0、battery=100% → battery_score=0 → score=0.0

        [English] A robot at the zone with full battery scores 0.0 (minimum).
        distance=0 → distance_score=0, battery=100% → battery_score=0 → score=0.0
        """
        robot = make_robot("r1", battery=100.0, x=5.0, y=5.0)
        score = score_robot(robot, zone_x=5.0, zone_y=5.0, max_distance=10.0)
        assert score == pytest.approx(0.0)

    def test_worst_score_farthest_empty_battery(self):
        """
        [日本語] ゾーンから最遠・バッテリー0% のロボットは最大スコア (1.0) になる。
        distance_score=1.0, battery_score=1.0 → score = 0.6 + 0.4 = 1.0

        [English] A robot farthest from zone with 0% battery scores 1.0 (maximum).
        distance_score=1.0, battery_score=1.0 → score = 0.6 + 0.4 = 1.0
        """
        robot = make_robot("r1", battery=0.0, x=10.0, y=0.0)
        score = score_robot(robot, zone_x=0.0, zone_y=0.0, max_distance=10.0)
        assert score == pytest.approx(1.0)

    def test_weight_distribution_is_60_40(self):
        """
        [日本語] スコアの重みが距離60%・バッテリー40% であることを検証。
        ロボットを max_distance の半分の距離に置き、バッテリー0% にした場合:
          distance_score = 0.5, battery_score = 1.0
          score = 0.6 × 0.5 + 0.4 × 1.0 = 0.70

        [English] Verifies the 60% distance / 40% battery weight distribution.
        Robot placed at half of max_distance with 0% battery:
          distance_score = 0.5, battery_score = 1.0
          score = 0.6 × 0.5 + 0.4 × 1.0 = 0.70
        """
        robot = make_robot("r1", battery=0.0, x=5.0, y=0.0)
        score = score_robot(robot, zone_x=0.0, zone_y=0.0, max_distance=10.0)
        assert score == pytest.approx(0.70)

    def test_distance_score_capped_at_1(self):
        """
        [日本語] distance が max_distance を超えても distance_score は 1.0 を超えない。
        min(distance / max_distance, 1.0) によってキャップされることを確認。

        [English] distance_score is capped at 1.0 even if distance > max_distance.
        Verified by min(distance / max_distance, 1.0).
        """
        robot = make_robot("r1", battery=100.0, x=100.0, y=0.0)
        score = score_robot(robot, zone_x=0.0, zone_y=0.0, max_distance=10.0)
        # distance=100, max_distance=10 → distance_score = min(10, 1) = 1.0
        # battery_score = 0.0
        assert score == pytest.approx(W_DISTANCE * 1.0 + W_BATTERY * 0.0)

    def test_zero_max_distance_does_not_raise(self):
        """
        [日本語] max_distance=0 の場合 (ロボットが1台) は ZeroDivisionError を起こさない。
        distance_score は 0.0 として扱われる。

        [English] max_distance=0 (single robot) should not raise ZeroDivisionError.
        distance_score defaults to 0.0.
        """
        robot = make_robot("r1", battery=50.0, x=3.0, y=4.0)
        score = score_robot(robot, zone_x=0.0, zone_y=0.0, max_distance=0.0)
        # distance_score = 0.0, battery_score = 0.5 → score = 0.4 × 0.5 = 0.2
        assert score == pytest.approx(W_BATTERY * 0.5)

    def test_euclidean_distance_calculation(self):
        """
        [日本語] ユークリッド距離が正しく計算されることを確認。
        (3, 4) から (0, 0) への距離は sqrt(9+16) = 5.0

        [English] Verifies correct Euclidean distance calculation.
        Distance from (3, 4) to (0, 0) = sqrt(9+16) = 5.0
        """
        robot = make_robot("r1", battery=100.0, x=3.0, y=4.0)
        distance = math.sqrt((3.0 - 0.0) ** 2 + (4.0 - 0.0) ** 2)
        assert distance == pytest.approx(5.0)
        # max_distance=10 → distance_score = 5/10 = 0.5, battery_score = 0
        score = score_robot(robot, zone_x=0.0, zone_y=0.0, max_distance=10.0)
        assert score == pytest.approx(W_DISTANCE * 0.5)


# ---------------------------------------------------------------------------
# allocate のテスト / Tests for allocate()
# ---------------------------------------------------------------------------

class TestAllocate:
    """
    [日本語] allocate() 関数のテスト
    複数ロボットの中から最適なロボットを選択するロジックの検証。

    [English] Tests for allocate()
    Validates the logic for selecting the best robot from multiple candidates.
    """

    def test_returns_nearest_idle_robot(self):
        """
        [日本語] ゾーンに最も近いアイドルロボットを選択する。
        バッテリーが同等の場合、距離スコアが優先されて近いロボットが選ばれる。

        [English] Selects the idle robot nearest to the zone.
        When battery levels are equal, distance score dominates.
        """
        robots = [
            make_robot("near",  battery=80.0, x=1.0, y=0.0),
            make_robot("far",   battery=80.0, x=9.0, y=0.0),
        ]
        result = allocate(robots, zone_x=0.0, zone_y=0.0)
        assert result == "near"

    def test_returns_higher_battery_when_equidistant(self):
        """
        [日本語] 距離が同じ場合、バッテリー残量が多いロボットが選ばれる。
        battery_score = (100 - battery) / 100 なので、バッテリーが多いほどスコアが低い。

        [English] When equidistant, the robot with higher battery is selected.
        battery_score = (100 - battery) / 100: higher battery → lower score → higher priority.
        """
        robots = [
            make_robot("low_bat",  battery=30.0, x=5.0, y=0.0),
            make_robot("high_bat", battery=90.0, x=5.0, y=0.0),
        ]
        result = allocate(robots, zone_x=5.0, zone_y=0.0)
        assert result == "high_bat"

    def test_returns_none_when_no_candidates(self):
        """
        [日本語] 候補がいない場合は None を返す。
        アイドル状態のロボットが0台の場合のフォールバック動作。

        [English] Returns None when no candidates are available.
        Fallback behavior when zero idle robots exist.
        """
        result = allocate([], zone_x=0.0, zone_y=0.0)
        assert result is None

    def test_excludes_non_idle_robots(self):
        """
        [日本語] idle 以外のステータス (cleaning, charging, docked) のロボットは対象外。
        idle のロボットだけが選択候補になる。

        [English] Non-idle robots (cleaning, charging, docked) are excluded from selection.
        Only idle robots are eligible candidates.
        """
        robots = [
            make_robot("cleaning", battery=90.0, x=1.0, y=0.0, status="cleaning"),
            make_robot("charging", battery=90.0, x=1.0, y=0.0, status="charging"),
            make_robot("docked",   battery=90.0, x=1.0, y=0.0, status="docked"),
            make_robot("idle",     battery=50.0, x=5.0, y=0.0, status="idle"),
        ]
        result = allocate(robots, zone_x=0.0, zone_y=0.0)
        assert result == "idle"

    def test_excludes_low_battery_robots(self):
        """
        [日本語] バッテリー残量が MIN_BATTERY_PCT (20%) 未満のロボットは対象外。
        19% のロボットは選択されず、21% のロボットが選ばれる。

        [English] Robots with battery < MIN_BATTERY_PCT (20%) are excluded.
        A robot at 19% is not selected; a robot at 21% is chosen instead.
        """
        robots = [
            make_robot("too_low",   battery=MIN_BATTERY_PCT - 1, x=1.0, y=0.0),
            make_robot("just_ok",   battery=MIN_BATTERY_PCT + 1, x=9.0, y=0.0),
        ]
        result = allocate(robots, zone_x=0.0, zone_y=0.0)
        assert result == "just_ok"

    def test_exactly_minimum_battery_is_eligible(self):
        """
        [日本語] バッテリー残量がちょうど MIN_BATTERY_PCT (20%) のロボットは対象になる。
        境界値: >= 20% が条件なので 20% はギリギリ有効。

        [English] A robot with exactly MIN_BATTERY_PCT (20%) battery is eligible.
        Boundary: condition is >= 20%, so exactly 20% is valid.
        """
        robots = [make_robot("boundary", battery=MIN_BATTERY_PCT, x=0.0, y=0.0)]
        result = allocate(robots, zone_x=0.0, zone_y=0.0)
        assert result == "boundary"

    def test_returns_none_all_robots_low_battery(self):
        """
        [日本語] 全ロボットがバッテリー不足の場合、None を返す。
        充電が必要なフリートに対してミッションを割り当てないことを保証。

        [English] Returns None when all robots have insufficient battery.
        Ensures no mission is assigned to a fleet that needs charging.
        """
        robots = [
            make_robot("r1", battery=15.0, x=1.0, y=0.0),
            make_robot("r2", battery=10.0, x=2.0, y=0.0),
        ]
        result = allocate(robots, zone_x=0.0, zone_y=0.0)
        assert result is None

    def test_single_robot_is_selected(self):
        """
        [日本語] 候補が1台だけの場合、そのロボットが選択される。
        max_distance=0 になるが ZeroDivisionError が起きないことも確認。

        [English] When only one candidate exists, that robot is selected.
        Also verifies no ZeroDivisionError when max_distance=0.
        """
        robots = [make_robot("only_one", battery=80.0, x=3.0, y=4.0)]
        result = allocate(robots, zone_x=0.0, zone_y=0.0)
        assert result == "only_one"

    def test_tradeoff_near_low_battery_vs_far_high_battery(self):
        """
        [日本語] 近いがバッテリーが低いロボット vs 遠いがバッテリーが高いロボット。
        スコアを手動計算して、アルゴリズムが正しい判断をすることを確認。

        candidates: near (x=1, bat=25%), far (x=9, bat=95%), zone=(0,0), max_dist=9
          near: dist_score=1/9≈0.111, bat_score=0.75 → score = 0.6*0.111 + 0.4*0.75 = 0.367
          far:  dist_score=1.0,       bat_score=0.05 → score = 0.6*1.0   + 0.4*0.05 = 0.620
        → near wins (lower score)

        [English] Near robot with low battery vs far robot with high battery.
        Manual score calculation confirms the algorithm makes the correct choice.
        """
        robots = [
            make_robot("near_low",  battery=25.0, x=1.0, y=0.0),
            make_robot("far_high",  battery=95.0, x=9.0, y=0.0),
        ]
        result = allocate(robots, zone_x=0.0, zone_y=0.0)
        # near_low score = 0.6*(1/9) + 0.4*0.75 ≈ 0.367
        # far_high score = 0.6*1.0   + 0.4*0.05 = 0.620
        assert result == "near_low"

    def test_score_constants_have_correct_values(self):
        """
        [日本語] アルゴリズムの定数が仕様通りであることを確認。
        MIN_BATTERY_PCT=20, W_DISTANCE=0.6, W_BATTERY=0.4, 合計=1.0

        [English] Verifies algorithm constants match the specification.
        MIN_BATTERY_PCT=20, W_DISTANCE=0.6, W_BATTERY=0.4, sum=1.0
        """
        assert MIN_BATTERY_PCT == 20.0
        assert W_DISTANCE == pytest.approx(0.6)
        assert W_BATTERY == pytest.approx(0.4)
        assert W_DISTANCE + W_BATTERY == pytest.approx(1.0)
