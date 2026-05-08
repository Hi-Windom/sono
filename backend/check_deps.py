#!/usr/bin/env python3
"""检查并安装后端依赖"""
import subprocess
import sys
import os
import importlib.util


def check_package(package_name, import_name=None):
    """检查包是否已安装"""
    if import_name is None:
        import_name = package_name.replace('-', '_').split('[')[0]
    spec = importlib.util.find_spec(import_name)
    return spec is not None


def install_requirements():
    """安装 requirements.txt 中的依赖"""
    req_file = os.path.join(os.path.dirname(__file__), 'requirements.txt')
    if not os.path.exists(req_file):
        print("  requirements.txt 不存在，跳过")
        return

    print("  检查 requirements.txt 依赖...")
    with open(req_file, 'r') as f:
        lines = f.readlines()

    missing = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith('#'):
            continue

        # 解析包名（去除版本号）
        pkg_name = line.split('>=')[0].split('<')[0].split('==')[0].strip()
        import_name = pkg_name.replace('-', '_').split('[')[0]

        if not check_package(pkg_name, import_name):
            missing.append(line)

    if missing:
        print(f"  缺少 {len(missing)} 个依赖，正在安装...")
        for pkg in missing:
            print(f"    - {pkg}")
        subprocess.check_call([
            sys.executable, '-m', 'pip', 'install', *missing
        ])
        print("  依赖安装完成")
    else:
        print("  所有依赖已安装")


if __name__ == '__main__':
    install_requirements()
