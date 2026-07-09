"""IPBanTool — FastAPI 后端服务

提供 Web 页面和 API 用于多平台 IP 封禁。

启动: python main.py
"""

import asyncio
import os
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

import ip_utils
from config import config, AppConfig
from providers import ban_on_provider, get_available_providers

# ─── 应用初始化 ───────────────────────────────────────────────

app = FastAPI(title="IPBanTool", version="1.0.0")

# 支持 PyInstaller 打包模式（sys._MEIPASS）和开发模式
if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    TEMPLATES_DIR = Path(sys._MEIPASS) / "templates"
else:
    TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


def load_config_on_startup():
    """启动时加载配置，失败只记录不崩溃。"""
    config.load()
    if config.load_error:
        print(f"[WARN] 配置警告: {config.load_error}")
    else:
        providers = config.get_configured_providers()
        print(f"[OK] 已加载配置，可用平台: {', '.join(p.name for p in providers)}")


load_config_on_startup()


# ─── 数据模型 ──────────────────────────────────────────────────


class BanRequest(BaseModel):
    ips: list[str]
    providers: list[str]


class BanResponse(BaseModel):
    results: dict[str, dict[str, str]]   # { ip: { provider: "ok"|错误 } }
    summary: dict[str, int]              # { ok: N, fail: M }


class WhitelistAddRequest(BaseModel):
    ip: str
    group: str = "未分组"


class WhitelistDeleteRequest(BaseModel):
    ip: str
    group: str


# ─── 路由 ──────────────────────────────────────────────────────


@app.get("/", response_class=HTMLResponse)
async def index():
    """提供前端页面。"""
    html_path = TEMPLATES_DIR / "index.html"
    if not html_path.exists():
        return HTMLResponse("<h1>500 - 前端文件缺失</h1>", status_code=500)
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


@app.get("/api/status")
async def api_status():
    """返回各平台配置状态。"""
    providers_info = []
    for pdef in get_available_providers():
        cfg = config.providers.get(pdef)
        providers_info.append({
            "key": pdef,
            "name": cfg.name if cfg else pdef,
            "configured": cfg.configured if cfg else False,
        })

    return {
        "status": "ok" if config.has_any_provider else "no_provider",
        "message": config.load_error or "",
        "providers": providers_info,
    }


@app.post("/api/ban", response_model=BanResponse)
async def api_ban(req: BanRequest):
    """执行 IP 封禁。

    接收 IP 列表和要封禁的平台列表，逐个封禁并返回结果。
    """
    # 1. 校验配置是否已加载
    if not config.has_any_provider:
        raise HTTPException(status_code=400, detail="未检测到有效的云平台配置，请检查 .env 文件")

    # 2. 解析并校验 IP
    parsed_ips = ip_utils.parse_ip_input("\n".join(req.ips))
    if not parsed_ips:
        raise HTTPException(status_code=400, detail="没有有效的 IP 地址")

    # 3. 过滤无效的 provider
    valid_providers = []
    for pk in req.providers:
        cfg = config.providers.get(pk)
        if cfg and cfg.configured:
            valid_providers.append((pk, cfg))
        elif pk not in get_available_providers():
            raise HTTPException(status_code=400, detail=f"未知平台: {pk}")
        # 已配置但未配置 → 静默跳过（前端不该传，但容错）

    if not valid_providers:
        raise HTTPException(status_code=400, detail="没有可用的封禁平台")

    # 3.5 白名单检查
    whitelist_json_path = _get_whitelist_json_path()
    whitelist_cidrs = ip_utils.load_whitelist(config.whitelist_path, whitelist_json_path) if config.whitelist_path else []

    # 4. 执行封禁
    results: dict[str, dict[str, str]] = {}
    ok_count = 0
    fail_count = 0
    whitelisted_count = 0

    for ip_cidr in parsed_ips:
        ip_results: dict[str, str] = {}

        # 白名单命中检查
        if whitelist_cidrs and ip_utils.is_whitelisted(ip_cidr, whitelist_cidrs):
            print(f"[WHITELIST] 跳过封禁白名单 IP: {ip_cidr}")
            for pk, cfg in valid_providers:
                ip_results[pk] = "whitelisted"
            whitelisted_count += 1
        else:
            for pk, cfg in valid_providers:
                try:
                    # 在线程池中执行，避免阻塞事件循环
                    outcome = await asyncio.to_thread(ban_on_provider, pk, ip_cidr, cfg)
                    ip_results[pk] = outcome
                    if outcome == "ok":
                        ok_count += 1
                    else:
                        fail_count += 1
                except Exception as e:
                    ip_results[pk] = f"执行异常: {e}"
                    fail_count += 1
        results[ip_cidr] = ip_results

    return BanResponse(
        results=results,
        summary={"ok": ok_count, "fail": fail_count, "whitelisted": whitelisted_count},
    )


def _get_whitelist_json_path() -> str:
    """返回 whitelist.json 的路径（与 whitelist.txt 同目录）。"""
    if config.whitelist_path:
        return os.path.join(os.path.dirname(config.whitelist_path), "whitelist.json")
    return ""


@app.get("/api/whitelist")
async def api_get_whitelist():
    """返回白名单条目列表（含分组）。"""
    json_path = _get_whitelist_json_path()
    entries = ip_utils.load_whitelist_json(json_path) if json_path else []
    return {"entries": entries}


@app.post("/api/whitelist")
async def api_add_whitelist(req: WhitelistAddRequest):
    """添加白名单条目。"""
    json_path = _get_whitelist_json_path()
    if not json_path:
        raise HTTPException(status_code=500, detail="白名单未配置")

    ok, msg = ip_utils.add_whitelist_entry(req.ip, req.group, json_path)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "msg": msg}


@app.delete("/api/whitelist")
async def api_delete_whitelist(req: WhitelistDeleteRequest):
    """删除白名单条目。"""
    json_path = _get_whitelist_json_path()
    if not json_path:
        raise HTTPException(status_code=500, detail="白名单未配置")

    ok, msg = ip_utils.remove_whitelist_entry(req.ip, req.group, json_path)
    if not ok:
        raise HTTPException(status_code=404, detail=msg)
    return {"ok": True, "msg": msg}


# ─── 启动 ──────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    print("[IPBanTool] 启动中...")
    print(f"  端口: 5000")
    print(f"  页面: http://localhost:5000")
    uvicorn.run(app, host="0.0.0.0", port=5000)
