# Projector Bridge

Rebuild the Home Assistant projector control configured on an Ubuntu Mac mini:
an authenticated Bluetooth Classic HID remote for **sleep**, a bounded Xiaomi
BLE wake advertisement for **wake from deep standby**, and a loopback-only MQTT
bridge. Home Assistant waits for the projector's real network power state.

Hardware verified on **28 October 2026**: Mi Smart Compact Projector **MiProjM05**,
Android TV 9; Ubuntu 24.04.5 LTS, Python 3.12.3, BlueZ 5.72. Compatibility with
other projector firmware, Bluetooth controllers or Linux releases is unverified.

```text
HA scripts ── MQTT on 127.0.0.1:1883 ── projector-ble.service
                                            ├── Classic HID → sleep / connected wake
                                            └── 20 s BLE advertisement → deep-standby wake
HA Android TV Remote integration ←──── actual projector power state over LAN
```

This is the complete host bridge missing from the standalone experimental sender
in the [MiPower PR](https://github.com/DenizOner/MiPower/pull/2). MiPower is not a
runtime dependency. ADB is not needed for normal use.

## Rebuild on a new machine

1. [Prepare Ubuntu, install files, and start only the new services](docs/install.md).
2. [Pair the new adapter and make the projector recognize it as a wake remote](docs/pairing.md).
3. [Connect Home Assistant, import scripts and the two-button dashboard](docs/home-assistant.md).
4. [Test deep standby and review troubleshooting](docs/operations.md).

Installation defaults to a printable plan. `--stage` builds a review copy without
calling pip, Docker or systemd. `--apply` installs a fresh instance but **does not
start services**. The activation step is explicit because the service changes
the **shared adapter alias and device class**. Existing installs/state are never
overwritten by the fresh-install tool.

On a new Bluetooth adapter, pair normally using a new on-screen code. The physical
adapter MAC changes with the hardware; renaming is insufficient. The repository
contains no bond keys, passwords, HA tokens, SSH credentials, projector IP/MAC
addresses or internal Home Assistant storage.

## Contents

| Path | Purpose |
| --- | --- |
| `runtime/` | The three Python modules captured from the working host, byte for byte |
| `deploy/` | Portable systemd unit, environment defaults, pinned MQTT Compose image |
| `home-assistant/` | Generic working scripts/dashboard and Assist power-switch configuration |
| `tools/install.py` | Plan, stage, and fresh-install paths; preserves existing installations |
| `tools/projectorctl.py` | Local status, bounded pairing, explicit code confirmation, HID commands |
| `tools/fetch_gatt.py` | Fetch one original GATT dependency at a pinned commit and SHA-256 |
| `tools/render_ha.py` | Render scripts, dashboard and voice-helper reference for your HA remote entity |
| `docs/` | Installation, pairing, recovery and measured validation evidence |
| `tests/` | Wake packet/cleanup, installer safety, HA rendering and local client checks |

Only the projector work is captured here. Other applications, voice containers,
and unrelated HA automations are outside this repository. For a whole-HA disaster
recovery, keep an encrypted Home Assistant backup separately; see
[migration notes](docs/operations.md#backup-and-migration).

## Development checks

```sh
python3 tools/fetch_gatt.py
PYTHONPATH=runtime:tools python3 -m unittest discover -s tests -v
```

Optional real D-Bus object/report checks on Ubuntu (isolated session bus, no
Bluetooth operations): `docs/validation.md`.

`ci/github-actions.yml.example` is an optional GitHub Actions template. It is not
an active workflow: the GitHub credential used for the initial upload has no
`workflow` scope. With suitable repository credentials, copy it to
`.github/workflows/check.yml` to enable CI. Local and isolated Ubuntu checks were
performed separately; no GitHub CI result is claimed.

Read [dependency provenance](THIRD_PARTY.md) and [validation limits](docs/validation.md).
The rebuild instructions have been staged and checked; a fresh OS installation
on another physical machine has not been performed.

Кратко по-русски: это исходники, установка и инструкции для восстановления
управления проектором на новой Ubuntu-машине. Начните с [установки](docs/install.md).
На новом Bluetooth-адаптере понадобится новое сопряжение с подтверждением кода;
ключи действующей пары здесь намеренно не хранятся.
