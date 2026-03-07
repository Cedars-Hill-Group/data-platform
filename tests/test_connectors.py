"""Tests for data_platform.connectors."""

from __future__ import annotations

import pytest

from data_platform.config import DatabaseConfig, ObjectStorageConfig, WarehouseConfig
from data_platform.connectors.database import DatabaseConnector
from data_platform.connectors.object_storage import ObjectStorageConnector
from data_platform.connectors.warehouse import WarehouseConnector


class TestDatabaseConnector:
    def _make_connector(self) -> DatabaseConnector:
        cfg = DatabaseConfig(url="sqlite:///:memory:", echo=False)
        return DatabaseConnector(cfg)

    def test_connect_disconnect(self):
        conn = self._make_connector()
        assert not conn.is_connected()
        conn.connect()
        assert conn.is_connected()
        conn.disconnect()
        assert not conn.is_connected()

    def test_context_manager(self):
        conn = self._make_connector()
        with conn:
            assert conn.is_connected()
        assert not conn.is_connected()

    def test_execute_ddl_and_query(self):
        with self._make_connector() as conn:
            conn.execute("CREATE TABLE test (id INTEGER, name TEXT)")
            conn.execute("INSERT INTO test VALUES (:id, :name)", {"id": 1, "name": "Alice"})
            rows = conn.execute("SELECT * FROM test")
            assert len(rows) == 1
            assert rows[0]["name"] == "Alice"

    def test_execute_requires_connection(self):
        conn = self._make_connector()
        with pytest.raises(RuntimeError, match="Not connected"):
            conn.execute("SELECT 1")

    def test_engine_property_requires_connection(self):
        conn = self._make_connector()
        with pytest.raises(RuntimeError, match="Not connected"):
            _ = conn.engine

    def test_session_requires_connection(self):
        conn = self._make_connector()
        with pytest.raises(RuntimeError, match="Not connected"):
            conn.session()

    def test_session_returns_session(self):
        with self._make_connector() as conn:
            session = conn.session()
            assert session is not None
            session.close()


class TestWarehouseConnector:
    def test_none_type_no_op(self):
        cfg = WarehouseConfig(type="none")
        conn = WarehouseConnector(cfg)
        conn.connect()
        assert not conn.is_connected()  # type=none → engine stays None
        conn.disconnect()

    def test_unsupported_type_raises(self):
        cfg = WarehouseConfig(type="oracle")
        conn = WarehouseConnector(cfg)
        with pytest.raises(ValueError, match="Unsupported warehouse type"):
            conn.connect()

    def test_bigquery_missing_config_raises(self):
        cfg = WarehouseConfig(type="bigquery")
        conn = WarehouseConnector(cfg)
        with pytest.raises((ValueError, ImportError)):
            conn.connect()

    def test_execute_requires_connection(self):
        cfg = WarehouseConfig(type="none")
        conn = WarehouseConnector(cfg)
        conn.connect()
        with pytest.raises(RuntimeError, match="not connected"):
            conn.execute("SELECT 1")


class TestObjectStorageConnector:
    def test_local_backend(self, tmp_path):
        cfg = ObjectStorageConfig(type="local", root_path=tmp_path)
        conn = ObjectStorageConnector(cfg)
        conn.connect()
        assert conn.is_connected()
        conn.disconnect()
        assert not conn.is_connected()

    def test_none_backend(self):
        cfg = ObjectStorageConfig(type="none")
        conn = ObjectStorageConnector(cfg)
        conn.connect()
        assert conn.is_connected()  # none still marks connected=True

    def test_unsupported_type_raises(self):
        cfg = ObjectStorageConfig(type="ftp")
        conn = ObjectStorageConnector(cfg)
        with pytest.raises(ValueError, match="Unsupported"):
            conn.connect()

    def test_execute_not_implemented(self):
        cfg = ObjectStorageConfig(type="none")
        conn = ObjectStorageConnector(cfg)
        conn.connect()
        with pytest.raises(NotImplementedError):
            conn.execute("anything")

    def test_local_upload_download(self, tmp_path):
        cfg = ObjectStorageConfig(type="local", root_path=tmp_path / "store")
        conn = ObjectStorageConnector(cfg)
        conn.connect()

        src = tmp_path / "hello.txt"
        src.write_text("hello world")

        conn.upload(src, "subdir/hello.txt")
        dest = tmp_path / "out" / "hello.txt"
        conn.download("subdir/hello.txt", dest)
        assert dest.read_text() == "hello world"

    def test_local_list_objects(self, tmp_path):
        cfg = ObjectStorageConfig(type="local", root_path=tmp_path / "store")
        conn = ObjectStorageConnector(cfg)
        conn.connect()

        for name in ["a.txt", "b.txt"]:
            f = tmp_path / name
            f.write_text("data")
            conn.upload(f, name)

        objects = conn.list_objects()
        assert "a.txt" in objects
        assert "b.txt" in objects
