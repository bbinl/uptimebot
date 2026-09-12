import os
import sys
import time
import requests
import asyncio
from datetime import datetime
from contextlib import asynccontextmanager
from typing import Dict

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

# Safe terminal encoding
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# ==========================================
# ⚙️ CONFIGURATION
# ==========================================
TARGET_URL = os.getenv("TARGET_URL", "https://nuphi.onrender.com/")
CHECK_INTERVAL_SECONDS = int(os.getenv("CHECK_INTERVAL_SECONDS", 120))  # ২ মিনিট (120s)
TIMEOUT_SECONDS = int(os.getenv("TIMEOUT_SECONDS", 30))                 # সর্বোচ্চ ৩০ সেকেন্ড অপেক্ষা
MAX_RETRY_WINDOW_SECONDS = 30
RETRY_DELAY_SECONDS = 5

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

LATEST_STATUS = {
    "url": TARGET_URL,
    "last_checked": None,
    "is_up": False,
    "status_code": None,
    "response_time_ms": None,
    "error": None,
    "total_checks": 0
}

# ==========================================
# 🔍 CHECK FUNCTION
# ==========================================
def check_single_attempt(url: str, timeout: int = 30) -> Dict:
    start_time = time.time()
    try:
        response = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        response_time = round((time.time() - start_time) * 1000, 2)
        is_up = (200 <= response.status_code < 400)
        return {
            "is_up": is_up,
            "status_code": response.status_code,
            "response_time_ms": response_time,
            "error": None
        }
    except requests.exceptions.Timeout:
        return {
            "is_up": False,
            "status_code": None,
            "response_time_ms": None,
            "error": f"Timeout (Website did not respond within {timeout}s)"
        }
    except requests.exceptions.RequestException as e:
        return {
            "is_up": False,
            "status_code": None,
            "response_time_ms": None,
            "error": str(e)
        }

def monitor_url_with_30s_wait(url: str) -> Dict:
    start_window = time.time()
    attempt = 1

    while True:
        elapsed = time.time() - start_window
        remaining_time = max(1, int(TIMEOUT_SECONDS - elapsed))
        
        result = check_single_attempt(url, timeout=min(30, remaining_time))
        
        if result["is_up"]:
            result["attempts"] = attempt
            result["wait_duration"] = round(time.time() - start_window, 2)
            return result

        if (time.time() - start_window) >= MAX_RETRY_WINDOW_SECONDS:
            result["attempts"] = attempt
            result["wait_duration"] = round(time.time() - start_window, 2)
            return result

        print(f"   [WAIT] [{datetime.now().strftime('%H:%M:%S')}] Attempt {attempt} failed. Retrying... (Waiting up to 30s)")
        time.sleep(RETRY_DELAY_SECONDS)
        attempt += 1

# ==========================================
# 🔄 BACKGROUND WORKER LOOP
# ==========================================
async def background_monitoring_loop():
    await asyncio.sleep(2) # Initial brief delay
    print("=" * 60)
    print("🤖 UPTIME ROBOT WORKER STARTED")
    print(f"🎯 Target: {TARGET_URL}")
    print(f"⏱️ Timeout: {TIMEOUT_SECONDS}s | Interval: {CHECK_INTERVAL_SECONDS}s")
    print("=" * 60)

    loop = asyncio.get_running_loop()
    while True:
        try:
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"\n[Scan Cycle: {current_time}] Checking {TARGET_URL}...")

            # Run synchronous requests in thread pool
            result = await loop.run_in_executor(None, monitor_url_with_30s_wait, TARGET_URL)

            LATEST_STATUS["last_checked"] = current_time
            LATEST_STATUS["is_up"] = result["is_up"]
            LATEST_STATUS["status_code"] = result["status_code"]
            LATEST_STATUS["response_time_ms"] = result["response_time_ms"]
            LATEST_STATUS["error"] = result["error"]
            LATEST_STATUS["total_checks"] += 1

            if result["is_up"]:
                print(
                    f"   ✅ [UP] Status: {result['status_code']} | "
                    f"Time: {result['response_time_ms']}ms | "
                    f"Attempts: {result['attempts']} | "
                    f"Wait: {result['wait_duration']}s"
                )
            else:
                print(
                    f"   ❌ [DOWN] Error: {result['error']} | "
                    f"Attempts: {result['attempts']} | "
                    f"Wait: {result['wait_duration']}s"
                )

        except Exception as e:
            print(f"Error in monitor loop: {e}")

        await asyncio.sleep(CHECK_INTERVAL_SECONDS)

# ==========================================
# 🚀 FASTAPI APP LIFECYCLE
# ==========================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start the uptime robot background task
    task = asyncio.create_task(background_monitoring_loop())
    yield
    task.cancel()

app = FastAPI(title="Uptime Robot", lifespan=lifespan)

@app.get("/", response_class=HTMLResponse)
async def home():
    status_text = "UP" if LATEST_STATUS['is_up'] else "DOWN / STARTING"
    status_color = "#22c55e" if LATEST_STATUS['is_up'] else "#ef4444"
    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta http-equiv="refresh" content="30">
    <title>Uptime Robot</title>
</head>
<body style="font-family: Arial, sans-serif; background: #0f172a; color: #f8fafc; padding: 40px; line-height: 1.6;">
    <h2>🤖 Uptime Robot Status</h2>
    <p><strong>Target:</strong> <a href="{LATEST_STATUS['url']}" style="color: #38bdf8;" target="_blank">{LATEST_STATUS['url']}</a></p>
    <p><strong>Status:</strong> <span style="color:{status_color}; font-weight:bold;">{status_text}</span></p>
    <p><strong>Last Checked:</strong> {LATEST_STATUS['last_checked'] or 'Starting initial scan...'}</p>
    <p><strong>Status Code:</strong> {LATEST_STATUS['status_code'] or 'N/A'}</p>
    <p><strong>Response Time:</strong> {LATEST_STATUS['response_time_ms']} ms</p>
    <p><strong>Total Checks:</strong> {LATEST_STATUS['total_checks']}</p>
    <hr style="border: 0.5px solid #334155; margin: 20px 0;">
    <p style="color: #94a3b8; font-size: 13px;">Auto-pinging every {CHECK_INTERVAL_SECONDS}s with 30s wake-up timeout.</p>
</body>
</html>"""

@app.get("/health")
async def health():
    return {"status": "ok", "uptime_robot": LATEST_STATUS}

if __name__ == "__main__":
    import uvicorn
    raw_port = os.getenv("PORT", "8080")
    digits = ''.join(c for c in str(raw_port) if c.isdigit())
    port = int(digits) if digits else 8080
    print(f"🚀 Starting Uvicorn on port {port}...")
    uvicorn.run("main:app", host="0.0.0.0", port=port)
