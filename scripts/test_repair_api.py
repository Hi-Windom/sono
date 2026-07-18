import urllib.request
import urllib.parse
import urllib.error
import time
import os
import json

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

def http_post_file(url, file_path, field_name="file"):
    import mimetypes
    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    
    filename = os.path.basename(file_path)
    mimetype = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    
    with open(file_path, "rb") as f:
        file_data = f.read()
    
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'
        f"Content-Type: {mimetype}\r\n"
        "\r\n"
    ).encode() + file_data + f"\r\n--{boundary}--\r\n".encode()
    
    req = urllib.request.Request(
        url,
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
    print("10MB MP3 修复全流程测试 (后端 API)")
    print("=" * 60)
    
    file_size = os.path.getsize(TEST_FILE)
    print(f"\n测试文件: {TEST_FILE}")
    print(f"文件大小: {file_size / 1024 / 1024:.2f} MB")
    
    # 1. 上传文件
    print("\n1. 上传文件...")
    start_time = time.time()
    
    status, upload_data = http_post_file(f"{BASE_URL}/upload", TEST_FILE)
    
    if status != 200:
        print(f"   ❌ 上传失败: {status}")
        print(f"   {upload_data}")
        return False
    
    task_id = upload_data.get("task_id")
    file_hash = upload_data.get("file_hash")
    print(f"   ✅ 上传成功")
    print(f"   task_id: {task_id}")
    print(f"   file_hash: {file_hash}")
    print(f"   耗时: {time.time() - start_time:.1f}s")
    
    # 2. 检查波形生成
    print("\n2. 检查波形生成...")
    try:
        status, waveform_data = http_get(f"{BASE_URL}/waveform/{file_hash}")
        if status == 200:
            peaks = waveform_data.get("peaks", [])
            print(f"   ✅ 波形生成成功，{len(peaks)} 个峰值点")
        else:
            print(f"   ⚠️  波形生成状态: {status}")
            print(f"   {str(waveform_data)[:200]}")
    except Exception as e:
        print(f"   ⚠️  波形请求异常: {e}")
    
    # 3. 发起修复 (v2.0 单轨模式)
    print("\n3. 发起修复 (v2.0 单轨模式)...")
    
    repair_params = {
        "algorithm_version": "v2.0",
        "sample_rate": 44100,
        "bit_depth": 16,
        "mastering_mode": "standard",
        "output_gain": 0,
        "processing_mode": "single",
    }
    
    status, resp_data = http_post_json(f"{BASE_URL}/repair", {
        "task_id": task_id,
        "params": repair_params
    })
    print(f"   响应状态: {status}")
    
    if status in (200, 202):
        print(f"   ✅ 修复任务已提交")
    else:
        print(f"   响应内容: {str(resp_data)[:300]}")
    
    # 4. 轮询修复状态
    print("\n4. 等待修复完成...")
    repair_start = time.time()
    max_wait = 300
    
    while time.time() - repair_start < max_wait:
        try:
            status, status_data = http_get(f"{BASE_URL}/status/{task_id}")
        except Exception as e:
            print(f"   ⚠️  获取状态失败: {e}")
            time.sleep(2)
            continue
        
        task_status = status_data.get("status", "unknown")
        progress = status_data.get("progress", 0)
        step = status_data.get("step", "")
        elapsed = time.time() - repair_start
        
        print(f"   [{elapsed:5.1f}s] {task_status} - {progress*100:5.1f}% - {step}")
        
        if task_status in ("completed", "error", "failed", "cancelled"):
            if task_status == "completed":
                print(f"\n   ✅ 修复完成！总耗时: {elapsed:.1f}s")
                
                # 检查修复结果
                repair_result = status_data.get("repair_result", {})
                print(f"\n   修复结果摘要:")
                if "issues_found" in repair_result:
                    print(f"     发现问题: {repair_result['issues_found']}")
                if "snr_improvement_db" in repair_result:
                    print(f"     SNR 提升: {repair_result['snr_improvement_db']} dB")
                if "waveform_peaks" in repair_result:
                    print(f"     输出波形: 有")
                
                # 检查输出文件
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
        
        time.sleep(2)
    
    print(f"\n   ⏰ 修复超时 ({max_wait}s)")
    return False


if __name__ == "__main__":
    success = test_repair_flow()
    print("\n" + "=" * 60)
    print(f"测试结果: {'✅ 通过' if success else '❌ 失败'}")
    print("=" * 60)
    exit(0 if success else 1)
