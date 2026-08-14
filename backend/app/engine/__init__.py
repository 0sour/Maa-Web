"""Engine layer (M2): real ADB + MAA Asst core adapters.

  adb.py        — platform-tools adb binary wrapper (scan / connect / disconnect)
  asstproxy.py  — MAA Asst 核心（MaaCore 动态库）会话池 + AsstMsg 回调映射
  manager.py    — connect/disconnect state machine + environment status
  resource_mgr  — MAA 引擎包下载/更新（S-07）
"""
from __future__ import annotations
