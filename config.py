"""从 .env 文件加载云平台凭据配置。

查找顺序：
1. 当前工作目录下的 .env（exe 分发模式）
2. IPBanTool/../.venv/.env（开发模式，共享凭据）
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv


def _find_env_file() -> Path:
    """按优先级查找 .env 文件。"""
    # 1. 当前工作目录（exe 运行目录）
    cwd_env = Path.cwd() / ".env"
    if cwd_env.exists():
        return cwd_env

    # 2. 开发模式：Project/.venv/.env（共享凭据）
    #    __file__ 在脚本模式是 config.py 路径，在 exe 模式指向临时目录
    try:
        script_dir = Path(__file__).resolve().parent
    except NameError:
        script_dir = Path(sys.executable).parent
    dev_env = script_dir.parent / ".venv" / ".env"
    if dev_env.exists():
        return dev_env

    # 默认返回 CWD
    return cwd_env


ENV_PATH = _find_env_file()
PROJECT_DIR = Path(__file__).resolve().parent if "__file__" in dir() else Path(sys.executable).parent


class ProviderConfig:
    """单个云平台的配置。"""

    def __init__(self, key: str, name: str, env_prefix: str,
                 required_vars: list[str], optional_vars: dict[str, str] | None = None):
        self.key = key
        self.name = name
        self.env_prefix = env_prefix
        self.required_vars = required_vars
        self.optional_vars = optional_vars or {}
        self.configured = False
        self.values: dict[str, str] = {}

    def load(self, env: dict[str, str]) -> None:
        """从环境变量字典加载配置，检查必要变量是否完整。"""
        self.values = {}
        for var in self.required_vars:
            full_key = f"{self.env_prefix}{var}"
            val = env.get(full_key, "").strip()
            if not val:
                self.configured = False
                return
            self.values[var] = val
        # 加载可选变量（有默认值）
        for var, default in self.optional_vars.items():
            full_key = f"{self.env_prefix}{var}"
            val = env.get(full_key, "").strip()
            self.values[var] = val if val else default
        self.configured = True

    def get(self, var: str) -> str:
        return self.values.get(var, "")


# 已知的云平台配置定义
PROVIDER_DEFINITIONS: list[ProviderConfig] = [
    ProviderConfig(
        key="alibabacloud",
        name="阿里云·云防火墙",
        env_prefix="ALIBABACLOUD_",
        required_vars=[
            "ACCESS_KEY_ID",
            "ACCESS_KEY_SECRET",
            "REGION",
        ],
        optional_vars={
            "ADDRESS_BOOK_IPV4_NAME": "封禁ip地址簿_ipv4",
            "ADDRESS_BOOK_IPV6_NAME": "封禁ip地址簿_ipv6",
            "DESCRIPTION": "攻防演练封禁",
        },
    ),
    ProviderConfig(
        key="tencentcloud",
        name="腾讯云·CVM安全组",
        env_prefix="TENCENTCLOUD_",
        required_vars=[
            "SECRET_ID",
            "SECRET_KEY",
            "REGION",
        ],
        optional_vars={
            "DESCRIPTION": "攻防演练封禁",
            "SG_NAME_PREFIX": "封禁ip-攻防演练-上海金融",
            "SG_INSTANCES": "ins-f62w1qvw,ins-rmq29bks,ins-g8m28zyq,ins-nxj9slqu",
            "SG_MAX_RULES": "100",
        },
    ),
]


class AppConfig:
    """应用全局配置。"""

    def __init__(self):
        self.providers: dict[str, ProviderConfig] = {}
        self.env_path = ENV_PATH
        self.load_error: str | None = None
        self.has_any_provider = False
        self.whitelist_path: str | None = None

    def load(self) -> None:
        """从 ../.env 加载配置。"""
        env_path = self.env_path

        if not env_path.exists():
            self.load_error = f"配置文件不存在: {env_path}（请在 .venv/ 目录下创建 .env 文件）"
            return

        load_dotenv(dotenv_path=env_path)

        # 读取所有环境变量
        env = {k: v for k, v in os.environ.items()}

        # 依次加载每个 provider
        self.providers = {}
        for pdef in PROVIDER_DEFINITIONS:
            pdef.load(env)
            self.providers[pdef.key] = pdef

        self.has_any_provider = any(p.configured for p in self.providers.values())

        if not self.has_any_provider:
            self.load_error = (
                f"已读取 {env_path}，但未检测到有效的云平台配置。\n"
                f"请确保文件中包含阿里云(ALIBABACLOUD_*)或腾讯云(TENCENTCLOUD_*)的完整凭据。"
            )

        # 白名单文件路径
        raw_path = env.get("WHITELIST_PATH", "").strip()
        if raw_path:
            self.whitelist_path = raw_path
        else:
            self.whitelist_path = str(PROJECT_DIR / "whitelist.txt")

    def get_configured_providers(self) -> list[ProviderConfig]:
        """返回已配置的 provider 列表。"""
        return [p for p in self.providers.values() if p.configured]


# 全局单例
config = AppConfig()
