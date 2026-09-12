import os
import sys
import time
import requests
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime
from typing import Dict

# Safe print handling for Windows/Linux terminals
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# ==========================================
# ⚙️ CONFIGURATION / সেটিংস
# (Environment Variable অথবা ডিফল্ট ভ্যালু)
# ==========================================
TARGET_URL = os.getenv("TARGET_URL", "https://nuphi.onrender.com/")
CHECK_INTERVAL_SECONDS = int(os.getenv("CHECK_INTERVAL_SECONDS", 120))  # ২ মিনিট (120s)
TIMEOUT_SECONDS = int(os.getenv("TIMEOUT_SECONDS", 30))                 # সর্বোচ্চ ৩০ সেকেন্ড ওয়েট
MAX_RETRY_WINDOW_SECONDS = 30
RETRY_DELAY_SECONDS = 5

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# সর্বশেষ চেকিং স্ট্যাটাস
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
# 🌐 HEALTH SERVER (Railway Health Check)
# ==========================================
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        status_text = "UP" if LATEST_STATUS['is_up'] else "DOWN / STARTING"
        status_color = "#22c55e" if LATEST_STATUS['is_up'] else "#ef4444"
        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta http-equiv="refresh" content="30">
    <title>Uptime Robot</title>
</head>
<body style="font-family: Arial, sans-serif; background: #0f172a; color: #f8fafc; padding: 40px; line-height: 1.6;">
    <h2>[ Uptime Robot Status ]</h2>
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
        self.wfile.write(html.encode("utf-8"))

    def log_message(self, format, *args):
        pass

def start_health_server(port: int):
    try:
        server = HTTPServer(("0.0.0.0", port), HealthHandler)
        server.serve_forever()
    except Exception as e:
        print(f"[!] Server error on port {port}: {e}")

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
# 🚀 MAIN LOOP
# ==========================================
def main():
    port = int(os.getenv("PORT", 8080))
    server_thread = threading.Thread(target=start_health_server, args=(port,), daemon=True)
    server_thread.start()

    print("=" * 60)
    print("UPTIME ROBOT (Railway Ready)")
    print("=" * 60)
    print(f"Target URL: {TARGET_URL}")
    print(f"Timeout / Retry Wait Limit: {TIMEOUT_SECONDS}s")
    print(f"Check Interval: {CHECK_INTERVAL_SECONDS}s")
    print(f"Health Server running on port: {port}")
    print("=" * 60)

    try:
        while True:
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"\n[Scan Cycle: {current_time}]")
            print(f"Checking: {TARGET_URL}")

            result = monitor_url_with_30s_wait(TARGET_URL)

            # স্ট্যাটাস আপডেট
            LATEST_STATUS["last_checked"] = current_time
            LATEST_STATUS["is_up"] = result["is_up"]
            LATEST_STATUS["status_code"] = result["status_code"]
            LATEST_STATUS["response_time_ms"] = result["response_time_ms"]
            LATEST_STATUS["error"] = result["error"]
            LATEST_STATUS["total_checks"] += 1

            if result["is_up"]:
                print(
                    f"   [UP] Status: {result['status_code']} | "
                    f"Response Time: {result['response_time_ms']}ms | "
                    f"Attempts: {result['attempts']} | "
                    f"Total Wait: {result['wait_duration']}s"
                )
            else:
                print(
                    f"   [DOWN] Error: {result['error']} | "
                    f"Attempts: {result['attempts']} | "
                    f"Total Wait: {result['wait_duration']}s"
                )

            print(f"Sleeping for {CHECK_INTERVAL_SECONDS} seconds...")
            time.sleep(CHECK_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        print("\nUptime Robot stopped by user.")

if __name__ == "__main__":
    main()
