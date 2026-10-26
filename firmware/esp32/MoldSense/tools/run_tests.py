"""Compile and run the actual platform-independent production C++ modules."""
import argparse
from pathlib import Path
import subprocess
import os

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--compiler', default='g++', help='g++, clang++, or full path to zig.exe')
args = parser.parse_args()
build = root/'build/tests'
build.mkdir(parents=True, exist_ok=True)
compiler_path = Path(args.compiler)
compiler = [str(compiler_path.resolve()) if compiler_path.is_file() else args.compiler]
if Path(args.compiler).stem == 'zig':
    compiler += ['c++']
    if os.name == 'nt':
        compiler += ['-target', 'x86_64-windows-gnu']
exe = build/('core_tests.exe' if os.name == 'nt' else 'core_tests')
sources = ['tests/test_core.cpp', 'src/Analysis/MoldRiskEngine.cpp', 'src/Analysis/MoldVOCClassifier.cpp', 'src/Sensors/WallMoisture.cpp', 'src/Calibration/BaselineManager.cpp', 'src/Storage/StorageManager.cpp', 'src/UI/ResearchProtocol.cpp', 'src/UI/Console.cpp']
command = compiler+['-std=c++17', '-O2', '-Wall', '-Wextra', '-DMOLDSENSE_HOST_TEST', '-I'+str(root/'tests/mocks')]+[str(root/p) for p in sources]+['-o',str(exe)]
env = os.environ.copy()
env['ZIG_GLOBAL_CACHE_DIR'] = str(build/'zig-cache')
result = subprocess.run(command, text=True, capture_output=True, env=env)
(build/'compile.txt').write_text(result.stdout+result.stderr)
if result.returncode:
    print(result.stdout+result.stderr)
    raise SystemExit(result.returncode)
result = subprocess.run([str(exe)],text=True,capture_output=True,cwd=build)
(build/'results.txt').write_text(result.stdout+result.stderr)
print(result.stdout+result.stderr)
raise SystemExit(result.returncode)
