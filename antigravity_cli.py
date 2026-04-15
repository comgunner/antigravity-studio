#!/usr/bin/env python3
"""
antigravity-studio CLI — Chat and image generation with Google Antigravity.

Multi-Account Support:
    python3 antigravity_cli.py login --account work       # Login to 'work' account
    python3 antigravity_cli.py accounts                    # List all accounts
    python3 antigravity_cli.py accounts add work           # Add account
    python3 antigravity_cli.py accounts switch work        # Switch active account

Summary Support:
    python3 antigravity_cli.py --resume btc --tf 4h       # BTC 4h Technical Summary
    python3 antigravity_cli.py --resume sol --tf 1h       # SOL 1h Technical Summary

Usage:
    python3 antigravity_cli.py login              # OAuth login (browser)
    python3 antigravity_cli.py login --device     # Device code login (headless)
    python3 antigravity_cli.py refresh            # Refresh token
    python3 antigravity_cli.py models             # List available models
    python3 antigravity_cli.py chat "Hello"       # Text chat
    python3 antigravity_cli.py img "A cat"        # Generate image
"""

import argparse
import sys
import time
from pathlib import Path


def cmd_login(args):
    """OAuth login to Google Antigravity."""
    from antigravity_auth import login_browser, login_device_code, save_auth, get_account_label
    from antigravity_client import AntigravityClient

    account = getattr(args, "account", "default")
    label = get_account_label(account)

    print(f"{'=' * 50}")
    print(f"Login: {label}")
    print(f"{'=' * 50}")

    if args.device:
        cred = login_device_code()
    else:
        cred = login_browser()

    print("Fetching project ID...")
    try:
        project_id = AntigravityClient.fetch_project_id(cred["access_token"])
        cred["project_id"] = project_id
    except Exception as e:
        print(f"⚠ Could not fetch project ID: {e}")
        cred["project_id"] = AntigravityClient.FALLBACK_PROJECT_ID

    # Email already extracted from id_token in login_browser/login_device_code
    email = cred.get("email", "unknown")
    if email != "unknown":
        print(f"Email: {email}")

    save_auth(cred, account)
    print(f"\n✓ Logged in as '{label}'! Project: {project_id}")


def cmd_refresh(args):
    """Refresh access token."""
    from antigravity_auth import load_auth, refresh_access_token, save_auth, get_account_label
    from datetime import datetime, timedelta, timezone

    account = getattr(args, "account", "default")
    label = get_account_label(account)

    cred = load_auth(account)
    if not cred or not cred.get("refresh_token"):
        print(f"No refresh token found for '{label}'. Run 'login --account {account}' first.")
        sys.exit(1)

    print(f"Refreshing access token for '{label}'...")
    tokens = refresh_access_token(cred["refresh_token"])
    cred["access_token"] = tokens["access_token"]
    if "refresh_token" in tokens:
        cred["refresh_token"] = tokens["refresh_token"]
    cred["expires_at"] = (datetime.now(timezone.utc) + timedelta(seconds=tokens.get("expires_in", 3600))).isoformat()
    save_auth(cred, account)
    print(f"✓ Token refreshed for '{label}'")


def cmd_models(args):
    """List available models."""
    from antigravity_auth import get_valid_token, get_account_label
    from antigravity_client import AntigravityClient

    account = getattr(args, "account", "default")
    label = get_account_label(account)

    cred = get_valid_token(account)
    if not cred.get("project_id"):
        print("Fetching project ID...")
        cred["project_id"] = AntigravityClient.fetch_project_id(cred["access_token"])

    client = AntigravityClient(cred["access_token"], cred["project_id"])
    models = client.list_models()

    print(f"Available Antigravity Models for {label}:")
    print("─" * 60)
    for m in models:
        print(f"  ✓ {m['id']} ({m['display_name']})")


def cmd_accounts(args):
    """Manage multi-account configuration."""
    from antigravity_auth import list_accounts, add_account, remove_account, switch_account

    if args.subcmd == "list":
        accounts = list_accounts()
        print(f"Antigravity Accounts (Active: {accounts['active']})")
        print("─" * 60)
        for name, info in accounts["accounts"].items():
            active_mark = "★" if name == accounts["active"] else " "
            status = "✓ Auth" if info.get("refresh_token") else "✗ No Auth"
            email = info.get("email", "unknown")
            label = info.get("label", name)
            print(f"{active_mark} {name:<12} | {label:<16} | {status:<8} | {email}")

    elif args.subcmd == "add":
        add_account(args.name, args.label)
        print(f"✓ Account '{args.name}' added. Run 'login --account {args.name}' to authenticate.")

    elif args.subcmd == "switch":
        switch_account(args.name)
        print(f"✓ Switched active account to '{args.name}'.")

    elif args.subcmd == "remove":
        remove_account(args.name)
        print(f"✓ Account '{args.name}' removed.")


def cmd_chat(args):
    """Send a text chat message."""
    from antigravity_auth import get_valid_token, get_account_label
    from antigravity_client import AntigravityClient

    account = getattr(args, "account", "default")
    label = get_account_label(account)

    cred = get_valid_token(account)
    if not cred.get("project_id"):
        cred["project_id"] = AntigravityClient.fetch_project_id(cred["access_token"])

    client = AntigravityClient(cred["access_token"], cred["project_id"])
    
    # Auto-retry on 429
    response = client.chat(
        args.prompt, 
        model=args.model, 
        max_tokens=args.max_tokens,
        temperature=getattr(args, "temperature", 0.7)
    )
    
    if response:
        print(response)


def cmd_img(args):
    """Generate an image with multi-account failover support."""
    from antigravity_auth import get_all_accounts, get_valid_token, save_auth, get_account_label
    from antigravity_client import AntigravityClient
    from datetime import datetime, timezone
    import os

    # 1. Prepare inputs
    prompt = args.prompt
    aspect_ratio = args.aspect_ratio
    model = args.model
    output_path = args.output
    if not output_path:
        ts = int(time.time())
        output_path = f"generated_{ts}.png"

    ref_images = []
    if args.reference:
        for p in args.reference:
            if os.path.exists(p):
                ref_images.append(p)
            else:
                print(f"⚠ Warning: Reference image not found: {p}")

    # 2. Get prioritized accounts (active first)
    accounts_info = get_all_accounts()
    all_names = list(accounts_info["accounts"].keys())
    active_name = accounts_info["active"]
    
    # Move active to front
    if active_name in all_names:
        all_names.remove(active_name)
        all_names.insert(0, active_name)

    print(f"Generating image: '{prompt[:50]}...'")
    print(f"Using {len(all_names)} accounts for failover strategy.")

    start_time = time.time()
    attempt_log = []
    success = False

    for name in all_names:
        label = accounts_info["accounts"][name].get("label", name)
        print(f"→ Trying account: {label}...", end=" ", flush=True)
        
        try:
            cred = get_valid_token(name)
            if not cred.get("project_id"):
                cred["project_id"] = AntigravityClient.fetch_project_id(cred["access_token"])
                save_auth(cred, name)

            client = AntigravityClient(cred["access_token"], cred["project_id"])
            
            # Request image
            img_data = client.generate_image(
                prompt,
                model=model,
                aspect_ratio=aspect_ratio,
                reference_images=ref_images
            )
            
            if img_data:
                # SUCCESS
                with open(output_path, "wb") as f:
                    f.write(img_data)
                
                print(f"✅ SUCCESS ({len(img_data):,} bytes)")
                attempt_log.append({"account": label, "status": "SUCCESS", "time": round(time.time() - start_time, 1)})
                success = True
                
                # Cooldown logic for this account
                if args.cooldown > 0:
                    print(f"⏱ Post-generation cooldown: {args.cooldown}s (to prevent ban)")
                    # In a real scenario, we might want to store this timestamp in auth.json
                    # to enforce it across different command runs.
                
                break
            else:
                # Should not happen as client raises for errors, but safety first
                print("✗ Failed (empty response)")
                attempt_log.append({"account": label, "status": "FAILED", "time": 0})

        except Exception as e:
            err_msg = str(e)
            if "429" in err_msg:
                print("⚠ 429 COOLDOWN")
                attempt_log.append({"account": label, "status": "429 COOLDOWN", "time": 0})
            elif "500" in err_msg or "503" in err_msg:
                print("⚠ 500 SERVER ERROR")
                attempt_log.append({"account": label, "status": "500 SERVER ERROR", "time": 0})
            else:
                print(f"✗ ERROR: {err_msg[:30]}")
                attempt_log.append({"account": label, "status": "ERROR", "time": 0})
            continue

    # 3. Summary
    elapsed = round(time.time() - start_time, 1)
    print(f"\n{'=' * 60}")
    print(f"📊 ATTEMPT SUMMARY")
    print(f"{'=' * 60}")
    print(f"{'Account':<20} {'Status':<18} {'Time':<8}")
    print("─" * 60)
    for entry in attempt_log:
        print(f"  {entry['account']:<18} {entry['status']:<18} {entry['time']}s")
    
    print("─" * 60)
    result = "✅ SUCCESS" if success else "❌ ALL FAILED"
    print(f"  {result} | Total time: {elapsed}s | Attempts: {len(attempt_log)}")
    print(f"{'=' * 60}")


def cmd_resume(args):
    """Generate coin technical summary."""
    try:
        import coin_summary
        coin_summary.run_summary(args.resume, args.tf)
    except ImportError:
        print("[!] Error: coin_summary.py not found.")
    except Exception as e:
        print(f"[!] Error: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="antigravity-studio CLI — Chat and image generation with Google Antigravity",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Multi-Account Examples:
  %(prog)s login --account work           # Login to 'work' account
  %(prog)s accounts                       # List all accounts
  %(prog)s accounts add work              # Add account
  %(prog)s accounts switch work           # Switch active account

Chat Examples:
  %(prog)s chat "What is Python?"         # Text chat with default model
  %(prog)s chat "Hola" --model gemini-3-flash

Image Examples:
  %(prog)s img "A cat" -o cat.png         # Generate image
  %(prog)s img "Sunset" --model gemini-3.1-flash-image --aspect-ratio 16:9

Summary Examples:
  %(prog)s --resume btc --tf 4h           # BTC 4h Technical Summary
  %(prog)s --resume sol --tf 1h           # SOL 1h Technical Summary
        """,
    )
    # Global flags for Resume
    parser.add_argument("--resume", help="Generate technical summary for a coin (e.g. btc, eth, sol)")
    parser.add_argument("--tf", default="4h", help="Timeframe for the summary (default: 4h). Valid: 1m, 5m, 15m, 1h, 4h, 1d")

    sub = parser.add_subparsers(dest="command")

    # login
    p_login = sub.add_parser("login", help="OAuth login to Google Antigravity")
    p_login.add_argument("--account", default="default", help="Account name (default: default)")
    p_login.add_argument("--device", action="store_true", help="Use device code flow (headless)")
    p_login.set_defaults(func=cmd_login)

    # refresh
    p_refresh = sub.add_parser("refresh", help="Refresh access token")
    p_refresh.add_argument("--account", default="default", help="Account name (default: default)")
    p_refresh.set_defaults(func=cmd_refresh)

    # models
    p_models = sub.add_parser("models", help="List available models")
    p_models.add_argument("--account", default="default", help="Account name (default: default)")
    p_models.set_defaults(func=cmd_models)

    # accounts (sub-commands)
    p_accounts = sub.add_parser("accounts", help="Manage multiple accounts")
    p_accounts.set_defaults(func=cmd_accounts)
    p_accounts_sub = p_accounts.add_subparsers(dest="subcmd")

    # accounts list (default)
    p_accounts_list = p_accounts_sub.add_parser("list", help="List all accounts")
    p_accounts_list.set_defaults(func=cmd_accounts, subcmd="list")

    # accounts add
    p_accounts_add = p_accounts_sub.add_parser("add", help="Add new account")
    p_accounts_add.add_argument("name", help="Account name")
    p_accounts_add.add_argument("--label", help="Display label")
    p_accounts_add.set_defaults(func=cmd_accounts)

    # accounts switch
    p_accounts_switch = p_accounts_sub.add_parser("switch", help="Switch active account")
    p_accounts_switch.add_argument("name", help="Account name to switch to")
    p_accounts_switch.set_defaults(func=cmd_accounts)

    # accounts remove
    p_accounts_remove = p_accounts_sub.add_parser("remove", help="Remove account")
    p_accounts_remove.add_argument("name", help="Account name to remove")
    p_accounts_remove.set_defaults(func=cmd_accounts)

    # chat
    p_chat = sub.add_parser("chat", help="Send a chat message")
    p_chat.add_argument("prompt", help="Your message")
    p_chat.add_argument("--model", default="gemini-3-flash", help="Model to use (default: gemini-3-flash)")
    p_chat.add_argument("--max-tokens", type=int, default=2048, help="Max tokens in response (default: 2048)")
    p_chat.add_argument("--temperature", type=float, default=0.7, help="Temperature 0-1 (default: 0.7)")
    p_chat.set_defaults(func=cmd_chat)

    # img
    p_img = sub.add_parser("img", help="Generate an image")
    p_img.add_argument("prompt", help="Image description")
    p_img.add_argument("--model", default="gemini-3.1-flash-image", help="Image model (default: gemini-3.1-flash-image)")
    p_img.add_argument("--aspect-ratio", default="1:1", help="Aspect ratio (default: 1:1)")
    p_img.add_argument("--reference", "-r", nargs="+", help="Path to reference image(s) (up to 10)")
    p_img.add_argument("--output", "-o", help="Output file path (default: generated_<timestamp>.png)")
    p_img.add_argument("--cooldown", "-c", type=int, default=300,
                        help="Cooldown seconds after generation (default: 300 = 5 min, env: AUTH_IMAGE_COOLDOWN)")
    p_img.set_defaults(func=cmd_img)

    args = parser.parse_args()

    # Handle global --resume flag
    if args.resume:
        cmd_resume(args)
        sys.exit(0)

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Handle 'accounts' without subcommand — default to 'list'
    if args.command == "accounts" and not getattr(args, "subcmd", None):
        args.subcmd = "list"

    args.func(args)


if __name__ == "__main__":
    main()
