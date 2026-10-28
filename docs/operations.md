# Operation, recovery and migration

## Verify a complete deep-standby cycle

1. Start with an actual image visible and HA's Android TV Remote state `on`.
2. Run `script.projector_turn_off`. The display should go dark without a shutdown
   confirmation dialog; HA should report `off` shortly afterward.
3. Wait until both the Bluetooth HID connection and projector network connection
   have actually dropped. On the tested unit this took several minutes. Testing
   wake immediately after the screen turns off exercises a different state.
4. Run `script.projector_turn_on` once. Do not press the native remote during the
   observation. The beacon lasts at most 20 seconds; allow up to 90 seconds for
   the projector and HA feedback to return.
5. Verify the image and actual HA state. A local result saying that the beacon
   was sent proves only signal transmission. Verify no temporary advertising
   instance remains after the burst if diagnosing radio behavior.

Use the HA scripts for normal use. The local client can send individual commands
when diagnosing:

```sh
sudo python3 /opt/projector-bridge/projectorctl.py status
sudo journalctl -u projector-ble.service -n 50 --no-pager
```

`projectorctl.py send sleep` and `send wake` are real physical actions. Avoid
issuing test commands while somebody is watching the projector.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Device absent from accessory search | Open the bounded pairing window, verify alias/class, reopen projector discovery |
| Very fast pairing rejection | Cached computer class/name; refresh discovery and inspect the pending request/journal |
| Code shown on projector but no pending request | Another agent may own pairing; do not auto-accept or repeatedly delete bonds |
| `No approved paired projector` | Approved target must also be paired in BlueZ; copied JSON is not a bond |
| Sleep command accepted but image stays on | Actual HA state, authenticated Classic connection and first-report timing; 750 ms delay is included |
| Wake works immediately but fails after minutes | Test real standby and firmware wake-list enrollment, not just connected HID wake |
| Beacon completes but projector remains off | Correct **projector Bluetooth MAC**, host wake-list recognition, actual advertising source address and firmware compatibility |
| No free advertising slot / management command unsupported | Controller/kernel capability or other advertiser; do not remove another app's instance |
| HA cannot reach MQTT | HA must share host networking for this loopback topology; check broker/container logs |
| MQTT error or wake still running | Command path is bounded and serializes active reports/beacon; wait for completion instead of overlapping senders |
| HA API request returned successfully | Read actual `remote.*` state and check image; command acceptance is not wake proof |
| New adapter rejected by baseline guard | Do not migrate old baseline/address state onto different hardware; use the new-host pairing procedure |

The runtime has fixed MQTT discovery identifiers from the captured single-host
setup. Run only one copy per broker. Do not run a standalone MiPower wake sender
or another advertising reconfiguration concurrently on the same adapter. Normal
existing HA scanning was retained in the verified setup.

## Back up and migrate

Git tracks source, dependencies and reconstructible configuration. It does not
track identity secrets or HA's internal state. Maintain a separate encrypted HA
backup if you want to preserve all HA users, integrations and other automations.
Keep any infrastructure credentials in a password manager, not in Git.

For a **new machine/new adapter**, follow install → pairing → HA setup, using its
own current adapter identity. Pair normally and let the projector enroll that
identity. Do not clone the native remote MAC, copy raw BlueZ key files, load key
tables, or reuse the old host's adapter baseline. The original native remote
stays usable throughout. Remove obsolete custom-host accessories only when you
have identified them and the new host has been tested.

For the **same installation**, root-only `/var/lib/projector-ble/targets.json`
and `adapter-baseline.json` are machine-specific runtime state, not credentials
for another host. A normal whole-machine encrypted backup may preserve them with
the same hardware. They are deliberately excluded from this repository.

## Updates

The fresh-install helper intentionally does not upgrade an existing bridge.
Before a manual upgrade, record the current Git revision and back up only the
bridge source/unit/environment and machine-specific state to protected storage.
Stop **projector-ble.service** normally, update only its files, run validation,
and restart only that service. Review changes before applying them. Do not run
the original `ble-hid-keyboard` installer or modify the shared Bluetooth daemon.

The original working Mac mini still uses its original deployment path; creating
this repository did not move or redeploy it. The portable `/opt` layout is for
fresh installations and was validated through staging and isolated tests.

## Stop or roll back

```sh
sudo systemctl disable --now projector-ble.service
sudo docker compose -f /opt/projector-bridge/mqtt/compose.yaml stop mqtt
```

Normal bridge shutdown closes HID channels and its pairing agent, cancels its
own wake burst, and conditionally restores its saved alias/class. It does not
remove bonds or power off/reset the controller. Other services may have changed
shared settings since startup, so inspect rather than blindly restoring a stale
baseline after an abnormal termination.

Remove only the HA scripts/dashboard and MQTT diagnostic discovery entries owned
by this setup if you no longer want them. Keep unrelated HA entries and the
native projector remote. Do not delete `/var/lib/bluetooth`, restore old key
tables or restart shared Bluetooth/HA as a cleanup shortcut. Preserve local
state/backups until you have verified the rollback.
