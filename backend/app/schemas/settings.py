"""Pydantic DTOs for the settings API (M3) — mirror sources & MirrorChyan CDK."""
from __future__ import annotations

from pydantic import BaseModel, Field


class MirrorSourceSettings(BaseModel):
    """Mirror 下载源配置（ghproxy 类前缀 + MirrorChyan CDK）。

    对齐 MAA 客户端「下载源」：可配置多个 ghproxy 前缀（逗号分隔），
    并可填写 MirrorChyan CDK 用于官方高速更新源。
    """

    # 资源更新源：github（直连/镜像）| mirrorchyan（Mirror酱）
    update_source: str = "github"
    # ghproxy 类镜像前缀，逗号/换行分隔，形如
    # "https://ghproxy.net/,https://ghfast.top/"；空 = 官方直连。
    mirror_prefixes: str = ""
    # 已配置的镜像前缀列表（由后端解析并回显，前端只读）
    mirror_prefix_list: list[str] = Field(default_factory=list)
    # 当前生效的前缀（含 .env 回退），供状态页展示
    effective_prefix_list: list[str] = Field(default_factory=list)
    # MirrorChyan CDK（读取时脱敏展示，不回传明文）
    mirrorchyan_cdk_masked: str = ""
    # MirrorChyan CDK 明文（单用户 NAS 场景，设置页需要回显完整 CDK 供查看/修改）
    mirrorchyan_cdk: str = ""
    # CDK 是否已配置
    mirrorchyan_cdk_configured: bool = False
    # CDK 有效期（unix 秒；0 = 未检查过）
    mirrorchyan_cdk_expired_time: int = 0
    # CDK 剩余天数；None = 未知/未配置
    mirrorchyan_cdk_remaining_days: float | None = None
    # 上次检查结果提示（如「已过期」「剩余 12.3 天」）；空 = 无记录
    mirrorchyan_cdk_message: str = ""
    # HTTP 代理（clash 等场景，如 http://192.168.10.110:7890）；空 = 直连
    http_proxy: str = ""
    # 动态资源（MaaResource）独立源：空 = 跟随 update_source；github | mirrorchyan 显式解耦
    dynamic_source: str = ""


class MirrorSourceUpdate(BaseModel):
    """PUT /settings/mirror 请求体 — 保存镜像源配置。"""

    # 资源更新源：github | mirrorchyan。None = 不修改。
    update_source: str | None = None
    # 为空字符串表示清空（恢复官方直连）。None = 不修改该项。
    mirror_prefixes: str | None = None
    # MirrorChyan CDK。None = 不修改；"" = 清除。
    mirrorchyan_cdk: str | None = None
    # HTTP 代理。None = 不修改；"" = 清除（恢复直连）。
    http_proxy: str | None = None
    # 动态资源源："" = 跟随引擎包源；github | mirrorchyan 显式指定。None = 不修改。
    dynamic_source: str | None = None


class MirrorCdkCheckPayload(BaseModel):
    """POST /settings/mirror/check 请求体 — 检查 CDK 有效期。"""

    cdk: str = Field(min_length=1, max_length=64, description="MirrorChyan CDK")


class MirrorCdkCheckResult(BaseModel):
    """CDK 有效期检查结果。"""

    ok: bool
    message: str
    code: int = 0
    cdk_expired_time: int = 0
    remaining_days: float | None = None


# ── 通用设置分组（S-04/§4.4 设置中心） ──────────────────────

# 支持的设置分组前缀（对齐 MAA 客户端设置窗口可落地分组）
SETTING_GROUPS = ("game", "connection", "ui", "notify", "accounts")


class SettingsGroupsRead(BaseModel):
    """GET /settings — 全部设置，按分组前缀组织（key 去掉前缀）。"""

    game: dict[str, object] = Field(default_factory=dict)
    connection: dict[str, object] = Field(default_factory=dict)
    ui: dict[str, object] = Field(default_factory=dict)
    notify: dict[str, object] = Field(default_factory=dict)
    accounts: dict[str, object] = Field(default_factory=dict)


class SettingsGroupUpdate(BaseModel):
    """PUT /settings/{group} 请求体 — 保存一组设置（扁平 dict）。"""

    values: dict[str, object] = Field(default_factory=dict)
