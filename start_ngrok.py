"""Keep ngrok tunnel alive for LINE webhook testing (固定域名)."""
import os
import signal
import sys
import time

from dotenv import load_dotenv
from pyngrok import conf, ngrok

load_dotenv(".env")
load_dotenv("secrets.private.env", override=True)

AUTHTOKEN = os.environ.get("NGROK_AUTHTOKEN", "")
NGROK_DOMAIN = os.environ.get("NGROK_DOMAIN", "")
PORT = int(os.environ.get("APP_PORT", "8000"))

if not AUTHTOKEN:
    raise RuntimeError("NGROK_AUTHTOKEN 未設定，請在 secrets.private.env 設定")
if not NGROK_DOMAIN:
    raise RuntimeError("NGROK_DOMAIN 未設定，請在 secrets.private.env 設定")

conf.get_default().auth_token = AUTHTOKEN
conf.get_default().region = 'ap'

tunnel = ngrok.connect(str(PORT), bind_tls=True, domain=NGROK_DOMAIN)
public_url = tunnel.public_url
if public_url and public_url.startswith("http://"):
    public_url = public_url.replace("http://", "https://", 1)

print(f"=== ngrok tunnel active (固定域名) ===")
print(f"Public URL: {public_url}")
print(f"Webhook URL: {public_url}/webhook")
print(f"Press Ctrl+C to stop")

def shutdown(sig, frame):
    print("\nShutting down ngrok...")
    ngrok.kill()
    sys.exit(0)

signal.signal(signal.SIGINT, shutdown)
signal.signal(signal.SIGTERM, shutdown)

# Keep alive
while True:
    time.sleep(1)
