# Security review and deployment boundaries

Review date: **29 October 2026**. This is a scoped source/dependency review, not
a penetration test or a guarantee that the projector, host OS or dependencies
are free of vulnerabilities.

## Pre-publication checks

- Inspected the complete Git history, commit identities, all reachable file
  blobs, documentation, code, configuration and examples. Checked for supplied
  credentials, private keys, bearer/JWT/GitHub tokens, real LAN/Bluetooth
  addresses, personal paths, private email addresses and host-specific names.
- Replaced local identifiers with generic defaults and commit identities with
  the repository owner's public GitHub handle and GitHub noreply address.
  Source history predating this cleanup remains private rather than being
  attached to the public repository. No private keys, credentials, raw traffic
  captures or internal HA storage are published. Bluetooth addresses and codes
  in tests/instructions are deliberately synthetic examples.
- Ran `detect-secrets` locally without online secret verification. Reviewed its
  high-entropy matches: HID report bytes and commit/source/dependency hashes,
  rather than credentials. Also compared repository bytes with supplied local
  credential values without displaying or uploading those values.
- Ran Bandit on runtime and installation tools. No high-severity result was
  reported. Reviewed the remaining findings: constant argument-list subprocess
  calls in local administration tools and a fixed HTTPS dependency URL guarded
  by SHA-256. No user-controlled shell command or download destination is used.
- Ran `pip-audit` for pinned `paho-mqtt==2.1.0`; its advisory database returned no
  known vulnerability. Installation now also checks the wheel/source SHA-256
  values published by PyPI.
- Ran Trivy 0.76.1 with an updated database against the pinned Mosquitto image
  digest on **linux/amd64**: 35 recognized Alpine 3.23.7 packages, zero reported
  vulnerabilities. The ARM64 scan also returned zero. This covers packages the
  scanner recognizes, not a source audit of every compiled binary in the image.
- Ran 15 unit tests, including MQTT command limits/status redaction, existing
  installation/state preservation, payload cleanup and HA template rendering.
  The 15 tests, isolated session D-Bus smoke test, Compose check and staging also
  passed in a temporary directory on Ubuntu. The existing service start times
  and container IDs stayed unchanged. The original hardware validation is
  recorded in `docs/validation.md`; this hardening has not been redeployed to
  that working installation or validated through another physical wake cycle.

Known-vulnerability results are time-dependent. Recheck the pinned versions and
image digest when installing or updating; an empty scan is not proof of absence.
Ubuntu/BlueZ packages supplied by the target OS, the projector firmware and the
downloaded upstream GATT module require their own maintenance/review. Keep the
host patched. Upstream security information:
[Mosquitto security](https://mosquitto.org/security/),
[Paho advisories](https://github.com/eclipse-paho/paho.mqtt.python/security/advisories).

## Trust model

- **Trusted Linux host and local clients.** The MQTT listener binds only to
  `127.0.0.1:1883`. It is intentionally anonymous; any local process able to reach
  it can issue the allowed projector commands. Loopback limits network reach;
  it is not per-user authentication. Do not use this configuration on a
  multi-user/untrusted host, expose the port externally, or add a proxy to it.
  Remote MQTT/authentication is outside the captured implementation.
- **Root bridge.** Bluetooth management and authenticated L2CAP need host
  privileges in this setup. The local control socket is mode 0600; its runtime
  directory and state directory are mode 0700. The supplied systemd service
  sets those permissions and filesystem restrictions. Run through that unit;
  ad-hoc root launches do not inherit all its protections.
- **Minimal commands.** MQTT accepts only the fixed command set, ASCII payloads
  up to 64 bytes, and no messages delivered as retained. Publishers must still
  use `retain=false`: a newly published retained command can be delivered live
  to an existing subscriber without the retained flag.
- **Private pairing information.** MQTT status omits pending pairing details and
  unrelated paired accessories. Pairing codes remain available through the
  root-only control socket and are omitted from service logs. Do not upload raw
  status/journals/packet captures without reviewing identifiers and codes.
- **Explicit pairing and allowlist.** Open a bounded window, compare the exact
  code/device and close the window. Classic HID requires authenticated channels
  and an approved paired target. Pairing temporarily changes shared adapter
  flags and agent ownership. Cleanup after a hard crash is not guaranteed.
- **Shared radio.** The bridge changes alias/class and creates bounded wake
  advertisements without replacing existing advertising instances or bond keys.
  It does not isolate other Bluetooth apps. Concurrent advertising reconfiguration
  is unsupported; kernel timeouts bound a beacon if the process exits.
- **Wake advertisements are not authentication.** Their payload and MAC-derived
  fields reproduce a vendor wake protocol; they do not establish an encrypted
  session. Publishing the sender does not make this an authenticated wake
  protocol. Use only on your own paired projector; radio-range abuse is outside
  the protection offered by this bridge.
- **Supply chain.** Fetch the GATT dependency only at the pinned commit/hash,
  install hash-pinned Paho, and review image/OS updates deliberately. Review code
  before running the installer as root. Do not commit credentials, HA `.storage`,
  BlueZ keys, actual adapter baselines, or raw traffic dumps.

## Reporting

Use the repository's Security tab to report a vulnerability privately if private
reporting is enabled. Do not put credentials or sensitive captures in a public
issue. General installation bugs can be reported publicly with anonymized data.
