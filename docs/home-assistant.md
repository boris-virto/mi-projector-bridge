# Home Assistant integration

## Fresh HA or existing HA

For a new HA installation, follow the official
[Home Assistant Container guide](https://www.home-assistant.io/installation/linux#install-home-assistant-container)
and complete onboarding. Use **host networking** on the same Ubuntu machine as
this bridge so `127.0.0.1:1883` reaches its broker. The observed working HA version
was 2026.10.4. The bridge does not require privileged access inside HA or changes
to HA's Bluetooth setup; Bluetooth is handled by the separate host service.

For an existing installation, keep its container, networks, credentials,
integrations and scripts. Do not replace its Compose file or `.storage` contents.
The following configuration is additive and can use script reloads.

## 1. Actual power state

Add the projector through
[Android TV Remote](https://www.home-assistant.io/integrations/androidtv_remote/):
Settings → Devices & services → Add integration → Android TV Remote. Use the
projector's **LAN IP**, and complete its normal authorization prompt. A DHCP
reservation helps keep that address stable. No ADB permission is required.

Find the resulting `remote.*` entity in Developer tools → States. The original
installation used a room-specific name; the examples use `remote.projector`.
Check that it reports `on` while displaying an image and `off` when the display
sleeps. This entity is the actual state feedback; the MQTT bridge's process
availability is not the projector's power state.

## 2. MQTT

Add the [MQTT integration](https://www.home-assistant.io/integrations/mqtt/)
with broker **127.0.0.1**, port **1883**, no username/password, matching the local
listener. Do not change an unrelated existing MQTT integration to point here.
If HA already uses a different broker, this snapshot needs a deliberate broker
configuration change in the host bridge; it does not ship a broker migration.

The bridge publishes diagnostic wake/power buttons through MQTT discovery.
Use the scripts below as normal controls because they wait for actual state.

| Topic | Payload / purpose | Retained |
| --- | --- | --- |
| `projector_ble/command` | `wake`, `sleep`, `power`, `home`, `back`, `enter`, arrows | **false** |
| `projector_ble/result` | JSON command acceptance/completion or error | false |
| `projector_ble/state` | Bridge/pair/connection status, not actual projector power | true |
| `projector_ble/availability` | Bridge process `online` / `offline` | true |

The client ignores commands delivered with MQTT's retained flag. Publishers must
still **always use retain=false**: a command freshly published with retain=true
can reach an already subscribed client as a live message. Clear any accidental
retained command before connecting the bridge.

## 3. Scripts

Render examples for your actual Android TV Remote entity:

```sh
python3 tools/render_ha.py --entity remote.projector --output /tmp/projector-ha
```

Replace `remote.projector` in that command with the entity you found. The renderer
does not contact HA and refuses to overwrite existing output files.

Back up the existing `scripts.yaml`, then merge **only** the three `projector_*`
entries from the rendered file. Do not replace the whole file or duplicate an
existing script ID. On a fresh default HA configuration, `configuration.yaml`
normally contains:

```yaml
script: !include scripts.yaml
```

If you use packages or a different include structure, merge the entries into that
structure instead. Validate configuration, then call `script.reload` from
Developer tools → Actions. Existing installs need no HA/container restart for
these script changes. Adding a new include structure may require a planned HA
restart; do not restart a working server merely to import the examples.

`projector_turn_off` sends **sleep**, not a shutdown dialog. `projector_turn_on`
uses connected HID wake or a 20-second beacon and waits up to 90 seconds for
actual `remote.*` state `on`. Sleep waits 30 seconds for `off` or `unavailable`.
An unavailable result is loss of feedback, not independent physical proof of
sleep. Inspect the image during the first test. Full shutdown remains a separate
optional script; final beacon wake after that mode was not revalidated.

## 4. Dashboard

Create a new dashboard, open its raw configuration editor, and paste the rendered
`dashboard.yaml`. It has two buttons for the normal on/off scripts. Avoid
overwriting any existing dashboard. You may translate the button/script aliases
without changing their IDs.

## 5. Built-in Assist: natural power commands

For phrases such as **«Включи проектор»** / **«Выключи проектор»**, expose a single
template **switch** called **Проектор** that calls the tested on/off scripts.
Exposing a media player with the same name sends these phrases to its normal
network power path, which does not use this bridge. Merely exposing scripts named
«Включить проектор» / «Выключить проектор» does not turn them into a single device
with natural on/off behavior.

Create the helper without restarting HA:

1. Settings → Devices & services → Helpers → Create helper → Template → Switch.
2. Name: `Проектор` (use a name in your Assist language).
3. State template: `{{ is_state('remote.projector', 'on') }}`, using your actual
   Android TV Remote entity.
4. Turn-on action: `script.turn_on`, target `script.projector_turn_on`.
5. Turn-off action: `script.turn_on`, target `script.projector_turn_off`.
6. Save it and, if desired, rename its entity ID to `switch.projector_power`.
7. In Settings → Voice assistants → Expose, expose this switch to **Assist**.
   Remove the projector's same-named media player from Assist exposure to avoid
   power-command ambiguity. This only changes voice exposure, not the media
   player's normal controls. Keep diagnostic buttons, the raw remote and optional
   full-shutdown script unexposed.
8. Add aliases such as `проектор`, `кинопроектор`, `проектор в спальне`. Use
   equivalent names/aliases and the correct pipeline language for other languages.

The rendered `voice-helper.json` contains the helper's configuration fields for
reference/API provisioning. It is not a `configuration.yaml` include: the helper
is created through the UI/config flow. Its `remote.projector` reference is
substituted by `tools/render_ha.py` just like the scripts and dashboard.

Both actions use the non-blocking `script.turn_on` service, including when
starting the **off** script. This launches the selected script; it does not turn
the projector on by itself. Assist can acknowledge the request promptly while
the script waits for real power feedback in the background. A voice
acknowledgment means the action was accepted; deep wake can still take up to
90 seconds. The switch's state follows actual network feedback, not the request.
An unavailable remote is displayed as off by this simple template; do not treat
that as independently confirmed sleep.

Before executing commands, use Settings → Tools → Assist's sentence parser to
check the target. Both phrases should match **only** `switch.projector_power`.
This diagnostic parser does not switch the device. Then test with the actual
microphone. Activate Assist, wait for its ready indication, and speak the entire
command. If you get “not recognized,” inspect the pipeline's STT text first:
in the original failed attempts it contained only «проекта» / «проектор», without
the verb. That observation establishes missing command text, not the precise
cause (speech timing, audio gating or transcription still need a fresh test).

References: [Assist aliases](https://www.home-assistant.io/voice_control/aliases/),
[Assist troubleshooting and sentence parser](https://www.home-assistant.io/voice_control/troubleshooting/).
No voice container, shared Bluetooth service or HA restart is required for this
helper/exposure change.

## API testing (optional)

Use a separate user-created HA access token, kept outside this repository.
POST `/api/services/script/projector_turn_on` or
`/api/services/script/projector_turn_off` with bearer authorization, then GET
`/api/states/remote.YOUR_ENTITY` to verify the actual state. HTTP success, a
finished script, or `wake_advertisement_sent` alone does not prove physical wake.
Allow at least 90 seconds for the on request; a short HTTP timeout can return
before HA's script finishes. Never extract tokens from HA's internal session
storage. API credentials are not needed by the production bridge.
