import asyncio
import time

import requests
import websockets


BASE = 'http://127.0.0.1:8080/api/v1'


def login() -> str:
  s = requests.Session()
  r = s.post(
    f'{BASE}/auth/login',
    data={'username': 'admin', 'password': 'admin123'},
    timeout=15,
  )
  print('login', r.status_code)
  r.raise_for_status()
  token = r.json().get('access_token')
  if not token:
    raise RuntimeError('No access_token in response')
  return token


def smoke_http(token: str) -> None:
  hdr = {'Authorization': f'Bearer {token}'}
  s = requests.Session()
  for path in [
    '/users/me',
    '/dashboard/stats',
    '/dashboard/system-overview',
    '/dashboard/summary?period=day',
    '/pipeline/status',
  ]:
    rr = s.get(f'{BASE}{path}', headers=hdr, timeout=15)
    print(path, rr.status_code)
    rr.raise_for_status()
  print('pipeline_status', s.get(f'{BASE}/pipeline/status', headers=hdr, timeout=15).json())


async def smoke_ws(token: str) -> None:
  url = f'ws://127.0.0.1:8080/api/v1/pipeline/preview-stream?token={token}'
  t0 = time.time()
  try:
    async with websockets.connect(
      url,
      open_timeout=8,
      close_timeout=2,
      max_size=5_000_000,
    ) as ws:
      print('ws_open', True)
      first = None
      while time.time() - t0 < 6:
        try:
          msg = await asyncio.wait_for(ws.recv(), timeout=1)
        except asyncio.TimeoutError:
          continue
        if isinstance(msg, (bytes, bytearray)) and len(msg) > 0:
          first = len(msg)
          break
      print('ws_first_frame_bytes', first)
  except Exception as e:
    print('ws_open', False, type(e).__name__, str(e))


def main() -> None:
  token = login()
  smoke_http(token)
  asyncio.run(smoke_ws(token))


if __name__ == '__main__':
  main()

