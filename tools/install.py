#!/usr/bin/env python3
"""Fresh install only. Default is a plan; staging never invokes host services."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

from fetch_gatt import ROOT, verify


def payload():
    dependency = ROOT / '.deps/core/ble_dbus.py'
    if not dependency.is_file():
        raise ValueError('Run python3 tools/fetch_gatt.py first')
    verify(dependency.read_bytes())
    files = {f'opt/projector-bridge/{p.name}': p for p in (ROOT / 'runtime').glob('*.py')}
    files.update({
        'opt/projector-bridge/core/ble_dbus.py': dependency,
        'opt/projector-bridge/requirements.txt': ROOT / 'requirements.txt',
        'opt/projector-bridge/projectorctl.py': ROOT / 'tools/projectorctl.py',
        'etc/projector-bridge/bridge.env': ROOT / 'deploy/bridge.env.example',
        'etc/systemd/system/projector-ble.service': ROOT / 'deploy/projector-ble.service',
        'opt/projector-bridge/mqtt/compose.yaml': ROOT / 'deploy/mqtt/compose.yaml',
        'opt/projector-bridge/mqtt/mosquitto.conf': ROOT / 'deploy/mqtt/mosquitto.conf',
    })
    return files


def install_files(destination):
    destination = destination.resolve()
    files = payload()
    # Check the whole plan before writing anything. Never merge into an old install.
    for reserved in ('opt/projector-bridge', 'etc/projector-bridge',
                     'etc/systemd/system/projector-ble.service',
                     'etc/systemd/system/projector-ble.service.d',
                     'var/lib/projector-ble'):
        path = destination / reserved
        if path.exists() or path.is_symlink():
            raise FileExistsError(f'Existing installation or state: {path}; nothing written')
    for name, source in files.items():
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        target.chmod(0o600 if name.endswith('bridge.env') else 0o644)
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--stage', type=Path, help='Write a fresh filesystem tree here; no pip/systemd/Docker calls')
    group.add_argument('--apply', action='store_true', help='Install on this host; does not start services')
    args = parser.parse_args()
    if args.stage:
        if args.stage.resolve() == Path('/'):
            parser.error('Use --apply to install on the host')
        files = install_files(args.stage)
        print(f'Staged {len(files)} files in {args.stage.resolve()}; no services changed')
    elif args.apply:
        if sys.platform != 'linux' or os.geteuid() != 0:
            parser.error('--apply requires root on Linux')
        if subprocess.run(['/usr/bin/systemctl', 'is-active', '--quiet', 'projector-ble.service']).returncode == 0:
            parser.error('A projector bridge is already running; nothing changed')
        # Verify Ubuntu's system modules before writing any installation files.
        subprocess.run(['/usr/bin/python3', '-c', 'import dbus; from gi.repository import GLib'], check=True)
        install_files(Path('/'))
        subprocess.run(['/usr/bin/python3', '-m', 'venv', '--system-site-packages', '/opt/projector-bridge/.venv'], check=True)
        subprocess.run(['/opt/projector-bridge/.venv/bin/python', '-m', 'pip', 'install', '-r', '/opt/projector-bridge/requirements.txt'], check=True)
        subprocess.run(['/usr/bin/systemctl', 'daemon-reload'], check=True)
        print('Installed. No service started. Follow docs/install.md to activate and pair.')
    else:
        for name in payload():
            print('/' + name)
        print('Plan only. Use --stage DIR for a review copy, or sudo ... --apply on a fresh host.')


if __name__ == '__main__':
    main()
