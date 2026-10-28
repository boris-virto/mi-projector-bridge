# Evidence and validation limits

## Original hardware result — 28 October 2026

One Mi Smart Compact Projector **MiProjM05**, Android TV 9, was tested with an
Ubuntu Mac mini (Ubuntu 24.04.5 LTS, kernel 7.0.0-38-generic, BlueZ 5.72,
Python 3.12.3). These are single-device observations, not a model-wide guarantee.

The final configuration combined all of the following:

- Shared alias `MI RC HA Projector` and keyboard class; physical host MAC unchanged.
- Authenticated Classic HID pairing approved with the projector's displayed code.
- Projector vendor log confirming recognition of the name and addition of the
  host address to the wake list **alongside the unchanged native remote**.
- No continuous own BLE keyboard advertisement; Classic SDP and GATT registered.
- A recorded 31-byte Xiaomi wake payload, connectable legacy ADV_IND, 20 ms
  interval, bounded to 20 seconds in a previously unused advertising instance.
- 750 ms before the first report after new Classic channels so Android can
  register its input device, followed by a 180 ms key release.

The payload encodes the **projector's** final three Bluetooth address bytes in
reverse order. Its short name `MI RC` and manufacturer/service/class fields are
advertisement data; they do not replace the controller's public MAC or the
registered HID UUIDs. A successful burst removes only its own temporary slot
and verifies the pre-existing instance set and shared adapter address/settings.

Full HA REST API cycle on the working deployment:

| Observation | Measured result |
| --- | --- |
| Sleep invocation to actual HA remote `off` | 2.7 s |
| Independent Android check after sleep | Asleep / display off |
| Bluetooth loss after sleep | Approximately 6 minutes later |
| Wake script invocation to actual HA remote `on` after loss | 66.8 s |
| Independent Android check after wake | Awake / display on |
| Earlier successful deep-wake trial | LAN returned after 46 s; user confirmed image without pressing native remote |

The pair key file did not change during the successful final wake tests/cycle.
Existing HA and the five other containers retained their IDs/start times; the
shared Bluetooth daemon was not restarted. Temporary ADB access was disabled
after diagnostics, with TCP 5555 closed and normal Android TV Remote still
available. No earlier raw diagnostic experiments or key-recovery code are shipped
in this repository. In particular, no bulk key loading is part of the solution.

The combined result does not establish that alias alone, a packet alone, another
firmware, a private/RPA advertising address, or full shutdown will work. Wake
after the optional full-shutdown script was not revalidated with the final sender.

## Source capture

`runtime/` contains the exact three working source files exported read-only from
the Mac mini. `source-manifest.json` records their SHA-256 values. The portable
systemd unit changes only deployment paths and moves the three environment
settings into one file. HA examples translate aliases and replace the specific
remote entity with a placeholder; control behavior follows the captured scripts.
The MQTT image is pinned to the digest inspected on the working host.

## Repository checks

Run the offline unit suite after the pinned dependency has been fetched:

```sh
PYTHONPATH=runtime:tools python3 -m unittest discover -s tests -v
```

On 28 October 2026, all **13 tests** passed locally and on the Ubuntu host using
Python 3.12. The isolated GATT smoke test, Docker Compose configuration check,
and fresh-install staging also passed on Ubuntu. The validation recorded the
existing service start times and running container IDs before and after; they
were unchanged. YAML examples parsed locally, and tracked files were scanned
against the supplied credential values without displaying those values.

The suite checks packet layout and safe advertising cleanup on failure, duration
bounds and occupied slots; fresh-install staging and refusal to overwrite old
configuration/state; code/device input checks; and HA entity rendering.

For actual GATT report serialization, install the Ubuntu dependencies described
in the install guide, then run on an **isolated session D-Bus**, with the source
and fetched dependency visible:

```sh
PYTHONPATH=runtime:.deps dbus-run-session -- python3 -B tests/smoke_gatt.py
```

This constructs GATT objects on the session bus only. It does not register with
BlueZ, open a pairing window, transmit radio packets, or switch the projector.

Staging and tests do not prove a fresh OS/hardware rebuild end to end. No second
physical host has been installed from this repository. The existing Mac mini
deployment remains unchanged. After migration, perform the actual deep-standby
cycle in `operations.md` to validate the new adapter and projector enrollment.
