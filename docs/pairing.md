# Pairing and projector wake enrollment

## Know which identity you are changing

| Field | Meaning in this setup |
| --- | --- |
| Host Bluetooth public MAC | Physical adapter identity; must be paired/enrolled on the projector |
| Host alias | Shared adapter name `MI RC HA Projector`; firmware recognition used this prefix |
| Class of Device | Shared keyboard classification used by Classic accessory discovery |
| BLE advertisement name/data | Temporary wake packet fields; do not create a new adapter identity |
| Projector Bluetooth MAC | Destination used to build the wake packet; **not** its Wi-Fi MAC or IP |
| Native remote Bluetooth MAC | Separate accessory; never clone, remove or replace it |

Use `bluetoothctl show` to see the host identity. This does not by itself prove
which address appears over the air when privacy/RPA is enabled. The working
controller advertised with its public identity; private/RPA configurations are
unverified. Do not change global privacy settings blindly on a shared adapter.

A **new adapter needs normal pairing** and firmware wake enrollment. The saved
`targets.json` file is only an allowlist of BlueZ object paths, not a backup of
bond keys. Copying that file cannot restore a pair on different hardware. Do not
copy the old `adapter-baseline.json` to a new adapter: its address guard will
correctly reject the mismatch.

## First pairing on the new host

1. Turn the projector on with its native remote. Keep the native remote paired.
2. On Ubuntu, open a short explicit pairing window:

```sh
sudo python3 /opt/projector-bridge/projectorctl.py pair --seconds 300
```

3. On the projector, open **Remotes & accessories → Add accessory**. Select
   **MI RC HA Projector**. Confirm the displayed code on the projector.
4. Immediately read the pending request on the host:

```sh
sudo python3 /opt/projector-bridge/projectorctl.py status
```

5. Compare the projector's code to `pending.code`, and confirm the **exact**
   `pending.device` path. This is an anonymized example, not a real code/address:

```sh
sudo python3 /opt/projector-bridge/projectorctl.py confirm \
  --device /org/bluez/hci0/dev_AA_BB_CC_11_22_33 --code 123456
```

The pending request expires after 90 seconds. Do not confirm an unexpected
device or mismatch. The bridge records the approved path only after explicit
confirmation and initiates authenticated Classic HID channels.

6. Wait for successful pairing on the projector and `paired: true` in status.
   Close the window promptly:

```sh
sudo python3 /opt/projector-bridge/projectorctl.py close-pairing
sudo python3 /opt/projector-bridge/projectorctl.py status
```

Opening a window temporarily makes the shared adapter pairable, discoverable and
connectable and registers a default pairing agent. Closing it or normal shutdown
restores the saved flags and unregisters that agent. Do not run another pairing
agent at the same time. A hard crash during the window can prevent cleanup;
inspect adapter flags before leaving the system unattended.

## Make firmware recognize the host as a wake remote

On the tested MiProjM05 firmware, the vendor Bluetooth service classifies remotes
using VID/PID **or recognized name prefixes**, including `MI RC`, and saves their
addresses in a wake list. The host name must already have the prefix when the
projector discovers or refreshes its name. The stock remote must remain in that
list. Renaming alone is not established as sufficient on every firmware.

If a previously paired host shows an old name, exit and reopen accessory search
to refresh it; do not delete its bond as the first troubleshooting step. The
original working installation updated the name and wake enrollment without
re-pairing. Fresh installations should pair under the final name from the start.

Optional diagnostic evidence, only when ADB is already enabled and authorized:
the vendor service logged `checkXiaomiRcName:MI RC HA Projector`,
`compare rc name ok!`, `setWakeUpRcAddr` and `saveWakeUpRcAddr, saveToEnv=true`.
Its resulting `wakeUpTotal` included **both** the native remote and host addresses.
Do not manually overwrite `rc_macaddr` / boot environment values. Disable ADB
again after diagnosis; normal operation uses no ADB connection.

## If pairing fails

- Verify the adapter has the final alias and keyboard class in `bluetoothctl show`.
- Reopen accessory search so the projector refreshes discovery/class information.
- Verify `pending` and the journal rather than repeatedly sending blind accepts.
- `No approved paired projector` means the host lacks an approved, paired target;
  an advertisement alone does not fix this.
- If recovery truly requires re-pairing, identify and remove only **this custom
  host remote** on the projector, never its native remote or other accessories.
  Removing a corresponding host bond requires a deliberate, matching-device
  operation; no bulk reset or key loading is part of this repository.

Next: [Home Assistant setup](home-assistant.md), then test **deep standby**;
successful pairing proves only the awake connection path.
