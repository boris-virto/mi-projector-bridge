#!/usr/bin/env python3
"""Read-only preflight for the supported single-adapter, same-host topology."""
import argparse
import socket
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before-start', action='store_true', help='Also require the dedicated MQTT port to be free')
    args = parser.parse_args()
    import dbus
    bus = dbus.SystemBus()
    manager = dbus.Interface(bus.get_object('org.bluez', '/'), 'org.freedesktop.DBus.ObjectManager')
    adapters = [(str(p), interfaces['org.bluez.Adapter1'], interfaces)
                for p, interfaces in manager.GetManagedObjects().items()
                if 'org.bluez.Adapter1' in interfaces]
    if len(adapters) != 1:
        raise SystemExit('This snapshot supports exactly one Bluetooth adapter; do not guess on a shared multi-adapter host')
    path, props, interfaces = adapters[0]
    print('Adapter:', path, 'public identity:', props['Address'], 'alias:', props['Alias'])
    print('Class:', hex(int(props['Class'])))
    if not props.get('Powered'):
        raise SystemExit('Adapter is powered off; review why before changing shared settings')
    for required in ('org.bluez.GattManager1', 'org.bluez.LEAdvertisingManager1'):
        if required not in interfaces:
            raise SystemExit('Missing BlueZ interface: ' + required)
    subprocess.run(['/usr/bin/docker', 'compose', 'version'], check=True)
    if args.before_start:
        with socket.socket() as probe:
            try:
                probe.bind(('127.0.0.1', 1883))
            except OSError:
                raise SystemExit('127.0.0.1:1883 is occupied. Do not replace an existing MQTT broker')
        existing = subprocess.check_output(['/usr/bin/docker', 'ps', '-a', '--filter', 'name=^/projector-mqtt$', '--format', '{{.Names}}'], text=True).strip()
        if existing:
            raise SystemExit('Container projector-mqtt already exists; review it rather than taking it over')
    print('Preflight passed. This is not a hardware wake test; no Bluetooth setting changed.')


if __name__ == '__main__':
    main()
