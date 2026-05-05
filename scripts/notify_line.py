"""
ส่งแจ้งเตือนยาใกล้หมดอายุเข้ากลุ่ม LINE - แบบแสดง batch แยก
รันโดย GitHub Actions ทุกวันที่ 1 ของเดือน

เกณฑ์การแจ้งเตือนตามรหัส SKU:
  11xxx, 61xx -> เตือนเมื่อเหลือ <= 13 เดือน (390 วัน)
  12xxx, 14xxx, 62xx, 63xx, 64xx -> เตือนเมื่อเหลือ <= 10 เดือน (300 วัน)

แต่ละ batch ที่เข้าเกณฑ์จะแสดงแยกกันในรายงาน
"""
import os
import sys
import json
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

LINE_TOKEN = os.environ.get('LINE_TOKEN', '').strip()
LINE_GROUP_ID = os.environ.get('LINE_GROUP_ID', '').strip()
HTML_URL = os.environ.get('HTML_URL', '').strip()

if not all([LINE_TOKEN, LINE_GROUP_ID, HTML_URL]):
    print('Missing required environment variables')
    sys.exit(1)

BKK = timezone(timedelta(hours=7))
now = datetime.now(BKK)
print(f'Run at {now.strftime("%Y-%m-%d %H:%M:%S")} (Bangkok)')


def get_threshold(sku):
    """คืนค่าจำนวนวันสำหรับเริ่มแจ้งเตือน ตามรหัส SKU"""
    s = str(sku)
    if s.startswith('11'):
        return 390
    if s.startswith('12') or s.startswith('14'):
        return 300
    if s.startswith('61'):
        return 390
    if s.startswith('62') or s.startswith('63') or s.startswith('64'):
        return 300
    return 300


def get_group_key(sku):
    """ส่งคืน key ของกลุ่มสำหรับจัดหมวด"""
    s = str(sku)
    if s.startswith('11'):
        return '11'
    if s.startswith('12') or s.startswith('14'):
        return '12_14'
    if s.startswith('61'):
        return '61'
    if s.startswith('62') or s.startswith('63') or s.startswith('64'):
        return '62_64'
    return 'other'


# ดึงข้อมูลจาก HTML
print(f'Fetching HTML from {HTML_URL}')
try:
    req = urllib.request.Request(HTML_URL, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=30) as resp:
        html = resp.read().decode('utf-8')
except Exception as e:
    print(f'Cannot fetch HTML: {e}')
    sys.exit(1)

import re
m = re.search(r'const EMBEDDED_SKU_MAP = (\{.*?\});', html, re.DOTALL)
if not m:
    print('Cannot find EMBEDDED_SKU_MAP')
    sys.exit(1)
sku_map = json.loads(m.group(1))

# ดึง BATCHES_MAP (ใหม่) - ถ้าไม่มีให้ fallback ไปใช้ EXPIRY_MAP
m = re.search(r'const BATCHES_MAP = (\{.*?\});', html, re.DOTALL)
batches_map = {}
if m:
    batches_map = json.loads(m.group(1))
    print(f'Loaded BATCHES_MAP with {len(batches_map)} SKUs')
else:
    print('No BATCHES_MAP found, falling back to EXPIRY_MAP')
    m = re.search(r'const EXPIRY_MAP = (\{.*?\});', html, re.DOTALL)
    if m:
        expiry_map = json.loads(m.group(1))
        # Convert to batches structure
        for sku, ts in expiry_map.items():
            qty = sku_map.get(sku, {}).get('systemQty', 0)
            batches_map[sku] = [{'exp': ts, 'qty': qty, 'dateIn': None, 'batchBC': ''}]

print(f'Loaded {len(sku_map)} SKUs')

now_ms = int(now.timestamp() * 1000)

# แยกตามหมวด - แต่ละหมวดเก็บเป็น list ของ (sku_info, batch_info)
groups = {
    '11': {'name': '🏥 ยาองค์การเภสัชกรรม (11xxx)', 'months': '13 เดือน', 'items': []},
    '12_14': {'name': '💊 ยาผู้ผลิตอื่น/สมุนไพร (12xxx, 14xxx)', 'months': '10 เดือน', 'items': []},
    '61': {'name': '📦 หมวด 61xxx', 'months': '13 เดือน', 'items': []},
    '62_64': {'name': '📦 หมวด 62-64xxx', 'months': '10 เดือน', 'items': []},
    'other': {'name': '🔹 อื่นๆ', 'months': '10 เดือน', 'items': []},
}
expired_items = []

for sku, batches in batches_map.items():
    if sku not in sku_map:
        continue
    info = sku_map[sku]
    threshold = get_threshold(sku)
    name = info.get('name', '').split('\n')[0]
    uom = info.get('uom', '')

    for batch in batches:
        exp_ts = batch['exp']
        days_left = (exp_ts - now_ms) // (86400 * 1000)
        exp_date = datetime.fromtimestamp(exp_ts / 1000, BKK)
        qty = batch.get('qty', 0)
        date_in = batch.get('dateIn', None)

        item = {
            'sku': sku,
            'name': name,
            'qty': qty,
            'uom': uom,
            'days_left': days_left,
            'exp_date': exp_date.strftime('%d/%m/%Y'),
            'date_in': date_in,
        }

        if days_left <= 0:
            expired_items.append(item)
        elif days_left <= threshold:
            group_key = get_group_key(sku)
            groups[group_key]['items'].append(item)

# Sort each group by days_left ascending
for g in groups.values():
    g['items'].sort(key=lambda x: x['days_left'])
expired_items.sort(key=lambda x: x['days_left'])

total_near = sum(len(g['items']) for g in groups.values())
print(f'Found: {len(expired_items)} expired batches, {total_near} near-expiry batches')
for k, g in groups.items():
    if g['items']:
        print(f'   {k}: {len(g["items"])} batches')

month_th = ['', 'มกราคม','กุมภาพันธ์','มีนาคม','เมษายน','พฤษภาคม','มิถุนายน',
            'กรกฎาคม','สิงหาคม','กันยายน','ตุลาคม','พฤศจิกายน','ธันวาคม']

header = f'🏥 รายงานยาใกล้หมดอายุ\n📍 ร้านชิดลม\n📅 {month_th[now.month]} {now.year + 543}\n'


def format_item(it, idx):
    """สร้างบรรทัดสำหรับแต่ละ batch"""
    name_short = it['name'][:30]
    batch_info = ''
    if it['date_in']:
        # format date_in: 2025-02-28 -> 28/02/68
        try:
            d = datetime.strptime(it['date_in'], '%Y-%m-%d')
            batch_info = f' [Lot:{d.strftime("%d/%m/%y")}]'
        except Exception:
            pass
    return f'{idx}. {name_short}{batch_info}\n   หมด {it["exp_date"]} | คงเหลือ {it["qty"]} {it["uom"]}'


if not expired_items and total_near == 0:
    msg = header + '\n✅ เดือนนี้ไม่มียาที่ใกล้หมดอายุ\n(ยาทั้งหมดยังมีอายุเพียงพอที่จะส่งคืนคลังได้)'
else:
    parts = [header]

    if expired_items:
        parts.append(f'\n🔴 หมดอายุแล้ว ({len(expired_items)} batch)')
        for i, it in enumerate(expired_items[:10], 1):
            parts.append(format_item(it, i))
        if len(expired_items) > 10:
            parts.append(f'... และอีก {len(expired_items) - 10} batch')

    for key, g in groups.items():
        if not g['items']:
            continue
        parts.append(f'\n⚠️ {g["name"]}\n(เหลือ ≤{g["months"]}, {len(g["items"])} batch)')
        for i, it in enumerate(g['items'][:8], 1):
            parts.append(format_item(it, i))
        if len(g['items']) > 8:
            parts.append(f'... และอีก {len(g["items"]) - 8} batch ในหมวดนี้')

    parts.append(f'\n👉 ดูทั้งหมดที่:\n{HTML_URL}')
    msg = '\n'.join(parts)

if len(msg) > 4800:
    msg = msg[:4800] + '\n\n...(ตัดส่วนที่เหลือ - ดูในเว็บ)'

print(f'Message length: {len(msg)} chars')
print('-' * 50)
print(msg)
print('-' * 50)

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
        print(f'LINE API response: {resp.status} {result}')
except urllib.error.HTTPError as e:
    err = e.read().decode('utf-8')
    print(f'LINE API error: {e.code} {err}')
    sys.exit(1)
except Exception as e:
    print(f'Network error: {e}')
    sys.exit(1)

print('Done!')
