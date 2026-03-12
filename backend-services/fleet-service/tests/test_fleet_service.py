"""
テスト仕様書: fleet-service — FleetService
==========================================

[日本語]
このファイルは FleetService クラスのテスト仕様書です。
ロボットの登録・一覧・テレメトリ更新・フリートサマリーの仕様を定義します。

仕様:
  register_robot()      : 新しいロボットを DB に登録する
  get_robot()           : robot_id でロボットを取得、存在しない場合は None
  list_robots()         : フィルタ付き一覧取得 (facility / status)
  update_telemetry()    : UPSERT — 未知のロボットは自動登録、既存ロボットは更新
  get_fleet_summary()   : フリート全体の統計 (total / online / cleaning / avg_battery)

[English]
This file is the test specification for the FleetService class.
Documents robot registration, listing, telemetry updates, and fleet summary.

Specification:
  register_robot()      : Register a new robot in the DB
  get_robot()           : Get robot by robot_id, return None if not found
  list_robots()         : Filtered listing (facility / status)
  update_telemetry()    : UPSERT — auto-register unknown robots, update existing ones
  get_fleet_summary()   : Fleet-wide statistics (total / online / cleaning / avg_battery)
"""
from datetime import datetime, timezone
import os
import sys
from unittest.mock import AsyncMock, MagicMock
import uuid

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.db.models import RobotORM
from src.dto.robot import RobotCreate, RobotStatus, RobotUpdate
from src.services.fleet_service import FleetService

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_db():
    """
    [日本語] SQLAlchemy AsyncSession のモック。

    [English] Mock for SQLAlchemy AsyncSession.
    """
    db = AsyncMock()
    db.add = MagicMock()

    async def fake_refresh(obj):
        # SQLAlchemy ORM columns always exist as attributes (even when None),
        # so use getattr(...) is None rather than not hasattr(...)
        if getattr(obj, "id", None) is None:
            obj.id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        if getattr(obj, "registered_at", None) is None:
            obj.registered_at = now
        if getattr(obj, "updated_at", None) is None:
            obj.updated_at = now
        if getattr(obj, "position_floor", None) is None:
            obj.position_floor = 1
        if getattr(obj, "facility", None) is None:
            obj.facility = "office_building_a"
        if getattr(obj, "status", None) is None:
            obj.status = "idle"

    db.refresh = fake_refresh
    return db


def make_robot_orm(
    robot_id: str,
    status: str = "idle",
    battery_level: float = 80.0,
    facility: str = "office_building_a",
    firmware_version: str = None,
) -> RobotORM:
    """テスト用 RobotORM オブジェクトを生成 / Generate a test RobotORM object."""
    robot = RobotORM()
    robot.id = uuid.uuid4()
    robot.robot_id = robot_id
    robot.name = robot_id
    robot.facility = facility
    robot.model = "CleanBot-X1"
    robot.firmware_version = firmware_version
    robot.status = status
    robot.battery_level = battery_level
    robot.position_x = 5.0
    robot.position_y = 5.0
    robot.position_floor = 1
    robot.last_seen = datetime.now(timezone.utc)
    robot.registered_at = datetime.now(timezone.utc)
    robot.updated_at = datetime.now(timezone.utc)
    return robot


# ---------------------------------------------------------------------------
# register_robot のテスト / Tests for FleetService.register_robot()
# ---------------------------------------------------------------------------

class TestRegisterRobot:
    """
    [日本語] register_robot() のテスト。
    新しいロボットを登録する。

    [English] Tests for register_robot().
    Registers a new robot.
    """

    async def test_adds_robot_to_db(self, mock_db):
        """
        [日本語] 登録リクエストを受け取ると db.add() が呼ばれる。

        [English] db.add() is called when a registration request is received.
        """
        service = FleetService(db=mock_db)
        data = RobotCreate(robot_id="robot_001", name="Bot Alpha", facility="warehouse_a")

        await service.register_robot(data)

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called()

    async def test_returns_robot_response_with_correct_robot_id(self, mock_db):
        """
        [日本語] 登録後に返される RobotResponse に正しい robot_id が含まれる。

        [English] Returned RobotResponse contains the correct robot_id after registration.
        """
        service = FleetService(db=mock_db)
        data = RobotCreate(robot_id="robot_042", name="Bot Omega", facility="office_a")

        result = await service.register_robot(data)

        assert result.robot_id == "robot_042"


# ---------------------------------------------------------------------------
# get_robot のテスト / Tests for FleetService.get_robot()
# ---------------------------------------------------------------------------

class TestGetRobot:
    """
    [日本語] get_robot() のテスト。

    [English] Tests for get_robot().
    """

    async def test_returns_robot_when_found(self, mock_db):
        """
        [日本語] ロボットが存在する場合は RobotResponse を返す。

        [English] Returns RobotResponse when the robot exists.
        """
        mock_robot = make_robot_orm("robot_001")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_robot
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = FleetService(db=mock_db)
        result = await service.get_robot("robot_001")

        assert result is not None
        assert result.robot_id == "robot_001"

    async def test_returns_none_when_not_found(self, mock_db):
        """
        [日本語] 存在しない robot_id を指定した場合は None を返す。

        [English] Returns None when the specified robot_id does not exist.
        """
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = FleetService(db=mock_db)
        result = await service.get_robot("nonexistent_robot")

        assert result is None


# ---------------------------------------------------------------------------
# get_fleet_summary のテスト / Tests for FleetService.get_fleet_summary()
# ---------------------------------------------------------------------------

class TestGetFleetSummary:
    """
    [日本語] get_fleet_summary() のテスト。
    フリート全体の統計情報を計算する。

    [English] Tests for get_fleet_summary().
    Calculates fleet-wide statistics.
    """

    async def test_counts_robots_by_status(self, mock_db):
        """
        [日本語] ステータス別のロボット数が正確にカウントされる。
        idle=2, cleaning=1, charging=1 → summary の値が一致すること。

        [English] Robots are counted accurately by status.
        idle=2, cleaning=1, charging=1 → summary values match.
        """
        robots = [
            make_robot_orm("r1", status="idle"),
            make_robot_orm("r2", status="idle"),
            make_robot_orm("r3", status="cleaning"),
            make_robot_orm("r4", status="charging"),
        ]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = robots
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = FleetService(db=mock_db)
        summary = await service.get_fleet_summary()

        assert summary.total == 4
        assert summary.idle == 2
        assert summary.cleaning == 1

    async def test_calculates_average_battery(self, mock_db):
        """
        [日本語] バッテリー平均が正しく計算される。
        battery=[60, 80, 100] → avg=80.0

        [English] Average battery is calculated correctly.
        battery=[60, 80, 100] → avg=80.0
        """
        robots = [
            make_robot_orm("r1", battery_level=60.0),
            make_robot_orm("r2", battery_level=80.0),
            make_robot_orm("r3", battery_level=100.0),
        ]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = robots
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = FleetService(db=mock_db)
        summary = await service.get_fleet_summary()

        assert summary.avg_battery == pytest.approx(80.0)

    async def test_avg_battery_is_none_when_no_robots(self, mock_db):
        """
        [日本語] ロボットが0台のとき avg_battery は None になる。
        ゼロ除算を避けるフォールバック動作。

        [English] avg_battery is None when no robots exist.
        Fallback to avoid division by zero.
        """
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = FleetService(db=mock_db)
        summary = await service.get_fleet_summary()

        assert summary.total == 0
        assert summary.avg_battery is None

    async def test_docked_robots_counted_as_charging(self, mock_db):
        """
        [日本語] docked 状態のロボットは charging としてカウントされる。
        summary.charging は CHARGING + DOCKED の合計。

        [English] Docked robots are counted as charging in the summary.
        summary.charging = CHARGING + DOCKED.
        """
        robots = [
            make_robot_orm("r1", status="docked"),
            make_robot_orm("r2", status="charging"),
        ]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = robots
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = FleetService(db=mock_db)
        summary = await service.get_fleet_summary()

        assert summary.charging == 2

    async def test_to_response_with_position(self, mock_db):
        """
        [日本語] position_x / position_y が設定されている場合、
        RobotResponse の position フィールドが正しく変換される。

        [English] When position_x/y are set, RobotResponse.position is correctly populated.
        """
        robot = make_robot_orm("r1")
        robot.position_x = 3.5
        robot.position_y = 7.2
        robot.position_floor = 2

        response = FleetService._to_response(robot)

        assert response.position is not None
        assert response.position.x == pytest.approx(3.5)
        assert response.position.y == pytest.approx(7.2)
        assert response.position.floor == 2

    async def test_to_response_without_position(self, mock_db):
        """
        [日本語] position_x / position_y が None の場合、
        RobotResponse の position フィールドも None になる。

        [English] When position_x/y are None, RobotResponse.position is None.
        """
        robot = make_robot_orm("r1")
        robot.position_x = None
        robot.position_y = None

        response = FleetService._to_response(robot)

        assert response.position is None
