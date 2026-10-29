# Dependency provenance

The original host project was cloned from
[artyomsoft/ble-hid-keyboard](https://github.com/artyomsoft/ble-hid-keyboard),
commit `59e1504668643ef0c5dadbbb35550ee9fe22409a`.
The bridge uses only `core/ble_dbus.py` from that project. The original keyboard
service, setup scripts, controller power/reset helpers and other modules are not
installed or run.

`tools/fetch_gatt.py` downloads that one file at the exact commit and validates
SHA-256 `05b75c8bc2f8392e01d648d6e2c3a1b6e12e12412e576a9cba211630d50ce37d`.
The downloaded file stays in ignored `.deps/`; it is not redistributed in this
repository. The upstream tree had no license file and GitHub returned no declared
license when inspected on 28 October 2026. No license for upstream content is
invented or implied here.

Runtime dependencies are Ubuntu's `python3-dbus` / `python3-gi`, and
`paho-mqtt==2.1.0` from PyPI. The MQTT container is Eclipse Mosquitto 2.1.2, pinned
to the digest inspected on the working host. Each dependency retains its own
license. This repository publishes infrastructure recovery code and instructions; it does
not claim a blanket open-source license for upstream components.

The wake sender is also contributed as a standalone tool in
[MiPower PR #2](https://github.com/DenizOner/MiPower/pull/2). This bridge does not
copy or require the MiPower integration itself.
