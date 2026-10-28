#!/usr/bin/env python3
"""Local BLE HID remote; never changes controller power or bond storage."""
import json
import ctypes
import logging
import os
from pathlib import Path
import signal
import socket
import socketserver
import subprocess
import struct
import sys
import threading
import time

import dbus
import dbus.mainloop.glib
import dbus.service
from gi.repository import GLib
from core.ble_dbus import (
    Application, Service, Characteristic, Descriptor, DBUS_PROP_IFACE,
    GATT_CHRC_IFACE, GATT_DESC_IFACE, NotSupportedException,
)

NAME = os.environ.get('PROJECTOR_REMOTE_NAME', 'HA Projector')
SOCKET = '/run/projector-ble/control.sock'
AGENT = 'org.bluez.Agent1'
ADV = 'org.bluez.LEAdvertisement1'
TOPIC = 'projector_ble'
# Three independent input reports: keyboard (8 bytes), consumer (2), system (1).
REPORT_MAP = bytes.fromhex(
    '05010906a1018501050719e029e715002501750195088102'
    '75089501810175089506150025650507190029658100c0'
    '050c0901a1018502150026ff0319002aff03751095018100c0'
    '05010980a101850315002501750195030981098209838102'
    '750595018103c0'
)

def report_for(command):
    if command in ('wake', 'sleep', 'system_power'):
        return 3, bytes([{'system_power': 1, 'sleep': 2, 'wake': 4}[command]])
    if command in ('power', 'home', 'back'):
        return 2, {'power': 0x30, 'home': 0x223, 'back': 0x224}[command].to_bytes(2, 'little')
    if command in ('enter', 'up', 'down', 'left', 'right'):
        return 1, bytes([0, 0, {'enter': 0x28, 'up': 0x52, 'down': 0x51,
                               'left': 0x50, 'right': 0x4f}[command], 0, 0, 0, 0, 0])
    raise ValueError('Unsupported command')

def array(data):
    return dbus.Array(data, signature='y')

class Value(Characteristic):
    def __init__(self, name, service, uuid, data, flags=('read',)):
        super().__init__(name, service, uuid, list(flags))
        self.value = bytes(data)

    @dbus.service.method(GATT_CHRC_IFACE, in_signature='a{sv}', out_signature='ay')
    def ReadValue(self, options):
        offset = int(options.get('offset', 0))
        return array(self.value[offset:])

    @dbus.service.method(GATT_CHRC_IFACE, in_signature='aya{sv}')
    def WriteValue(self, value, options):
        if not any('write' in flag for flag in self.flags):
            raise NotSupportedException()
        self.value = bytes(value)

class Reference(Descriptor):
    def __init__(self, characteristic, report_id):
        super().__init__(characteristic.service.bus, 1, '2908', ['read'], characteristic)
        self.report_id = report_id

    @dbus.service.method(GATT_DESC_IFACE, in_signature='a{sv}', out_signature='ay')
    def ReadValue(self, options):
        return array([self.report_id, 1])

class Report(Value):
    def __init__(self, service, report_id, length):
        super().__init__('Input' + str(report_id), service, '2a4d', bytes(length),
                         ('encrypt-read', 'notify'))
        self.notifying = False
        self.descriptors = [Reference(self, report_id)]

    @dbus.service.method(GATT_CHRC_IFACE)
    def StartNotify(self):
        self.notifying = True
        logging.info('Notifications enabled: %s', self.name)

    @dbus.service.method(GATT_CHRC_IFACE)
    def StopNotify(self):
        self.notifying = False
        logging.info('Notifications disabled: %s', self.name)

    def send(self, data):
        self.value = bytes(data)
        self.properties_changed({'Value': array(self.value)})

class HID(Service):
    def __init__(self, bus):
        super().__init__(bus, '1812', True)
        self.reports = {i: Report(self, i, n) for i, n in ((1, 8), (2, 2), (3, 1))}
        self.characteristics = [
            Value('Protocol', self, '2a4e', b'\x01', ('read', 'write-without-response')),
            Value('Info', self, '2a4a', bytes.fromhex('11010002')),
            Value('Control', self, '2a4c', b'\x00', ('write-without-response',)),
            Value('ReportMap', self, '2a4b', REPORT_MAP),
            *self.reports.values(),
        ]

class Info(Service):
    def __init__(self, bus):
        super().__init__(bus, '180a', True)
        self.characteristics = [Value(n, self, u, v.encode()) for n,u,v in (
            ('Manufacturer', '2a29', 'Local Home Assistant'),
            ('Model', '2a24', 'HA Projector Remote'),
            ('Serial', '2a25', 'projector-remote-01'),
            ('Version', '2a28', '1.0.0'),
        )]

class Advertisement(dbus.service.Object):
    def __init__(self, bridge):
        self.bridge = bridge
        self.path = '/org/bluez/ProjectorRemote/advertisement'
        super().__init__(bridge.bus, self.path)

    @dbus.service.method(DBUS_PROP_IFACE, in_signature='s', out_signature='a{sv}')
    def GetAll(self, interface):
        if interface != ADV:
            raise NotSupportedException()
        return {'Type': 'peripheral', 'LocalName': NAME,
                'ServiceUUIDs': dbus.Array(['1812'], signature='s'),
                'Appearance': dbus.UInt16(0x03c1),
                'Discoverable': dbus.Boolean(time.monotonic() < self.bridge.pair_until)}

    @dbus.service.method(ADV, in_signature='', out_signature='')
    def Release(self):
        logging.info('Advertisement released')

class Rejected(dbus.DBusException):
    _dbus_error_name = 'org.bluez.Error.Rejected'

class PairingAgent(dbus.service.Object):
    def __init__(self, bridge):
        self.bridge = bridge
        self.path = '/org/bluez/ProjectorRemote/agent'
        super().__init__(bridge.bus, self.path)

    def request(self, device, kind, code, ok, error):
        if time.monotonic() > self.bridge.pair_until or self.bridge.pending:
            error(Rejected('Pairing window closed or request pending'))
            return
        self.bridge.pending = {'device': str(device), 'kind': kind, 'code': code,
                               'ok': ok, 'error': error, 'expires': time.monotonic()+90}
        logging.info('PAIRING REQUEST device=%s kind=%s code=%s', device, kind, code)

    @dbus.service.method(AGENT, in_signature='ou', out_signature='', async_callbacks=('ok','error'))
    def RequestConfirmation(self, device, passkey, ok, error):
        self.request(device, 'confirmation', int(passkey), ok, error)

    @dbus.service.method(AGENT, in_signature='o', out_signature='u', async_callbacks=('ok','error'))
    def RequestPasskey(self, device, ok, error):
        self.request(device, 'passkey', None, ok, error)

    @dbus.service.method(AGENT, in_signature='o', out_signature='', async_callbacks=('ok','error'))
    def RequestAuthorization(self, device, ok, error):
        self.request(device, 'authorization', None, ok, error)

    @dbus.service.method(AGENT, in_signature='ouq', out_signature='')
    def DisplayPasskey(self, device, passkey, entered):
        logging.info('PAIRING DISPLAY device=%s code=%06d entered=%s', device, passkey, entered)

    @dbus.service.method(AGENT, in_signature='os', out_signature='')
    def AuthorizeService(self, device, uuid):
        if str(device) not in self.bridge.targets or str(uuid).lower() != '00001812-0000-1000-8000-00805f9b34fb':
            raise Rejected('Not an approved projector HID connection')

    @dbus.service.method(AGENT, in_signature='', out_signature='')
    def Cancel(self):
        self.bridge.pending = None
        logging.info('Pairing cancelled')

    @dbus.service.method(AGENT, in_signature='', out_signature='')
    def Release(self):
        logging.info('Pairing agent released')

class Bridge:
    def __init__(self, bus):
        self.bus = bus
        self.loop = GLib.MainLoop()
        self.pending = None
        self.pair_until = 0
        self.pairing_advertised = False
        self.busy = False
        self.wake_in_progress = False
        self.wake_stop = threading.Event()
        self.wake_thread = None
        self.mqtt = None
        self.classic = None
        self.agent_registered = False
        self.previous_pairable = None
        self.previous_connectable = None
        self.previous_discoverable = None
        self.target_file = Path('/var/lib/projector-ble/targets.json')
        self.targets = set(json.loads(self.target_file.read_text())) if self.target_file.exists() else set()
        self.om = dbus.Interface(bus.get_object('org.bluez','/'), 'org.freedesktop.DBus.ObjectManager')
        bus.add_signal_receiver(self.device_changed, dbus_interface=DBUS_PROP_IFACE,
                                signal_name='PropertiesChanged', path_keyword='path')
        self.adapter = next(str(p) for p,i in self.om.GetManagedObjects().items()
                            if 'org.bluez.GattManager1' in i)
        self.app = Application(bus)
        self.hid = HID(bus)
        self.app.services = [self.hid, Info(bus)]
        self.advertisement = Advertisement(self)
        self.agent = PairingAgent(self)
        self.agent_manager = dbus.Interface(bus.get_object('org.bluez','/org/bluez'), 'org.bluez.AgentManager1')
        self.ad_manager = dbus.Interface(bus.get_object('org.bluez',self.adapter), 'org.bluez.LEAdvertisingManager1')
        self.adapter_props=dbus.Interface(bus.get_object('org.bluez',self.adapter),DBUS_PROP_IFACE)
        self.adapter_index=self.adapter.rsplit('hci',1)[1]

    def controller_command(self,opcode,payload=b''):
        # Python 3.12 exposes no HCI control-channel bind, so use sockaddr_hci.
        with socket.socket(socket.AF_BLUETOOTH,socket.SOCK_RAW,socket.BTPROTO_HCI) as channel:
            address=ctypes.create_string_buffer(struct.pack('HHH',socket.AF_BLUETOOTH,0xffff,3))
            libc=ctypes.CDLL(None,use_errno=True)
            if libc.bind(channel.fileno(),ctypes.byref(address),6)!=0:
                error=ctypes.get_errno()
                raise OSError(error,os.strerror(error))
            channel.settimeout(5)
            index=int(self.adapter_index)
            channel.send(struct.pack('<HHH',opcode,index,len(payload))+payload)
            until=time.monotonic()+5
            while time.monotonic()<until:
                packet=channel.recv(65535)
                event,controller,length=struct.unpack_from('<HHH',packet)
                if event in (1,2) and controller==index and len(packet)>=9:
                    command,status=struct.unpack_from('<HB',packet,6)
                    if command==opcode:
                        if status:raise ValueError('Controller rejected command: '+str(status))
                        return packet[9:]
            raise TimeoutError('No controller command completion')

    def mgmt(self,*args):
        if args[0]=='class':
            return self.controller_command(0x000e,bytes([int(args[1]),int(args[2])])).hex()
        if args[0]=='connectable':
            return self.controller_command(0x0007,bytes([args[1]=='on'])).hex()
        if args[0]=='info':
            information=self.controller_command(0x0004)
            settings=int.from_bytes(information[13:17],'little')
            return 'current settings: '+('connectable' if settings & 2 else '')
        raise ValueError('Unsupported controller command')

    def configure_identity(self):
        path=Path('/var/lib/projector-ble/adapter-baseline.json')
        if not path.exists():
            baseline={'alias':str(self.adapter_props.Get('org.bluez.Adapter1','Alias')),
                      'class':int(self.adapter_props.Get('org.bluez.Adapter1','Class')),
                      'address':str(self.adapter_props.Get('org.bluez.Adapter1','Address'))}
            path.write_text(json.dumps(baseline))
            os.chmod(path,0o600)
        self.adapter_baseline=json.loads(path.read_text())
        current=str(self.adapter_props.Get('org.bluez.Adapter1','Address'))
        if current!=self.adapter_baseline['address']:
            raise ValueError('Controller address differs from saved baseline')
        self.adapter_props.Set('org.bluez.Adapter1','Alias',dbus.String(NAME))
        self.mgmt('class','5','64')
        logging.info('Controller classified as keyboard; Bluetooth address unchanged')

    def restore_identity(self):
        if not hasattr(self,'adapter_baseline'):
            return
        original=self.adapter_baseline
        if str(self.adapter_props.Get('org.bluez.Adapter1','Alias'))==NAME:
            self.adapter_props.Set('org.bluez.Adapter1','Alias',dbus.String(original['alias']))
        current=int(self.adapter_props.Get('org.bluez.Adapter1','Class'))
        if current & 0x1ffc == 0x0540:
            self.mgmt('class',str((original['class']>>8)&0x1f),str(original['class']&0xfc))

    def status(self):
        devices=[]
        for path, interfaces in self.om.GetManagedObjects().items():
            d=interfaces.get('org.bluez.Device1')
            if d and (str(path) in self.targets or bool(d.get('Paired'))):
                devices.append({'path':str(path),'name':str(d.get('Name','')),
                                'paired':bool(d.get('Paired')),'connected':bool(d.get('Connected'))})
        pending = {k:v for k,v in (self.pending or {}).items() if k in ('device','kind','code')}
        return {'name':NAME,'wake_advertising':self.wake_in_progress,'pairing_open':time.monotonic()<self.pair_until,
                'pending':pending,'devices':devices,
                'notifying':{str(k):v.notifying for k,v in self.hid.reports.items()},
                'classic':self.classic.status() if self.classic else None}

    def device_changed(self, interface, changed, invalidated, path=None):
        if str(interface)=='org.bluez.Device1':
            selected={str(k):str(v) for k,v in changed.items()
                      if str(k) in ('Connected','Paired','Bonded','ServicesResolved','Name')}
            if selected:
                logging.info('Device changed %s %s',path,selected)

    def register_ad(self):
        if os.environ.get('PROJECTOR_BLE_ADVERTISING', '1') != '1':
            logging.info('Own BLE advertisement disabled for identity trial')
            return
        self.ad_manager.RegisterAdvertisement(self.advertisement.path, {},
            reply_handler=lambda:logging.info('Advertisement registered: %s', NAME),
            error_handler=lambda e:logging.error('Advertisement registration failed: %s', e))

    def pairing(self, seconds):
        seconds=max(0,min(1200,int(seconds)))
        if seconds:
            if not self.agent_registered:
                self.previous_pairable=bool(self.adapter_props.Get('org.bluez.Adapter1','Pairable'))
                self.previous_discoverable=bool(self.adapter_props.Get('org.bluez.Adapter1','Discoverable'))
                settings=next((l for l in self.mgmt('info').splitlines() if 'current settings:' in l),'')
                self.previous_connectable='connectable' in settings.split()
                self.agent_manager.RegisterAgent(self.agent.path,'DisplayYesNo')
                self.agent_registered=True
            self.agent_manager.RequestDefaultAgent(self.agent.path)
            self.adapter_props.Set('org.bluez.Adapter1','Pairable',dbus.Boolean(True))
            self.mgmt('connectable','on')
            self.adapter_props.Set('org.bluez.Adapter1','Discoverable',dbus.Boolean(True))
        elif self.agent_registered:
            if self.pending:
                self.pending['error'](Rejected('Pairing window closed'))
                self.pending=None
            self.agent_manager.UnregisterAgent(self.agent.path)
            self.agent_registered=False
            self.mgmt('connectable','on' if self.previous_connectable else 'off')
            self.adapter_props.Set('org.bluez.Adapter1','Discoverable',dbus.Boolean(self.previous_discoverable))
            self.adapter_props.Set('org.bluez.Adapter1','Pairable',dbus.Boolean(self.previous_pairable))
        self.pair_until=time.monotonic()+seconds
        self.pairing_advertised=bool(seconds)
        if os.environ.get('PROJECTOR_BLE_ADVERTISING', '1') == '1':
            self.ad_manager.UnregisterAdvertisement(self.advertisement.path)
        self.register_ad()
        return {'pairing_seconds':seconds,'name':NAME}

    def start_wake_beacon(self, path):
        address = path.rsplit('dev_', 1)[-1].replace('_', ':')
        index = int(self.adapter_index)
        self.busy = True
        self.wake_in_progress = True
        self.wake_stop.clear()
        def worker():
            result = {'wake_advertisement_sent': True}
            try:
                from projector_wake import advertise
                advertise(address, 20, index, connectable=True, cancel_event=self.wake_stop)
                logging.info('Xiaomi wake advertisement completed for approved projector')
            except Exception as error:
                result = {'error': str(error)}
                logging.exception('Xiaomi wake advertisement failed')
            def complete():
                self.busy = False
                self.wake_in_progress = False
                if self.mqtt:
                    self.mqtt.publish(TOPIC+'/result', json.dumps(result), retain=False)
                return False
            GLib.idle_add(complete)
        self.wake_thread = threading.Thread(target=worker, daemon=True)
        self.wake_thread.start()
        return {'wake_advertising': True, 'seconds': 20}

    def command(self, request):
        action=request.get('action')
        if action=='status':
            return self.status()
        if action=='pairing':
            return self.pairing(request.get('seconds',1200))
        if action=='confirm':
            pending=self.pending
            if not pending:
                raise ValueError('No pending pairing request')
            if request.get('device') != pending['device']:
                raise ValueError('Device mismatch')
            if pending['kind']=='confirmation' and int(request.get('code',-1))!=pending['code']:
                raise ValueError('Confirmation code mismatch')
            if pending['kind']=='passkey':
                code=int(request['code'])
                if not 0<=code<=999999:
                    raise ValueError('Invalid passkey')
                pending['ok'](dbus.UInt32(code))
            else:
                pending['ok']()
            self.targets.add(pending['device'])
            self.target_file.parent.mkdir(parents=True,exist_ok=True)
            self.target_file.write_text(json.dumps(sorted(self.targets)))
            os.chmod(self.target_file,0o600)
            self.pending=None
            if self.classic:
                def connect_after_pairing():
                    try:self.classic.connect(pending['device'])
                    except Exception:logging.exception('Post-pairing Classic connection failed')
                    return False
                GLib.idle_add(connect_after_pairing)
            return {'accepted':pending['device']}
        if action=='send':
            report_id,data=report_for(request['command'])
            report=self.hid.reports[report_id]
            if self.busy:
                raise ValueError('A key press is already in progress')
            status=self.status()
            approved=[d for d in status['devices'] if d['paired'] and d['path'] in self.targets]
            if not approved:
                raise ValueError('No approved paired projector')
            use_classic=self.classic and self.classic.status()['connected']
            if not use_classic and not report.notifying:
                if request['command'] == 'wake' and os.environ.get('PROJECTOR_WAKE_BEACON') == '1':
                    return self.start_wake_beacon(approved[0]['path'])
                if self.classic:
                    return self.classic.connect(approved[0]['path'],request['command'])
                raise ValueError('Projector is not connected and subscribed to this HID report')
            self.busy=True
            sender=(lambda value:self.classic.send(report_id,value)) if use_classic else report.send
            try:sender(data)
            except Exception:
                self.busy=False
                raise
            def release():
                try:sender(bytes(len(data)))
                except Exception:logging.exception('Key release failed')
                finally:self.busy=False
                return False
            GLib.timeout_add(180,release)
            logging.info('HID command sent: %s',request['command'])
            return {'sent':request['command']}
        if action=='classic_connect':
            approved=[d for d in self.status()['devices'] if d['paired'] and d['path'] in self.targets]
            if not approved:
                raise ValueError('No approved paired projector')
            return self.classic.connect(approved[0]['path'])
        raise ValueError('Unknown action')

    def tick(self):
        if self.pairing_advertised and time.monotonic()>self.pair_until:
            self.pairing(0)
            logging.info('Pairing window expired')
        if self.pending and self.pending['expires']<time.monotonic():
            self.pending['error'](Rejected('Pairing confirmation timed out'))
            self.pending=None
        if self.mqtt:
            status=self.status()
            self.mqtt.publish(TOPIC+'/state',json.dumps(status),retain=True)
        return True

    def start_mqtt(self):
        import paho.mqtt.client as mqtt
        self.mqtt=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,client_id='projector-bridge-client')
        self.mqtt.will_set(TOPIC+'/availability','offline',retain=True)
        def connected(client,userdata,flags,reason,properties):
            if reason.is_failure:
                logging.error('MQTT connection failed: %s',reason)
                return
            client.subscribe(TOPIC+'/command')
            client.publish(TOPIC+'/availability','online',retain=True)
            device={'identifiers':['projector-bridge'],'name':'Projector BLE Remote',
                    'manufacturer':'Local','model':'HA Projector Remote'}
            for cmd in ('wake','power'):
                cfg={'name':{'wake':'Wake (BLE test)','power':'Power (BLE test)'}[cmd],
                     'unique_id':'projector_ble_'+cmd,'command_topic':TOPIC+'/command',
                     'payload_press':cmd,'availability_topic':TOPIC+'/availability',
                     'device':device,'entity_category':'diagnostic'}
                client.publish('homeassistant/button/projector_ble/'+cmd+'/config',json.dumps(cfg),retain=True)
        def message(client,userdata,msg):
            if msg.retain:
                return
            try:
                command=msg.payload.decode()
                if command not in ('wake','power','sleep','home','back','enter','up','down','left','right'):
                    return
                def send():
                    try:
                        result=self.command({'action':'send','command':command})
                    except Exception as e:
                        result={'error':str(e)}
                        logging.warning('MQTT command rejected: %s',e)
                    client.publish(TOPIC+'/result',json.dumps(result),retain=False)
                    return False
                GLib.idle_add(send)
            except Exception:
                logging.exception('MQTT message failed')
        self.mqtt.on_connect=connected
        self.mqtt.on_message=message
        self.mqtt.connect_async('127.0.0.1',1883,60)
        self.mqtt.loop_start()

    def run(self):
        self.configure_identity()
        from classic_remote import ClassicRemote
        try:self.classic=ClassicRemote(self,REPORT_MAP)
        except Exception:logging.exception('Classic HID profile could not be registered')
        manager=dbus.Interface(self.bus.get_object('org.bluez',self.adapter),'org.bluez.GattManager1')
        manager.RegisterApplication(self.app.get_path(),{},reply_handler=self.register_ad,
                                    error_handler=lambda e:(logging.error('GATT registration failed: %s',e),self.loop.quit()))
        Path(SOCKET).parent.mkdir(parents=True,exist_ok=True)
        if os.path.exists(SOCKET):
            os.unlink(SOCKET)
        bridge=self
        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                self.request.settimeout(10)
                try:
                    req=json.loads(self.rfile.readline(4096))
                    event=threading.Event()
                    result={}
                    def dispatch():
                        try:
                            result.update(bridge.command(req))
                        except Exception as e:
                            result['error']=str(e)
                        finally:
                            event.set()
                        return False
                    GLib.idle_add(dispatch)
                    if not event.wait(8):
                        result={'error':'Main loop timed out'}
                    self.wfile.write(json.dumps(result).encode()+b'\n')
                except Exception as e:
                    logging.warning('Control request failed: %s',e)
        server=socketserver.ThreadingUnixStreamServer(SOCKET,Handler)
        server.daemon_threads=True
        os.chmod(SOCKET,0o600)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        self.start_mqtt()
        GLib.timeout_add_seconds(2,self.tick)
        for sig in (signal.SIGINT,signal.SIGTERM):
            GLib.unix_signal_add(GLib.PRIORITY_DEFAULT,sig,lambda:(self.loop.quit(),False)[1])
        logging.info('BLE remote started; pairing is closed until explicitly opened')
        try:
            self.loop.run()
        finally:
            self.wake_stop.set()
            if self.wake_thread:
                self.wake_thread.join(timeout=10)
            for callback in (
                lambda:self.pairing(0) if self.agent_registered else None,
                lambda:self.classic.unregister() if self.classic else None,
                lambda:self.ad_manager.UnregisterAdvertisement(self.advertisement.path),
                lambda:manager.UnregisterApplication(self.app.get_path()),
                lambda:self.agent_manager.UnregisterAgent(self.agent.path) if self.agent_registered else None,
                self.restore_identity):
                try:callback()
                except dbus.DBusException:pass
            self.mqtt.publish(TOPIC+'/availability','offline',retain=True).wait_for_publish(timeout=2)
            self.mqtt.disconnect()
            self.mqtt.loop_stop()
            server.shutdown()
            server.server_close()
            if os.path.exists(SOCKET):os.unlink(SOCKET)

def main():
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    if len(sys.argv)>1:
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:
            client.settimeout(12)
            client.connect(SOCKET)
            client.sendall(sys.argv[1].encode()+b'\n')
            print(client.recv(65536).decode())
        return
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bridge=Bridge(dbus.SystemBus())
    try:bridge.run()
    finally:bridge.restore_identity()

if __name__=='__main__':
    main()
