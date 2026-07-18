#!/usr/bin/env python3
"""真实测试上传API - 使用10MB MP3文件"""
import urllib.request
import urllib.parse
import json
import os
import time
import hashlib
import uuid

BASE_URL = "http://localhost:8000/api/v1"
TEST_FILE = "/workspace/public/test_10mb.mp3"

def compute_file_hash(filepath):
    h = hashlib.sha256()
    with open(filepath, 'rb') as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()

def multipart_encode(fields, files):
    """简单的multipart/form-data编码"""
    boundary = '----TestBoundary' + uuid.uuid4().hex
    lines = []
    
    for name, value in fields.items():
        lines.append(f'--{boundary}')
        lines.append(f'Content-Disposition: form-data; name="{name}"')
        lines.append('')
        lines.append(str(value))
    
    for name, (filename, data, content_type) in files.items():
        lines.append(f'--{boundary}')
        lines.append(f'Content-Disposition: form-data; name="{name}"; filename="{filename}"')
        lines.append(f'Content-Type: {content_type}')
        lines.append('')
        if isinstance(data, bytes):
            lines.append(data)
        else:
            lines.append(data.encode('utf-8'))
    
    lines.append(f'--{boundary}--')
    lines.append('')
    
    body = b''
    for line in lines:
        if isinstance(line, bytes):
            body += line + b'\r\n'
        else:
            body += line.encode('utf-8') + b'\r\n'
    
    return body, boundary

def post_multipart(url, fields, files, timeout=120):
    body, boundary = multipart_encode(fields, files)
    req = urllib.request.Request(
        url,
        data=body,
        method='POST',
        headers={
            'Content-Type': f'multipart/form-data; boundary={boundary}',
            'Content-Length': str(len(body)),
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode('utf-8')
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8')
    except Exception as e:
        return 0, str(e)

def post_json(url, data, timeout=30):
    body = json.dumps(data).encode('utf-8')
    req = urllib.request.Request(
        url,
        data=body,
        method='POST',
        headers={
            'Content-Type': 'application/json',
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode('utf-8')
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8')
    except Exception as e:
        return 0, str(e)

def post_form(url, data, timeout=30):
    body = urllib.parse.urlencode(data).encode('utf-8')
    req = urllib.request.Request(
        url,
        data=body,
        method='POST',
        headers={
            'Content-Type': 'application/x-www-form-urlencoded',
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode('utf-8')
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8')
    except Exception as e:
        return 0, str(e)

def get_request(url, params=None, timeout=30):
    if params:
        url += '?' + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status, resp.read().decode('utf-8')
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8')
    except Exception as e:
        return 0, str(e)

def test_simple_upload():
    """测试简单上传"""
    print("=" * 60)
    print("测试1: 简单上传 (simple upload)")
    print("=" * 60)
    
    file_size = os.path.getsize(TEST_FILE)
    print(f"文件大小: {file_size / 1024 / 1024:.2f} MB")
    
    file_hash = compute_file_hash(TEST_FILE)
    print(f"SHA256: {file_hash[:32]}...")
    
    start = time.time()
    try:
        with open(TEST_FILE, 'rb') as f:
            file_data = f.read()
        
        status, text = post_multipart(
            f"{BASE_URL}/upload",
            {'file_hash': file_hash},
            {'file': ('test_10mb.mp3', file_data, 'audio/mpeg')},
            timeout=180
        )
        
        elapsed = time.time() - start
        print(f"耗时: {elapsed:.2f}s")
        print(f"状态码: {status}")
        
        if status == 200:
            result = json.loads(text)
            print(f"✅ 上传成功!")
            print(f"   task_id: {result.get('task_id')}")
            print(f"   filename: {result.get('filename')}")
            print(f"   size: {result.get('size')}")
            print(f"   audio_info: {result.get('audio_info')}")
            return True, result
        else:
            print(f"❌ 上传失败: {text[:500]}")
            return False, text
    except Exception as e:
        elapsed = time.time() - start
        print(f"❌ 异常 (耗时{elapsed:.2f}s): {e}")
        return False, str(e)

def test_chunked_upload():
    """测试分块上传"""
    print("\n" + "=" * 60)
    print("测试2: 分块上传 (chunked upload)")
    print("=" * 60)
    
    file_size = os.path.getsize(TEST_FILE)
    file_hash = compute_file_hash(TEST_FILE)
    chunk_size = 5 * 1024 * 1024  # 5MB per chunk
    total_chunks = (file_size + chunk_size - 1) // chunk_size
    
    print(f"文件大小: {file_size / 1024 / 1024:.2f} MB")
    print(f"分块大小: {chunk_size / 1024 / 1024:.1f} MB")
    print(f"总分块数: {total_chunks}")
    
    start = time.time()
    
    # Step 1: 初始化
    print("\n[1/4] 初始化上传会话...")
    try:
        status, text = post_form(f"{BASE_URL}/upload-init", {
            'filename': 'test_10mb.mp3',
            'total_size': file_size,
            'total_chunks': total_chunks,
            'file_hash': file_hash,
        }, timeout=30)
        print(f"状态码: {status}")
        if status != 200:
            print(f"❌ 初始化失败: {text}")
            return False, text
        init_result = json.loads(text)
        session_id = init_result['session_id']
        print(f"✅ 会话创建成功: session_id={session_id}")
    except Exception as e:
        print(f"❌ 初始化异常: {e}")
        return False, str(e)
    
    # Step 2: 上传分块
    print(f"\n[2/4] 上传 {total_chunks} 个分块...")
    try:
        with open(TEST_FILE, 'rb') as f:
            for i in range(total_chunks):
                chunk_data = f.read(chunk_size)
                chunk_start = time.time()
                status, text = post_multipart(
                    f"{BASE_URL}/upload-chunk",
                    {
                        'session_id': session_id,
                        'chunk_index': str(i),
                    },
                    {'chunk': (f'chunk_{i}', chunk_data, 'application/octet-stream')},
                    timeout=60
                )
                chunk_elapsed = time.time() - chunk_start
                speed = len(chunk_data) / chunk_elapsed / 1024 / 1024 if chunk_elapsed > 0 else 0
                status_icon = "✅" if status == 200 else "❌"
                print(f"  {status_icon} 分块 {i+1}/{total_chunks}: {len(chunk_data)} bytes, {chunk_elapsed:.2f}s, {speed:.1f} MB/s")
                if status != 200:
                    print(f"     错误: {text[:500]}")
                    return False, f"chunk {i} failed: {text}"
    except Exception as e:
        print(f"❌ 上传分块异常: {e}")
        return False, str(e)
    
    # Step 3: 查询状态
    print("\n[3/4] 查询上传状态...")
    try:
        status, text = get_request(f"{BASE_URL}/upload-status", {'session_id': session_id}, timeout=10)
        if status == 200:
            status_data = json.loads(text)
            print(f"✅ 状态: {status_data['uploaded_count']}/{status_data['total_chunks']} = {status_data['progress']:.1f}%")
        else:
            print(f"⚠️  查询失败: {text}")
    except Exception as e:
        print(f"⚠️  查询异常: {e}")
    
    # Step 4: 合并
    print("\n[4/4] 合并分块...")
    try:
        status, text = post_form(f"{BASE_URL}/upload-finalize", {'session_id': session_id}, timeout=180)
        elapsed = time.time() - start
        print(f"状态码: {status}")
        if status == 200:
            result = json.loads(text)
            print(f"✅ 合并成功! (总耗时 {elapsed:.2f}s)")
            print(f"   task_id: {result.get('task_id')}")
            print(f"   filename: {result.get('filename')}")
            print(f"   size: {result.get('size')}")
            print(f"   audio_info: {result.get('audio_info')}")
            return True, result
        else:
            print(f"❌ 合并失败: {text[:500]}")
            return False, text
    except Exception as e:
        elapsed = time.time() - start
        print(f"❌ 合并异常 (耗时{elapsed:.2f}s): {e}")
        return False, str(e)

def test_check_hash():
    """测试哈希检查"""
    print("\n" + "=" * 60)
    print("测试3: 哈希检查 (check-hash)")
    print("=" * 60)
    
    file_hash = compute_file_hash(TEST_FILE)
    print(f"测试哈希: {file_hash[:32]}...")
    
    try:
        status, text = post_json(f"{BASE_URL}/check-hash", {'file_hash': file_hash}, timeout=10)
        print(f"状态码: {status}")
        if status == 200:
            result = json.loads(text)
            print(f"结果: exists={result.get('exists')}")
            if result.get('exists'):
                print(f"   task_id: {result.get('task_id')}")
                print(f"   status: {result.get('status')}")
            return True, result
        else:
            print(f"❌ 失败: {text[:500]}")
            return False, text
    except Exception as e:
        print(f"❌ 异常: {e}")
        return False, str(e)

if __name__ == '__main__':
    print("后端API真实上传测试 - 10MB MP3")
    print(f"测试文件: {TEST_FILE}")
    print(f"文件存在: {os.path.exists(TEST_FILE)}")
    
    # 先测一下健康检查
    print("\n检查后端是否可用...")
    status, text = get_request(f"{BASE_URL}/health", timeout=5)
    print(f"health: status={status}, response={text[:200]}")
    
    results = []
    
    # 测试1: 简单上传
    ok, data = test_simple_upload()
    results.append(('简单上传', ok))
    
    # 测试2: 分块上传
    ok, data = test_chunked_upload()
    results.append(('分块上传', ok))
    
    # 测试3: 哈希检查
    ok, data = test_check_hash()
    results.append(('哈希检查', ok))
    
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)
    for name, ok in results:
        status = "✅ 通过" if ok else "❌ 失败"
        print(f"  {status}: {name}")
    
    all_pass = all(ok for _, ok in results)
    print(f"\n总体: {'全部通过 ✅' if all_pass else '存在失败 ❌'}")
