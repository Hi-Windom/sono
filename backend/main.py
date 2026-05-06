import sys
import subprocess

def check_dependencies():
    print("检查依赖...")
    try:
        import librosa
        import soundfile
        import soxr
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
