"""
テスト仕様書: telemetry-service — TelemetryService
===================================================

[日本語]
このファイルは TelemetryService クラスのテスト仕様書です。
TimescaleDB に蓄積されたテレメトリ履歴の取得ロジックを定義します。

仕様:
  get_telemetry():
    - robot_id で時系列テレメトリを取得
    - from_ts / to_ts が None の場合はデフォルト範囲 (epoch〜現在) を使用
    - limit 件数でページング

  get_latest():
    - 指定ロボットの最新テレメトリを1件取得
    - 存在しない場合は None を返す

[English]
This file is the test specification for the TelemetryService class.
Documents logic for querying telemetry history stored in TimescaleDB.

Specification:
  get_telemetry():
    - Retrieve time-series telemetry by robot_id
    - Use default range (epoch to now) when from_ts/to_ts is None
    - Paginate with limit

  get_latest():
    - Get most recent telemetry entry for a robot
    - Return None if no records exist
"""
from datetime import datetime, timezone
import os
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.services.telemetry_service import TelemetryService

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
    return AsyncMock()


def make_telemetry_row(**kwargs) -> dict:
    """テスト用テレメトリ行データを生成 / Generate test telemetry row data."""
    defaults = {
        "time": datetime.now(timezone.utc),
        "robot_id": "robot_001",
        "battery_level": 75.0,
        "position_x": 5.0,
        "position_y": 10.0,
        "position_floor": 1,
        "nav_status": "cleaning",
        "speed": 0.5,
        "mission_progress": 50.0,
        "motor_load_left": None,
        "motor_load_right": None,
        "sensor_health": None,
        "mission_id": None,
    }
    defaults.update(kwargs)
    return defaults


# ---------------------------------------------------------------------------
# get_telemetry のテスト / Tests for TelemetryService.get_telemetry()
# ---------------------------------------------------------------------------

class TestGetTelemetry:
    """
    [日本語] get_telemetry() のテスト。
    時系列テレメトリの範囲クエリ。

    [English] Tests for get_telemetry().
    Range query for time-series telemetry.
    """

    async def test_returns_list_of_telemetry_points(self, mock_db):
        """
        [日本語] テレメトリレコードを TelemetryPoint のリストとして返す。
        DB に3行あれば3件のリストが返る。

        [English] Returns telemetry records as a list of TelemetryPoint.
        3 DB rows → 3-item list returned.
        """
        rows = [
            make_telemetry_row(robot_id="robot_001", battery_level=80.0),
            make_telemetry_row(robot_id="robot_001", battery_level=75.0),
            make_telemetry_row(robot_id="robot_001", battery_level=70.0),
        ]
        mock_result = MagicMock()
        # SQLAlchemy の mappings().all() は dict-like RowMapping を返す。
        # テストでは dict を使う (dict(row) が正しく動作するため)。
        # Use plain dicts: service calls dict(row) which works correctly on dicts.
        mock_result.mappings.return_value.all.return_value = rows
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = TelemetryService(db=mock_db)
        result = await service.get_telemetry("robot_001", None, None, limit=10)

        assert len(result) == 3

    async def test_returns_empty_list_when_no_data(self, mock_db):
        """
        [日本語] テレメトリが存在しない場合は空リストを返す。

        [English] Returns an empty list when no telemetry exists.
        """
        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = TelemetryService(db=mock_db)
        result = await service.get_telemetry("nonexistent", None, None, limit=10)

        assert result == []

    async def test_uses_epoch_as_default_from_ts(self, mock_db):
        """
        [日本語] from_ts が None の場合は epoch (1970-01-01) がデフォルト値として使われる。
        全期間のデータを取得するための仕様。

        [English] Uses epoch (1970-01-01) as default from_ts when None.
        Specification to retrieve data from all time.
        """
        captured_params = {}
        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = []

        async def capture_execute(query, params=None):
            if params:
                captured_params.update(params)
            return mock_result

        mock_db.execute = capture_execute

        service = TelemetryService(db=mock_db)
        await service.get_telemetry("robot_001", None, None, limit=10)

        assert captured_params.get("from_ts") == datetime.utcfromtimestamp(0)


# ---------------------------------------------------------------------------
# get_latest のテスト / Tests for TelemetryService.get_latest()
# ---------------------------------------------------------------------------

class TestGetLatest:
    """
    [日本語] get_latest() のテスト。
    ロボットの最新テレメトリを1件取得する。

    [English] Tests for get_latest().
    Retrieves the most recent telemetry entry for a robot.
    """

    async def test_returns_latest_telemetry_point(self, mock_db):
        """
        [日本語] 最新のテレメトリが TelemetryPoint として返される。

        [English] Returns the latest telemetry as a TelemetryPoint.
        """
        row = make_telemetry_row(robot_id="robot_001", battery_level=55.0)
        mock_result = MagicMock()
        # dict(row) が正しく動作するよう plain dict を使う / Use plain dict for dict(row) to work.
        mock_result.mappings.return_value.first.return_value = row
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = TelemetryService(db=mock_db)
        result = await service.get_latest("robot_001")

        assert result is not None

    async def test_returns_none_when_no_telemetry(self, mock_db):
        """
        [日本語] テレメトリが存在しない場合は None を返す。
        新規ロボット登録直後などのエッジケース。

        [English] Returns None when no telemetry exists.
        Edge case: immediately after new robot registration.
        """
        mock_result = MagicMock()
        mock_result.mappings.return_value.first.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = TelemetryService(db=mock_db)
        result = await service.get_latest("new_robot")

        assert result is None
