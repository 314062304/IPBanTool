"""IP 地址校验、标准化、工具函数。支持 IPv4 和 IPv6。"""

import ipaddress
import json
import os
import re
from typing import List


# 常见的私有/保留地址段（IPv4）
PRIVATE_IPV4_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),       # loopback
    ipaddress.ip_network("169.254.0.0/16"),    # link-local
    ipaddress.ip_network("0.0.0.0/8"),         # 当前网络
    ipaddress.ip_network("224.0.0.0/4"),       # 组播
    ipaddress.ip_network("240.0.0.0/4"),       # 保留
]

# 常见的私有/保留地址段（IPv6）
PRIVATE_IPV6_NETWORKS = [
    ipaddress.ip_network("::1/128"),           # loopback
    ipaddress.ip_network("fe80::/10"),         # link-local
    ipaddress.ip_network("fc00::/7"),          # unique local
    ipaddress.ip_network("ff00::/8"),          # 组播
    ipaddress.ip_network("::/96"),             # IPv4兼容
    ipaddress.ip_network("2001:db8::/32"),     # 文档/示例
]


def parse_ip_input(raw: str) -> list[str]:
    """解析用户输入的 IP 文本，返回标准化 CIDR 列表。

    支持：
    - 单 IP: "1.2.3.4" → "1.2.3.4/32"
    - IPv6: "::1" → "::1/128"
    - CIDR: "1.2.3.0/24" 或 "2001::/32"
    - 换行/逗号分隔
    - 自动 trim 空格、去空行、去重
    """
    if not raw or not raw.strip():
        return []

    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    parts = re.split(r"[\n,]+", raw)

    seen: set[str] = set()
    result: list[str] = []

    for part in parts:
        item = part.strip()
        if not item:
            continue

        # 补齐 /32（IPv4）或 /128（IPv6）
        if "/" not in item:
            item = f"{item}/32" if "." in item else f"{item}/128"

        if item in seen:
            continue
        seen.add(item)

        err = validate_cidr(item)
        if err:
            continue
        result.append(item)

    return result


def get_ip_version(cidr: str) -> int | None:
    """判断 IP 版本：4 或 6，无效返回 None。"""
    try:
        network = ipaddress.ip_network(cidr, strict=False)
        if isinstance(network, ipaddress.IPv4Network):
            return 4
        elif isinstance(network, ipaddress.IPv6Network):
            return 6
    except ValueError:
        pass
    return None


def validate_cidr(cidr: str) -> str | None:
    """验证 CIDR 格式，返回 None 表示合法，返回字符串表示错误消息。"""
    try:
        network = ipaddress.ip_network(cidr, strict=False)
    except ValueError:
        return f"无效的 IP 地址: {cidr}"

    if isinstance(network, ipaddress.IPv4Network):
        for priv in PRIVATE_IPV4_NETWORKS:
            if network.overlaps(priv):
                return f"不允许封禁私有/保留地址: {cidr}"
    elif isinstance(network, ipaddress.IPv6Network):
        for priv in PRIVATE_IPV6_NETWORKS:
            if network.overlaps(priv):
                return f"不允许封禁私有/保留地址: {cidr}"
    else:
        return f"不支持的 IP 类型: {cidr}"

    return None


def normalize_cidr(cidr: str) -> str:
    """标准化 CIDR 格式。"""
    return str(ipaddress.ip_network(cidr, strict=False))


def load_whitelist(txt_path: str, json_path: str | None = None) -> list:
    """从多个来源加载白名单 CIDR，返回 ip_network 对象列表。

    加载顺序：
    1. whitelist.json（带分组信息）
    2. whitelist.txt（传统文本格式，兼容）
    两者合并后去重，统一用于 IP 检查。
    """
    seen_networks: set[str] = set()
    whitelist: list = []

    # 1. 加载 JSON 白名单
    if json_path and os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8-sig") as f:
                entries = json.load(f)
            for entry in entries:
                cidr = entry.get("ip", "").strip()
                group = entry.get("group", "未分组")
                if not cidr:
                    continue
                try:
                    network = ipaddress.ip_network(cidr, strict=False)
                    key = str(network)
                    if key not in seen_networks:
                        seen_networks.add(key)
                        whitelist.append(network)
                except ValueError:
                    print(f"[WARN] 白名单JSON无效条目: {cidr} (所属分组: {group})")
        except Exception as e:
            print(f"[WARN] 读取白名单JSON失败: {e}")

    # 2. 加载 TXT 白名单（兼容）
    try:
        with open(txt_path, "r", encoding="utf-8-sig") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                try:
                    network = ipaddress.ip_network(line, strict=False)
                    key = str(network)
                    if key not in seen_networks:
                        seen_networks.add(key)
                        whitelist.append(network)
                except ValueError:
                    print(f"[WARN] 白名单文件第{line_num}行无效，已跳过: {line}")
    except FileNotFoundError:
        if not json_path or not os.path.exists(json_path):
            print(f"[INFO] 白名单文件不存在，跳过白名单检查: {txt_path}")
    except Exception as e:
        print(f"[WARN] 读取白名单文件失败: {e}")

    return whitelist


def is_whitelisted(ip_cidr: str, whitelist: list) -> bool:
    """检查 IP 是否命中白名单（IP 是白名单中任一 CIDR 的子网）。"""
    if not whitelist:
        return False
    try:
        network = ipaddress.ip_network(ip_cidr, strict=False)
    except ValueError:
        return False
    for wl_net in whitelist:
        try:
            if network.subnet_of(wl_net):
                return True
        except TypeError:
            # IPv4 vs IPv6 不匹配，跳过
            continue
    return False


def _normalize_ip_for_save(ip_str: str) -> str | None:
    """标准化 IP 字符串，自动补齐 /32 或 /128，校验合法性。"""
    ip_str = ip_str.strip()
    if not ip_str:
        return None
    if "/" not in ip_str:
        ip_str = f"{ip_str}/32" if "." in ip_str else f"{ip_str}/128"
    try:
        return str(ipaddress.ip_network(ip_str, strict=False))
    except ValueError:
        return None


def load_whitelist_json(path: str) -> list[dict]:
    """加载 JSON 白名单文件，返回条目列表。

    返回格式：[{"ip": "10.0.0.0/8", "group": "政务云", "source": "json"}, ...]
    文件不存在时返回空列表。
    """
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            entries = json.load(f)
        # 标准化并过滤无效条目
        result = []
        for entry in entries:
            cidr = _normalize_ip_for_save(entry.get("ip", ""))
            if cidr:
                result.append({
                    "ip": cidr,
                    "group": entry.get("group", "未分组").strip() or "未分组",
                    "source": "json",
                })
        return result
    except Exception as e:
        print(f"[WARN] 读取白名单JSON失败: {e}")
        return []


def save_whitelist_json(entries: list[dict], path: str) -> bool:
    """保存条目列表到 JSON 文件。"""
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"[ERROR] 保存白名单JSON失败: {e}")
        return False


def add_whitelist_entry(raw_ip: str, group: str, json_path: str) -> tuple[bool, str]:
    """添加白名单条目。

    Returns:
        (True, "成功消息") 或 (False, "错误消息")
    """
    cidr = _normalize_ip_for_save(raw_ip)
    if not cidr:
        return False, f"无效的 IP 地址: {raw_ip}"

    group = group.strip() or "未分组"

    entries = load_whitelist_json(json_path)
    # 去重检查
    for entry in entries:
        if entry["ip"] == cidr and entry["group"] == group:
            return False, f"该条目已存在（IP: {cidr}, 分组: {group}）"

    entries.append({"ip": cidr, "group": group, "source": "json"})
    if save_whitelist_json(entries, json_path):
        return True, f"已添加 {cidr}（{group}）"
    return False, "保存失败"


def remove_whitelist_entry(raw_ip: str, group: str, json_path: str) -> tuple[bool, str]:
    """删除白名单条目。

    Returns:
        (True, "成功消息") 或 (False, "错误消息")
    """
    cidr = _normalize_ip_for_save(raw_ip)
    if not cidr:
        return False, f"无效的 IP 地址: {raw_ip}"

    group = group.strip()

    entries = load_whitelist_json(json_path)
    new_entries = [e for e in entries if not (e["ip"] == cidr and e["group"] == group)]
    if len(new_entries) == len(entries):
        return False, f"未找到该条目（IP: {cidr}, 分组: {group}）"

    if save_whitelist_json(new_entries, json_path):
        return True, f"已删除 {cidr}（{group}）"
    return False, "保存失败"
