import urllib.request
import urllib.error
import time
import os
import json
import mimetypes

BASE_URL = "http://localhost:8000/api/v1"
TEST_FILE = "/workspace/scripts/test_10mb.mp3"

def http_get(url):
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as resp:
        return resp.status, json.loads(resp.read().decode())

def http_post_json(url, data):
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode(),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())

def upload_dual(filepath):
    boundary = "----TestBoundary123456789"
    filename = os.path.basename(filepath)
    mimetype = mimetypes.guess_type(filename)[0] or "audio/mpeg"
    
    with open(filepath, "rb") as f:
        file_data = f.read()
    
    parts = []
    
    parts.append(f"--{boundary}\r\n".encode())
    parts.append(f'Content-Disposition: form-data; name="vocal_file"; filename="vocal_{filename}"\r\n'.encode())
    parts.append(f"Content-Type: {mimetype}\r\n\r\n".encode())
    parts.append(file_data)
    parts.append(f"\r\n--{boundary}\r\n".encode())
    parts.append(f'Content-Disposition: form-data; name="accompaniment_file"; filename="acc_{filename}"\r\n'.encode())
    parts.append(f"Content-Type: {mimetype}\r\n\r\n".encode())
    parts.append(file_data)
    parts.append(f"\r\n--{boundary}--\r\n".encode())
    
    body = b"".join(parts)
    
    req = urllib.request.Request(
        f"{BASE_URL}/upload-dual",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST"
    )
    
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())

def test_repair_flow():
    print("=" * 60)
    print("10MB MP3 + v3.2 双轨修复全流程测试 (后端 API)")
    print("=" * 60)
    
    file_size = os.path.getsize(TEST_FILE)
    print(f"\n测试文件: {TEST_FILE}")
    print(f"文件大小: {file_size / 1024 / 1024:.2f} MB")
    
    # 1. 双轨上传
    print("\n1. 双轨上传 (人声+伴奏)...")
    status, upload_data = upload_dual(TEST_FILE)
    
    if status != 200:
        print(f"   ❌ 上传失败: {status}")
        print(f"   {upload_data}")
        return False
    
    main_task_id = upload_data["task_id"]
    vocal_task_id = upload_data["vocal_task_id"]
    accompaniment_task_id = upload_data["accompaniment_task_id"]
    print(f"   ✅ 双轨上传成功")
    print(f"   主任务: {main_task_id}")
    print(f"   人声任务: {vocal_task_id}")
    print(f"   伴奏任务: {accompaniment_task_id}")
    
    # 2. 发起双轨修复 (v3.2)
    print("\n2. 发起 v3.2 双轨修复...")
    
    repair_params = {
        "algorithm_version": "v3.2",
        "sample_rate": 44100,
        "bit_depth": 16,
        "mastering_mode": "standard",
        "output_gain": 0,
        "processing_mode": "dual",
    }
    
    status, resp_data = http_post_json(f"{BASE_URL}/repair-dual", {
        "task_id": main_task_id,
        "vocal_task_id": vocal_task_id,
        "accompaniment_task_id": accompaniment_task_id,
        "params": repair_params,
        "mix_ratio": 0.5,
    })
    print(f"   响应状态: {status}")
    
    if status not in (200, 202):
        print(f"   ❌ 修复提交失败: {resp_data}")
        return False
    
    print(f"   ✅ 修复任务已提交")
    
    # 3. 轮询修复状态
    print("\n3. 等待修复完成...")
    repair_start = time.time()
    max_wait = 600
    
    while time.time() - repair_start < max_wait:
        try:
            status, status_data = http_get(f"{BASE_URL}/status/{main_task_id}")
        except Exception as e:
            print(f"   ⚠️  获取状态失败: {e}")
            time.sleep(2)
            continue
        
        task_status = status_data.get("status", "unknown")
        progress = status_data.get("progress", 0)
        step = status_data.get("step", "")
        elapsed = time.time() - repair_start
        
        print(f"   [{elapsed:6.1f}s] {task_status} - {progress*100:5.1f}% - {step}")
        
        if task_status in ("completed", "error", "failed", "cancelled"):
            if task_status == "completed":
                print(f"\n   ✅ 修复完成！总耗时: {elapsed:.1f}s")
                
                repair_result = status_data.get("repair_result", {})
                print(f"\n   修复结果摘要:")
                if "issues_found" in repair_result:
                    print(f"     发现问题: {repair_result['issues_found']}")
                if "waveform_peaks" in repair_result:
                    print(f"     输出波形: 有")
                
                output_path = status_data.get("output_path")
                if output_path and os.path.exists(output_path):
                    output_size = os.path.getsize(output_path)
                    print(f"     输出文件: {output_size / 1024 / 1024:.2f} MB")
                else:
                    print(f"     输出路径: {output_path}")
                
                return True
            else:
                error = status_data.get("error", "未知错误")
                print(f"\n   ❌ 修复失败: {error}")
                return False
        
        time.sleep(3)
    
    print(f"\n   ⏰ 修复超时 ({max_wait}s)")
    return False


if __name__ == "__main__":
    success = test_repair_flow()
    print("\n" + "=" * 60)
    print(f"测试结果: {'✅ 通过' if success else '❌ 失败'}")
    print("=" * 60)
    exit(0 if success else 1)
