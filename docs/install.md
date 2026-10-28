# Install on a new Ubuntu host

This guide rebuilds **projector control**, not the other applications on the old
Mac mini. The supported topology is one powered, dual-mode Bluetooth adapter,
the bridge and MQTT on the Ubuntu host, and Home Assistant on that same host
using host networking. The projector is on the same LAN. Multiple adapters and
remote MQTT brokers need changes and are not covered by the captured runtime.

## 1. Prepare a fresh OS

Use Ubuntu 24.04 LTS as the baseline. The captured host ran 24.04.5, BlueZ 5.72,
Python 3.12.3, Docker 29.9.2 and Compose 5.6.1. This is a record of the tested
environment, not a promise that every version combination behaves identically.

On the **new host**, install the OS dependencies:

```sh
sudo apt-get update
sudo apt-get install -y git ca-certificates bluez dbus python3 python3-venv python3-dbus python3-gi
```

Install Docker Engine with the Compose plugin using the
[official Ubuntu instructions](https://docs.docker.com/engine/install/ubuntu/).
Verify `sudo docker compose version`. Do not uninstall or replace Docker or
upgrade BlueZ on a working home server just to follow a fresh-machine guide.
The bridge installer itself installs no OS packages and restarts no shared
service.

The working BlueZ daemon uses its normal service command, without
`--experimental` or disabled input plugins. The original active configuration
had `AutoEnable=true`; no custom `input.conf` setting was required. Ensure the
new adapter is powered and available. Do not reset an adapter used by other apps.

Clone the private repository with an account/key that can read it:

```sh
git clone git@github.com:boris-virto/projector-bridge.git
cd projector-bridge
python3 tools/fetch_gatt.py
```

The fetch verifies the one required upstream module against its pinned SHA-256.
It does not run the original keyboard project's setup or controller-reset code.

## 2. Review and install files

```sh
python3 tools/install.py
python3 tools/install.py --stage /tmp/projector-bridge-review
sudo python3 tools/check_host.py --before-start
sudo python3 tools/install.py --apply
```

The first command prints the plan. The second writes only into the fresh staging
directory. Choose another directory if it already contains an installation.
Preflight reads adapter state and checks that the MQTT port/container name are
unused. It does not change Bluetooth settings.

`--apply` requires root and refuses existing installation directories, service
files/drop-ins or `/var/lib/projector-ble` state. This intentionally rejects the
already configured Mac mini. It copies files, creates a system-site-packages
venv, installs pinned Paho MQTT, and reloads systemd's unit definitions. It does
not enable/start the bridge or any container, and never edits HA configuration,
`/etc/bluetooth`, or `/var/lib/bluetooth`.

Installed paths:

| Path | Contents |
| --- | --- |
| `/opt/projector-bridge/` | Runtime, venv, local client, MQTT Compose files |
| `/etc/projector-bridge/bridge.env` | Three bridge settings, root-readable |
| `/etc/systemd/system/projector-ble.service` | New service, initially stopped |
| `/var/lib/projector-ble/` | Created by systemd on start; approved targets and adapter baseline |
| `/run/projector-ble/control.sock` | Root-only local socket while running |

If dependency installation fails after files were copied, fix the package/network
problem and rerun the displayed venv/pip steps manually; the installer will not
overwrite the partial tree. Do not delete a tree that already contains a working
installation or pairing state to bypass its guard.

## 3. Start only the dedicated MQTT broker

Review `/opt/projector-bridge/mqtt/mosquitto.conf`:
the only listener is `127.0.0.1:1883`. Anonymous access is limited to local
processes. Do not change it to `0.0.0.0` without adding authentication and reviewing
the network design. A host-network HA container can access this listener;
a normal isolated Docker bridge container cannot use its own `127.0.0.1` for it.

```sh
sudo docker compose -f /opt/projector-bridge/mqtt/compose.yaml config
sudo docker compose -f /opt/projector-bridge/mqtt/compose.yaml up -d mqtt
```

If port 1883 or container `projector-mqtt` already exists, stop and identify its
owner. Do not replace another MQTT setup. The captured runtime assumes this
dedicated local broker; it does not implement remote broker credentials.

## 4. Activate the HID bridge

Read the environment file before starting:

```sh
sudo cat /etc/projector-bridge/bridge.env
```

Starting the service sets the **shared** adapter alias to `MI RC HA Projector`
and its class to keyboard (`0x0540` major/minor bits). The public MAC, VID/PID and
standard HID service UUIDs are not replaced. The original alias/class/address
are saved in a root-only baseline; normal stop restores the alias/class when
they still match the values owned by this bridge.

The adapter is also used by any other Bluetooth applications. Start only after
accepting those shared identity changes:

```sh
sudo systemctl enable --now projector-ble.service
sudo python3 /opt/projector-bridge/projectorctl.py status
sudo journalctl -u projector-ble.service -n 30 --no-pager
```

The service runs as root because it uses BlueZ D-Bus and Bluetooth management /
authenticated L2CAP sockets. Its state and control socket are root-only. The
unit uses a read-only system filesystem, private temporary directory and no new
privileges. No HA token, SSH password or ADB key is required.

Pairing starts **closed**. The default disables the bridge's continuous BLE
advertisement while keeping Classic HID and GATT registered. Deep wake creates
its own temporary, at most 20-second advertisement, using a free instance.

Next: [pair and enroll the new adapter](pairing.md), then
[connect Home Assistant](home-assistant.md).
