#!/usr/bin/env python3
"""Helper script to list available domains from Cloudflare Workers temp email."""
import asyncio
import httpx

from dotenv import load_dotenv
load_dotenv()

from config import Config


async def list_domains():
    api_url = Config().cloudflare_api_url
    
    print("🔍 Testing Cloudflare Workers Temp Email API...\n")
    
    async with httpx.AsyncClient(timeout=10) as client:
        print("Creating test address with empty domain (auto-detect)...")
        resp = await client.post(
            f"{api_url}/api/new_address",
            json={"name": "", "domain": "", "cf_token": "", "enableRandomSubdomain": False}
        )
        
        if resp.status_code == 200:
            data = resp.json()
            email = data.get("address", "")
            domain = email.split("@")[-1] if "@" in email else ""
            
            print(f"✅ Success!")
            print(f"   Test Email: {email}")
            print(f"   Auto-detected Domain: {domain}")
            print(f"\n💡 Tips:")
            print(f"   - Leave domain empty for auto-detection")
            print(f"   - Or manually set domain to: {domain}")
            print(f"   - Check your Cloudflare Workers for more domains")
        else:
            print(f"❌ Failed: {resp.status_code} {resp.text}")

if __name__ == "__main__":
    asyncio.run(list_domains())
