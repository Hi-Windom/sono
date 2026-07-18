import sys
import os
import pytest
import threading
import tempfile
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.file_gateway import SafeFileGateway, SecurityError


@pytest.fixture
def gateway():
    tmp_dir = tempfile.mkdtemp()
    gw = SafeFileGateway(tmp_dir)
    yield gw
    shutil.rmtree(tmp_dir, ignore_errors=True)


class TestSecurityError:
    def test_security_error_inherits_value_error(self):
        assert issubclass(SecurityError, ValueError)

    def test_security_error_can_be_raised(self):
        with pytest.raises(SecurityError):
            raise SecurityError("test")


class TestResolve:
    def test_normal_filename_resolves(self, gateway):
        result = gateway.resolve("test.txt")
        assert result.endswith("test.txt")
        assert gateway.base_dir in result

    def test_path_with_directory_rejected(self, gateway):
        with pytest.raises(SecurityError):
            gateway.resolve("subdir/test.txt")

    def test_path_traversal_dot_dot_rejected(self, gateway):
        with pytest.raises(SecurityError):
            gateway.resolve("../etc/passwd")

    def test_path_traversal_absolute_rejected(self, gateway):
        with pytest.raises(SecurityError):
            gateway.resolve("/etc/passwd")

    def test_empty_filename_rejected(self, gateway):
        with pytest.raises(SecurityError):
            gateway.resolve("")

    def test_dot_filename_rejected(self, gateway):
        with pytest.raises(SecurityError):
            gateway.resolve(".")

    def test_double_dot_rejected(self, gateway):
        with pytest.raises(SecurityError):
            gateway.resolve("..")

    def test_filename_with_backslash_rejected(self, gateway):
        with pytest.raises(SecurityError):
            gateway.resolve("subdir\\test.txt")


class TestExists:
    def test_file_does_not_exist(self, gateway):
        assert not gateway.exists("nonexistent.txt")

    def test_file_exists_after_write(self, gateway):
        gateway.safe_write("test.txt", b"hello")
        assert gateway.exists("test.txt")

    def test_path_traversal_returns_false(self, gateway):
        assert not gateway.exists("../etc/passwd")


class TestSafeWrite:
    def test_write_creates_file(self, gateway):
        gateway.safe_write("test.txt", b"hello world")
        assert gateway.exists("test.txt")
        assert gateway.get_size("test.txt") == len(b"hello world")

    def test_write_overwrites_existing(self, gateway):
        gateway.safe_write("test.txt", b"first")
        gateway.safe_write("test.txt", b"second")
        with open(gateway.resolve("test.txt"), "rb") as f:
            assert f.read() == b"second"

    def test_write_uses_atomic_rename(self, gateway):
        gateway.safe_write("test.txt", b"data")
        tmp_path = gateway.resolve("test.txt") + ".tmp"
        assert not os.path.exists(tmp_path)


class TestSafeRename:
    def test_rename_file(self, gateway):
        gateway.safe_write("old.txt", b"rename me")
        gateway.safe_rename("old.txt", "new.txt")
        assert not gateway.exists("old.txt")
        assert gateway.exists("new.txt")
        with open(gateway.resolve("new.txt"), "rb") as f:
            assert f.read() == b"rename me"

    def test_rename_nonexistent_raises(self, gateway):
        with pytest.raises(FileNotFoundError):
            gateway.safe_rename("nonexistent.txt", "target.txt")

    def test_rename_with_path_traversal_rejected(self, gateway):
        gateway.safe_write("test.txt", b"data")
        with pytest.raises(SecurityError):
            gateway.safe_rename("test.txt", "../target.txt")


class TestSafeDelete:
    def test_delete_existing_file(self, gateway):
        gateway.safe_write("test.txt", b"delete me")
        assert gateway.exists("test.txt")
        assert gateway.safe_delete("test.txt")
        assert not gateway.exists("test.txt")

    def test_delete_nonexistent_returns_false(self, gateway):
        assert not gateway.safe_delete("nonexistent.txt")

    def test_delete_path_traversal_returns_false(self, gateway):
        assert not gateway.safe_delete("../etc/passwd")


class TestGetSize:
    def test_get_size_of_existing_file(self, gateway):
        data = b"hello world"
        gateway.safe_write("test.txt", data)
        assert gateway.get_size("test.txt") == len(data)

    def test_get_size_nonexistent_raises(self, gateway):
        with pytest.raises(FileNotFoundError):
            gateway.get_size("nonexistent.txt")


class TestListFiles:
    def test_list_empty_dir(self, gateway):
        assert gateway.list_files() == []

    def test_list_multiple_files(self, gateway):
        gateway.safe_write("a.txt", b"a")
        gateway.safe_write("b.txt", b"bb")
        gateway.safe_write("c.txt", b"ccc")
        files = gateway.list_files()
        assert sorted(files) == ["a.txt", "b.txt", "c.txt"]

    def test_list_only_files_not_dirs(self, gateway):
        gateway.safe_write("file.txt", b"data")
        subdir = os.path.join(gateway.base_dir, "subdir")
        os.makedirs(subdir)
        files = gateway.list_files()
        assert files == ["file.txt"]


class TestGetDirSize:
    def test_empty_dir_size_zero(self, gateway):
        assert gateway.get_dir_size() == 0

    def test_single_file_size(self, gateway):
        gateway.safe_write("test.txt", b"12345")
        assert gateway.get_dir_size() == 5

    def test_multiple_files_total_size(self, gateway):
        gateway.safe_write("a.txt", b"123")
        gateway.safe_write("b.txt", b"4567")
        assert gateway.get_dir_size() == 3 + 4


class TestFileLock:
    def test_get_lock_returns_lock(self, gateway):
        lock = gateway.get_lock("test.txt")
        assert hasattr(lock, "acquire")
        assert hasattr(lock, "release")
        assert callable(lock.acquire)
        assert callable(lock.release)

    def test_same_file_same_lock(self, gateway):
        lock1 = gateway.get_lock("test.txt")
        lock2 = gateway.get_lock("test.txt")
        assert lock1 is lock2

    def test_different_files_different_locks(self, gateway):
        lock1 = gateway.get_lock("a.txt")
        lock2 = gateway.get_lock("b.txt")
        assert lock1 is not lock2


class TestConcurrentWrite:
    def test_concurrent_writes_same_file(self, gateway):
        num_threads = 10
        writes_per_thread = 100

        def writer(thread_id):
            for i in range(writes_per_thread):
                data = f"thread-{thread_id}-{i}".encode()
                gateway.safe_write("shared.txt", data)

        threads = []
        for t in range(num_threads):
            th = threading.Thread(target=writer, args=(t,))
            threads.append(th)
            th.start()

        for th in threads:
            th.join()

        assert gateway.exists("shared.txt")
        with open(gateway.resolve("shared.txt"), "rb") as f:
            content = f.read()
        assert len(content) > 0

    def test_concurrent_writes_different_files(self, gateway):
        num_threads = 10

        def writer(thread_id):
            filename = f"file_{thread_id}.txt"
            data = f"data from thread {thread_id}".encode()
            gateway.safe_write(filename, data)

        threads = []
        for t in range(num_threads):
            th = threading.Thread(target=writer, args=(t,))
            threads.append(th)
            th.start()

        for th in threads:
            th.join()

        files = gateway.list_files()
        assert len(files) == num_threads


class TestLockLRU:
    def test_lock_eviction_after_max(self, gateway):
        gateway._MAX_LOCKS = 10
        for i in range(15):
            gateway.get_lock(f"file_{i}.txt")
        assert len(gateway._locks) <= 10

    def test_lru_order_maintained(self, gateway):
        gateway._MAX_LOCKS = 5
        for i in range(5):
            gateway.get_lock(f"file_{i}.txt")
        gateway.get_lock("file_0.txt")
        gateway.get_lock("file_6.txt")
        first_key = next(iter(gateway._locks))
        assert first_key == "file_2.txt"


class TestGlobalGateways:
    def test_output_gateway_exists(self):
        from services.file_gateway import output_gateway
        assert hasattr(output_gateway, "base_dir")

    def test_upload_gateway_exists(self):
        from services.file_gateway import upload_gateway
        assert hasattr(upload_gateway, "base_dir")

    def test_output_gateway_points_to_output_dir(self):
        from services.file_gateway import output_gateway, get_output_gateway
        gw = get_output_gateway()
        assert "outputs" in gw.base_dir

    def test_upload_gateway_points_to_upload_dir(self):
        from services.file_gateway import upload_gateway, get_upload_gateway
        gw = get_upload_gateway()
        assert "uploads" in gw.base_dir
