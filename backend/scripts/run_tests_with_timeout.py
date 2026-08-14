"""Run each pytest file with a hard timeout to isolate which one hangs."""
import subprocess
import sys
import time
from pathlib import Path

BACKEND = Path(r"D:\Maa-Web\backend")
PY = r"D:\Maa-Web\backend\.venv\Scripts\python.exe"
TIMEOUT = 60  # seconds per file

files = sorted((BACKEND / "tests").glob("test_*.py"))
failures = []
for f in files:
    t0 = time.time()
    try:
        r = subprocess.run(
            [PY, "-m", "pytest", str(f), "-q", "--no-header"],
            cwd=BACKEND,
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
        )
        dur = time.time() - t0
        status = "OK " if r.returncode == 0 else "FAIL"
        tail = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else ""
        print(f"[{status}] {f.name}  ({dur:.1f}s)  {tail}")
        if r.returncode != 0:
            failures.append(f.name)
    except subprocess.TimeoutExpired:
        dur = time.time() - t0
        print(f"[HANG] {f.name}  ({dur:.1f}s > {TIMEOUT}s)  ← 卡死")
        failures.append(f"{f.name} (HANG)")

print("\n==== 汇总 ====")
print("异常/卡死文件:", failures if failures else "无，全部通过")
