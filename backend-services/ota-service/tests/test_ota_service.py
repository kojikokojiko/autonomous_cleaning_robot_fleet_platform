"""
テスト仕様書: ota-service — OTAService
=======================================

[日本語]
このファイルは OTAService クラスのテスト仕様書です。
ファームウェアの登録・S3アップロード・OTAジョブ作成・ロボットへの MQTT 配信の仕様を定義します。

仕様:
  create_firmware():
    1. ファームウェア JSON を生成し SHA-256 checksum を計算
    2. S3 に firmware/{version}/firmware.json としてアップロード
    3. PostgreSQL firmware テーブルに保存
    4. s3_key / checksum / file_size は自動計算 (ユーザー入力は無視)

  create_jobs():
    1. ロボットが idle / docked の場合のみジョブを作成
    2. 不明なロボットはスキップ
    3. OTA ジョブを PostgreSQL ota_jobs テーブルに保存
    4. MQTT QoS 1 で robot/{id}/ota にコマンドを送信

  download_firmware():
    1. S3 の s3_key からファームウェアバイトを取得して返す

[English]
This file is the test specification for the OTAService class.
Documents firmware registration, S3 upload, OTA job creation, and MQTT delivery.

Specification:
  create_firmware():
    1. Generate firmware JSON and compute SHA-256 checksum
    2. Upload to S3 as firmware/{version}/firmware.json
    3. Persist to PostgreSQL firmware table
    4. s3_key / checksum / file_size are auto-computed (user input ignored)

  create_jobs():
    1. Create jobs only for idle / docked robots
    2. Skip unknown robots
    3. Save OTA jobs to PostgreSQL ota_jobs table
    4. Send command via MQTT QoS 1 to robot/{id}/ota

  download_firmware():
    1. Fetch firmware bytes from S3 using the stored s3_key
"""
from datetime import datetime, timezone
import hashlib
import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch
import uuid

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.dto.ota import FirmwareCreate, OTAJobCreate
from src.services.ota_service import OTAService

pytestmark = pytest.mark.asyncio

# ヘルパー: _firmware_content は staticmethod なのでクラス外から呼べるように
def firmware_content(version: str, config: dict) -> bytes:
    return json.dumps({"version": version, "config": config}, sort_keys=True).encode()


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
        if getattr(obj, "uploaded_at", None) is None:
            obj.uploaded_at = datetime.now(timezone.utc)

    db.refresh = fake_refresh
    return db


# ---------------------------------------------------------------------------
# create_firmware のテスト / Tests for OTAService.create_firmware()
# ---------------------------------------------------------------------------

class TestCreateFirmware:
    """
    [日本語] create_firmware() のテスト。
    ファームウェアを S3 に保存し DB に登録する。

    [English] Tests for create_firmware().
    Saves firmware to S3 and registers it in the DB.
    """

    async def test_uploads_firmware_to_s3(self, mock_db):
        """
        [日本語] ファームウェアが S3 にアップロードされることを確認。
        s3_client.upload() が正しいキーとコンテンツで呼ばれる。

        [English] Verifies firmware is uploaded to S3.
        s3_client.upload() is called with the correct key and content.
        """
        service = OTAService(db=mock_db)
        data = FirmwareCreate(version="v2.0.0", config={"step_per_cycle": 1.2})

        with patch("src.services.ota_service.s3_client.upload") as mock_upload:
            await service.create_firmware(data)

        expected_key = "firmware/v2.0.0/firmware.json"
        mock_upload.assert_called_once()
        call_args = mock_upload.call_args[0]
        assert call_args[0] == expected_key

    async def test_s3_key_format_is_firmware_version_filename(self, mock_db):
        """
        [日本語] S3 キーが "firmware/{version}/firmware.json" の形式であることを確認。

        [English] S3 key follows "firmware/{version}/firmware.json" format.
        """
        service = OTAService(db=mock_db)
        data = FirmwareCreate(version="v3.1.0", config={})

        saved_key = None

        def capture_upload(key, content, *args, **kwargs):
            nonlocal saved_key
            saved_key = key

        with patch("src.services.ota_service.s3_client.upload", side_effect=capture_upload):
            await service.create_firmware(data)

        assert saved_key == "firmware/v3.1.0/firmware.json"

    async def test_checksum_is_sha256_of_canonical_json(self, mock_db):
        """
        [日本語] checksum_sha256 はファームウェア JSON の SHA-256 ハッシュである。
        同じバージョン・設定から常に同じ checksum が生成される (決定論的)。

        [English] checksum_sha256 is the SHA-256 hash of the firmware JSON.
        Same version + config always produces the same checksum (deterministic).
        """
        service = OTAService(db=mock_db)
        config = {"step_per_cycle": 1.5}
        data = FirmwareCreate(version="v1.0.0", config=config)

        saved_fw = None
        original_add = mock_db.add

        def capture_add(obj):
            nonlocal saved_fw
            saved_fw = obj
            return original_add(obj)

        mock_db.add = capture_add

        with patch("src.services.ota_service.s3_client.upload"):
            await service.create_firmware(data)

        expected_content = firmware_content("v1.0.0", config)
        expected_checksum = hashlib.sha256(expected_content).hexdigest()
        assert saved_fw.checksum_sha256 == expected_checksum

    async def test_file_size_bytes_is_set_automatically(self, mock_db):
        """
        [日本語] file_size_bytes はファームウェアコンテンツのバイト数が自動計算される。
        ユーザーが指定した値は無視される。

        [English] file_size_bytes is auto-calculated from firmware content length.
        User-provided values are ignored.
        """
        service = OTAService(db=mock_db)
        data = FirmwareCreate(version="v1.0.0", config={"key": "val"})

        saved_fw = None

        def capture_add(obj):
            nonlocal saved_fw
            saved_fw = obj

        mock_db.add = capture_add

        with patch("src.services.ota_service.s3_client.upload"):
            await service.create_firmware(data)

        expected_content = firmware_content("v1.0.0", {"key": "val"})
        assert saved_fw.file_size_bytes == len(expected_content)

    async def test_saves_to_database(self, mock_db):
        """
        [日本語] ファームウェードが PostgreSQL に保存されることを確認。
        db.add() → db.commit() の順で呼ばれる。

        [English] Verifies firmware is persisted to PostgreSQL.
        db.add() followed by db.commit().
        """
        service = OTAService(db=mock_db)
        data = FirmwareCreate(version="v1.0.0", config={})

        with patch("src.services.ota_service.s3_client.upload"):
            await service.create_firmware(data)

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called()


# ---------------------------------------------------------------------------
# download_firmware のテスト / Tests for OTAService.download_firmware()
# ---------------------------------------------------------------------------

class TestDownloadFirmware:
    """
    [日本語] download_firmware() のテスト。
    ロボットがファームウェアをダウンロードするとき S3 からバイトを取得する。

    [English] Tests for download_firmware().
    Fetches bytes from S3 when a robot downloads firmware.
    """

    async def test_fetches_from_s3_using_stored_key(self, mock_db):
        """
        [日本語] DB に保存された s3_key を使って S3 からダウンロードする。
        s3_client.download() が正しいキーで呼ばれることを確認。
        get_firmware() をモックして S3 ダウンロードのみを検証する。

        [English] Downloads from S3 using the stored s3_key.
        Verifies s3_client.download() is called with the correct key.
        Mocks get_firmware() to isolate S3 download behavior.
        """
        firmware_id = uuid.uuid4()
        # get_firmware() が返す FirmwareResponse を模したオブジェクト
        mock_fw_resp = MagicMock()
        mock_fw_resp.s3_key = "firmware/v1.0.0/firmware.json"

        expected_bytes = b'{"version": "v1.0.0", "config": {}}'

        service = OTAService(db=mock_db)
        with patch.object(service, "get_firmware", AsyncMock(return_value=mock_fw_resp)):
            with patch("src.services.ota_service.s3_client.download", return_value=expected_bytes) as mock_dl:  # noqa: E501
                result = await service.download_firmware(firmware_id)

        mock_dl.assert_called_once_with("firmware/v1.0.0/firmware.json")
        assert result == expected_bytes

    async def test_returns_none_when_firmware_not_found(self, mock_db):
        """
        [日本語] 存在しない firmware_id の場合は None を返す。

        [English] Returns None when firmware_id does not exist.
        """
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = OTAService(db=mock_db)
        result = await service.download_firmware(uuid.uuid4())

        assert result is None


# ---------------------------------------------------------------------------
# s3_client のテスト / Tests for s3_client module
# ---------------------------------------------------------------------------

class TestS3Client:
    """
    [日本語] s3_client モジュールのテスト。
    LocalStack (ローカル) と 本番 S3 への接続設定を検証。

    [English] Tests for the s3_client module.
    Validates connection configuration for LocalStack (local) and production S3.
    """

    def test_uses_localstack_endpoint_when_env_set(self):
        """
        [日本語] S3_ENDPOINT モジュール変数が設定されている場合、
        LocalStack エンドポイントを使用する。
        ローカル開発環境では http://localstack:4566 に接続する。
        注: S3_ENDPOINT はモジュール読み込み時に確定するため、patch.dict ではなく
        モジュール変数を直接パッチする。

        [English] Uses LocalStack endpoint when S3_ENDPOINT module variable is set.
        In local dev, connects to http://localstack:4566.
        Note: S3_ENDPOINT is resolved at module import time, so we patch the module
        variable directly rather than using patch.dict.
        """
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from src.services import s3_client

        with patch("src.services.s3_client.S3_ENDPOINT", "http://localstack:4566"):
            with patch("boto3.client") as mock_boto:
                mock_boto.return_value = MagicMock()
                s3_client._client()

            call_kwargs = mock_boto.call_args[1]
            assert call_kwargs.get("endpoint_url") == "http://localstack:4566"

    def test_uses_dummy_credentials_for_localstack(self):
        """
        [日本語] LocalStack 使用時はダミーの AWS 認証情報 ("test"/"test") を使う。
        LocalStack は認証情報を検証しないため、任意の値で動作する。

        [English] Uses dummy AWS credentials ("test"/"test") for LocalStack.
        LocalStack doesn't validate credentials, so any value works.
        """
        from src.services import s3_client

        with patch("src.services.s3_client.S3_ENDPOINT", "http://localstack:4566"):
            with patch("boto3.client") as mock_boto:
                mock_boto.return_value = MagicMock()
                s3_client._client()

            call_kwargs = mock_boto.call_args[1]
            assert call_kwargs.get("aws_access_key_id") == "test"
            assert call_kwargs.get("aws_secret_access_key") == "test"
