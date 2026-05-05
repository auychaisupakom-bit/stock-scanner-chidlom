"""
ส่งแจ้งเตือนยาใกล้หมดอายุ (≤ 6 เดือน) เข้ากลุ่ม LINE
รันโดย GitHub Actions ทุกวันที่ 1 ของเดือน
"""
import os
import sys
import json
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

# ─── อ่าน secrets จาก environment ─────────────────────────────
LINE_TOKEN = os.environ.get('LINE_TOKEN', '').strip()
LINE_GROUP_ID = os.environ.get('LINE_GROUP_ID', '').strip()
FIREBASE_URL = os.environ.get('FIREBASE_URL', '').strip()
HTML_URL = os.environ.get('HTML_URL', '').strip()  # URL ของไฟล์ HTML ใน GitHub Pages

if not all([LINE_TOKEN, LINE_GROUP_ID, HTML_URL]):
    print('❌ Missing required environment variables')
    sys.exit(1)

# ─── ใช้ Bangkok timezone ──────────────────────────────────────
BKK = timezone(timedelta(hours=7))
now = datetime.now(BKK)
print(f'⏰ Run at {now.strftime("%Y-%m-%d %H:%M:%S")} (Bangkok)')

# ─── ดึงข้อมูล EXPIRY_MAP + EMBEDDED_SKU_MAP จาก HTML ที่ deploy ──
print(f'📥 Fetching HTML from {HTML_URL}')
try:
    req = urllib.request.Request(HTML_URL, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=30) as resp:
        html = resp.read().decode('utf-8')
except Exception as e:
    print(f'❌ Cannot fetch HTML: {e}')
    sys.exit(1)

# parse EMBEDDED_SKU_MAP
import re
m = re.search(r'const EMBEDDED_SKU_MAP = (\{.*?\});', html, re.DOTALL)
if not m:
    print('❌ Cannot find EMBEDDED_SKU_MAP in HTML')
    sys.exit(1)
sku_map = json.loads(m.group(1))

# parse EXPIRY_MAP
m = re.search(r'const EXPIRY_MAP = (\{.*?\});', html, re.DOTALL)
if not m:
    print('❌ Cannot find EXPIRY_MAP in HTML')
    sys.exit(1)
expiry_map = json.loads(m.group(1))

print(f'✅ Loaded {len(sku_map)} SKUs, {len(expiry_map)} expiry entries')

# ─── หา SKU ที่ใกล้หมดอายุ (≤ 6 เดือน = 180 วัน) ─────────────────
THRESHOLD_DAYS = 180
now_ms = int(now.timestamp() * 1000)
threshold_ms = now_ms + (THRESHOLD_DAYS * 86400 * 1000)

near_expiry = []
expired = []

for sku, exp_ts in expiry_map.items():
    if sku not in sku_map:
        continue
    info = sku_map[sku]
    days_left = (exp_ts - now_ms) // (86400 * 1000)
    exp_date = datetime.fromtimestamp(exp_ts / 1000, BKK)

    item = {
        'sku': sku,
        'name': info.get('name', ''),
        'qty': info.get('systemQty', 0),
        'uom': info.get('uom', ''),
        'days_left': days_left,
        'exp_date': exp_date.strftime('%d/%m/%Y'),
    }

    if days_left <= 0:
        expired.append(item)
    elif days_left <= THRESHOLD_DAYS:
        near_expiry.append(item)

# Sort: หมดอายุก่อนขึ้นก่อน
expired.sort(key=lambda x: x['days_left'])
near_expiry.sort(key=lambda x: x['days_left'])

print(f'📊 Found: {len(expired)} expired, {len(near_expiry)} near-expiry (≤{THRESHOLD_DAYS} days)')

# ─── สร้างข้อความ ─────────────────────────────────────────────
month_name_th = ['', 'มกราคม','กุมภาพันธ์','มีนาคม','เมษายน','พฤษภาคม','มิถุนายน',
                 'กรกฎาคม','สิงหาคม','กันยายน','ตุลาคม','พฤศจิกายน','ธันวาคม']
header = f'🏥 รายงานยาใกล้หมดอายุ\n📍 ร้านชิดลม\n📅 {month_name_th[now.month]} {now.year + 543}\n'

if not expired and not near_expiry:
    body = '\n✅ เดือนนี้ไม่มียาที่ใกล้หมดอายุ\n(ยาทั้งหมดยังมีอายุมากกว่า 6 เดือน)'
    msg = header + body
else:
    parts = [header]
    if expired:
        parts.append(f'\n🔴 หมดอายุแล้ว ({len(expired)} รายการ)')
        for i, it in enumerate(expired[:20], 1):
            parts.append(f'{i}. {it["name"][:35]} | {it["exp_date"]} | คงเหลือ {it["qty"]} {it["uom"]}')
        if len(expired) > 20:
            parts.append(f'... และอีก {len(expired) - 20} รายการ')

    if near_expiry:
        parts.append(f'\n⚠️ ใกล้หมดอายุ ≤6 เดือน ({len(near_expiry)} รายการ)')
        for i, it in enumerate(near_expiry[:20], 1):
            parts.append(f'{i}. {it["name"][:35]} | {it["exp_date"]} (เหลือ {it["days_left"]} วัน) | คงเหลือ {it["qty"]} {it["uom"]}')
        if len(near_expiry) > 20:
            parts.append(f'... และอีก {len(near_expiry) - 20} รายการ')

    parts.append(f'\n👉 ดูทั้งหมดที่: {HTML_URL}')
    msg = '\n'.join(parts)

# LINE limit ต่อข้อความ ~5000 chars
if len(msg) > 4500:
    msg = msg[:4500] + '\n\n...(ตัดส่วนที่เหลือ)'

print(f'📝 Message length: {len(msg)} chars')
print('─' * 50)
print(msg)
print('─' * 50)

# ─── ส่งเข้า LINE ─────────────────────────────────────────────
data = json.dumps({
    'to': LINE_GROUP_ID,
    'messages': [{'type': 'text', 'text': msg}]
}).encode('utf-8')

req = urllib.request.Request(
    'https://api.line.me/v2/bot/message/push',
    data=data,
    headers={
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {LINE_TOKEN}',
    },
    method='POST'
)

try:
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = resp.read().decode('utf-8')
        print(f'✅ LINE API response: {resp.status} {result}')
except urllib.error.HTTPError as e:
    err = e.read().decode('utf-8')
    print(f'❌ LINE API error: {e.code} {err}')
    sys.exit(1)
except Exception as e:
    print(f'❌ Network error: {e}')
    sys.exit(1)

print('🎉 Done!')
