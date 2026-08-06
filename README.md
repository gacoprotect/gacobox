# Blackbox.ai Auto-Farm CLI

CLI tool untuk batch register akun Blackbox.ai + harvest API keys. Setiap akun baru dapet akses ke **32 text LLM models gratis** termasuk GPT-5.4, DeepSeek V4 Pro, Kimi K3, GLM-5.2, Grok 4.3, Gemini 3.5 Flash.

## Fitur

- **TUI Menu** — Arrow key navigation, gak perlu hapal command
- **Full automation** — Signup → OTP → Verify → Login → Create API key
- **Playwright-based** — Browser beneran, bypass Next.js server actions
- **Multi-worker** — N browser concurrent
- **catchmail.io** — Temp email gratis, gak perlu API key
- **Session resume** — Lanjut dari run terakhir kalau crash/interupsi
- **9Router inject** — Auto-inject keys ke 9Router SQLite (blackbox provider)
- **Random delay** — 3-10 detik antar akun (anti-detection)
- **Model testing** — Auto-test semua 32 working models
- **Multi-format export** — TXT, JSON, CSV
- **32 free models** — GPT-5.4, DeepSeek V4 Pro, Kimi K3, GLM-5.2, Grok 4.3, Gemini 3.5 Flash, Codestral, Llama 3.1 70B, dll

## Install

```bash
cd D:\Labs\blackbox-farm
pip install -r requirements.txt
python -m playwright install chromium
```

## Cara Pakai

### Jalankan TUI

```bash
python main.py
```

Muncul menu utama:

```
╔══════════════════════════════════════╗
║     BLACKBOX FARM v2.0               ║
║     32 models ready                  ║
╠══════════════════════════════════════╣
║  >>> Register Accounts               ║
║    Test Models                       ║
║    View Harvested Keys               ║
║    Export Keys                       ║
║    Inject to 9Router                 ║
║    Run Status                        ║
║    Quit                              ║
╚══════════════════════════════════════╝
```

### Navigasi

| Tombol | Fungsi |
|--------|--------|
| Arrow Up/Down | Pilih menu |
| Enter | Masuk ke menu |
| 1-5 | Edit field (di submenu Register) |
| Space | Toggle Headless ON/OFF |
| q / Escape | Back / Quit |

### Register Accounts

```
╔══════════════════════════════════════╗
║     Register Accounts                ║
╠══════════════════════════════════════╣
║  Count:    10                        ║
║  Workers:  3                         ║
║  Headless: ON                        ║
║  Domain:   catchmail.io              ║
║  Key Name: auto-farm-key             ║
╠══════════════════════════════════════╣
║  >>> START (New)                     ║
║    RESUME (Continue)                 ║
║    Back                              ║
╚══════════════════════════════════════╝
```

- Tekan **1** → edit Count
- Tekan **2** → edit Workers
- Tekan **3** → toggle Headless
- Tekan **4** → edit Domain
- Tekan **5** → edit Key Name
- Pilih **START (New)** → register fresh
- Pilih **RESUME (Continue)** → lanjut dari run terakhir

### Test Models

```
╔══════════════════════════════════════╗
║     Test Models                      ║
╠══════════════════════════════════════╣
║  Key: sk-abc123...                  ║
╠══════════════════════════════════════╣
║  Results: 32 OK / 6 FAIL             ║
║  [OK]  z-ai/glm-5.2                 ║
║  [OK]  blackboxai/deepseek/...      ║
║  [ERR] blackboxai/openai/gpt-5.4   ║
╚══════════════════════════════════════╝
```

### View Harvested Keys

```
╔══════════════════════════════════════╗
║     Harvested Keys (32)              ║
╠══════════════════════════════════════╣
║  #  Email                    Key     ║
║  1  email1@catchmail.io      sk-abc ║
║  2  email2@catchmail.io      sk-def ║
╚══════════════════════════════════════╝
```

### Export Keys

Pilih format: TXT, JSON, CSV, atau ALL.

### Inject to 9Router

```
╔══════════════════════════════════════╗
║     Inject to 9Router                ║
╠══════════════════════════════════════╣
║  DB: C:\Users\Design\.9router\...    ║
║  Keys ready: 32                      ║
║  Already injected: 0                 ║
╠══════════════════════════════════════╣
║  >>> INJECT                          ║
║    VIEW injected keys                ║
║    REMOVE all blackbox keys          ║
║    Back                              ║
╚══════════════════════════════════════╝
```

- Auto-detect 9Router SQLite database
- Inject semua keys dari `output/keys.txt`
- Skip keys yang udah ada (no duplicate)
- Format sesuai 9Router schema (authType: `apikey`, providerSpecificData)

### Run Status

```
╔══════════════════════════════════════╗
║     Run Status                       ║
╠══════════════════════════════════════╣
║  Target:    10                       ║
║  Success:    8                       ║
║  Failed:     2                       ║
║  Keys:      8                        ║
╠══════════════════════════════════════╣
║  Recent failures:                    ║
║    email4@x.com: timeout             ║
╚══════════════════════════════════════╝
```

## Output Files

| File | Format | Deskripsi |
|------|--------|-----------|
| `output/keys.txt` | `email:password:apikey` | Plain text, 1 line per akun |
| `output/keys.json` | JSON array | Full metadata |
| `output/keys.csv` | CSV | Spreadsheet format |
| `output/state.json` | JSON | Run state untuk resume |
| `output/model_test.json` | JSON | Hasil test semua models |

## 32 Working Models (Gratis, Terverifikasi)

| # | Model ID | Provider |
|---|----------|----------|
| 1 | `blackboxai/openai/gpt-5.4` | OpenAI |
| 2 | `blackboxai/openai/gpt-5.4-pro` | OpenAI |
| 3 | `blackboxai/openai/gpt-5.4-nano` | OpenAI |
| 4 | `blackboxai/openai/gpt-5.3-codex` | OpenAI |
| 5 | `blackboxai/openai/gpt-oss-120b` | OpenAI OSS |
| 6 | `blackboxai/openai/gpt-nemotron` | OpenAI+NVIDIA |
| 7 | `z-ai/glm-5.2` | Z.AI (Zhipu) |
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

**Catatan:** GPT-5.4 Pro/Nano/Codex + Blackbox Pro = ERR400 (butuh credits). Claude Nemotron = TIMEOUT (provider down).

## Cara Pakai API Key

```python
from openai import OpenAI
client = OpenAI(base_url="https://api.blackbox.ai/v1", api_key="sk-xxx")
response = client.chat.completions.create(
    model="z-ai/glm-5.2",
    messages=[{"role": "user", "content": "Hello!"}]
)
```

```bash
curl https://api.blackbox.ai/v1/chat/completions \
  -H "Authorization: Bearer sk-xxx" \
  -H "Content-Type: application/json" \
  -d '{"model":"z-ai/glm-5.2","messages":[{"role":"user","content":"Hello!"}]}'
```

## Arsitektur

```
main.py              # TUI menu + async worker + state resume
config.py            # Dataclass config
dashboard.py         # Rich live terminal dashboard
models.py            # 32 working models + testing
exporter.py          # txt / json / csv
providers/
  blackbox.py        # Playwright: signup → OTP → key
  tempmail.py        # catchmail.io OTP polling
```

### Flow Per Akun

```
[Temp Mail] → [Browser: /signup] → [OTP Poll] → [Browser: Verify OTP]
     → [Auto-login] → [Browser: /keys] → [Create Key] → [Extract sk-xxx]
```

## Performance

- **~41 detik per akun**
- **32 free text LLM models** per akun
- **123 total models** (32 free, 91 need credits)

## Rate Limits

| Setting | Detail |
|---------|--------|
| **RPM** | Requests Per Minute per API key |
| **TPM** | Tokens Per Minute per API key |
| **Configurable** | Bisa diatur per key dari dashboard |
| **Default** | Standard rate limits (generous untuk free tier) |

**Strategy:** Banyak key = rotate keys = effectively unlimited.
1 key = set RPM/TPM sendiri dari dashboard.
100 keys = 100x capacity.

## Disclaimer

Untuk educational dan authorized testing only. Automated account creation mungkin melanggar Terms of Service Blackbox.ai.

---

*Last updated: 2026-08-05*
