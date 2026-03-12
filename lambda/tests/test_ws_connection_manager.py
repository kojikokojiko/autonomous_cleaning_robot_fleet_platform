"""
テスト仕様書: Lambda ws-connection-manager
==========================================

[日本語]
このファイルは WebSocket 接続管理 Lambda 関数のテスト仕様書です。
ブラウザが WebSocket に接続・切断したときの Redis 操作を定義します。

仕様:
  $connect    → Redis Set "ws:connections" に connectionId を追加 (SADD)
  $disconnect → Redis Set "ws:connections" から connectionId を削除 (SREM)
  $default    → 何もせず 200 を返す (デバッグ用エコー)
  認証情報がある場合 → "ws:conn:{connectionId}" に 1時間 TTL で保存

[English]
This file is the test specification for the WebSocket connection manager Lambda.
Documents Redis operations performed on browser connect/disconnect events.

Specification:
  $connect    → SADD connectionId to Redis Set "ws:connections"
  $disconnect → SREM connectionId from Redis Set "ws:connections"
  $default    → Return 200 without action (debug echo)
  If authorizer context → store in "ws:conn:{connectionId}" with 1h TTL
"""
import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# Lambda のパスを通す / Add Lambda path to sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../lambda/ws-connection-manager"))

# 他の Lambda handler.py とのモジュールキャッシュ衝突を防ぐ
# Prevent module cache collision with other Lambda handler.py files
if "handler" in sys.modules:
    del sys.modules["handler"]

import handler

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_redis_singleton():
    """
    [日本語] 各テスト前後に Redis シングルトンをリセットする。
    handler.py はモジュールレベルで _redis_client をキャッシュするため、
    テスト間で状態が漏れないようにリセットが必要。

    [English] Reset the Redis singleton before/after each test.
    handler.py caches _redis_client at module level; reset prevents state leakage.
    """
    handler._redis_client = None
    yield
    handler._redis_client = None


def make_event(route_key: str, connection_id: str, authorizer: dict = None) -> dict:
    """テスト用 API GW WebSocket イベントを生成 / Generate a mock API GW WebSocket event."""
    ctx = {"routeKey": route_key, "connectionId": connection_id}
    if authorizer:
        ctx["authorizer"] = authorizer
    return {"requestContext": ctx}


# ---------------------------------------------------------------------------
# $connect のテスト / Tests for $connect
# ---------------------------------------------------------------------------

class TestConnect:
    """
    [日本語] $connect ルートのテスト。
    新しいブラウザ接続が来たときに connectionId が Redis に保存される。

    [English] Tests for the $connect route.
    Verifies connectionId is stored in Redis when a new browser connects.
    """

    def test_sadd_connection_id_to_redis_set(self):
        """
        [日本語] $connect 時に Redis Set "ws:connections" に connectionId が追加される。
        SADD コマンドが正しい引数で呼ばれることを確認。

        [English] On $connect, connectionId is added to Redis Set "ws:connections".
        Verifies SADD is called with correct arguments.
        """
        mock_redis = MagicMock()
        mock_redis.scard.return_value = 1

        with patch.object(handler, "_get_redis", return_value=mock_redis):
            result = handler.lambda_handler(
                make_event("$connect", "conn-abc123"), context={}
            )

        mock_redis.sadd.assert_called_once_with("ws:connections", "conn-abc123")
        assert result == {"statusCode": 200}

    def test_returns_200_on_connect(self):
        """
        [日本語] $connect の応答は常に HTTP 200 OK である。
        API Gateway WebSocket は statusCode=200 を成功とみなす。

        [English] $connect always returns HTTP 200 OK.
        API Gateway WebSocket treats statusCode=200 as success.
        """
        mock_redis = MagicMock()
        mock_redis.scard.return_value = 1

        with patch.object(handler, "_get_redis", return_value=mock_redis):
            result = handler.lambda_handler(
                make_event("$connect", "conn-xyz"), context={}
            )

        assert result["statusCode"] == 200

    def test_stores_authorizer_context_with_ttl(self):
        """
        [日本語] 認証コンテキスト (Cognito JWT の claims 等) がある場合、
        "ws:conn:{connectionId}" に JSON 形式で 3600秒 TTL を付けて保存する。

        [English] When authorizer context exists (e.g., Cognito JWT claims),
        it is stored as JSON at "ws:conn:{connectionId}" with a 3600-second TTL.
        """
        mock_redis = MagicMock()
        mock_redis.scard.return_value = 1
        auth_ctx = {"userId": "user-001", "role": "operator"}

        with patch.object(handler, "_get_redis", return_value=mock_redis):
            handler.lambda_handler(
                make_event("$connect", "conn-auth", authorizer=auth_ctx), context={}
            )

        mock_redis.setex.assert_called_once_with(
            "ws:conn:conn-auth", 3600, json.dumps(auth_ctx)
        )

    def test_no_setex_when_no_authorizer(self):
        """
        [日本語] 認証コンテキストがない場合、setex は呼ばれない。
        不要な Redis キーを作成しないことを確認。

        [English] When there is no authorizer context, setex is not called.
        Verifies no unnecessary Redis keys are created.
        """
        mock_redis = MagicMock()
        mock_redis.scard.return_value = 1

        with patch.object(handler, "_get_redis", return_value=mock_redis):
            handler.lambda_handler(
                make_event("$connect", "conn-noauth"), context={}
            )

        mock_redis.setex.assert_not_called()


# ---------------------------------------------------------------------------
# $disconnect のテスト / Tests for $disconnect
# ---------------------------------------------------------------------------

class TestDisconnect:
    """
    [日本語] $disconnect ルートのテスト。
    ブラウザが切断したときに connectionId が Redis から削除される。

    [English] Tests for the $disconnect route.
    Verifies connectionId is removed from Redis when a browser disconnects.
    """

    def test_srem_connection_id_from_redis_set(self):
        """
        [日本語] $disconnect 時に Redis Set から connectionId が削除される。
        SREM コマンドが正しい引数で呼ばれることを確認。

        [English] On $disconnect, connectionId is removed from the Redis Set.
        Verifies SREM is called with correct arguments.
        """
        mock_redis = MagicMock()
        mock_redis.scard.return_value = 0

        with patch.object(handler, "_get_redis", return_value=mock_redis):
            result = handler.lambda_handler(
                make_event("$disconnect", "conn-abc123"), context={}
            )

        mock_redis.srem.assert_called_once_with("ws:connections", "conn-abc123")
        assert result == {"statusCode": 200}

    def test_deletes_conn_metadata_key(self):
        """
        [日本語] 切断時に "ws:conn:{connectionId}" のメタデータキーも削除される。
        接続時に保存した認証情報のゴミが残らないことを確認。

        [English] On disconnect, the "ws:conn:{connectionId}" metadata key is also deleted.
        Ensures no leftover auth info from the $connect phase.
        """
        mock_redis = MagicMock()
        mock_redis.scard.return_value = 0

        with patch.object(handler, "_get_redis", return_value=mock_redis):
            handler.lambda_handler(
                make_event("$disconnect", "conn-todelete"), context={}
            )

        mock_redis.delete.assert_called_once_with("ws:conn:conn-todelete")

    def test_returns_200_on_disconnect(self):
        """
        [日本語] $disconnect の応答は HTTP 200 OK である。

        [English] $disconnect returns HTTP 200 OK.
        """
        mock_redis = MagicMock()
        mock_redis.scard.return_value = 0

        with patch.object(handler, "_get_redis", return_value=mock_redis):
            result = handler.lambda_handler(
                make_event("$disconnect", "conn-bye"), context={}
            )

        assert result["statusCode"] == 200


# ---------------------------------------------------------------------------
# $default のテスト / Tests for $default
# ---------------------------------------------------------------------------

class TestDefault:
    """
    [日本語] $default ルート (未知のルート) のテスト。
    接続中のクライアントからメッセージが来た場合の処理。

    [English] Tests for the $default route (unknown routes).
    Handles messages sent by connected clients.
    """

    def test_returns_200_on_default_route(self):
        """
        [日本語] $default は 200 を返すだけで Redis 操作は行わない。

        [English] $default returns 200 and performs no Redis operations.
        """
        mock_redis = MagicMock()

        with patch.object(handler, "_get_redis", return_value=mock_redis):
            result = handler.lambda_handler(
                make_event("$default", "conn-msg"), context={}
            )

        mock_redis.sadd.assert_not_called()
        mock_redis.srem.assert_not_called()
        assert result["statusCode"] == 200
