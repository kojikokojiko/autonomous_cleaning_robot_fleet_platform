"""
テスト仕様書: robot-agent — RobotAgent 状態機械
================================================

[日本語]
このファイルは RobotAgent クラスの状態機械テスト仕様書です。
ロボットが受け取るコマンドに応じてどのように状態遷移するかを定義します。

状態遷移仕様:
  IDLE      → start_mission コマンド受信 → CLEANING
  CLEANING  → pause_mission コマンド受信 → IDLE
  CLEANING  → return_to_dock コマンド受信 → CHARGING (移動開始)
  CHARGING  → ドック到着 → DOCKED
  DOCKED    → バッテリー 100% → IDLE
  任意状態  → emergency_stop コマンド受信 → IDLE (即座に停止)

OTA 仕様:
  IDLE/DOCKED → OTA コマンド受信 → OTA_UPDATE → checksum 検証 → 設定適用 → IDLE
  それ以外の状態では → OTA を延期 (deferral)

[English]
This file is the test specification for RobotAgent state machine behavior.
Documents how the robot transitions between states based on received commands.

State transition specification:
  IDLE      → receive start_mission → CLEANING
  CLEANING  → receive pause_mission → IDLE
  CLEANING  → receive return_to_dock → CHARGING (start transit)
  CHARGING  → arrive at dock → DOCKED
  DOCKED    → battery reaches 100% → IDLE
  Any state → receive emergency_stop → IDLE (immediate halt)

OTA specification:
  IDLE/DOCKED → receive OTA command → OTA_UPDATE → verify checksum → apply config → IDLE
  Other states → defer OTA
"""
import json
import os
from pathlib import Path
import sys
import threading
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.nodes.robot_agent import ALLOWED_COMMANDS, RobotAgent
from src.nodes.state import RobotState, RobotStatus

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_mqtt():
    """
    [日本語] MQTT クライアントのモック。
    接続・パブリッシュ操作をシミュレートする。

    [English] Mock for the MQTT client.
    Simulates connect and publish operations.
    """
    mqtt = MagicMock()
    mqtt.connect = MagicMock()
    mqtt.publish_event = MagicMock()
    mqtt.publish_telemetry = MagicMock()
    return mqtt


@pytest.fixture
def agent(mock_mqtt, tmp_path):
    """
    [日本語] テスト用 RobotAgent を生成する。
    MQTT クライアントをモックで差し替え、設定ファイルを一時ディレクトリに保存。

    [English] Generate a RobotAgent for testing.
    Replace MQTT client with mock, save config to temp directory.
    """
    with patch("src.nodes.robot_agent.RobotMQTTClient", return_value=mock_mqtt):
        with patch("src.nodes.robot_agent.ROBOT_CONFIG_DIR", tmp_path):
            a = RobotAgent(robot_id="test_robot")
            a.mqtt = mock_mqtt
    return a


# ---------------------------------------------------------------------------
# 状態機械のテスト / Tests for state machine
# ---------------------------------------------------------------------------

class TestStateMachine:
    """
    [日本語] RobotAgent の状態機械テスト。
    各コマンドに対する状態遷移を検証する。

    [English] Tests for RobotAgent state machine.
    Validates state transitions for each command.
    """

    def test_initial_state_is_idle(self, agent):
        """
        [日本語] ロボットの初期状態は IDLE である。
        新規起動時のデフォルト状態。

        [English] Initial robot state is IDLE.
        Default state on fresh startup.
        """
        assert agent.state.status == RobotStatus.IDLE

    def test_return_to_dock_transitions_to_charging(self, agent):
        """
        [日本語] return_to_dock コマンドを受け取ると CHARGING 状態に遷移する。
        (CHARGING = ドックへの移動中を意味する)

        [English] Receiving return_to_dock transitions to CHARGING state.
        (CHARGING means "moving toward dock")
        """
        agent.state.status = RobotStatus.IDLE
        agent._cmd_return_to_dock()

        assert agent.state.status == RobotStatus.CHARGING

    def test_emergency_stop_transitions_to_idle(self, agent):
        """
        [日本語] emergency_stop コマンドは清掃中でも即座に IDLE に遷移する。
        どの状態でも最優先で停止する。

        [English] emergency_stop immediately transitions to IDLE from any state.
        Highest priority stop regardless of current state.
        """
        agent.state.status = RobotStatus.CLEANING
        agent._cmd_emergency_stop()

        assert agent.state.status == RobotStatus.IDLE

    def test_emergency_stop_sets_speed_to_zero(self, agent):
        """
        [日本語] emergency_stop 後にスピードが 0 になる。
        物理的にロボットが止まることを保証。

        [English] Speed becomes 0 after emergency_stop.
        Ensures robot physically stops.
        """
        agent.state.speed = 1.5
        agent._cmd_emergency_stop()

        assert agent.state.speed == 0.0

    def test_battery_drains_when_cleaning(self, agent):
        """
        [日本語] CLEANING 状態ではテレメトリサイクルごとにバッテリーが減少する。
        実際の掃除機が電力を消費することをシミュレート。

        [English] Battery decreases each telemetry cycle during CLEANING.
        Simulates real vacuum cleaner power consumption.
        """
        agent.state.status = RobotStatus.CLEANING
        initial_battery = 80.0
        agent.state.battery_level = initial_battery

        # 1 サイクル分のシミュレーション
        agent._simulate_state()

        assert agent.state.battery_level < initial_battery

    def test_battery_charges_when_docked(self, agent):
        """
        [日本語] DOCKED 状態ではテレメトリサイクルごとにバッテリーが増加する。

        [English] Battery increases each telemetry cycle when DOCKED.
        """
        agent.state.status = RobotStatus.DOCKED
        initial_battery = 50.0
        agent.state.battery_level = initial_battery

        agent._simulate_state()

        assert agent.state.battery_level > initial_battery

    def test_docked_transitions_to_idle_at_full_charge(self, agent):
        """
        [日本語] DOCKED 状態でバッテリーが 100% になると IDLE に遷移する。
        充電完了後に次のミッションを受け入れられる状態に戻る。

        [English] DOCKED transitions to IDLE when battery reaches 100%.
        Returns to ready state to accept new missions after charging.
        """
        agent.state.status = RobotStatus.DOCKED
        agent.state.battery_level = 99.99  # 1サイクルで100%に到達

        agent._simulate_state()

        assert agent.state.status == RobotStatus.IDLE


# ---------------------------------------------------------------------------
# OTA フローのテスト / Tests for OTA flow
# ---------------------------------------------------------------------------

class TestOTAFlow:
    """
    [日本語] OTA アップデートフローのテスト。
    ファームウェア受信・検証・適用・永続化の流れを検証。

    [English] Tests for the OTA update flow.
    Validates firmware receive, verify, apply, and persist sequence.
    """

    def test_ota_deferred_when_not_idle_or_docked(self, agent):
        """
        [日本語] CLEANING 状態では OTA を延期する (実行しない)。
        清掃中の中断によるデータロスを防ぐ。

        [English] OTA is deferred when in CLEANING state.
        Prevents data loss from mid-mission interruption.
        """
        agent.state.status = RobotStatus.CLEANING

        ota_payload = {
            "job_id": "job-001",
            "version": "v2.0.0",
            "firmware_id": "fw-001",
            "checksum_sha256": "abc123",
        }

        # OTA スレッドが開始されないことを確認
        with patch.object(threading, "Thread") as mock_thread:
            agent._handle_ota(ota_payload)
            mock_thread.assert_not_called()

    def test_config_persisted_to_disk_after_ota(self, agent, tmp_path):
        """
        [日本語] OTA 適用後に設定がディスクに永続化される。
        ロボット再起動後も設定が維持されることを保証。

        [English] Config is persisted to disk after OTA application.
        Ensures settings survive robot restart.
        """
        config = {"step_per_cycle": 1.5, "_version": "v2.0.0"}

        with patch("src.nodes.robot_agent.ROBOT_CONFIG_DIR", tmp_path):
            agent._save_config(config, version="v2.0.0")

        config_path = tmp_path / "test_robot.json"
        assert config_path.exists()

        saved = json.loads(config_path.read_text())
        assert saved["_version"] == "v2.0.0"
        assert saved["step_per_cycle"] == 1.5

    def test_config_restored_from_disk_on_startup(self, agent, tmp_path):
        """
        [日本語] 起動時にディスクから設定を復元する。
        OTA 後に再起動しても前回の設定が適用されることを確認。

        [English] Config is restored from disk on startup.
        Verifies previous config is applied after OTA + restart.
        """
        config_path = tmp_path / "test_robot.json"
        config_path.write_text(json.dumps({
            "step_per_cycle": 2.0,
            "_version": "v3.0.0",
        }))

        with patch("src.nodes.robot_agent.ROBOT_CONFIG_DIR", tmp_path):
            agent._load_config()

        assert agent._step_per_cycle == 2.0
        assert agent._firmware_version == "v3.0.0"

    def test_step_per_cycle_applied_from_config(self, agent):
        """
        [日本語] config の step_per_cycle がエージェントの移動速度に適用される。
        OTA で速度変更が実際に反映されることを確認。

        [English] step_per_cycle from config is applied to agent movement speed.
        Verifies OTA speed changes actually take effect.
        """
        initial_step = agent._step_per_cycle

        agent._apply_config({"step_per_cycle": 2.5})

        assert agent._step_per_cycle == pytest.approx(2.5)
        assert agent._step_per_cycle != initial_step


# ---------------------------------------------------------------------------
# ALLOWED_COMMANDS 定数のテスト / Tests for ALLOWED_COMMANDS constant
# ---------------------------------------------------------------------------

class TestAllowedCommands:
    """
    [日本語] ALLOWED_COMMANDS 定数のテスト。
    ロボットが受け付けるコマンドが仕様と一致することを確認。

    [English] Tests for ALLOWED_COMMANDS constant.
    Verifies robot-accepted commands match the specification.
    """

    def test_contains_all_required_commands(self):
        """
        [日本語] ロボットが受け付ける4種類のコマンドが定義されている。

        [English] All 4 required commands are defined.
        """
        assert "start_mission" in ALLOWED_COMMANDS
        assert "pause_mission" in ALLOWED_COMMANDS
        assert "return_to_dock" in ALLOWED_COMMANDS
        assert "emergency_stop" in ALLOWED_COMMANDS
