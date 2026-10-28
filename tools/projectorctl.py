#!/usr/bin/env python3
"""Root-only local control client. Pairing always requires an explicit code/device."""
import argparse
import json
import socket

SOCKET = '/run/projector-ble/control.sock'


def make_request(args):
    if args.action == 'status':
        return {'action': 'status'}
    if args.action == 'pair':
        if not 1 <= args.seconds <= 1200:
            raise ValueError('Pairing window must be 1..1200 seconds')
        return {'action': 'pairing', 'seconds': args.seconds}
    if args.action == 'close-pairing':
        return {'action': 'pairing', 'seconds': 0}
    if args.action == 'confirm':
        if not args.device.startswith('/org/bluez/hci') or '/dev_' not in args.device:
            raise ValueError('Use the full pending device path from status')
        if not args.code.isdigit() or len(args.code) != 6:
            raise ValueError('Code must be exactly six digits')
        return {'action': 'confirm', 'device': args.device, 'code': int(args.code)}
    return {'action': 'send', 'command': args.command}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    sub.add_parser('status')
    pair = sub.add_parser('pair')
    pair.add_argument('--seconds', type=int, default=300)
    sub.add_parser('close-pairing')
    confirm = sub.add_parser('confirm')
    confirm.add_argument('--device', required=True)
    confirm.add_argument('--code', required=True)
    send = sub.add_parser('send')
    send.add_argument('command', choices=['wake', 'sleep', 'power', 'home', 'back', 'enter', 'up', 'down', 'left', 'right'])
    args = parser.parse_args()
    try:
        request = make_request(args)
    except ValueError as e:
        parser.error(str(e))
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(12)
        client.connect(SOCKET)
        client.sendall(json.dumps(request).encode() + b'\n')
        data = b''
        while b'\n' not in data:
            chunk = client.recv(65536)
            if not chunk:
                raise RuntimeError('Bridge closed connection without a complete response')
            data += chunk
            if len(data) > 1024 * 1024:
                raise RuntimeError('Bridge response exceeds limit')
    result = json.loads(data)
    print(json.dumps(result, indent=2))
    if 'error' in result:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
