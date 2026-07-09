"""云平台封禁 API 实现。

当前支持：
- 阿里云：云防火墙地址簿 (ModifyAddressBook)，自动识别 IPv4/IPv6
- 腾讯云：CVM 安全组入站规则 (CreateSecurityGroupPolicies)
"""

from config import ProviderConfig
from ip_utils import get_ip_version


# ─── 阿里云 · 云防火墙 ────────────────────────────────────────

# 根据 IP 版本 -> (地址簿名称配置键, 地址簿 GroupType)
ALIBABA_ADDRESS_BOOK_MAP = {
    4: ("ADDRESS_BOOK_IPV4_NAME", "ip"),
    6: ("ADDRESS_BOOK_IPV6_NAME", "ipv6"),
}


def _build_alibaba_client(cfg: ProviderConfig):
    """构建阿里云云防火墙客户端。"""
    from alibabacloud_tea_openapi import models as open_api_models
    from alibabacloud_cloudfw20171207.client import Client as CloudfwClient

    return CloudfwClient(
        open_api_models.Config(
            access_key_id=cfg.get("ACCESS_KEY_ID"),
            access_key_secret=cfg.get("ACCESS_KEY_SECRET"),
            region_id=cfg.get("REGION"),
        )
    )


def _resolve_address_book_uuid(client, name: str, group_type: str) -> str | None:
    """根据地址簿名称和类型查询 UUID。

    返回 UUID 字符串，未找到返回 None。
    """
    from alibabacloud_cloudfw20171207 import models as cloudfw_models

    req = cloudfw_models.DescribeAddressBookRequest(
        query=name,
        group_type=group_type,
        page_size=20,
        current_page=1,
    )
    resp = client.describe_address_book(req)

    if not resp.body or not resp.body.acls:
        return None

    for item in resp.body.acls:
        if item.group_name == name and item.group_type == group_type:
            return item.group_uuid

    return None


def ban_alibaba(ip_cidr: str, cfg: ProviderConfig) -> str:
    """在阿里云云防火墙地址簿中添加 IP。

    自动识别 IPv4/IPv6 并路由到对应名称的地址簿。
    返回 "ok" 或错误描述。
    """
    try:
        from alibabacloud_cloudfw20171207 import models as cloudfw_models

        # 1. 判断 IP 版本
        ip_ver = get_ip_version(ip_cidr)
        if ip_ver not in ALIBABA_ADDRESS_BOOK_MAP:
            return f"不支持的 IP 版本"

        name_key, group_type = ALIBABA_ADDRESS_BOOK_MAP[ip_ver]
        book_name = cfg.get(name_key)

        # 2. 构建客户端
        client = _build_alibaba_client(cfg)

        # 3. 查找地址簿 UUID（按名称）
        book_uuid = _resolve_address_book_uuid(client, book_name, group_type)
        if not book_uuid:
            return f"未找到{ip_ver}地址簿 '{book_name}'，请确认云防火墙中已创建该地址簿"

        # 4. 添加 IP（不预先检查——让 API 报重复时再处理）
        req = cloudfw_models.ModifyAddressBookRequest(
            group_uuid=book_uuid,
            group_name=book_name,
            address_list=ip_cidr,
            modify_mode="Append",
            description=cfg.get("DESCRIPTION"),
        )
        client.modify_address_book(req)
        return "ok"

    except Exception as e:
        err_str = str(e)
        # 地址已存在不算失败，当作成功
        if "AddressDuplicate" in err_str or "already exist" in err_str:
            return "ok"
        return f"阿里云封禁失败: {e}"


def _get_alibaba_address_list(client, book_name: str, group_type: str) -> list[str] | None:
    """获取阿里云地址簿中所有 CIDR 条目列表。"""
    from alibabacloud_cloudfw20171207 import models as cloudfw_models

    req = cloudfw_models.DescribeAddressBookRequest(
        query=book_name,
        group_type=group_type,
        page_size=20,
        current_page=1,
    )
    resp = client.describe_address_book(req)

    if not resp.body or not resp.body.acls:
        return None

    for item in resp.body.acls:
        if item.group_name == book_name and item.group_type == group_type:
            if item.address_list:
                return [x.strip() for x in item.address_list.split(",") if x.strip()]
    return None


def query_alibaba(ip_cidr: str, cfg: ProviderConfig) -> list[dict]:
    """在阿里云地址簿中搜索 IP（子网匹配）。

    返回 [{provider, provider_name, found, location, location_id, matched_cidr}, ...]
    即使未找到也会返回一条 found=False 的记录，供前端展示「已检查」状态。
    """
    import ipaddress

    try:
        search_net = ipaddress.ip_network(ip_cidr, strict=False)
    except ValueError:
        return [{"provider": "alibabacloud", "provider_name": "阿里云·云防火墙",
                 "found": False, "location": "", "location_id": "", "matched_cidr": ""}]

    results: list[dict] = []
    client = _build_alibaba_client(cfg)

    for ip_ver, (name_key, group_type) in ALIBABA_ADDRESS_BOOK_MAP.items():
        book_name = cfg.get(name_key)
        if not book_name:
            continue

        entries = _get_alibaba_address_list(client, book_name, group_type)
        if not entries:
            continue

        matched = []
        for entry in entries:
            try:
                entry_net = ipaddress.ip_network(entry, strict=False)
                if search_net.subnet_of(entry_net):
                    matched.append(entry)
            except ValueError:
                continue

        for m in matched:
            results.append({
                "provider": "alibabacloud",
                "provider_name": "阿里云·云防火墙",
                "found": True,
                "location": book_name,
                "location_id": "",
                "matched_cidr": m,
            })

    if not results:
        results.append({"provider": "alibabacloud", "provider_name": "阿里云·云防火墙",
                        "found": False, "location": "", "location_id": "", "matched_cidr": ""})

    return results


def unban_alibaba(ip_cidr: str, cfg: ProviderConfig) -> str:
    """从阿里云地址簿移除 IP（解封）。"""
    try:
        from alibabacloud_cloudfw20171207 import models as cloudfw_models

        ip_ver = get_ip_version(ip_cidr)
        if ip_ver not in ALIBABA_ADDRESS_BOOK_MAP:
            return f"不支持的 IP 版本"
        name_key, group_type = ALIBABA_ADDRESS_BOOK_MAP[ip_ver]
        book_name = cfg.get(name_key)

        client = _build_alibaba_client(cfg)
        book_uuid = _resolve_address_book_uuid(client, book_name, group_type)
        if not book_uuid:
            return f"未找到地址簿 '{book_name}'"

        req = cloudfw_models.ModifyAddressBookRequest(
            group_uuid=book_uuid,
            group_name=book_name,
            address_list=ip_cidr,
            modify_mode="Remove",
            description=cfg.get("DESCRIPTION"),
        )
        client.modify_address_book(req)
        return "ok"

    except Exception as e:
        return f"阿里云解封失败: {e}"


# ─── 腾讯云 · CVM安全组（自动管理）─────────────────────────
#
# 流程：
# 1. 查找名称前缀匹配的最新安全组（如"封禁ip-攻防演练-上海金融-20260707"）
# 2. 若找到且规则数 < 上限 → 直接添加 IP
# 3. 若找不到或已满 → 用当天日期创建新安全组 → 绑定实例 → 添加 IP


def _build_tencent_client(cfg: ProviderConfig):
    """构建腾讯云 VPC 客户端。"""
    from tencentcloud.common import credential
    from tencentcloud.vpc.v20170312 import vpc_client

    cred = credential.Credential(
        cfg.get("SECRET_ID"),
        cfg.get("SECRET_KEY"),
    )
    return vpc_client.VpcClient(cred, cfg.get("REGION"))


def _count_tencent_sg_rules(client, sg_id: str) -> int:
    """统计安全组中 DROP 入站规则的数量。"""
    from tencentcloud.vpc.v20170312 import models as vpc_models

    req = vpc_models.DescribeSecurityGroupPoliciesRequest()
    req.SecurityGroupId = sg_id
    resp = client.DescribeSecurityGroupPolicies(req)

    count = 0
    if resp and resp.SecurityGroupPolicySet:
        for rule in resp.SecurityGroupPolicySet.Ingress or []:
            if rule.Action == "DROP":
                count += 1
    return count


def _get_tencent_banned_cidrs(client, sg_id: str) -> set[str]:
    """获取指定安全组中已有的 DROP 规则 IP 集合。"""
    from tencentcloud.vpc.v20170312 import models as vpc_models

    req = vpc_models.DescribeSecurityGroupPoliciesRequest()
    req.SecurityGroupId = sg_id
    resp = client.DescribeSecurityGroupPolicies(req)

    banned: set[str] = set()
    if resp and resp.SecurityGroupPolicySet:
        for rule in resp.SecurityGroupPolicySet.Ingress or []:
            if rule.Action == "DROP":
                banned.add(rule.CidrBlock)
    return banned


def _find_latest_tencent_sg(client, prefix: str, max_rules: int) -> tuple[str, str] | None:
    """查找名称以 prefix 开头且有剩余位置的最近安全组。

    Returns:
        (sg_id, sg_name) 或 None（找不到/全满）
    """
    from tencentcloud.vpc.v20170312 import models as vpc_models

    req = vpc_models.DescribeSecurityGroupsRequest()
    req.Limit = "100"
    resp = client.DescribeSecurityGroups(req)

    import re
    date_pattern = re.compile(r"^\d{8}$")

    candidates = []
    if resp and resp.SecurityGroupSet:
        for sg in resp.SecurityGroupSet:
            name = sg.SecurityGroupName or ""
            if name.startswith(prefix):
                # 从名称中提取后缀，必须是 8 位日期格式 "prefix-YYYYMMDD"
                suffix = name[len(prefix) + 1:] if len(name) > len(prefix) else ""
                if date_pattern.match(suffix):
                    candidates.append((sg.SecurityGroupId, name, suffix))

    # 按日期倒序（最新的优先）
    candidates.sort(key=lambda x: x[2], reverse=True)

    for sg_id, sg_name, _ in candidates:
        count = _count_tencent_sg_rules(client, sg_id)
        if count < max_rules:
            return (sg_id, sg_name)

    return None


def _create_tencent_sg(client, name: str) -> str:
    """创建安全组，返回 sg_id。"""
    from tencentcloud.vpc.v20170312 import models as vpc_models

    req = vpc_models.CreateSecurityGroupRequest()
    req.GroupName = name
    req.GroupDescription = name
    resp = client.CreateSecurityGroup(req)
    return resp.SecurityGroup.SecurityGroupId


def _bind_instances_to_sg(client, sg_id: str, instance_ids: list[str]) -> str | None:
    """将安全组绑定到云服务器实例的网络接口。

    先查询实例的弹性网卡 ID，再将安全组绑定到网卡。
    返回 None 成功，返回字符串表示错误。
    """
    from tencentcloud.vpc.v20170312 import models as vpc_models

    try:
        # 1. 查询实例的弹性网卡
        eni_req = vpc_models.DescribeNetworkInterfacesRequest()
        eni_req.Filters = [{"Name": "attachment.instance-id", "Values": instance_ids}]
        eni_req.Limit = 50
        eni_resp = client.DescribeNetworkInterfaces(eni_req)

        eni_ids = []
        if eni_resp and eni_resp.NetworkInterfaceSet:
            for eni in eni_resp.NetworkInterfaceSet:
                if eni.NetworkInterfaceId:
                    eni_ids.append(eni.NetworkInterfaceId)

        if not eni_ids:
            return f"未找到实例 {instance_ids} 的弹性网卡"

        # 2. 绑定安全组到网卡
        req = vpc_models.AssociateNetworkInterfaceSecurityGroupsRequest()
        req.NetworkInterfaceIds = eni_ids
        req.SecurityGroupIds = [sg_id]
        client.AssociateNetworkInterfaceSecurityGroups(req)
        return None

    except Exception as e:
        return f"绑实例失败: {e}"


def _bind_instances_via_cvm(cfg: ProviderConfig, sg_id: str, instance_ids: list[str]) -> None:
    """通过 CVM API 绑定安全组到实例（VPC 方式失败时的替代方案）。"""
    from tencentcloud.cvm.v20170312 import cvm_client, models
    from tencentcloud.common import credential

    cred = credential.Credential(cfg.get("SECRET_ID"), cfg.get("SECRET_KEY"))
    cvm = cvm_client.CvmClient(cred, cfg.get("REGION"))

    for instance_id in instance_ids:
        # 获取实例当前已有的安全组
        desc_req = models.DescribeInstancesRequest()
        desc_req.InstanceIds = [instance_id]
        resp = cvm.DescribeInstances(desc_req)

        current_sgs: list[str] = []
        if resp and resp.InstanceSet and len(resp.InstanceSet) > 0:
            current_sgs = list(resp.InstanceSet[0].SecurityGroupIds or [])

        if sg_id not in current_sgs:
            current_sgs.append(sg_id)

        # 设置安全组（覆盖式，需先查再加）
        req = models.ModifyInstancesAttributeRequest()
        req.InstanceIds = [instance_id]
        req.SecurityGroups = current_sgs
        cvm.ModifyInstancesAttribute(req)


def ban_tencent(ip_cidr: str, cfg: ProviderConfig) -> str:
    """在腾讯云安全组中添加 DROP 入站规则。

    自动管理安全组生命周期：查找现有组 → 满则新建 → 绑定实例 → 添加 IP。
    返回 "ok" 或错误描述。
    """
    try:
        from tencentcloud.vpc.v20170312 import models as vpc_models
        from datetime import date

        client = _build_tencent_client(cfg)

        prefix = cfg.get("SG_NAME_PREFIX")
        max_rules = int(cfg.get("SG_MAX_RULES"))
        instances_str = cfg.get("SG_INSTANCES")
        instance_ids = [x.strip() for x in instances_str.split(",") if x.strip()]

        # 1. 查找有位置的已有安全组
        result = _find_latest_tencent_sg(client, prefix, max_rules)

        if result:
            sg_id, sg_name = result
        else:
            # 2. 没有可用安全组 → 新建
            today_str = date.today().strftime("%Y%m%d")
            sg_name = f"{prefix}-{today_str}"
            sg_id = _create_tencent_sg(client, sg_name)
            # 3. 绑定实例（失败不影响封禁，后续可补绑）
            if instance_ids:
                bind_err = _bind_instances_to_sg(client, sg_id, instance_ids)
                if bind_err:
                    # VPC 方式失败，尝试 CVM API 方式绑定
                    try:
                        _bind_instances_via_cvm(cfg, sg_id, instance_ids)
                    except Exception:
                        pass  # 绑定非关键，静默忽略

        # 4. 幂等检查
        existing = _get_tencent_banned_cidrs(client, sg_id)
        if ip_cidr in existing:
            return "ok"

        # 5. 添加 DROP 规则（IPv4 用 CidrBlock，IPv6 用 Ipv6CidrBlock）
        req = vpc_models.CreateSecurityGroupPoliciesRequest()
        req.SecurityGroupId = sg_id

        policy = vpc_models.SecurityGroupPolicy()
        policy.Protocol = "ALL"
        policy.Port = "ALL"
        ip_ver = get_ip_version(ip_cidr)
        if ip_ver == 6:
            policy.Ipv6CidrBlock = ip_cidr
        else:
            policy.CidrBlock = ip_cidr
        policy.Action = "DROP"
        policy.PolicyDescription = cfg.get("DESCRIPTION")

        policy_set = vpc_models.SecurityGroupPolicySet()
        policy_set.Ingress = [policy]

        req.SecurityGroupPolicySet = policy_set
        client.CreateSecurityGroupPolicies(req)
        return "ok"

    except Exception as e:
        return f"腾讯云封禁失败: {e}"


def _find_all_tencent_sgs(client, prefix: str) -> list[tuple[str, str]]:
    """查找所有名称以 prefix 开头的安全组，返回 [(sg_id, sg_name), ...]。"""
    from tencentcloud.vpc.v20170312 import models as vpc_models

    req = vpc_models.DescribeSecurityGroupsRequest()
    req.Limit = "100"
    resp = client.DescribeSecurityGroups(req)

    results: list[tuple[str, str]] = []
    if resp and resp.SecurityGroupSet:
        for sg in resp.SecurityGroupSet:
            name = sg.SecurityGroupName or ""
            if name.startswith(prefix):
                results.append((sg.SecurityGroupId, name))
    return results


def _get_tencent_banned_cidrs_all(client, sg_id: str) -> set[str]:
    """获取安全组中所有 DROP 规则的 CIDR（含 IPv4 + IPv6）。"""
    from tencentcloud.vpc.v20170312 import models as vpc_models

    req = vpc_models.DescribeSecurityGroupPoliciesRequest()
    req.SecurityGroupId = sg_id
    resp = client.DescribeSecurityGroupPolicies(req)

    banned: set[str] = set()
    if resp and resp.SecurityGroupPolicySet:
        for rule in resp.SecurityGroupPolicySet.Ingress or []:
            if rule.Action == "DROP":
                if rule.CidrBlock:
                    banned.add(rule.CidrBlock)
                if hasattr(rule, 'Ipv6CidrBlock') and rule.Ipv6CidrBlock:
                    banned.add(rule.Ipv6CidrBlock)
    return banned


def query_tencent(ip_cidr: str, cfg: ProviderConfig) -> list[dict]:
    """在腾讯云所有安全组中搜索 IP（子网匹配）。

    遍历所有前缀匹配的安全组，逐一检查 DROP 规则。
    返回 [{provider, provider_name, found, location, location_id, matched_cidr}, ...]
    """
    import ipaddress

    try:
        search_net = ipaddress.ip_network(ip_cidr, strict=False)
    except ValueError:
        return [{"provider": "tencentcloud", "provider_name": "腾讯云·CVM安全组",
                 "found": False, "location": "", "location_id": "", "matched_cidr": ""}]

    results: list[dict] = []
    client = _build_tencent_client(cfg)
    prefix = cfg.get("SG_NAME_PREFIX")
    sgs = _find_all_tencent_sgs(client, prefix)

    for sg_id, sg_name in sgs:
        cidrs = _get_tencent_banned_cidrs_all(client, sg_id)
        for banned_cidr in cidrs:
            try:
                banned_net = ipaddress.ip_network(banned_cidr, strict=False)
                if search_net.subnet_of(banned_net):
                    results.append({
                        "provider": "tencentcloud",
                        "provider_name": "腾讯云·CVM安全组",
                        "found": True,
                        "location": sg_name,
                        "location_id": sg_id,
                        "matched_cidr": banned_cidr,
                    })
            except ValueError:
                continue

    if not results:
        results.append({"provider": "tencentcloud", "provider_name": "腾讯云·CVM安全组",
                        "found": False, "location": "", "location_id": "", "matched_cidr": ""})

    return results


def unban_tencent(ip_cidr: str, sg_id: str, cfg: ProviderConfig) -> str:
    """从指定腾讯云安全组移除 DROP 规则（解封）。"""
    try:
        from tencentcloud.vpc.v20170312 import models as vpc_models

        client = _build_tencent_client(cfg)
        ip_ver = get_ip_version(ip_cidr)

        req = vpc_models.DeleteSecurityGroupPoliciesRequest()
        req.SecurityGroupId = sg_id

        policy = vpc_models.SecurityGroupPolicy()
        policy.Protocol = "ALL"
        policy.Port = "ALL"
        if ip_ver == 6:
            policy.Ipv6CidrBlock = ip_cidr
        else:
            policy.CidrBlock = ip_cidr
        policy.Action = "DROP"

        policy_set = vpc_models.SecurityGroupPolicySet()
        policy_set.Ingress = [policy]

        req.Policies = policy_set
        client.DeleteSecurityGroupPolicies(req)
        return "ok"

    except Exception as e:
        return f"腾讯云解封失败: {e}"


# ─── 提供者注册表 ─────────────────────────────────────────────

PROVIDER_BAN_MAP = {
    "alibabacloud": ban_alibaba,
    "tencentcloud": ban_tencent,
}


def get_available_providers() -> list[str]:
    """返回当前实现的 provider key 列表。"""
    return list(PROVIDER_BAN_MAP.keys())


def ban_on_provider(provider_key: str, ip_cidr: str, cfg: ProviderConfig) -> str:
    """在指定 provider 上执行封禁。

    Args:
        provider_key: "alibabacloud" | "tencentcloud"
        ip_cidr: 标准化后的 CIDR
        cfg: 该 provider 的配置

    Returns:
        "ok" 或错误消息
    """
    func = PROVIDER_BAN_MAP.get(provider_key)
    if not func:
        return f"未知平台: {provider_key}"
    return func(ip_cidr, cfg)


# ─── 查询注册表 ───────────────────────────────────────────────

PROVIDER_QUERY_MAP = {
    "alibabacloud": query_alibaba,
    "tencentcloud": query_tencent,
}


def query_on_provider(provider_key: str, ip_cidr: str, cfg: ProviderConfig) -> list[dict]:
    """在指定 provider 上查询 IP 封禁状态。"""
    func = PROVIDER_QUERY_MAP.get(provider_key)
    if not func:
        return [{"provider": provider_key, "provider_name": provider_key,
                 "found": False, "location": "", "location_id": "", "matched_cidr": ""}]
    return func(ip_cidr, cfg)


# ─── 解封注册表 ───────────────────────────────────────────────

PROVIDER_UNBAN_MAP = {
    "alibabacloud": unban_alibaba,
    "tencentcloud": unban_tencent,
}


def unban_on_provider(provider_key: str, ip_cidr: str, cfg: ProviderConfig,
                      location_id: str | None = None) -> str:
    """在指定 provider 上执行解封。

    Args:
        provider_key: "alibabacloud" | "tencentcloud"
        ip_cidr: 要移除的精确 CIDR
        cfg: 该 provider 的配置
        location_id: 腾讯云需要安全组 ID，阿里云不需要

    Returns:
        "ok" 或错误消息
    """
    func = PROVIDER_UNBAN_MAP.get(provider_key)
    if not func:
        return f"未知平台: {provider_key}"
    # 腾讯云需要 location_id，阿里云不需要
    if provider_key == "tencentcloud":
        return func(ip_cidr, location_id, cfg) if location_id else f"缺少安全组 ID"
    return func(ip_cidr, cfg)
