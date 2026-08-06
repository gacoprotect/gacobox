# Blackbox.ai 自动农场 CLI

批量注册 Blackbox.ai 账户 + 收割 API 密钥的 CLI 工具。每个新账户可免费使用 **32 个文本大语言模型**，包括 GPT-5.4、DeepSeek V4 Pro、Kimi K3、GLM-5.2、Grok 4.3、Gemini 3.5 Flash。

## 功能特性

- **TUI 菜单** — 方向键导航，无需记忆命令
- **全自动化** — 注册 → 邮箱验证码 → 验证 → 登录 → 创建 API 密钥
- **基于 Playwright** — 真实浏览器，绕过 Next.js 服务端操作
- **多线程并发** — 同时运行 N 个浏览器
- **catchmail.io** — 免费临时邮箱，无需 API 密钥
- **断点续传** — 崩溃/中断后从上次进度继续
- **9Router 注入** — 自动将密钥注入 9Router SQLite 数据库（blackbox provider）
- **随机延迟** — 每个账户间隔 3-10 秒（防检测）
- **模型测试** — 自动测试全部 32 个可用模型
- **多格式导出** — TXT、JSON、CSV
- **32 个免费模型** — GPT-5.4、DeepSeek V4 Pro、Kimi K3、GLM-5.2、Grok 4.3、Gemini 3.5 Flash、Codestral、Llama 3.1 70B 等

## 安装

```bash
cd blackbox-farm
pip install -r requirements.txt
python -m playwright install chromium
```

## 使用方法

### 启动 TUI

```bash
python main.py
```

主菜单界面：

```
╔══════════════════════════════════════╗
║     BLACKBOX FARM v2.0               ║
║     32 个模型已就绪                  ║
╠══════════════════════════════════════╣
║  >>> 注册账户                        ║
║    测试模型                          ║
║    查看已收割密钥                    ║
║    导出密钥                          ║
║    注入到 9Router                    ║
║    运行状态                          ║
║    退出                              ║
╚══════════════════════════════════════╝
```

### 操作说明

| 按键 | 功能 |
|------|------|
| 方向键上/下 | 选择菜单 |
| 回车 | 进入菜单 |
| 1-5 | 编辑字段（在注册子菜单中） |
| 空格 | 切换无头模式 ON/OFF |
| q / Esc | 返回 / 退出 |

### 注册账户

```
╔══════════════════════════════════════╗
║     注册账户                          ║
╠══════════════════════════════════════╣
║  数量：    10                         ║
║  并发数：  3                          ║
║  无头模式：开启                       ║
║  邮箱域名：catchmail.io               ║
║  密钥名称：auto-farm-key              ║
╠══════════════════════════════════════╣
║  >>> 开始（新建）                     ║
║    继续（断点续传）                   ║
║    返回                              ║
╚══════════════════════════════════════╝
```

- 按 **1** → 编辑注册数量
- 按 **2** → 编辑并发数
- 按 **3** → 切换无头模式
- 按 **4** → 编辑邮箱域名
- 按 **5** → 编辑密钥名称
- 选择 **开始（新建）** → 全新注册
- 选择 **继续（断点续传）** → 从上次中断处继续

### 测试模型

```
╔══════════════════════════════════════╗
║     测试模型                          ║
╠══════════════════════════════════════╣
║  密钥：sk-abc123...                  ║
╠══════════════════════════════════════╣
║  结果：32 成功 / 6 失败              ║
║  [成功]  z-ai/glm-5.2                ║
║  [成功]  blackboxai/deepseek/...     ║
║  [失败]  blackboxai/openai/gpt-5.4  ║
╚══════════════════════════════════════╝
```

### 查看已收割密钥

```
╔══════════════════════════════════════╗
║     已收割密钥 (32)                   ║
╠══════════════════════════════════════╣
║  #  邮箱                     密钥    ║
║  1  email1@catchmail.io      sk-abc  ║
║  2  email2@catchmail.io      sk-def  ║
╚══════════════════════════════════════╝
```

### 导出密钥

选择格式：TXT、JSON、CSV 或全部。

### 注入到 9Router

```
╔══════════════════════════════════════╗
║     注入到 9Router                    ║
╠══════════════════════════════════════╣
║  数据库：~/.9router/db/data.sqlite   ║
║  待注入密钥：32                       ║
║  已注入：0                            ║
╠══════════════════════════════════════╣
║  >>> 注入                             ║
║    查看已注入密钥                     ║
║    删除所有 blackbox 密钥             ║
║    返回                              ║
╚══════════════════════════════════════╝
```

- 自动检测 9Router SQLite 数据库
- 从 `output/keys.txt` 注入所有密钥
- 跳过已存在的密钥（无重复）
- 格式符合 9Router 数据库架构（authType: `apikey`、providerSpecificData）

### 运行状态

```
╔══════════════════════════════════════╗
║     运行状态                          ║
╠══════════════════════════════════════╣
║  目标数量：  10                       ║
║  成功：       8                       ║
║  失败：       2                       ║
║  密钥总数：   8                       ║
╠══════════════════════════════════════╣
║  最近失败记录：                       ║
║    email4@x.com: 请求超时             ║
╚══════════════════════════════════════╝
```

## 输出文件

| 文件 | 格式 | 说明 |
|------|------|------|
| `output/keys.txt` | `邮箱:密码:API密钥` | 纯文本，每行一个账户 |
| `output/keys.json` | JSON 数组 | 包含完整元数据 |
| `output/keys.csv` | CSV | 电子表格格式 |
| `output/state.json` | JSON | 运行状态（用于断点续传） |
| `output/model_test.json` | JSON | 模型测试结果 |

## 32 个可用模型（免费，已验证）

| # | 模型 ID | 提供商 |
|---|---------|--------|
| 1 | `blackboxai/openai/gpt-5.4` | OpenAI |
| 2 | `blackboxai/openai/gpt-5.4-pro` | OpenAI |
| 3 | `blackboxai/openai/gpt-5.4-nano` | OpenAI |
| 4 | `blackboxai/openai/gpt-5.3-codex` | OpenAI |
| 5 | `blackboxai/openai/gpt-oss-120b` | OpenAI OSS |
| 6 | `blackboxai/openai/gpt-nemotron` | OpenAI+NVIDIA |
| 7 | `z-ai/glm-5.2` | Z.AI（智谱） |
| 8 | `blackboxai/deepseek/deepseek-v4-pro` | DeepSeek |
| 9 | `blackboxai/moonshotai/kimi-k3` | Moonshot |
| 10 | `blackboxai/moonshotai/kimi-k2.7-code` | Moonshot |
| 11 | `blackboxai/x-ai/grok-4.3` | xAI |
| 12 | `blackboxai/x-ai/grok-4.1-fast-non-reasoning` | xAI |
| 13 | `blackboxai/x-ai/grok-build-0.1` | xAI |
| 14 | `blackboxai/google/gemini-3.5-flash` | Google |
| 15 | `blackboxai/google/gemini-3.1-flash-lite` | Google |
| 16 | `blackboxai/google/gemma-4-31b-it` | Google |
| 17 | `blackboxai/google/gemma-4-26b-a4b-it` | Google |
| 18 | `blackboxai/mistral/devstral-2` | Mistral |
| 19 | `blackboxai/mistral/mistral-small` | Mistral |
| 20 | `blackboxai/mistral/mistral-nemo` | Mistral |
| 21 | `blackboxai/mistral/codestral` | Mistral |
| 22 | `blackboxai/mistral/pixtral-12b` | Mistral |
| 23 | `blackboxai/mistral/ministral-3b` | Mistral |
| 24 | `blackboxai/mistral/ministral-8b` | Mistral |
| 25 | `blackboxai/nvidia/nemotron-3-ultra` | NVIDIA |
| 26 | `blackboxai/nvidia/nemotron-3-super-120b-a12b:free` | NVIDIA |
| 27 | `blackboxai/nvidia/nemotron-3-nano-30b-a3b` | NVIDIA |
| 28 | `blackboxai/nvidia/nemotron-nano-12b-v2-vl` | NVIDIA |
| 29 | `nvidia/nemotron-3.5-nano-blackbox` | NVIDIA |
| 30 | `blackboxai/amazon/nova-2-lite` | Amazon |
| 31 | `blackboxai/amazon/nova-micro` | Amazon |
| 32 | `blackboxai/meta/llama-3.1-8b` | Meta |
| 33 | `blackboxai/meta/llama-3.1-70b` | Meta |
| 34 | `blackboxai/morph/morph-v3-fast` | Morph |
| 35 | `blackboxai/morph/morph-v3-large` | Morph |
| 36 | `blackboxai/arcee-ai/trinity-large-thinking` | Arcee |

**注意：** GPT-5.4 Pro/Nano/Codex 和 Blackbox Pro = ERR400（需要付费额度）。Claude Nemotron = 超时（服务商宕机）。

## API 密钥使用方法

```python
from openai import OpenAI
client = OpenAI(base_url="https://api.blackbox.ai/v1", api_key="sk-xxx")
response = client.chat.completions.create(
    model="z-ai/glm-5.2",
    messages=[{"role": "user", "content": "你好！"}]
)
```

```bash
curl https://api.blackbox.ai/v1/chat/completions \
  -H "Authorization: Bearer sk-xxx" \
  -H "Content-Type: application/json" \
  -d '{"model":"z-ai/glm-5.2","messages":[{"role":"user","content":"你好！"}]}'
```

## 项目结构

```
main.py              # TUI 菜单 + 异步工作线程 + 断点续传
config.py            # 数据类配置
dashboard.py         # Rich 终端实时仪表板
models.py            # 32 个可用模型 + 测试功能
exporter.py          # txt / json / csv 导出
providers/
  blackbox.py        # Playwright：注册 → 验证码 → 密钥
  tempmail.py        # catchmail.io 验证码轮询
```

### 单账户流程

```
[临时邮箱] → [浏览器：/signup] → [验证码轮询] → [浏览器：验证邮箱]
     → [自动登录] → [浏览器：/keys] → [创建密钥] → [提取 sk-xxx]
```

## 性能指标

- **约 41 秒/账户**
- 每个账户 **32 个免费文本大语言模型**
- **共计 123 个模型**（32 个免费，91 个需付费）

## 速率限制

| 设置 | 说明 |
|------|------|
| **RPM** | 每个 API 密钥每分钟请求数 |
| **TPM** | 每个 API 密钥每分钟 Token 数 |
| **可配置** | 可从控制面板按密钥调整 |
| **默认值** | 标准速率限制（免费额度较宽松） |

**策略：** 多密钥轮换 = 等效无限容量。
1 个密钥 = 从控制面板设置 RPM/TPM。
100 个密钥 = 100 倍容量。

## 免责声明

仅供教育和授权测试用途。自动创建账户可能违反 Blackbox.ai 服务条款。

---

*最后更新：2026-08-05*
