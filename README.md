# IPBanTool · 云平台自动封禁工具

攻防演练、重保期间，通过 Web 页面一键将攻击 IP 封禁到阿里云云防火墙 + 腾讯云 CVM 安全组。无需登录云控制台，无需手动操作。

---

## 功能

| 功能 | 说明 |
|------|------|
| **Web 页面操作** | 浏览器打开页面，输入 IP 即可封禁 |
| **多平台同步** | 一次操作同时封禁到阿里云和腾讯云 |
| **IPv4 + IPv6** | 自动识别 IP 类型，路由到对应地址簿或规则 |
| **多 IP 批量** | 支持单 IP、CIDR、批量（逗号/换行分隔） |
| **平台开关** | 页面上勾选/取消勾选，灵活控制封禁到哪些平台 |
| **自动去重** | 重复 IP 自动识别，不重复提交 |
| **自动管理腾讯云安全组** | 自动创建安全组、绑定 CVM 实例，满 100 条自动新建 |
| **导出为 exe** | 不需要 Python 环境，双击即可运行 |
| **白名单保护** | 封禁前自动检查白名单文件，命中生产 IP 则跳过，避免误封 |
| **封禁查询** | 输入 IP 自动在阿里云地址簿和腾讯云安全组中搜索是否已被封禁 |
| **一键解封** | 确认是客户 IP 后，点 [解封] 自动从对应平台移除 |

---

## 快速开始

### 方式一：Python 启动

```bash
# 安装依赖
pip install -r requirements.txt

# 配置凭据（见下方）
# ...

# 启动
python main.py
```

### 方式二：exe 启动（推荐分发）

> **运行要求：** exe 为单文件打包，前端页面已编译在内，无需额外文件。
> **仅需将 `.env` 放在 exe 同级目录**，如下所示：

```
exe 所在目录/
├── IPBanTool.exe       # 主程序
├── .env                # 云平台凭据（需自行创建）
├── whitelist.json      # 白名单（页面管理后自动生成，可选）
└── whitelist.txt       # 白名单（兼容旧版，可选）
```

1. 在 exe 同级目录创建 `.env`（见下方配置）
2. 双击 `IPBanTool.exe`
3. 浏览器访问 **http://localhost:5000**

> **如何打包 exe？** 运行 `build.bat` 即可，打包配置见 `IPBanTool.spec`。
> 打包前确认 `templates/` 目录存在且完整，无需额外修改。

---

## 配置说明

在程序同级目录创建 `.env` 文件，填入云平台 API 凭据：

```env
# ────── 阿里云 · 云防火墙 ──────
# 工具自动按名称查找地址簿，无需配置 UUID
# IPv4 地址簿名称：封禁ip地址簿_ipv4（可自定义）
# IPv6 地址簿名称：封禁ip地址簿_ipv6（可自定义）
ALIBABACLOUD_ACCESS_KEY_ID=LTAI5t...
ALIBABACLOUD_ACCESS_KEY_SECRET=...
ALIBABACLOUD_REGION=cn-hangzhou

# ────── 腾讯云 · CVM 安全组（自动管理）──────
# 工具自动创建/查找安全组并绑定 CVM 实例，无需配置安全组 ID
TENCENTCLOUD_SECRET_ID=AKID...
TENCENTCLOUD_SECRET_KEY=...
TENCENTCLOUD_REGION=ap-shanghai
```

### 可选配置

以下为可选变量，不配置则使用默认值：

```env
# 阿里云：地址簿名称自定义
ALIBABACLOUD_ADDRESS_BOOK_IPV4_NAME=封禁ip地址簿_ipv4
ALIBABACLOUD_ADDRESS_BOOK_IPV6_NAME=封禁ip地址簿_ipv6

# 腾讯云：安全组名称前缀（默认）
TENCENTCLOUD_SG_NAME_PREFIX=封禁ip-攻防演练-上海金融
# 腾讯云：绑定实例 ID 列表（逗号分隔）
TENCENTCLOUD_SG_INSTANCES=ins-xxxxx,ins-yyyyy,ins-zzzzz
# 腾讯云：安全组规则上限（默认100）
TENCENTCLOUD_SG_MAX_RULES=100

# 封禁描述（默认"攻防演练封禁"，可按需改为"重保封禁"等）
ALIBABACLOUD_DESCRIPTION=攻防演练封禁
TENCENTCLOUD_DESCRIPTION=攻防演练封禁

# 白名单文件路径（默认 whitelist.txt）
# WHITELIST_PATH=whitelist.txt
```

---

## 使用

1. 打开浏览器访问 **http://localhost:5000**
2. 在文本框中输入 IP 地址
   - 单 IP：`1.2.3.4`
   - CIDR：`1.2.3.0/24`
   - 批量：每行一个或用逗号分隔
3. 勾选需要封禁的平台（默认全选）
4. 点击「执行封禁」
5. 查看执行结果

### 自动处理

- 空格自动修剪
- 空行自动过滤
- 重复 IP 自动去重
- 私有地址（10.x.x.x、192.168.x.x 等）自动拦截
- 无效 IP 自动跳过

### 白名单保护

在页面底部 **🛡️ 白名单管理** 卡片中，按分组添加生产业务 IP：

```
添加 IP → 选择分组（如"政务云"、"腾讯云"）→ [+ 添加]
```

支持功能：
- **分组管理** — IP 按分组展示（政务云、腾讯云、京版机房等），清晰明了
- **一键添加/删除** — 页面操作，无需编辑文件
- **自动补齐掩码** — 输入 `10.0.1.5` 自动转为 `10.0.1.5/32`
- **CIDR 子网匹配** — 白名单写 `10.0.0.0/8`，封禁 `10.0.1.5` 自动命中

封禁时自动检查：如果输入的 IP 属于白名单中的任一网段，则**跳过封禁**，页面显示 🟡 提示。

> 数据保存在 `whitelist.json`，也兼容旧版 `whitelist.txt` 格式，两者合并去重。修改后立即生效，无需重启服务。
>
> 首次使用可参考 `whitelist.example.json` 和 `whitelist.example.txt` 的格式，复制后填入自己的业务 IP。

### 封禁查询与解封

在页面 **🔍 解封查询** 卡片中，输入 IP 即可查询是否已被封禁：

```
输入 IP（如 1.2.3.4）→ [查询] → 显示各平台封禁状态和位置 → [解封]
```

支持功能：
- **全平台搜索** — 同时查询阿里云地址簿和腾讯云所有安全组
- **子网匹配** — 搜索 `1.1.1.1` 能命中 `1.1.0.0/16` 等更宽范围
- **一键解封** — 确认是客户 IP 后，点 [解封] 自动从对应云平台移除
- **安全校验** — 解封时先读取完整列表，确认存在后才覆盖写入，避免误操作

---

## 各平台工作原理

### 阿里云 · 云防火墙

- 按名称自动查找地址簿（默认：`封禁ip地址簿_ipv4`、`封禁ip地址簿_ipv6`）
- 自动识别 IPv4/IPv6，路由到对应地址簿
- 调用 `ModifyAddressBook(Append)` 添加 IP
- 地址已存在时自动忽略，不报错

**前置条件：** 需先在云防火墙中创建好对应名称的地址簿，已有默认拒绝规则引用该地址簿。

### 腾讯云 · CVM 安全组

- 自动查找名称匹配的安全组（`前缀-YYYYMMDD` 格式）
- 有剩余位置 → 直接添加 DROP 入站规则
- 满 100 条 → 自动创建新安全组，名称带上当天日期
- 新安全组自动绑定配置的 CVM 实例
- IPv4 规则用 `CidrBlock`、IPv6 规则用 `Ipv6CidrBlock`

---

## 安全说明

- **凭据不编译进 exe** — `.env` 文件与 exe 分离存放，逆向 exe 无法获取凭据
- **各人使用各自凭据** — 分发给他人使用时，对方需填写自己的云平台 AK/SK
- **端口本地监听** — 默认监听 `127.0.0.1:5000`，不对外暴露

---

## 常见问题

**Q：如何更换封禁描述？**
在 `.env` 中设置 `ALIBABACLOUD_DESCRIPTION=重保封禁` 或 `TENCENTCLOUD_DESCRIPTION=重保封禁`，重启生效。

**Q：腾讯云安全组规则满了怎么办？**
工具会自动新建安全组，名称带上当天日期，并绑定 CVM 实例。无需手动干预。

**Q：如何查看已封禁的 IP？**
登录阿里云/腾讯云控制台，在对应地址簿或安全组中查看。

**Q：如何解封？**
在页面 **🔍 解封查询** 卡片中，输入 IP → [查询] → [解封] 即可从对应平台移除。支持阿里云地址簿和腾讯云安全组的一键解封。

---

## 云平台 RAM 权限要求

### 阿里云

| 操作 | 所需权限 |
|------|---------|
| 查询地址簿 | `cloudfw:DescribeAddressBook` |
| 添加/删除地址簿 IP | `cloudfw:ModifyAddressBook` |

### 腾讯云

| 操作 | 所需权限 |
|------|---------|
| 查询安全组 | `DescribeSecurityGroups` |
| 查询安全组规则 | `DescribeSecurityGroupPolicies` |
| 创建安全组 | `CreateSecurityGroup` |
| 添加规则 | `CreateSecurityGroupPolicies` |
| 删除规则 | `DeleteSecurityGroupPolicies` |
| 绑定安全组 | `AssociateNetworkInterfaceSecurityGroups` / `ModifyInstancesAttribute` |

---

## 项目结构

```
IPBanTool/
├── IPBanTool.exe           # 单文件 exe（分发用）
├── .env                    # 云平台凭据（需自行创建）
├── .env.example            # 配置模板
├── main.py                 # FastAPI 后端
├── config.py               # 配置加载（.env 解析）
├── ip_utils.py             # IP 校验与标准化
├── providers.py            # 阿里云 + 腾讯云 API 实现
├── requirements.txt        # Python 依赖
├── whitelist.txt            # 白名单（文本格式，兼容旧版，已 gitignore）
├── whitelist.json           # 白名单（页面管理，带分组信息，已 gitignore）
├── whitelist.example.txt    # 白名单模板（文本格式，可复制参考）
├── whitelist.example.json   # 白名单模板（JSON 格式，可复制参考）
├── build.bat               # PyInstaller 打包脚本（Windows）
├── templates/
│   └── index.html          # 前端页面
└── README.md
```

---

## 注意事项

### ⚠️ 阿里云解封：全量覆盖风险

阿里云云防火墙 API **不支持单独删除**地址簿中的某一条 IP。解封时采用「读取完整列表 → 移出目标 IP → 全量覆盖写入」的方式：

- 如果解封过程中另一个操作（如手动登录控制台）同时修改了同一地址簿，Cover 写入可能覆盖掉对方刚添加的 IP
- 代码已加入多重安全校验（读不到列表不写、IP 不在列表不写），但仍建议避免多人同时操作同一地址簿

### ⚠️ 确认客户身份再解封

查询到 IP 被封禁后，请先确认该 IP 确实是客户/业务地址，**确认无误后再点 [解封]**。解封操作不可逆，IP 会立即恢复访问。

### ⚠️ 白名单网段不宜过宽

白名单建议使用具体 IP（/32）或尽量小的子网。过宽的网段（如 `/8`）可能意外放过大量攻击 IP，削弱封禁效果。

### ⚠️ 凭据安全

- `.env` 文件包含云平台 API 密钥，**不要提交到 Git**
- 分发给他人时，对方需使用自己的 AK/SK
- `/.gitignore` 已自动排除 `.env` 和白名单文件

### ⚠️ 操作审计

封禁和解封操作都会在控制台输出日志（包含 IP、平台、时间），建议定期查看，追溯操作记录。

---

如需新增云平台：

1. 在 `providers.py` 中添加 `ban_新平台(ip_cidr, cfg) → str` 函数
2. 在 `PROVIDER_BAN_MAP` 中注册
3. 在 `config.py` 的 `PROVIDER_DEFINITIONS` 中添加配置定义
4. 在页面 `templates/index.html` 中添加 checkbox
