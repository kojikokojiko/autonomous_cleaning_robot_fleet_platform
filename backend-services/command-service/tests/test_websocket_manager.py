"""
テスト仕様書: command-service — ConnectionManager (WebSocket)
=============================================================

[日本語]
このファイルは ConnectionManager クラスのテスト仕様書です。
ブラウザとの WebSocket 接続を管理し、全接続にメッセージをブロードキャストする仕様を定義します。

仕様:
  - connect(ws)    → 接続を active_connections に追加
  - disconnect(ws) → 接続を active_connections から削除
  - broadcast(msg) → 全接続に send_json でメッセージを送信
  - 切れた接続 (例外発生) はブロードキャスト中に自動削除

[English]
This file is the test specification for the ConnectionManager class.
Documents WebSocket connection lifecycle and broadcast behavior.

Specification:
  - connect(ws)    → add to active_connections
  - disconnect(ws) → remove from active_connections
  - broadcast(msg) → send_json to all connections
  - Stale connections (those raising exceptions) are auto-removed during broadcast
"""
import os
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.services.websocket_manager import ConnectionManager

pytestmark = pytest.mark.asyncio


def make_mock_ws():
    """
    [日本語] FastAPI WebSocket のモックを生成する。
    accept() と send_json() を AsyncMock として定義。

    [English] Generate a mock FastAPI WebSocket.
    accept() and send_json() are AsyncMock.
    """
    ws = AsyncMock()
    ws.accept = AsyncMock()
    ws.send_json = AsyncMock()
    return ws


class TestConnectionManager:
    """
    [日本語] ConnectionManager クラスのテスト。

    [English] Tests for ConnectionManager class.
    """

    async def test_connect_adds_to_active_connections(self):
        """
        [日本語] connect() を呼ぶと接続が active_connections に追加される。
        また ws.accept() が呼ばれて WebSocket ハンドシェイクが完了する。

        [English] connect() adds the connection to active_connections.
        ws.accept() is called to complete the WebSocket handshake.
        """
        mgr = ConnectionManager()
        ws = make_mock_ws()

        await mgr.connect(ws)

        assert ws in mgr.active_connections
        ws.accept.assert_awaited_once()

    async def test_disconnect_removes_from_active_connections(self):
        """
        [日本語] disconnect() を呼ぶと接続が active_connections から削除される。

        [English] disconnect() removes the connection from active_connections.
        """
        mgr = ConnectionManager()
        ws = make_mock_ws()
        mgr.active_connections.append(ws)

        mgr.disconnect(ws)

        assert ws not in mgr.active_connections

    async def test_disconnect_nonexistent_does_not_raise(self):
        """
        [日本語] 存在しない接続を disconnect() しても例外が起きない。
        二重切断などのエッジケースに対して安全。

        [English] disconnect() on a non-existent connection does not raise.
        Safe against edge cases like double-disconnect.
        """
        mgr = ConnectionManager()
        ws = make_mock_ws()

        mgr.disconnect(ws)  # Should not raise

    async def test_broadcast_sends_to_all_connections(self):
        """
        [日本語] broadcast() は全接続の send_json() を呼ぶ。
        3 接続あれば 3 回呼ばれる。

        [English] broadcast() calls send_json() on all connections.
        With 3 connections, called 3 times.
        """
        mgr = ConnectionManager()
        ws1, ws2, ws3 = make_mock_ws(), make_mock_ws(), make_mock_ws()
        mgr.active_connections = [ws1, ws2, ws3]
        message = {"type": "telemetry_update", "data": {"robot_id": "r1"}}

        await mgr.broadcast(message)

        ws1.send_json.assert_awaited_once_with(message)
        ws2.send_json.assert_awaited_once_with(message)
        ws3.send_json.assert_awaited_once_with(message)

    async def test_broadcast_removes_dead_connections(self):
        """
        [日本語] ブロードキャスト中に例外が発生した接続は active_connections から削除される。
        切断済みブラウザへの送信失敗を自動クリーンアップ。

        [English] Connections that raise exceptions during broadcast are removed.
        Auto-cleanup for failed sends to already-disconnected browsers.
        """
        mgr = ConnectionManager()
        ws_alive = make_mock_ws()
        ws_dead = make_mock_ws()
        ws_dead.send_json.side_effect = RuntimeError("connection closed")

        mgr.active_connections = [ws_dead, ws_alive]

        await mgr.broadcast({"type": "test"})

        assert ws_dead not in mgr.active_connections
        assert ws_alive in mgr.active_connections

    async def test_broadcast_to_empty_connections_does_not_raise(self):
        """
        [日本語] 接続が0件のときに broadcast() を呼んでも例外が起きない。

        [English] broadcast() with no connections does not raise.
        """
        mgr = ConnectionManager()

        await mgr.broadcast({"type": "test"})  # Should not raise

    async def test_multiple_connects_tracked_independently(self):
        """
        [日本語] 複数の異なるブラウザが接続した場合、それぞれ独立して追跡される。

        [English] Multiple different browser connections are tracked independently.
        """
        mgr = ConnectionManager()
        ws1, ws2 = make_mock_ws(), make_mock_ws()

        await mgr.connect(ws1)
        await mgr.connect(ws2)

        assert len(mgr.active_connections) == 2
        assert ws1 in mgr.active_connections
        assert ws2 in mgr.active_connections
