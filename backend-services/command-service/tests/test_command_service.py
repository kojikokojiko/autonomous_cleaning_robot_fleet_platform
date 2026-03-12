"""
テスト仕様書: command-service — CommandService
===============================================

[日本語]
このファイルは CommandService クラスのテスト仕様書です。
ダッシュボードからのコマンドをロボットに MQTT QoS 1 で確実に届けるロジックを定義します。

仕様:
  1. 許可されたコマンド (start_mission / pause_mission / return_to_dock / emergency_stop) のみ受付
  2. 不正なコマンドタイプは ValueError を raise
  3. emergency_stop の場合は payload に "critical: true" を自動付加
  4. コマンドは PostgreSQL commands テーブルに保存される
  5. MQTT Publish に成功した場合は status="sent"、失敗した場合は status="failed"
  6. MQTT エラーが起きても例外は伝播しない (DB には failed として記録される)

[English]
This file is the test specification for the CommandService class.
Documents the logic for reliably delivering commands to robots via MQTT QoS 1.

Specification:
  1. Only allowed commands (start_mission / pause_mission / return_to_dock / emergency_stop)
  2. Invalid command types raise ValueError
  3. emergency_stop automatically adds "critical: true" to payload
  4. Commands are persisted to the PostgreSQL commands table
  5. status="sent" on MQTT success, status="failed" on MQTT failure
  6. MQTT errors do not propagate (recorded as "failed" in DB)
"""
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch
import uuid

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.dto.command import CommandCreate
from src.services.command_service import ALLOWED_COMMANDS, CommandService

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_db():
    """
    [日本語] SQLAlchemy AsyncSession のモック。
    DB 操作 (add, commit, refresh) をシミュレートする。

    [English] Mock for SQLAlchemy AsyncSession.
    Simulates DB operations (add, commit, refresh).
    """
    db = AsyncMock()
    db.add = MagicMock()

    # refresh は ORM オブジェクトの id と status を設定するシミュレート
    async def fake_refresh(obj):
        # SQLAlchemy ORM columns always exist as attributes (even when None),
        # so use getattr(...) is None rather than not hasattr(...)
        if getattr(obj, "id", None) is None:
            obj.id = uuid.uuid4()
        if getattr(obj, "issued_at", None) is None:
            from datetime import datetime, timezone
            obj.issued_at = datetime.now(timezone.utc)
        if getattr(obj, "updated_at", None) is None:
            from datetime import datetime, timezone
            obj.updated_at = datetime.now(timezone.utc)
        if getattr(obj, "retry_count", None) is None:
            obj.retry_count = 0

    db.refresh = fake_refresh
    return db


def make_command(
    command_type: str, robot_id: str = "robot_001", payload: dict = None
) -> CommandCreate:
    """テスト用コマンドリクエストを生成 / Generate a test command request."""
    return CommandCreate(
        robot_id=robot_id,
        command_type=command_type,
        payload=payload or {},
        issued_by="operator",
    )


# ---------------------------------------------------------------------------
# ALLOWED_COMMANDS のテスト / Tests for ALLOWED_COMMANDS constant
# ---------------------------------------------------------------------------

class TestAllowedCommands:
    """
    [日本語] 許可されたコマンドタイプの定数テスト。

    [English] Tests for the ALLOWED_COMMANDS constant.
    """

    def test_contains_all_expected_commands(self):
        """
        [日本語] 仕様に定義された4種類のコマンドが含まれる。

        [English] Contains all 4 command types defined in the specification.
        """
        assert "start_mission" in ALLOWED_COMMANDS
        assert "pause_mission" in ALLOWED_COMMANDS
        assert "return_to_dock" in ALLOWED_COMMANDS
        assert "emergency_stop" in ALLOWED_COMMANDS

    def test_does_not_contain_unknown_commands(self):
        """
        [日本語] 定義外のコマンドは含まれない。

        [English] Unknown commands are not in the set.
        """
        assert "self_destruct" not in ALLOWED_COMMANDS
        assert "reboot" not in ALLOWED_COMMANDS


# ---------------------------------------------------------------------------
# issue_command のテスト / Tests for CommandService.issue_command()
# ---------------------------------------------------------------------------

class TestIssueCommand:
    """
    [日本語] CommandService.issue_command() のテスト。
    コマンドを DB に保存し MQTT で送信するメインロジック。

    [English] Tests for CommandService.issue_command().
    Main logic that persists a command to DB and sends it via MQTT.
    """

    async def test_raises_on_unknown_command_type(self, mock_db):
        """
        [日本語] 許可されていないコマンドタイプは ValueError を raise する。
        不正なコマンドが MQTT に流れないようにする。

        [English] Raises ValueError for unauthorized command types.
        Prevents invalid commands from reaching MQTT.
        """
        service = CommandService(db=mock_db)
        with pytest.raises(ValueError, match="Unknown command type"):
            await service.issue_command(make_command("self_destruct"))

    async def test_saves_command_to_db(self, mock_db):
        """
        [日本語] コマンドが PostgreSQL に保存されることを確認。
        db.add() が呼ばれ、その後 commit() されること。

        [English] Verifies the command is persisted to PostgreSQL.
        db.add() is called, followed by commit().
        """
        service = CommandService(db=mock_db)
        with patch("src.services.command_service._mqtt_publish"):
            await service.issue_command(make_command("start_mission"))

        mock_db.add.assert_called_once()
        assert mock_db.commit.call_count >= 1

    async def test_emergency_stop_adds_critical_flag(self, mock_db):
        """
        [日本語] emergency_stop コマンドには payload に "critical: True" が自動付加される。
        緊急停止を他のコマンドと区別するためのフラグ。

        [English] emergency_stop automatically adds "critical: True" to the payload.
        Flag distinguishes emergency stops from other commands.
        """
        saved_cmd = None
        original_add = mock_db.add

        def capture_add(obj):
            nonlocal saved_cmd
            saved_cmd = obj
            return original_add(obj)

        mock_db.add = capture_add

        service = CommandService(db=mock_db)
        with patch("src.services.command_service._mqtt_publish"):
            await service.issue_command(make_command("emergency_stop"))

        assert saved_cmd is not None
        assert saved_cmd.payload.get("critical") is True

    async def test_status_is_sent_on_mqtt_success(self, mock_db):
        """
        [日本語] MQTT publish が成功した場合、コマンドの status は "sent" になる。

        [English] When MQTT publish succeeds, command status becomes "sent".
        """
        service = CommandService(db=mock_db)
        with patch("src.services.command_service._mqtt_publish"):
            response = await service.issue_command(make_command("return_to_dock"))

        assert response.status == "sent"

    async def test_status_is_failed_on_mqtt_error(self, mock_db):
        """
        [日本語] MQTT publish が失敗した場合、コマンドの status は "failed" になる。
        エラーは伝播せず、DB には失敗として記録される。

        [English] When MQTT publish fails, command status becomes "failed".
        Error is not propagated; recorded as failure in DB.
        """
        service = CommandService(db=mock_db)
        with patch(
            "src.services.command_service._mqtt_publish",
            side_effect=ConnectionError("broker unreachable"),
        ):
            response = await service.issue_command(make_command("pause_mission"))

        assert response.status == "failed"

    async def test_mqtt_topic_format(self, mock_db):
        """
        [日本語] MQTT トピックは "robot/{robot_id}/command" の形式であることを確認。
        IoT Core のルールと一致しないとロボットに届かない。

        [English] MQTT topic must follow the "robot/{robot_id}/command" format.
        Mismatch with IoT Core rules prevents delivery to robots.
        """
        captured_topic = None

        def capture_publish(topic, payload, qos=1):
            nonlocal captured_topic
            captured_topic = topic

        service = CommandService(db=mock_db)
        with patch("src.services.command_service._mqtt_publish", side_effect=capture_publish):
            await service.issue_command(make_command("start_mission", robot_id="robot_042"))

        assert captured_topic == "robot/robot_042/command"

    async def test_mqtt_payload_contains_command_id_and_type(self, mock_db):
        """
        [日本語] MQTT ペイロードに command_id と command_type が含まれることを確認。
        ロボット側での ACK に command_id が必要。

        [English] MQTT payload contains command_id and command_type.
        Robots need command_id for ACK processing.
        """
        captured_payload = None

        def capture_publish(topic, payload, qos=1):
            nonlocal captured_payload
            captured_payload = payload

        service = CommandService(db=mock_db)
        with patch("src.services.command_service._mqtt_publish", side_effect=capture_publish):
            await service.issue_command(make_command("start_mission"))

        assert "command_id" in captured_payload
        assert captured_payload["command_type"] == "start_mission"


# ---------------------------------------------------------------------------
# list_commands のテスト / Tests for CommandService.list_commands()
# ---------------------------------------------------------------------------

class TestListCommands:
    """
    [日本語] CommandService.list_commands() のテスト。
    コマンド履歴の一覧取得ロジック。

    [English] Tests for CommandService.list_commands().
    Logic for retrieving command history.
    """

    async def test_returns_empty_list_when_no_commands(self, mock_db):
        """
        [日本語] コマンドが存在しない場合は空リストを返す。

        [English] Returns an empty list when no commands exist.
        """
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = CommandService(db=mock_db)
        result = await service.list_commands()

        assert result == []
