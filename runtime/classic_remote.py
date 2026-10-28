"""Classic HID device-initiated channels; preserves BlueZ's existing listeners."""
import logging
import select
import socket
import threading
import time
import dbus
import dbus.service
from gi.repository import GLib

PROFILE='org.bluez.Profile1'
UUID='40d2984f-75fa-4993-87d0-6563f912b94e'

def service_record(descriptor):
    return f'''<?xml version="1.0" encoding="UTF-8" ?>
<record>
 <attribute id="0x0001"><sequence><uuid value="0x1124"/></sequence></attribute>
 <attribute id="0x0004"><sequence>
  <sequence><uuid value="0x0100"/><uint16 value="0x0011"/></sequence>
  <sequence><uuid value="0x0011"/></sequence>
 </sequence></attribute>
 <attribute id="0x0005"><sequence><uuid value="0x1002"/></sequence></attribute>
 <attribute id="0x0006"><sequence><uint16 value="0x656e"/><uint16 value="0x006a"/><uint16 value="0x0100"/></sequence></attribute>
 <attribute id="0x0009"><sequence><sequence><uuid value="0x1124"/><uint16 value="0x0101"/></sequence></sequence></attribute>
 <attribute id="0x000d"><sequence><sequence>
  <sequence><uuid value="0x0100"/><uint16 value="0x0013"/></sequence>
  <sequence><uuid value="0x0011"/></sequence>
 </sequence></sequence></attribute>
 <attribute id="0x0100"><text value="HA Projector Remote"/></attribute>
 <attribute id="0x0101"><text value="Home Assistant projector remote"/></attribute>
 <attribute id="0x0102"><text value="Local"/></attribute>
 <attribute id="0x0200"><uint16 value="0x0100"/></attribute>
 <attribute id="0x0201"><uint16 value="0x0111"/></attribute>
 <attribute id="0x0202"><uint8 value="0x40"/></attribute>
 <attribute id="0x0203"><uint8 value="0x00"/></attribute>
 <attribute id="0x0204"><boolean value="true"/></attribute>
 <attribute id="0x0205"><boolean value="true"/></attribute>
 <attribute id="0x0206"><sequence><sequence><uint8 value="0x22"/><text encoding="hex" value="{descriptor.hex()}"/></sequence></sequence></attribute>
 <attribute id="0x0207"><sequence><sequence><uint16 value="0x0409"/><uint16 value="0x0100"/></sequence></sequence></attribute>
 <attribute id="0x0208"><boolean value="false"/></attribute>
 <attribute id="0x0209"><boolean value="true"/></attribute>
 <attribute id="0x020a"><boolean value="true"/></attribute>
 <attribute id="0x020b"><uint16 value="0x0101"/></attribute>
 <attribute id="0x020c"><uint16 value="0x0c80"/></attribute>
 <attribute id="0x020d"><boolean value="false"/></attribute>
 <attribute id="0x020e"><boolean value="false"/></attribute>
</record>'''

class ClassicRemote(dbus.service.Object):
    def __init__(self,bridge,descriptor):
        self.bridge=bridge
        self.path='/org/bluez/ProjectorRemote/classic'
        super().__init__(bridge.bus,self.path)
        self.manager=dbus.Interface(bridge.bus.get_object('org.bluez','/org/bluez'),
                                    'org.bluez.ProfileManager1')
        self.control=None
        self.interrupt=None
        self.connecting=False
        self.last_error=None
        self.protocol=1
        self.lock=threading.RLock()
        self.registered=False
        # PSM zero registers SDP only. The existing system HID input listeners
        # remain owned by BlueZ. This device initiates its own outgoing channels.
        self.manager.RegisterProfile(self.path,UUID,{
            'Name':'HA Projector Classic HID','Service':'00001124-0000-1000-8000-00805f9b34fb','Role':'server','PSM':dbus.UInt16(0),
            'RequireAuthentication':True,'RequireAuthorization':True,
            'ServiceRecord':service_record(descriptor)})
        self.registered=True
        logging.info('Classic HID SDP profile registered without replacing system listeners')

    @dbus.service.method(PROFILE,in_signature='',out_signature='')
    def Release(self):
        self.registered=False
        self.close()

    @dbus.service.method(PROFILE,in_signature='oha{sv}',out_signature='')
    def NewConnection(self,device,fd,properties):
        raise dbus.exceptions.DBusException('Device initiates HID channels',
                                            name='org.bluez.Error.Rejected')

    @dbus.service.method(PROFILE,in_signature='o',out_signature='')
    def RequestDisconnection(self,device):
        self.close()

    def status(self):
        return {'registered':self.registered,'connected':self.control is not None and self.interrupt is not None,
                'connecting':self.connecting,'last_error':self.last_error}

    def close(self):
        with self.lock:
            channels=(self.control,self.interrupt)
            self.control=self.interrupt=None
            for channel in channels:
                if channel:
                    try:channel.close()
                    except OSError:pass

    def connect(self,device,command=None):
        if self.connecting:
            raise ValueError('Classic HID connection is already in progress')
        if self.status()['connected']:
            return {'connected':True}
        address=device.rsplit('/dev_',1)[1].replace('_',':')
        self.connecting=True
        def establish():
            try:
                for attempt in range(3):
                    channels=[]
                    try:
                        for psm in (17,19):
                            channel=socket.socket(socket.AF_BLUETOOTH,socket.SOCK_SEQPACKET,socket.BTPROTO_L2CAP)
                            channels.append(channel)
                            channel.setsockopt(getattr(socket,'SOL_BLUETOOTH',274),4,bytes([3,0]))
                            channel.settimeout(8)
                            channel.connect((address,psm))
                            logging.info('Classic HID channel connected to %s PSM %s',address,psm)
                        with self.lock:
                            self.control,self.interrupt=channels
                        self.last_error=None
                        threading.Thread(target=self.read_loop,args=tuple(channels),daemon=True).start()
                        if command:
                            def deliver():
                                if self.control is not channels[0] or self.interrupt is not channels[1]:
                                    logging.warning('Queued HID command discarded after channel changed')
                                    return False
                                try:self.bridge.command({'action':'send','command':command})
                                except Exception:logging.exception('Queued HID command failed')
                                return False
                            # Android must register the input device after SET_IDLE.
                            GLib.timeout_add(750,deliver)
                        return
                    except Exception as e:
                        self.last_error=str(e)
                        logging.warning('Classic HID connection to %s attempt %s failed: %s',address,attempt+1,e)
                        for channel in channels:
                            channel.close()
                        if getattr(e,'errno',None) not in (16,71,104,110,111,112) or attempt==2:
                            return
                        time.sleep(attempt+1)
            finally:
                self.connecting=False
        threading.Thread(target=establish,daemon=True).start()
        return {'connecting':True,'device':address,'queued_command':command}

    def read_loop(self,control,interrupt):
        try:
            while self.control is control:
                ready,_,_=select.select([control,interrupt],[],[],2)
                for channel in ready:
                    data=channel.recv(1024)
                    if not data:
                        return
                    logging.info('Classic HID received %s: %s',
                                 'control' if channel is control else 'interrupt',data.hex())
                    if channel is interrupt:
                        continue
                    operation=data[0]>>4
                    if operation==4: # GET_REPORT: return zero input report.
                        rid=data[1] if len(data)>1 else 1
                        length={1:8,2:2,3:1}.get(rid)
                        control.send(bytes([0xa1,rid])+bytes(length)) if length else control.send(b'\x02')
                    elif operation in (5,7,9): # SET_REPORT/PROTOCOL/IDLE
                        if operation==7:self.protocol=data[0]&1
                        control.send(b'\x00')
                    elif operation==6:
                        control.send(bytes([0xa0,self.protocol]))
                    elif operation==8:
                        control.send(bytes([0xa0,0]))
                    elif operation==1:
                        if data[0]&15==5:
                            logging.warning('Host requested virtual cable unplug; preserving bond store')
                            return
                    else:
                        control.send(b'\x03') # Unsupported transaction.
        except OSError as e:
            logging.info('Classic HID channel ended: %s',e)
        finally:
            if self.control is control:
                self.close()

    def send(self,report_id,data):
        with self.lock:
            if self.interrupt is None:
                raise ValueError('Classic HID interrupt channel is not connected')
            if self.protocol!=1:
                raise ValueError('Host selected boot protocol; power reports need report protocol')
            self.interrupt.send(bytes([0xa1,report_id])+bytes(data))

    def unregister(self):
        self.close()
        if self.registered:
            self.manager.UnregisterProfile(self.path)
            self.registered=False
