"""Blackbox.ai Farm — Clean Dashboard TUI."""
from __future__ import annotations

import asyncio
import io
import json
import os
import secrets
import string
import sys
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
load_dotenv()

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

from config import Config
from dashboard import FarmDashboard
from exporter import export_all
from injector import inject_keys, find_9router_db, list_injected, remove_keys
from models import WORKING_MODELS, test_all
from providers.blackbox import AccountResult, BlackboxClient
from providers.tempmail import generate_email

STATE_FILE = "state.json"
console = Console(width=80)

# ─── Helpers ──────────────────────────────────────────────────────────

def generate_password(length=16):
    return "".join(secrets.choice(string.ascii_letters + string.digits + "!@#$%") for _ in range(length))

def load_state(output_dir):
    p = Path(output_dir) / STATE_FILE
    if not p.exists(): return {"target": 0, "accounts": []}
    try: return json.loads(p.read_text(encoding="utf-8"))
    except: return {"target": 0, "accounts": []}

def save_state(output_dir, state):
    p = Path(output_dir) / STATE_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")

def append_key(output_dir, record):
    p = Path(output_dir) / "keys.txt"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(f"{record['email']}:{record['password']}:{record['api_key']}\n")

def done_emails(state):
    return {a.get("email", "") for a in state.get("accounts", []) if a.get("success")}

def count_keys():
    p = Path("output/keys.txt")
    if not p.exists(): return 0
    return len([l for l in p.read_text(encoding="utf-8").splitlines() if l.strip()])

def _first_key():
    p = Path("output/keys.txt")
    if not p.exists(): return ""
    for line in p.read_text(encoding="utf-8").splitlines():
        parts = line.split(":")
        if len(parts) >= 3 and parts[2].strip(): return parts[2].strip()
    return ""

def wait_key(prompt="Press Enter to continue..."):
    console.print(f"\n  {prompt}", end="")
    try: input()
    except: pass

def clear():
    os.system("cls" if os.name == "nt" else "clear")

# ─── Visual ───────────────────────────────────────────────────────────

def bar(percent, width=25):
    filled = int(width * min(percent, 1.0))
    empty = width - filled
    return f"{'=' * filled}{'-' * empty}"

def draw_dashboard():
    clear()
    state = load_state("output")
    accounts = state.get("accounts", [])
    ok = len([a for a in accounts if a.get("success")])
    fail = len([a for a in accounts if not a.get("success")])
    total = state.get("target", 0)
    keys = count_keys()
    db = find_9router_db()

    # Banner
    console.print(Panel(
        Text("BLACKBOX.AI FARM", style="bold white", justify="center"),
        subtitle="AI Model Farm Tool v2.1 | 32 Free Models",
        box=box.DOUBLE,
        border_style="cyan",
        width=62,
    ))

    # Status line
    db_status = "Connected" if db else "Not found"
    console.print(f"  Keys: {keys}  |  Success: {ok}  |  Failed: {fail}  |  DB: {db_status}")
    console.print()

    # Progress
    if total > 0:
        pct = ok / total
        console.print(f"  Registration: [{bar(pct)}] {ok}/{total} ({int(pct*100)}%)")
    else:
        console.print("  Registration: No data yet")
    console.print()

    # Stats table
    stats = Table(box=box.SIMPLE, show_header=False, padding=(0, 3), width=62)
    stats.add_column("k", style="dim", width=20)
    stats.add_column("v", justify="right", width=10)
    stats.add_row("Target", str(total))
    stats.add_row("Success", str(ok))
    stats.add_row("Failed", str(fail))
    stats.add_row("Keys", str(keys))
    console.print(stats)
    console.print()

    # Recent activity
    recent = accounts[-20:] if accounts else []
    if recent:
        chart = " ".join(["#" if a.get("success") else "X" for a in recent])
        console.print(f"  Last {len(recent)} runs: [{chart}]  # = OK  X = FAIL")
        console.print()

    # Menu
    console.print("  MAIN MENU")
    console.print("  " + "-" * 58)
    console.print("  1  REGISTER      Register new accounts and harvest API keys")
    console.print("  2  TEST MODELS   Check which AI models are working")
    console.print("  3  VIEW KEYS     Show all harvested API keys")
    console.print("  4  EXPORT        Export keys to file (TXT/JSON/CSV)")
    console.print("  5  INJECT DB     Push keys into provider database")
    console.print("  6  STATUS        Show detailed registration history")
    console.print("  7  QUIT          Exit application")
    console.print("  " + "-" * 58)

# ─── Main Menu ────────────────────────────────────────────────────────

def main_menu():
    while True:
        draw_dashboard()
        try:
            raw = input("\n  Select [1-7]: ").strip()
        except (EOFError, KeyboardInterrupt):
            return "quit"
        if raw in ("1",): return "reg"
        elif raw in ("2",): return "test"
        elif raw in ("3",): return "keys"
        elif raw in ("4",): return "export"
        elif raw in ("5",): return "inject"
        elif raw in ("6",): return "status"
        elif raw in ("7", "q", "x"): return "quit"

# ─── Register ─────────────────────────────────────────────────────────

def menu_register():
    count = 10
    workers = 3
    headless = True
    domain = "catchmail.io"
    state = load_state("output")
    done = len(done_emails(state))

    while True:
        clear()
        console.print(Panel("REGISTER ACCOUNTS", box=box.DOUBLE, border_style="green", width=62))
        if done > 0:
            console.print(f"  Previously completed: {done} accounts\n")

        console.print("  SETTINGS")
        console.print("  " + "-" * 58)
        console.print(f"  1  Count:       {count}")
        console.print(f"  2  Workers:     {workers}")
        console.print(f"  3  Headless:    {'ON' if headless else 'OFF'}")
        console.print(f"  4  Domain:      {domain}")
        console.print("  " + "-" * 58)
        console.print()
        console.print("  ACTIONS")
        console.print("  " + "-" * 58)
        console.print("  5  START NEW    Register fresh accounts")
        if done > 0:
            console.print(f"  6  RESUME       Continue from {done} previous accounts")
        console.print("  7  BACK         Return to main menu")
        console.print("  " + "-" * 58)

        try:
            raw = input("\n  Select: ").strip()
        except (EOFError, KeyboardInterrupt):
            return

        if raw == "1":
            val = input(f"  Count [{count}]: ").strip()
            if val.isdigit(): count = max(1, int(val))
        elif raw == "2":
            val = input(f"  Workers [{workers}]: ").strip()
            if val.isdigit(): workers = max(1, int(val))
        elif raw == "3":
            headless = not headless
        elif raw == "4":
            val = input(f"  Domain [{domain}]: ").strip()
            if val: domain = val
        elif raw == "5":
            _do_register(count, workers, headless, domain, resume=False)
            return
        elif raw == "6" and done > 0:
            _do_register(count, workers, headless, domain, resume=True)
            return
        elif raw in ("7", "q", "x", "b"):
            return

def _do_register(count, workers, headless, domain, resume=False):
    cfg = Config(max_workers=workers, headless=headless, tempmail_domain=domain)
    state = load_state(cfg.output_dir)

    if resume:
        already = done_emails(state)
        remaining = max(0, count - len(already))
        if remaining == 0:
            console.print(f"  All {count} accounts already done.")
            wait_key()
            return
        console.print(f"  Resuming: {len(already)} done, {remaining} remaining")
        count = remaining

    dashboard = FarmDashboard(total=count, max_workers=workers)
    dashboard.start()
    try:
        asyncio.run(_drive(cfg, count, dashboard, state))
    except KeyboardInterrupt:
        pass
    finally:
        dashboard.stop()
        accounts = state.get("accounts", [])
        ok = [a for a in accounts if a.get("success")]
        console.print(f"\n  Done: {len(ok)} succeeded, {len(accounts) - len(ok)} failed")

        if ok:
            db = find_9router_db()
            if db:
                try:
                    injected = inject_keys("output/keys.txt", str(db))
                    console.print(f"  Auto-injected {injected} keys to database")
                except Exception as e:
                    console.print(f"  Auto-inject failed: {e}")

        wait_key()

async def _drive(cfg, count, dashboard, state):
    sem = asyncio.Semaphore(cfg.max_workers)
    launched = 0
    tasks = []
    skip = done_emails(state)

    async def _account(wid, email, password):
        async with sem:
            result = AccountResult(email=email, password=password)
            start = time.monotonic()
            client = None
            try:
                dashboard.update_worker(wid, status="registering", email=email)
                client = BlackboxClient(cfg)
                await client.start()
                api_key = await client.register_and_create_key(email, password)
                result.api_key = api_key
                result.success = True
                dashboard.update_worker(wid, status="done", email=email)
            except Exception as e:
                result.error = str(e)[:200]
                dashboard.update_worker(wid, status="failed", error=result.error)
            finally:
                if client:
                    try: await client.stop()
                    except: pass
                result.elapsed = time.monotonic() - start
                record = {"email": result.email, "password": result.password,
                         "api_key": result.api_key, "success": result.success,
                         "error": result.error, "elapsed": round(result.elapsed, 2)}
                state["accounts"].append(record)
                state["target"] = count
                save_state(cfg.output_dir, state)
                if result.api_key:
                    append_key(cfg.output_dir, record)

    while launched < count:
        email = generate_email(cfg.tempmail_domain)
        while email in skip:
            email = generate_email(cfg.tempmail_domain)
        password = generate_password()
        tasks.append(asyncio.create_task(_account(launched % cfg.max_workers, email, password)))
        launched += 1
        await asyncio.sleep(secrets.SystemRandom().uniform(*cfg.delay_range))

    await asyncio.gather(*tasks, return_exceptions=True)

# ─── View Keys ────────────────────────────────────────────────────────

def menu_keys():
    clear()
    console.print(Panel("HARVESTED KEYS", box=box.DOUBLE, border_style="yellow", width=62))

    p = Path("output/keys.txt")
    if not p.exists():
        console.print("  No keys found. Run register first.")
        wait_key()
        return

    lines = [l for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    console.print(f"  Total: {len(lines)} keys\n")

    table = Table(box=box.ROUNDED, show_header=True, border_style="yellow")
    table.add_column("#", width=4, style="dim")
    table.add_column("Email", width=30)
    table.add_column("API Key", width=30, style="cyan")

    for i, line in enumerate(lines[:50], 1):
        parts = line.split(":")
        if len(parts) >= 3:
            table.add_row(str(i), parts[0][:28], parts[2][:25] + "...")

    if len(lines) > 50:
        console.print(f"  ... and {len(lines) - 50} more")

    console.print(table)
    wait_key()

# ─── Test Models ──────────────────────────────────────────────────────

def menu_test():
    clear()
    console.print(Panel("TEST MODELS", box=box.DOUBLE, border_style="blue", width=62))

    key = _first_key()
    if key:
        console.print(f"  Using key: {key[:20]}...")
    else:
        key = input("  API Key: ").strip()
        if not key:
            console.print("  No key provided")
            wait_key()
            return

    models = WORKING_MODELS[:32]
    console.print(f"\n  Testing {len(models)} models...\n")

    results = []
    ok_count = 0
    fail_count = 0

    # Test each model with live progress
    for i, model in enumerate(models, 1):
        # Show current test
        console.print(f"  [{i:2d}/{len(models)}] {model:<45}", end="")

        # Test model
        try:
            test_results = asyncio.run(test_all(key, [model]))
            if test_results and test_results[0].ok:
                console.print("[OK]")
                ok_count += 1
                results.append({"model": model, "ok": True})
            else:
                console.print("[FAIL]")
                fail_count += 1
                results.append({"model": model, "ok": False, "error": test_results[0].detail if test_results else "unknown"})
        except Exception as e:
            console.print(f"[ERR] {str(e)[:30]}")
            fail_count += 1
            results.append({"model": model, "ok": False, "error": str(e)[:50]})

        # Show progress bar
        pct = (i) / len(models)
        console.print(f"  Progress: [{bar(pct)}] {i}/{len(models)} ({int(pct*100)}%)\n")

    # Summary
    console.print("\n" + "=" * 62)
    console.print(f"  RESULTS: {ok_count} OK / {fail_count} FAIL")
    console.print(f"  Success Rate: [{bar(ok_count/len(models))}] {int(ok_count/len(models)*100)}%")
    console.print("=" * 62 + "\n")

    # Results table
    table = Table(box=box.ROUNDED, show_header=True, border_style="blue")
    table.add_column("Status", width=8)
    table.add_column("Model", width=40)
    for r in results:
        table.add_row("OK" if r["ok"] else "ERR", r["model"])
    console.print(table)

    # Save results
    Path("output").mkdir(exist_ok=True)
    Path("output/model_test.json").write_text(json.dumps({
        "ok": [r["model"] for r in results if r["ok"]],
        "fail": [{"model": r["model"], "error": r.get("error", "")} for r in results if not r["ok"]],
    }, indent=2), encoding="utf-8")
    wait_key()

# ─── Export ────────────────────────────────────────────────────────────

def menu_export():
    clear()
    console.print(Panel("EXPORT KEYS", box=box.DOUBLE, border_style="magenta", width=62))

    state = load_state("output")
    accounts = [a for a in state.get("accounts", []) if a.get("api_key")]
    if not accounts:
        console.print("  No successful accounts to export.")
        wait_key()
        return

    console.print(f"  {len(accounts)} accounts ready\n")
    console.print("  1  TXT        Plain text format")
    console.print("  2  JSON       Structured JSON")
    console.print("  3  CSV        Spreadsheet format")
    console.print("  4  ALL        Export all formats")
    console.print("  5  BACK       Return to main menu")

    try:
        raw = input("\n  Select: ").strip()
    except (EOFError, KeyboardInterrupt):
        return

    if raw in ("1", "2", "3", "4"):
        written = export_all("output", accounts)
        console.print()
        for fmt, path in written.items():
            console.print(f"  {fmt.upper()} -> {path}")
        wait_key()
    elif raw in ("5", "q", "x", "b"):
        return

# ─── Inject to Database ───────────────────────────────────────────────

def menu_inject():
    clear()
    console.print(Panel("INJECT TO DATABASE", box=box.DOUBLE, border_style="yellow", width=62))

    db = find_9router_db()
    if not db:
        console.print("  Database not found!")
        console.print("  Set PROVIDER_DB_PATH in .env file")
        wait_key()
        return

    p = Path("output/keys.txt")
    if not p.exists():
        console.print("  No keys to inject. Run register first.")
        wait_key()
        return

    lines = [l for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    existing = list_injected(str(db))

    while True:
        clear()
        console.print(Panel("INJECT TO DATABASE", box=box.DOUBLE, border_style="yellow", width=62))
        console.print(f"  DB: {db}")
        console.print(f"  Keys ready: {len(lines)}")
        console.print(f"  Already injected: {len(existing)}\n")
        console.print("  1  INJECT ALL     Push all keys to database")
        console.print("  2  VIEW INJECTED  Show keys already in database")
        console.print("  3  REMOVE ALL     Delete all keys from database")
        console.print("  4  BACK           Return to main menu")

        try:
            raw = input("\n  Select: ").strip()
        except (EOFError, KeyboardInterrupt):
            return

        if raw == "1":
            try:
                count = inject_keys("output/keys.txt", str(db))
                console.print(f"\n  Injected {count} new keys!")
                existing = list_injected(str(db))
            except Exception as e:
                console.print(f"\n  Error: {e}")
            wait_key()
        elif raw == "2":
            clear()
            console.print(Panel("INJECTED KEYS", box=box.DOUBLE, border_style="yellow", width=62))
            existing = list_injected(str(db))
            if not existing:
                console.print("  No keys in database.")
            else:
                table = Table(box=box.ROUNDED, show_header=True, border_style="yellow")
                table.add_column("#", width=4, style="dim")
                table.add_column("ID", width=25)
                table.add_column("Email", width=30)
                for i, row in enumerate(existing, 1):
                    table.add_row(str(i), row.get("id", "")[:23], row.get("email", "")[:28])
                console.print(table)
            wait_key()
        elif raw == "3":
            count = remove_keys(str(db))
            console.print(f"\n  Removed {count} keys.")
            existing = list_injected(str(db))
            wait_key()
        elif raw in ("4", "q", "x", "b"):
            return

# ─── Status ────────────────────────────────────────────────────────────

def menu_status():
    clear()
    console.print(Panel("RUN STATUS", box=box.DOUBLE, border_style="cyan", width=62))

    state = load_state("output")
    accounts = state.get("accounts", [])
    ok = [a for a in accounts if a.get("success")]
    failed = [a for a in accounts if not a.get("success")]

    stats = Table(box=box.SIMPLE, show_header=False, padding=(0, 3), width=62)
    stats.add_column("k", style="dim", width=20)
    stats.add_column("v", justify="right", width=10)
    stats.add_row("Target", str(state.get("target", 0)))
    stats.add_row("Success", str(len(ok)))
    stats.add_row("Failed", str(len(failed)))
    stats.add_row("Keys on disk", str(count_keys()))
    console.print(stats)

    if failed:
        console.print("\n  Recent failures:")
        for a in failed[-5:]:
            console.print(f"    {a.get('email', '?')[:28]}: {a.get('error', '?')[:40]}")

    wait_key()

# ─── Main ─────────────────────────────────────────────────────────────

def main():
    try:
        while True:
            choice = main_menu()
            if choice is None or choice == "quit":
                clear()
                console.print("\n  Goodbye!\n")
                break
            elif choice == "reg": menu_register()
            elif choice == "test": menu_test()
            elif choice == "keys": menu_keys()
            elif choice == "export": menu_export()
            elif choice == "inject": menu_inject()
            elif choice == "status": menu_status()
    except KeyboardInterrupt:
        clear()
        console.print("\n  Goodbye!\n")

if __name__ == "__main__":
    main()
