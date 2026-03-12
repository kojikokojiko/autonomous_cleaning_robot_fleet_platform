"""
テスト仕様書: Lambda telemetry-processor
=========================================

[日本語]
このファイルは Kinesis → TimescaleDB テレメトリ処理 Lambda のテスト仕様書です。
Kinesis から届くロボットテレメトリのパース・検証・DB 書き込みの仕様を定義します。

仕様:
  1. Kinesis レコードは Base64 エンコードされた JSON
  2. 各レコードから robot_id, battery_level, position, status 等を抽出
  3. 複数レコードをまとめて TimescaleDB に INSERT (バッチ処理)
  4. robot_id が欠けているレコードはスキップ
  5. タイムスタンプが不正な場合は現在時刻を使用
  6. パースエラーは例外を raise → Lambda が DLQ へ送信

[English]
This file is the test specification for the Kinesis → TimescaleDB telemetry processor Lambda.
Documents parsing, validation, and DB write specifications for robot telemetry.

Specification:
  1. Kinesis records are Base64-encoded JSON
  2. Extract robot_id, battery_level, position, status, etc. from each record
  3. Batch-insert multiple records into TimescaleDB
  4. Skip records missing robot_id
  5. Use current time when timestamp is malformed
  6. Raise on parse errors → Lambda sends to DLQ
"""
import base64
from datetime import datetime, timezone
import json
import os
import sys
from unittest.mock import MagicMock, call, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../lambda/telemetry-processor"))

# DATABASE_URL を設定しておくことでテスト時は Secrets Manager 呼び出しをスキップする
# Setting DATABASE_URL lets tests bypass Secrets Manager (DB_SECRET_ARN path)
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")

# 他の Lambda handler.py とのモジュールキャッシュ衝突を防ぐ
# Prevent module cache collision with other Lambda handler.py files
if "handler" in sys.modules:
    del sys.modules["handler"]

import handler

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def encode_record(payload: dict) -> dict:
    """
    [日本語] Kinesis レコード形式の dict を生成する。
    データは Base64 エンコードされた JSON。

    [English] Generate a dict in Kinesis record format.
    Data is Base64-encoded JSON.
    """
    encoded = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8")
    return {"kinesis": {"data": encoded}}


def make_kinesis_event(payloads: list[dict]) -> dict:
    """
    [日本語] 複数レコードを含む Kinesis イベントを生成する。

    [English] Generate a Kinesis event containing multiple records.
    """
    return {"Records": [encode_record(p) for p in payloads]}


VALID_TELEMETRY = {
    "robot_id": "robot_001",
    "timestamp": "2024-01-15T10:30:00+00:00",
    "battery_level": 75.5,
    "position": {"x": 5.2, "y": 10.3, "floor": 1},
    "nav_status": "cleaning",
    "speed": 0.5,
    "mission_progress": 45.0,
    "motor_load_left": 0.3,
    "motor_load_right": 0.35,
}


# ---------------------------------------------------------------------------
# _parse_telemetry のテスト / Tests for _parse_telemetry()
# ---------------------------------------------------------------------------

class TestParseTelemetry:
    """
    [日本語] _parse_telemetry() 関数のテスト。
    ロボットからの JSON ペイロードを DB 挿入用 dict に変換する。

    [English] Tests for _parse_telemetry().
    Converts robot JSON payload into a dict for DB insertion.
    """

    def test_parses_all_fields_correctly(self):
        """
        [日本語] 全フィールドが正しくパースされることを確認。
        robot_id, battery_level, position (x/y/floor), status, speed, mission_progress 等。

        [English] Verifies all fields are parsed correctly.
        robot_id, battery_level, position (x/y/floor), status, speed, mission_progress, etc.
        """
        row = handler._parse_telemetry(VALID_TELEMETRY)

        assert row["robot_id"] == "robot_001"
        assert row["battery_level"] == 75.5
        assert row["position_x"] == 5.2
        assert row["position_y"] == 10.3
        assert row["position_floor"] == 1
        assert row["nav_status"] == "cleaning"
        assert row["speed"] == 0.5
        assert row["mission_progress"] == 45.0
        assert row["motor_load_left"] == 0.3
        assert row["motor_load_right"] == 0.35

    def test_returns_none_when_robot_id_missing(self):
        """
        [日本語] robot_id が欠けているペイロードは None を返してスキップする。
        どのロボットのテレメトリか分からないデータは DB に入れない。

        [English] Returns None and skips payloads missing robot_id.
        Data with unknown origin should not be inserted into the DB.
        """
        payload = {**VALID_TELEMETRY}
        del payload["robot_id"]
        result = handler._parse_telemetry(payload)
        assert result is None

    def test_uses_iso_timestamp_when_valid(self):
        """
        [日本語] 有効な ISO 8601 タイムスタンプは datetime オブジェクトに変換される。

        [English] A valid ISO 8601 timestamp is converted to a datetime object.
        """
        row = handler._parse_telemetry(VALID_TELEMETRY)
        assert isinstance(row["time"], datetime)

    def test_falls_back_to_current_time_on_bad_timestamp(self):
        """
        [日本語] タイムスタンプが不正な場合は現在時刻にフォールバックする。
        ロボットの時計がズレていても処理が止まらないことを保証。

        [English] Falls back to current time when timestamp is malformed.
        Ensures processing continues even when robot clock is wrong.
        """
        payload = {**VALID_TELEMETRY, "timestamp": "not-a-date"}
        before = datetime.now(timezone.utc)
        row = handler._parse_telemetry(payload)
        after = datetime.now(timezone.utc)

        assert before <= row["time"].replace(tzinfo=timezone.utc) <= after

    def test_falls_back_to_current_time_when_no_timestamp(self):
        """
        [日本語] timestamp フィールドがない場合も現在時刻にフォールバックする。

        [English] Falls back to current time when timestamp field is absent.
        """
        payload = {k: v for k, v in VALID_TELEMETRY.items() if k != "timestamp"}
        row = handler._parse_telemetry(payload)
        assert isinstance(row["time"], datetime)

    def test_defaults_position_floor_to_1(self):
        """
        [日本語] position に floor が含まれない場合はデフォルト値 1 が使われる。

        [English] Defaults position_floor to 1 when not provided in position.
        """
        payload = {**VALID_TELEMETRY, "position": {"x": 3.0, "y": 4.0}}
        row = handler._parse_telemetry(payload)
        assert row["position_floor"] == 1

    def test_handles_missing_optional_fields_as_none(self):
        """
        [日本語] speed, mission_progress などのオプションフィールドが欠けていても None として処理。
        すべてのフィールドが必須でないことを確認。

        [English] Optional fields like speed, mission_progress are handled as None when missing.
        Confirms not all fields are required.
        """
        minimal = {"robot_id": "robot_002", "battery_level": 50.0}
        row = handler._parse_telemetry(minimal)
        assert row is not None
        assert row["speed"] is None
        assert row["mission_progress"] is None
        assert row["motor_load_left"] is None


# ---------------------------------------------------------------------------
# lambda_handler のテスト / Tests for lambda_handler()
# ---------------------------------------------------------------------------

class TestLambdaHandler:
    """
    [日本語] lambda_handler() のテスト。
    Kinesis バッチイベントを受け取り、DB に一括挿入する。

    [English] Tests for lambda_handler().
    Processes a Kinesis batch event and bulk-inserts into the DB.
    """

    def test_processes_multiple_records_and_inserts(self):
        """
        [日本語] 複数のレコードを受け取り、全てを DB に挿入する。
        3レコード → 3行が挿入され、inserted=3 が返る。

        [English] Processes multiple records and inserts all into DB.
        3 records → 3 rows inserted → returns inserted=3.
        """
        records = [
            {**VALID_TELEMETRY, "robot_id": f"robot_{i:03d}"}
            for i in range(3)
        ]
        event = make_kinesis_event(records)

        with patch.object(handler, "_batch_insert") as mock_insert:
            result = handler.lambda_handler(event, context={})

        mock_insert.assert_called_once()
        rows = mock_insert.call_args[0][0]
        assert len(rows) == 3
        assert result == {"statusCode": 200, "inserted": 3}

    def test_skips_invalid_records(self):
        """
        [日本語] robot_id が欠けているレコードはスキップし、有効なレコードのみ挿入する。
        部分的に不正なバッチでも処理が継続されることを確認。

        [English] Skips records missing robot_id; only inserts valid records.
        Verifies batch processing continues even with some invalid records.
        """
        records = [
            VALID_TELEMETRY,                                  # valid
            {**VALID_TELEMETRY, "robot_id": "robot_002"},    # valid
            {"battery_level": 50.0},                          # invalid: no robot_id
        ]
        event = make_kinesis_event(records)

        with patch.object(handler, "_batch_insert") as mock_insert:
            result = handler.lambda_handler(event, context={})

        rows = mock_insert.call_args[0][0]
        assert len(rows) == 2
        assert result["inserted"] == 2

    def test_returns_zero_inserted_for_empty_event(self):
        """
        [日本語] レコードが0件のイベントは inserted=0 を返す。
        空バッチを受け取っても例外が起きないことを確認。

        [English] Returns inserted=0 for an event with no records.
        Verifies empty batches don't raise exceptions.
        """
        event = {"Records": []}

        result = handler.lambda_handler(event, context={})

        assert result == {"statusCode": 200, "inserted": 0}

    def test_raises_on_malformed_base64(self):
        """
        [日本語] Base64 デコードに失敗した場合は例外を raise する。
        Lambda が自動リトライして DLQ に送れるよう、エラーを握り潰さない。

        [English] Raises an exception when Base64 decoding fails.
        Allows Lambda automatic retry and DLQ routing by not swallowing errors.
        """
        event = {"Records": [{"kinesis": {"data": "!!! not base64 !!!"}}]}

        with pytest.raises(Exception):
            handler.lambda_handler(event, context={})
