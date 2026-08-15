"""UI 可写的运行时设置（JSON 持久化，热更新，覆盖 .env 默认值）。

背景：`get_settings()` 是进程内 lru_cache 单例，启动时读取一次 .env，设置页
保存的镜像源 / MirrorChyan CDK 无法直接写回环境。因此引入独立 JSON 配置文件
（与 SQLite 同目录 `runtime_settings.json`），优先级高于 .env：

    UI 保存 → 写 JSON（标记 _configured） → 运行期读取生效（无需重启）

文件位置与测试隔离：
    <config_file 同目录>/runtime_settings.json（conftest 已把 DATA_DIR 指向
    temp 目录，测试互不污染）。
"""
from __future__ import annotations

import json
import re
import secrets
import threading
from pathlib import Path

from app.core.config import get_settings

# ── 字段默认值 ────────────────────────────────────────────
_DEFAULTS: dict = {
    "update_source": "github",  # 资源更新源：github（直连/镜像）| mirrorchyan（Mirror酱）
    # 动态资源（MaaResource）独立源：空 = 跟随 update_source；显式 github/mirrorchyan 可解耦
    #（NAS 场景：引擎包走 GitHub，动态资源走 Mirror 更快——互不干扰）
    "dynamic_source": "",
    "maa_resource_mirror": "",  # ghproxy 类镜像前缀（逗号/换行分隔）；空 = 官方直连
    "mirrorchyan_cdk": "",  # Mirror酱 CDK（对齐 MAA 客户端下载源）
    "mirrorchyan_cdk_expired_time": 0,  # unix 秒；0 = 未检查过
    "mirrorchyan_sp_id": "",  # 本机唯一标识（首次生成并持久化，供 API 使用）
    "http_proxy": "",  # HTTP 代理（如 http://192.168.10.110:7890，clash 场景）；空 = 直连
    "adb_path": "",  # ADB 可执行文件路径（设置页连接设置，热更新覆盖 MAAWEB_ADB_PATH）
}

_lock = threading.Lock()
_cache: dict | None = None


def _path() -> Path:
    return get_settings().config_file.parent / "runtime_settings.json"


def _persist(data: dict) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load() -> dict:
    """读取运行时设置（进程内缓存，首次从磁盘加载并补全默认值）。"""
    global _cache
    with _lock:
        if _cache is not None:
            return _cache
        data = dict(_DEFAULTS)
        try:
            raw = json.loads(_path().read_text(encoding="utf-8"))
            data.update({k: raw[k] for k in _DEFAULTS if k in raw})
        except (OSError, ValueError):
            pass
        if not data["mirrorchyan_sp_id"]:
            data["mirrorchyan_sp_id"] = secrets.token_hex(8)
            _persist(data)
        _cache = data
        return data


def update(**kw: object) -> dict:
    """合并写入运行时设置并落盘（仅在调用过 update 后才覆盖 .env 默认值）。"""
    data = load()
    with _lock:
        for k, v in kw.items():
            if k in _DEFAULTS:
                data[k] = v
        data["_configured"] = True
        _persist(data)
    return dict(data)


def mirror_prefixes() -> list[str]:
    """生效的镜像前缀列表（优先 UI 保存值，未配置时回退 .env）。

    用法为「前缀 + 完整 GitHub URL」，如 `https://ghproxy.net/`。返回列表已
    统一补全尾部 `/`，空配置返回 []（官方直连）。
    """
    data = load()
    s = data.get("maa_resource_mirror") if data.get("_configured") else get_settings().maa_resource_mirror
    return [m.strip().rstrip("/") + "/" for m in re.split(r"[,，\n]", s) if m.strip()]


def mirrorchyan_cdk() -> str:
    return str(load().get("mirrorchyan_cdk", "") or "").strip()


def mirrorchyan_sp_id() -> str:
    return str(load().get("mirrorchyan_sp_id", "") or "")


def http_proxy() -> str:
    """HTTP 代理（clash 等场景）；空字符串 = 直连。"""
    return str(load().get("http_proxy", "") or "").strip()


def update_source() -> str:
    """当前资源更新源：github | mirrorchyan（默认 github）。"""
    return str(load().get("update_source", "") or "github")


def dynamic_source() -> str:
    """动态资源（MaaResource）更新源：显式配置则独立生效，否则跟随 update_source。"""
    return str(load().get("dynamic_source", "") or "").strip() or update_source()


def adb_path() -> str:
    """设置页保存的 ADB 路径（仅 `_configured` 后生效，否则回退 .env）。"""
    data = load()
    if not data.get("_configured"):
        return ""
    return str(data.get("adb_path", "") or "").strip()
