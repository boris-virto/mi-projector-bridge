#!/usr/bin/env python3
"""Fetch the one upstream module used at runtime, pinned by commit and SHA-256."""
import hashlib
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
COMMIT = '59e1504668643ef0c5dadbbb35550ee9fe22409a'
URL = f'https://raw.githubusercontent.com/artyomsoft/ble-hid-keyboard/{COMMIT}/core/ble_dbus.py'
SHA256 = '05b75c8bc2f8392e01d648d6e2c3a1b6e12e12412e576a9cba211630d50ce37d'


def verify(data):
    if hashlib.sha256(data).hexdigest() != SHA256:
        raise ValueError('Upstream GATT module hash mismatch; refusing to install')
    return data


def fetch():
    target = ROOT / '.deps/core/ble_dbus.py'
    if target.exists():
        verify(target.read_bytes())
        print('Pinned GATT dependency already verified')
        return
    with urllib.request.urlopen(URL, timeout=30) as response:
        data = verify(response.read(1024 * 1024))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    print('Downloaded and verified pinned GATT dependency')


if __name__ == '__main__':
    fetch()
