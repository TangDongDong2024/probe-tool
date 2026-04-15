# 网络探测工具集 (Probe Tool v2)

## 项目简介

**网络探测工具集 (Probe Tool v2)** 是一个用于网络质量检测和诊断的 Python 工具集合。它提供了多种网络探测功能，支持 IPv4 和 IPv6 双栈协议，可用于 DNS 解析测试、网络连通性检测、HTTP 下载测试以及路由追踪等场景。

该工具集采用异步架构设计，使用 asyncio 实现高性能并发探测，并集成了 IP 归属地查询、DNS 封堵检测等高级功能。

## 功能特性

### 核心探测功能

1. **DNS 解析测试** (`probe_dns.py`)
   - 支持 A 记录和 AAAA 记录查询
   - 支持自定义 DNS 服务器
   - DNS 封堵检测（对比本地 DNS 和公共 DNS）
   - 解析时间统计（最小、最大、平均）

2. **ICMP Ping 测试** (`probe_icmpping.py`)
   - 支持 IPv4 和 IPv6
   - 丢包率统计
   - 延迟统计（最小、最大、平均、抖动）
   - IP 归属地查询

3. **TCP 端口测试** (`probe_tcping.py`)
   - 支持自定义端口
   - 支持 IPv4 和 IPv6
   - TCP 连接延迟统计
   - 丢包率计算

4. **HTTP 下载测试** (`probe_httpdown_fast.py`)
   - HTTP/HTTPS 访问测试
   - 下载速度测试
   - 响应时间分解（DNS 解析、TCP 连接、SSL 握手、首字节、总时间）
   - 重定向跟踪
   - DNS 封堵检测
   - 反诈网站识别

5. **路由追踪** (`probe_tracert_fast.py`)
   - 使用 Scapy 构造探测包
   - 支持并发 ping 测试沿途节点
   - IP 归属地查询
   - MQTT 结果上报

### 特色功能

- **双栈支持**：全面支持 IPv4 和 IPv6 协议
- **DNS 封堵检测**：对比本地 DNS 和公共 DNS 结果，识别域名是否被运营商封堵
- **IP 归属查询**：通过本地 SQLite 数据库查询 IP 的运营商、省份、城市信息
- **异步架构**：使用 asyncio 实现高并发探测
- **标准化输出**：所有测试输出 JSON 格式结果
- **反诈识别**：识别跳转到反诈网站的异常情况

## 技术架构

### 技术栈

- **Python 3.7+**
- **异步框架**：asyncio
- **DNS 解析**：aiodns
- **ICMP 探测**：icmplib
- **HTTP 测试**：curl (通过 subprocess 调用)
- **网络包构造**：Scapy
- **数据库**：SQLite (IP 归属地库)
- **系统信息**：WMI (Windows Management Instrumentation)

### 模块结构

```
probe_tool_v2/
├── probe_dns.py              # DNS 解析测试
├── probe_icmpping.py         # ICMP Ping 测试
├── probe_tcping.py           # TCP 端口测试
├── probe_httpdown_fast.py    # HTTP 下载测试
├── probe_tracert_fast.py     # 路由追踪
├── probe_dns_block.py        # DNS 封堵检测
├── ip_utils.py               # IP 归属地查询
├── xdbSearcher.py            # IP 库查询工具
├── mylogger.py               # 日志模块
├── curl2.exe                 # HTTP 测试工具
├── nettest_ipaddress.db      # IP 归属地数据库
└── respone_relation.txt      # 网络运营商配置
```

## 快速开始

### 环境要求

- **操作系统**：Windows (支持 WMI 调用)
- **Python**：3.7 或更高版本
- **依赖库**：详见 requirements.txt

### 安装步骤

1. **克隆或下载项目**
   ```bash
   git clone <repository-url>
   cd probe_tool_v2
   ```

2. **创建虚拟环境**（推荐）
   ```bash
   python -m venv venv
   venv\Scripts\activate
   ```

3. **安装依赖**
   ```bash
   pip install -r requirements.txt
   ```

### 快速测试

#### 1. DNS 解析测试
```bash
python probe_dns.py output.json www.baidu.com 8.8.8.8 10 1 60 4
```
参数说明：
- `output.json` - 输出文件
- `www.baidu.com` - 测试域名
- `8.8.8.8` - DNS 服务器
- `10` - 请求次数
- `1` - 单次超时时间（秒）
- `60` - 总超时时间（秒）
- `4` - 协议类型（4=IPv4, 6=IPv6, 0=双栈）

#### 2. ICMP Ping 测试
```bash
python probe_icmpping.py output.json www.baidu.com 10 56 4 0.5 10
```

#### 3. TCP 端口测试
```bash
python probe_tcping.py output.json www.baidu.com 443 4
```

#### 4. HTTP 下载测试
```bash
python probe_httpdown_fast.py output.json 4 https://www.baidu.com
```

#### 5. 路由追踪
```bash
python probe_tracert_fast.py www.baidu.com --address-family ipv4 --output-file trace.json
```

## 文档导航

- **[快速开始指南](./docs/QUICKSTART.md)** - 5 分钟上手教程
- **[API 文档](./docs/api/README.md)** - 详细的接口说明
- **[部署指南](./docs/deployment/README.md)** - 完整部署教程
- **[架构设计](./docs/architecture/README.md)** - 系统架构和设计思路
- **[用户手册](./docs/user-guide/README.md)** - 详细使用说明
- **[错误码参考](./docs/reference/error-codes.md)** - 错误码和解决方案

## 项目状态

- **当前版本**：v2.0
- **维护状态**：活跃开发中
- **最后更新**：2026-02

## 贡献指南

欢迎提交 Issue 和 Pull Request。

## 许可证

[待定 - 请补充许可证信息]

## 联系方式

[待定 - 请补充联系方式]

---

**注意**：此工具仅供网络诊断和测试使用，请遵守相关法律法规。
