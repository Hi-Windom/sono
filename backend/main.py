import sys
import subprocess
import os

# 限制 BLAS/OpenMP 线程数，避免与 ThreadPoolExecutor 冲突
os.environ['OPENBLAS_NUM_THREADS'] = '1'
os.environ['MKL_NUM_THREADS'] = '1'
os.environ['OMP_NUM_THREADS'] = '1'
os.environ['VECLIB_MAXIMUM_THREADS'] = '1'
os.environ['NUMEXPR_NUM_THREADS'] = '1'

def check_dependencies():
    print("检查依赖...")
    try:
        import miniaudio
        import soundfile
        import scipy
        import numpy
        print("  核心依赖已安装")
    except ImportError as e:
        print(f"  缺少依赖: {e}")
        print("  正在安装...")
        subprocess.check_call([
            sys.executable, "-m", "pip", "install", "-r",
            "requirements.txt", "-q"
        ])
        print("  依赖安装完成")

    try:
        import noisereduce
        print("  noisereduce 已安装 (深度降噪)")
    except ImportError:
        print("  noisereduce 未安装，将使用基础降噪 (可选: pip install noisereduce)")

    try:
        import pedalboard
        print("  pedalboard 已安装 (专业音效处理)")
    except ImportError:
        print("  pedalboard 未安装，将使用 scipy 降级算法 (可选: pip install pedalboard)")

    from services.mp3_encoder import is_available, get_version
    if is_available():
        print(f"  libmp3lame {get_version()} 已安装 (MP3编码)")
    else:
        print("  libmp3lame 未安装，MP3下载不可用 (尝试: pkg install lame)")

def main():
    check_dependencies()

    from database import init_db
    init_db()
    print("数据库初始化完成")

    import uvicorn
    from config import HOST, PORT

    print(f"""
╔══════════════════════════════════════════════╗
║   Next-Gen AI Audio Repair Server v2.0      ║
║   http://{HOST}:{PORT}                     ║
║                                              ║
║   API文档: http://{HOST}:{PORT}/docs        ║
╚══════════════════════════════════════════════╝
    """)

    uvicorn.run(
        "app:create_app",
        host=HOST,
        port=PORT,
        reload=False,
        factory=True,
    )

if __name__ == "__main__":
    main()
