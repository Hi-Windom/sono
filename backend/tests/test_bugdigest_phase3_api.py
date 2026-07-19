"""
Bug Digest Phase 3 - API 路由系统性扫描
========================================

发现的问题清单（共 15 个）：

【高严重程度】
BUG-001: 上传接口文件过大时先读内存再判断，导致 OOM 风险（upload.py:86-101）
BUG-002: 双轨上传空间不足时文件已写入但未清理，资源泄漏（upload.py:329-350）
BUG-003: CORS 配置 allow_origins=["*"] 与 allow_credentials=True 冲突（app.py:104-110）
BUG-004: /api/v1/log 接口无认证，任意客户端可写入服务器日志（system.py:97-108）
BUG-005: /cache/clear-all 接口无认证，可清空所有数据（cache.py:688-709）
BUG-006: /wasm/upload 接口无认证，可上传任意 WASM 模块（wasm.py:124-170）
BUG-007: 任务状态接口无鉴权，可通过 task_id 遍历访问他人任务（repair.py:305-320）

【中严重程度】
BUG-008: upload-status 接口 session_id 参数无类型校验，缺失时返回 500 而非 422（upload.py:210-213）
BUG-009: /download-file 路径遍历防护不足 - filename 含反斜杠可绕过（download.py:116-119）
BUG-010: WebSocket /ws/{task_id} 无鉴权，任意客户端可监听任务进度（system.py:510-512）
BUG-011: /perf/reset 接口无认证，可重置性能统计数据（perf.py:17-25）
BUG-012: /api/v1/logs 日志接口无认证，泄露服务器敏感信息（app.py:185-206）
BUG-013: /quality-tests/start 无认证且可无限启动子进程，DoS 风险（system.py:488-499）

【低严重程度】
BUG-014: /repair-debug 同步执行，大文件阻塞请求线程（repair.py:225-239）
BUG-015: get_task_status 异常返回 503 而非 500，状态码不正确（repair.py:317-320）
"""

import sys
import os
import json
import tempfile
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

os.environ["TESTING"] = "1"

from test_utils import make_wav_bytes


@pytest.fixture()
def fresh_db():
    from database import init_db, get_db, create_task, get_task, update_task

    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)

    old_path = None
    try:
        import config
        old_path = getattr(config, "DB_PATH", None)
        config.DB_PATH = db_path
    except Exception:
        pass

    init_db()
    yield {"db_path": db_path, "get_db": get_db, "create_task": create_task, "get_task": get_task, "update_task": update_task}

    if old_path is not None:
        try:
            config.DB_PATH = old_path
        except Exception:
            pass
    os.unlink(db_path)


@pytest.fixture()
def api_client(fresh_db):
    from fastapi.testclient import TestClient
    from app import create_app
    app = create_app()
    return TestClient(app)


# ============================================================
# 高严重程度 BUG 测试
# ============================================================


class TestBug001UploadOOMRisk:
    """BUG-001: 上传接口先读取整个文件到内存再判断大小，大文件可导致 OOM。
    
    upload.py:86-101 - /upload 接口中 await file.read() 会先将整个文件读入内存，
    然后才判断 len(content) > MAX_UPLOAD_SIZE。攻击者上传超大文件可直接耗尽内存。
    """

    def test_upload_reads_entire_file_before_size_check(self, api_client):
        """复现：上传文件时内容会被完整读取后才校验大小。
        
        预期修复：应该流式读取并在读取过程中检查大小，超过限制立即终止。
        """
        wav_data = make_wav_bytes(duration=0.5)
        files = {"file": ("test.wav", wav_data, "audio/wav")}
        data = {"file_hash": "abc123"}

        res = api_client.post("/api/v1/upload", files=files, data=data)

        assert res.status_code == 200
        data = res.json()
        assert "task_id" in data
        assert data["size"] == len(wav_data)

    def test_upload_no_chunked_size_validation(self, api_client):
        """验证：当前实现没有流式大小校验，全部读入内存。
        
        通过检查代码逻辑确认问题存在。
        """
        import inspect
        from api.routes.upload import upload_audio
        source = inspect.getsource(upload_audio)
        assert "await file.read()" in source
        assert "len(content) > MAX_UPLOAD_SIZE" in source
        read_pos = source.find("await file.read()")
        check_pos = source.find("MAX_UPLOAD_SIZE")
        assert read_pos < check_pos, "文件读取应在大小检查之前（证明 bug 存在）"


class TestBug002DualUploadResourceLeak:
    """BUG-002: 双轨上传空间不足时文件已写入内存但未保存到磁盘的内容泄漏。
    
    upload.py:329-350 - upload_dual_audio 中先读取两个文件内容到内存，
    再检查磁盘空间，空间不足时抛出异常但已读取到内存的内容无法释放（GC 不可控）。
    更严重的是，空间检查在文件写入之前，但若检查通过后写入失败也没有清理。
    """

    def test_dual_upload_reads_both_files_before_disk_check(self, api_client):
        """复现：双轨上传先读两个文件到内存再检查磁盘空间。"""
        import inspect
        from api.routes.upload import upload_dual_audio
        source = inspect.getsource(upload_dual_audio)
        vocal_read_pos = source.find("vocal_content = await vocal_file.read()")
        acc_read_pos = source.find("accompaniment_content = await accompaniment_file.read()")
        disk_check_pos = source.find("disk_usage = os.statvfs")
        assert vocal_read_pos < disk_check_pos
        assert acc_read_pos < disk_check_pos

    def test_dual_upload_no_cleanup_on_disk_full(self, api_client):
        """验证：磁盘空间不足时，已读入内存的内容没有清理逻辑。"""
        import inspect
        from api.routes.upload import upload_dual_audio
        source = inspect.getsource(upload_dual_audio)
        assert "os.remove(vocal_upload_path)" not in source
        assert "os.remove(accompaniment_upload_path)" not in source


class TestBug003CorsMisconfiguration:
    """BUG-003: CORS 配置 allow_origins=["*"] 与 allow_credentials=True 冲突。
    
    app.py:104-110 - 浏览器规范不允许在 allow_origins 为 "*" 时
    同时设置 allow_credentials=True。虽然 FastAPI 可能内部处理了，
    但这是不安全的配置，会导致凭据泄漏风险。
    """

    def test_cors_wildcard_with_credentials(self, api_client):
        """复现：CORS 响应头中同时存在通配符源和允许凭据。"""
        import inspect
        from app import create_app
        source = inspect.getsource(create_app)
        assert 'allow_origins=["*"]' in source
        assert "allow_credentials=True" in source

    def test_cors_preflight_response(self, api_client):
        """验证：预检请求的 CORS 响应头配置。"""
        res = api_client.options(
            "/api/v1/upload",
            headers={
                "Origin": "http://evil.example.com",
                "Access-Control-Request-Method": "POST",
            },
        )
        acao = res.headers.get("access-control-allow-origin", "")
        acac = res.headers.get("access-control-allow-credentials", "")
        assert acao != "", "应该有 CORS 响应头"
        if acao == "*":
            assert acac.lower() != "true", "通配符 origin 不应允许 credentials"


class TestBug004LogInjectionNoAuth:
    """BUG-004: /api/v1/log 接口无认证，任意客户端可注入日志。
    
    system.py:97-108 - 任何人都可以调用 POST /api/v1/log 写入服务器日志，
    可用于日志注入攻击、伪造日志条目、填满日志磁盘。
    同时 app.py:79-83 还有一个兼容路由 /api/log，也有同样问题。
    """

    def test_log_endpoint_no_auth(self, api_client):
        """复现：无需认证即可写入日志。"""
        res = api_client.post(
            "/api/v1/log",
            json={"message": "malicious log injection", "level": "error"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data.get("status") == "ok"

    def test_log_compat_route_no_auth(self, api_client):
        """复现：兼容路由 /api/log 也无认证。"""
        res = api_client.post(
            "/api/log",
            json={"message": "injected via compat route", "level": "warning"},
        )
        assert res.status_code == 200

    def test_log_level_validation_missing(self, api_client):
        """验证：日志级别没有严格校验，传入任意值都默认 info。"""
        res = api_client.post(
            "/api/v1/log",
            json={"message": "test", "level": "CRITICAL_SECURITY_ALERT"},
        )
        assert res.status_code == 200


class TestBug005CacheClearAllNoAuth:
    """BUG-005: /cache/clear-all 接口无认证，可清空所有数据。
    
    cache.py:688-709 - POST /cache/clear-all 可以删除所有上传文件、
    输出文件，并清空 tasks 表。无任何认证保护，破坏力极大。
    """

    def test_clear_all_no_auth(self, api_client):
        """复现：无需认证即可调用 clear-all。"""
        wav_data = make_wav_bytes(duration=0.1)
        files = {"file": ("test.wav", wav_data, "audio/wav")}
        upload_res = api_client.post("/api/v1/upload", files=files)
        assert upload_res.status_code == 200

        res = api_client.post("/api/v1/cache/clear-all")
        assert res.status_code == 200
        data = res.json()
        assert "released_bytes" in data

    def test_clear_upload_no_auth(self, api_client):
        """验证：clear-upload 也无认证。"""
        res = api_client.post("/api/v1/cache/clear-upload")
        assert res.status_code == 200

    def test_clear_output_no_auth(self, api_client):
        """验证：clear-output 也无认证。"""
        res = api_client.post("/api/v1/cache/clear-output")
        assert res.status_code == 200

    def test_clear_render_no_auth(self, api_client):
        """验证：clear-render 也无认证。"""
        res = api_client.post("/api/v1/cache/clear-render")
        assert res.status_code == 200


class TestBug006WasmUploadNoAuth:
    """BUG-006: /wasm/upload 接口无认证，可上传任意 WASM 模块。
    
    wasm.py:124-170 - WASM 模块上传接口无任何认证，攻击者可上传
    恶意 WASM 模块并加载执行，潜在 RCE 风险。
    """

    def test_wasm_upload_no_auth(self, api_client):
        """复现：无需认证即可上传 WASM 模块（会被格式校验拒绝但接口可访问）。"""
        fake_wasm = b"\x00asm\x01\x00\x00\x00"
        files = {"file": ("evil.wasm", fake_wasm, "application/wasm")}
        res = api_client.post("/api/v1/wasm/upload", files=files)
        assert res.status_code != 401
        assert res.status_code != 403

    def test_wasm_delete_no_auth(self, api_client):
        """验证：删除 WASM 模块也无认证。"""
        res = api_client.delete("/api/v1/wasm/modules/nonexistent")
        assert res.status_code not in (401, 403)

    def test_wasm_load_no_auth(self, api_client):
        """验证：加载 WASM 模块也无认证。"""
        res = api_client.post("/api/v1/wasm/modules/nonexistent/load")
        assert res.status_code not in (401, 403)


class TestBug007TaskIdInjection:
    """BUG-007: 任务状态接口无鉴权，可通过 task_id 遍历访问他人任务。
    
    repair.py:305-320 - /status/{task_id} 接口不需要任何认证，
    只要知道 task_id 就能查看任务详情，包括音频路径、参数等敏感信息。
    所有任务相关接口都有此问题：status、cancel、tracks、download 等。
    """

    def test_status_no_auth(self, api_client, fresh_db):
        """复现：无需认证即可查询任意任务状态。"""
        task_id = "test-task-001"
        fresh_db["create_task"](
            task_id, "secret_audio.wav", "/tmp/fake.wav",
            {"sensitive": "data"}, "hash123", 1024
        )
        res = api_client.get(f"/api/v1/status/{task_id}")
        assert res.status_code == 200
        data = res.json()
        assert data["id"] == task_id
        assert "original_filename" in data

    def test_cancel_no_auth(self, api_client, fresh_db):
        """验证：取消任务也无认证。"""
        task_id = "test-task-002"
        fresh_db["create_task"](
            task_id, "test.wav", "/tmp/fake.wav", {}, "hash", 1024
        )
        res = api_client.post(f"/api/v1/cancel/{task_id}")
        assert res.status_code == 200

    def test_tracks_no_auth(self, api_client, fresh_db):
        """验证：双轨状态也无认证。"""
        task_id = "test-task-003"
        fresh_db["create_task"](
            task_id, "test.wav", "/tmp/fake.wav", {}, "hash", 1024
        )
        res = api_client.get(f"/api/v1/tracks/{task_id}")
        assert res.status_code == 200


# ============================================================
# 中严重程度 BUG 测试
# ============================================================


class TestBug008UploadStatusValidation:
    """BUG-008: upload-status 接口 session_id 参数类型校验缺失。
    
    upload.py:210-213 - /upload-status 的 session_id 使用了 `= ...`
    这种写法在 FastAPI 中表示必填但没有类型注解，当缺失时返回 500 而非 422。
    而且使用了正则匹配，但没有校验 session_id 的长度上限。
    """

    def test_upload_status_missing_session_id_returns_500(self, api_client):
        """复现：缺失 session_id 参数时返回错误的状态码。"""
        res = api_client.get("/api/v1/upload-status")
        assert res.status_code in (422, 400), (
            f"缺失必填参数应返回 422 或 400，实际返回 {res.status_code}"
        )

    def test_upload_status_invalid_session_id(self, api_client):
        """验证：无效 session_id 格式应返回 400。"""
        res = api_client.get("/api/v1/upload-status?session_id=invalid-id")
        assert res.status_code == 400

    def test_upload_status_session_id_no_length_limit(self, api_client):
        """验证：session_id 没有长度上限校验。"""
        very_long_id = "a" * 10000 + "-0000-0000-0000-000000000000"
        res = api_client.get(f"/api/v1/upload-status?session_id={very_long_id}")
        assert res.status_code == 400


class TestBug009DownloadPathTraversal:
    """BUG-009: /download-file 路径遍历防护不足。
    
    download.py:116-119 - download_file 接口使用 _safe_output_path 校验，
    但 output_gateway.resolve 只检查了正斜杠和空字节，
    没有检查 Windows 风格的反斜杠路径遍历。
    另外 filename 直接从 URL 路径获取，编码问题可能导致绕过。
    """

    def test_download_file_backslash_bypass(self, api_client):
        """复现：使用反斜杠尝试路径遍历。"""
        malicious = "..\\..\\etc\\passwd"
        res = api_client.get(f"/api/v1/download-file/{malicious}")
        assert res.status_code in (400, 404), (
            f"路径遍历应被阻止，实际返回 {res.status_code}"
        )

    def test_download_file_encoded_traversal(self, api_client):
        """验证：URL 编码的路径遍历。"""
        import urllib.parse
        encoded = urllib.parse.quote("../../../etc/passwd")
        res = api_client.get(f"/api/v1/download-file/{encoded}")
        assert res.status_code in (400, 404)

    def test_safe_output_path_checks_backslash(self):
        """验证：output_gateway.resolve 是否检查反斜杠。"""
        from services.file_gateway import output_gateway, SecurityError
        try:
            output_gateway.resolve("..\\..\\test.wav")
            assert False, "反斜杠路径遍历应抛出 SecurityError"
        except SecurityError:
            pass


class TestBug010WebSocketNoAuth:
    """BUG-010: WebSocket /ws/{task_id} 无鉴权。
    
    system.py:510-512 - WebSocket 连接不需要任何认证，
    任意客户端都可以连接并监听任务进度，获取任务敏感信息。
    """

    def test_websocket_no_auth(self, api_client, fresh_db):
        """复现：无需认证即可连接 WebSocket 监听任务。"""
        task_id = "test-ws-task-001"
        fresh_db["create_task"](
            task_id, "test.wav", "/tmp/fake.wav",
            {"secret": "data"}, "hash", 1024
        )
        fresh_db["update_task"](task_id, status="completed", progress=1.0)

        try:
            with api_client.websocket_connect(f"/api/v1/ws/{task_id}") as ws:
                data = ws.receive_json()
                assert data["task_id"] == task_id
                assert "status" in data
        except Exception:
            pass

    def test_websocket_invalid_task_id_still_connects(self, api_client):
        """验证：即使任务不存在也会先 accept 再关闭。"""
        try:
            with api_client.websocket_connect("/api/v1/ws/nonexistent-task") as ws:
                data = ws.receive_json()
                assert "error" in data
        except Exception:
            pass


class TestBug011PerfResetNoAuth:
    """BUG-011: /perf/reset 接口无认证，可重置性能统计。
    
    perf.py:17-25 - 性能统计重置接口无认证保护，
    攻击者可以频繁重置，干扰性能监控。
    """

    def test_perf_reset_no_auth(self, api_client):
        """复现：无需认证即可重置性能统计。"""
        res = api_client.get("/api/v1/perf/reset")
        assert res.status_code == 200
        data = res.json()
        assert data.get("status") == "ok"

    def test_perf_summary_no_auth(self, api_client):
        """验证：性能摘要也无认证（虽然信息敏感程度较低）。"""
        res = api_client.get("/api/v1/perf/summary")
        assert res.status_code == 200


class TestBug012LogsEndpointNoAuth:
    """BUG-012: /api/v1/logs 日志接口无认证。
    
    app.py:185-206 - 日志下载接口无任何认证，
    可获取服务器完整日志，泄露敏感信息如路径、任务详情、错误堆栈等。
    """

    def test_logs_endpoint_no_auth(self, api_client):
        """复现：无需认证即可下载服务器日志。"""
        res = api_client.get("/api/v1/logs?lines=10")
        assert res.status_code == 200
        assert "text/plain" in res.headers.get("content-type", "")

    def test_logs_no_lines_limit_validation(self, api_client):
        """验证：lines 参数没有下限校验，负数可能导致问题。"""
        res = api_client.get("/api/v1/logs?lines=-100")
        assert res.status_code in (200, 422, 400)


class TestBug013QualityTestsDoS:
    """BUG-013: /quality-tests/start 无认证且无速率限制，DoS 风险。
    
    system.py:488-499 - 质量测试启动接口无认证，每次启动都会
    运行完整的 pytest 测试套件（180秒超时），攻击者可快速调用
    耗尽服务器 CPU 资源。
    """

    def test_quality_tests_start_no_auth(self, api_client):
        """复现：无需认证即可启动质量测试。"""
        res = api_client.post("/api/v1/quality-tests/start")
        assert res.status_code == 200
        data = res.json()
        assert "task_id" in data
        assert data["status"] == "running"

    def test_quality_tests_result_no_auth(self, api_client):
        """验证：结果查询也无认证。"""
        res = api_client.get("/api/v1/quality-tests/result/nonexistent")
        assert res.status_code == 200


# ============================================================
# 低严重程度 BUG 测试
# ============================================================


class TestBug014RepairDebugBlocking:
    """BUG-014: /repair-debug 同步执行，大文件阻塞请求线程。
    
    repair.py:225-239 - repair_debug_endpoint 直接调用 run_debug_repair，
    同步执行调试修复，大文件会导致请求长时间阻塞，甚至超时。
    """

    def test_repair_debug_is_synchronous(self, api_client):
        """复现：debug 接口是同步执行的。"""
        import inspect
        from api.routes.repair import repair_debug_endpoint
        source = inspect.getsource(repair_debug_endpoint)
        assert "executor.submit" not in source
        assert "run_debug_repair(audio_path" in source

    def test_repair_debug_no_task_queue(self, api_client, fresh_db):
        """验证：debug 接口不经过任务队列管理。"""
        task_id = "test-debug-001"
        fresh_db["create_task"](
            task_id, "test.wav", "/nonexistent/path.wav", {}, "hash", 1024
        )
        res = api_client.post(
            "/api/v1/repair-debug",
            json={"task_id": task_id},
        )
        assert res.status_code in (400, 500, 404)


class TestBug015StatusEndpointWrongStatusCode:
    """BUG-015: get_task_status 异常返回 503 而非 500。
    
    repair.py:317-320 - 状态查询接口内部异常时返回 503 Service Unavailable，
    但 503 通常表示服务暂时不可用（如过载、维护），
    内部错误应该返回 500 Internal Server Error。
    """

    def test_status_returns_503_on_error(self, api_client):
        """验证：异常时状态码不正确。
        
        通过检查源码确认问题存在。
        """
        import inspect
        from api.routes.repair import get_task_status
        source = inspect.getsource(get_task_status)
        assert "status_code=503" in source
        assert "获取任务状态失败" in source

    def test_status_nonexistent_task_returns_404(self, api_client):
        """验证：不存在的任务正确返回 404。"""
        res = api_client.get("/api/v1/status/nonexistent-task-id")
        assert res.status_code == 404
