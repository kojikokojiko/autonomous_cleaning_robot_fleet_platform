"""
テスト仕様書: Lambda ws-event-pusher
=====================================

[日本語]
このファイルは WebSocket イベントプッシュ Lambda 関数のテスト仕様書です。
EventBridge からのロボットイベントを、接続中の全ブラウザに配信する動作を定義します。

仕様:
  1. Redis "ws:connections" から接続中の全 connectionId を取得 (SMEMBERS)
  2. 各 connectionId に対して API GW Management API の post_to_connection を呼ぶ
  3. GoneException / ForbiddenException が返った接続は「切れた接続」として Redis から削除
  4. connectionId が0件の場合は何も送信しない
  5. WS_API_ENDPOINT が未設定の場合は何も送信しない

[English]
This file is the test specification for the WebSocket event pusher Lambda.
Documents the behavior of pushing robot events to all connected browsers.

Specification:
  1. Retrieve all connectionIds from Redis "ws:connections" (SMEMBERS)
  2. Call API GW Management API post_to_connection for each connectionId
  3. Remove stale connections (GoneException / ForbiddenException) from Redis
  4. Do nothing when no connections exist
  5. Do nothing when WS_API_ENDPOINT is not set
"""
import json
import os
import sys
from unittest.mock import MagicMock, call, patch

from botocore.exceptions import ClientError
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../lambda/ws-event-pusher"))

# 他の Lambda handler.py とのモジュールキャッシュ衝突を防ぐ
# Prevent module cache collision with other Lambda handler.py files
if "handler" in sys.modules:
    del sys.modules["handler"]

import handler

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_singletons():
    """
    [日本語] 各テスト前に Redis・API GW クライアントのシングルトンをリセット。

    [English] Reset Redis and API GW client singletons before each test.
    """
    handler._redis_client = None
    handler._apigw_client = None
    yield
    handler._redis_client = None
    handler._apigw_client = None


def make_eventbridge_event(detail_type: str = "RobotBatteryLow", detail: dict = None) -> dict:
    """
    [日本語] EventBridge から届くイベントのモックを生成する。

    [English] Generate a mock EventBridge event.
    """
    return {
        "source": "robotops.robot",
        "detail-type": detail_type,
        "detail": detail or {"robot_id": "robot_001", "battery_level": 15.0},
    }


def make_client_error(code: str) -> ClientError:
    """
    [日本語] botocore ClientError のモックを生成する。

    [English] Generate a mock botocore ClientError.
    """
    return ClientError({"Error": {"Code": code, "Message": "test"}}, "PostToConnection")


# ---------------------------------------------------------------------------
# lambda_handler のテスト / Tests for lambda_handler()
# ---------------------------------------------------------------------------

class TestLambdaHandler:
    """
    [日本語] lambda_handler() のテスト。
    EventBridge イベントを受け取りブラウザに配信するエントリポイント。

    [English] Tests for lambda_handler().
    Entry point that receives EventBridge events and pushes to browsers.
    """

    def test_returns_200(self):
        """
        [日本語] 正常処理時は {"statusCode": 200} を返す。

        [English] Returns {"statusCode": 200} on successful execution.
        """
        mock_redis = MagicMock()
        mock_redis.smembers.return_value = set()

        with patch.object(handler, "_get_redis", return_value=mock_redis):
            with patch.dict(os.environ, {"WS_API_ENDPOINT": ""}):
                result = handler.lambda_handler(make_eventbridge_event(), context={})

        assert result == {"statusCode": 200}

    def test_pushes_correct_payload_format(self):
        """
        [日本語] ブラウザに送信されるペイロードの形式を検証。
        {type: "robot_event", event_type: ..., data: {...}} の JSON バイト列であること。

        [English] Validates the payload format sent to browsers.
        Must be JSON bytes: {type: "robot_event", event_type: ..., data: {...}}.
        """
        mock_redis = MagicMock()
        mock_redis.smembers.return_value = {"conn-001"}
        mock_apigw = MagicMock()

        with patch.object(handler, "_get_redis", return_value=mock_redis):
            with patch.object(handler, "_get_apigw", return_value=mock_apigw):
                handler.lambda_handler(
                    make_eventbridge_event("RobotBatteryLow", {"robot_id": "r1", "battery_level": 15}),  # noqa: E501
                    context={},
                )

        call_args = mock_apigw.post_to_connection.call_args
        sent_data = json.loads(call_args.kwargs["Data"])
        assert sent_data["type"] == "robot_event"
        assert sent_data["event_type"] == "RobotBatteryLow"
        assert sent_data["data"]["robot_id"] == "r1"


# ---------------------------------------------------------------------------
# _push_to_all_connections のテスト / Tests for _push_to_all_connections()
# ---------------------------------------------------------------------------

class TestPushToAllConnections:
    """
    [日本語] _push_to_all_connections() のテスト。
    全接続にペイロードを配信し、切れた接続をクリーンアップする。

    [English] Tests for _push_to_all_connections().
    Distributes payload to all connections and cleans up stale ones.
    """

    def test_sends_to_all_active_connections(self):
        """
        [日本語] 接続中の全 connectionId に post_to_connection を呼ぶ。
        3台接続中なら 3回 呼ばれることを確認。

        [English] Calls post_to_connection for every active connectionId.
        With 3 connections, post_to_connection is called 3 times.
        """
        mock_redis = MagicMock()
        mock_redis.smembers.return_value = {"conn-1", "conn-2", "conn-3"}
        mock_apigw = MagicMock()
        payload = b'{"type":"robot_event"}'

        with patch.object(handler, "_get_redis", return_value=mock_redis):
            with patch.object(handler, "_get_apigw", return_value=mock_apigw):
                handler._push_to_all_connections(payload)

        assert mock_apigw.post_to_connection.call_count == 3

    def test_does_nothing_when_no_connections(self):
        """
        [日本語] 接続中のブラウザが0件の場合、API GW は呼ばれない。
        不要なコストを発生させないことを確認。

        [English] API GW is not called when no connections exist.
        Verifies no unnecessary costs are incurred.
        """
        mock_redis = MagicMock()
        mock_redis.smembers.return_value = set()
        mock_apigw = MagicMock()

        with patch.object(handler, "_get_redis", return_value=mock_redis):
            with patch.object(handler, "_get_apigw", return_value=mock_apigw):
                handler._push_to_all_connections(b"payload")

        mock_apigw.post_to_connection.assert_not_called()

    def test_removes_gone_connections_from_redis(self):
        """
        [日本語] GoneException が返った connectionId は Redis から削除する。
        ブラウザが既に切断済みの場合に接続リストをクリーンアップ。

        [English] connectionIds that return GoneException are removed from Redis.
        Cleans up connections list when browsers are already disconnected.
        """
        mock_redis = MagicMock()
        # set は反復順が不定なので1件のみ / Use single entry; set iteration order is undefined
        mock_redis.smembers.return_value = {"conn-gone"}
        mock_apigw = MagicMock()
        mock_apigw.post_to_connection.side_effect = make_client_error("GoneException")

        with patch.object(handler, "_get_redis", return_value=mock_redis):
            with patch.object(handler, "_get_apigw", return_value=mock_apigw):
                handler._push_to_all_connections(b"payload")

        mock_redis.srem.assert_called_once_with("ws:connections", "conn-gone")

    def test_removes_forbidden_connections_from_redis(self):
        """
        [日本語] ForbiddenException が返った connectionId も Redis から削除する。
        GoneException と同様に無効な接続として扱う。

        [English] connectionIds with ForbiddenException are also removed from Redis.
        Treated as invalid connections, same as GoneException.
        """
        mock_redis = MagicMock()
        mock_redis.smembers.return_value = {"conn-forbidden"}
        mock_apigw = MagicMock()
        mock_apigw.post_to_connection.side_effect = make_client_error("ForbiddenException")

        with patch.object(handler, "_get_redis", return_value=mock_redis):
            with patch.object(handler, "_get_apigw", return_value=mock_apigw):
                handler._push_to_all_connections(b"payload")

        mock_redis.srem.assert_called_once_with("ws:connections", "conn-forbidden")

    def test_does_not_remove_on_other_errors(self):
        """
        [日本語] GoneException / ForbiddenException 以外のエラー (例: ThrottlingException) は
        Redis からの削除を行わない。一時的な障害で接続を削除しないことを保証。

        [English] Errors other than GoneException/ForbiddenException (e.g., ThrottlingException)
        do not trigger Redis deletion. Prevents removing valid connections on transient failures.
        """
        mock_redis = MagicMock()
        mock_redis.smembers.return_value = {"conn-throttled"}
        mock_apigw = MagicMock()
        mock_apigw.post_to_connection.side_effect = make_client_error("ThrottlingException")

        with patch.object(handler, "_get_redis", return_value=mock_redis):
            with patch.object(handler, "_get_apigw", return_value=mock_apigw):
                handler._push_to_all_connections(b"payload")

        mock_redis.srem.assert_not_called()

    def test_does_nothing_when_apigw_not_initialized(self):
        """
        [日本語] WS_API_ENDPOINT が未設定で API GW クライアントが None の場合、
        処理をスキップする (ローカル開発環境での安全動作)。

        [English] Skips execution when API GW client is None (WS_API_ENDPOINT not set).
        Safe behavior in local development environments.
        """
        mock_redis = MagicMock()
        mock_redis.smembers.return_value = {"conn-001"}

        with patch.object(handler, "_get_redis", return_value=mock_redis):
            with patch("handler._get_apigw", return_value=None):
                # Should not raise, just log warning
                handler._push_to_all_connections(b"payload")
