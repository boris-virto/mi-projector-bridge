"""Run only under dbus-run-session; no system bus or radio operations."""
import dbus
import dbus.mainloop.glib
import projector_bridge as p

p.dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
bus = dbus.SessionBus()
app = p.Application(bus)
hid = p.HID(bus)
app.services = [hid, p.Info(bus)]
objects = app.GetManagedObjects()
assert len(objects) == 16, len(objects)
for command, report_id, length in [('wake', 3, 1), ('sleep', 3, 1), ('power', 2, 2),
                                    ('home', 2, 2), ('enter', 1, 8)]:
    number, data = p.report_for(command)
    assert number == report_id and len(data) == length
    assert hid.reports[number].descriptors[0].ReadValue({}) == [number, 1]
assert bytes(hid.characteristics[3].ReadValue({'offset': 10})) == p.REPORT_MAP[10:]
try:
    p.report_for('unsupported')
except ValueError:
    pass
else:
    raise AssertionError('Unsupported command accepted')
print('PASS: isolated GATT tree, report references/sizes, long-read offset, command validation')
