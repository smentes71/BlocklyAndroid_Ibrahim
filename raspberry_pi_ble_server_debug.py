#!/usr/bin/env python3

import dbus
import dbus.exceptions
import dbus.mainloop.glib
import dbus.service
import array
import json
import threading
import time
import sys
from gi.repository import GLib

# D-Bus ana döngüsünü ayarla
dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)

# Bluetooth sabitleri
BLUEZ_SERVICE_NAME = 'org.bluez'
GATT_MANAGER_IFACE = 'org.bluez.GattManager1'
DBUS_OM_IFACE = 'org.freedesktop.DBus.ObjectManager'
DBUS_PROP_IFACE = 'org.freedesktop.DBus.Properties'
GATT_SERVICE_IFACE = 'org.bluez.GattService1'
GATT_CHRC_IFACE = 'org.bluez.GattCharacteristic1'
GATT_DESC_IFACE = 'org.bluez.GattDescriptor1'
LE_ADVERTISING_MANAGER_IFACE = 'org.bluez.LEAdvertisingManager1'
LE_ADVERTISEMENT_IFACE = 'org.bluez.LEAdvertisement1'

def check_bluetooth_status():
    """Bluetooth durumunu kontrol et"""
    print("🔍 Bluetooth Durum Kontrolü")
    print("=" * 40)
    
    try:
        import subprocess
        
        # Bluetooth servis durumu
        result = subprocess.run(['systemctl', 'is-active', 'bluetooth'], 
                              capture_output=True, text=True)
        print(f"📡 Bluetooth Servisi: {result.stdout.strip()}")
        
        # HCI durumu
        result = subprocess.run(['hciconfig'], capture_output=True, text=True)
        if 'UP RUNNING' in result.stdout:
            print("✅ Bluetooth Adapter: Aktif")
        else:
            print("❌ Bluetooth Adapter: Pasif")
            print("🔧 Bluetooth'u etkinleştiriliyor...")
            subprocess.run(['sudo', 'hciconfig', 'hci0', 'up'])
        
        # Discoverable yap
        subprocess.run(['sudo', 'hciconfig', 'hci0', 'piscan'])
        print("🔍 Bluetooth keşfedilebilir yapıldı")
        
    except Exception as e:
        print(f"⚠️ Durum kontrolü hatası: {e}")

class InvalidArgsException(dbus.exceptions.DBusException):
    _dbus_error_name = 'org.freedesktop.DBus.Error.InvalidArgs'

class NotSupportedException(dbus.exceptions.DBusException):
    _dbus_error_name = 'org.bluez.Error.NotSupported'

class NotPermittedException(dbus.exceptions.DBusException):
    _dbus_error_name = 'org.bluez.Error.NotPermitted'

class InvalidValueLengthException(dbus.exceptions.DBusException):
    _dbus_error_name = 'org.bluez.Error.InvalidValueLength'

class FailedException(dbus.exceptions.DBusException):
    _dbus_error_name = 'org.bluez.Error.Failed'

class Application(dbus.service.Object):
    def __init__(self, bus):
        self.path = '/'
        self.services = []
        dbus.service.Object.__init__(self, bus, self.path)

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def add_service(self, service):
        self.services.append(service)

    @dbus.service.method(DBUS_OM_IFACE, out_signature='a{oa{sa{sv}}}')
    def GetManagedObjects(self):
        response = {}
        for service in self.services:
            response[service.get_path()] = service.get_properties()
            chrcs = service.get_characteristics()
            for chrc in chrcs:
                response[chrc.get_path()] = chrc.get_properties()
                descs = chrc.get_descriptors()
                for desc in descs:
                    response[desc.get_path()] = desc.get_properties()
        return response

class Service(dbus.service.Object):
    PATH_BASE = '/org/bluez/example/service'

    def __init__(self, bus, index, uuid, primary):
        self.path = self.PATH_BASE + str(index)
        self.bus = bus
        self.uuid = uuid
        self.primary = primary
        self.characteristics = []
        dbus.service.Object.__init__(self, bus, self.path)

    def get_properties(self):
        return {
            GATT_SERVICE_IFACE: {
                'UUID': self.uuid,
                'Primary': self.primary,
                'Characteristics': dbus.Array(
                    self.get_characteristic_paths(),
                    signature='o')
            }
        }

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def add_characteristic(self, characteristic):
        self.characteristics.append(characteristic)

    def get_characteristic_paths(self):
        result = []
        for chrc in self.characteristics:
            result.append(chrc.get_path())
        return result

    def get_characteristics(self):
        return self.characteristics

class Characteristic(dbus.service.Object):
    def __init__(self, bus, index, uuid, flags, service):
        self.path = service.path + '/char' + str(index)
        self.bus = bus
        self.uuid = uuid
        self.service = service
        self.flags = flags
        self.descriptors = []
        self.value = []
        dbus.service.Object.__init__(self, bus, self.path)

    def get_properties(self):
        return {
            GATT_CHRC_IFACE: {
                'Service': self.service.get_path(),
                'UUID': self.uuid,
                'Flags': self.flags,
                'Descriptors': dbus.Array(
                    self.get_descriptor_paths(),
                    signature='o')
            }
        }

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def add_descriptor(self, descriptor):
        self.descriptors.append(descriptor)

    def get_descriptor_paths(self):
        result = []
        for desc in self.descriptors:
            result.append(desc.get_path())
        return result

    def get_descriptors(self):
        return self.descriptors

    @dbus.service.method(GATT_CHRC_IFACE,
                        in_signature='a{sv}',
                        out_signature='ay')
    def ReadValue(self, options):
        print('📥 Characteristic okundu')
        return dbus.Array(self.value, signature=dbus.Signature('y'))

    @dbus.service.method(GATT_CHRC_IFACE, in_signature='aya{sv}')
    def WriteValue(self, value, options):
        print(f'📝 Veri yazıldı: {len(value)} byte')
        self.value = value
        self.handle_write_value(bytes(value))

    def handle_write_value(self, data):
        pass

    @dbus.service.method(GATT_CHRC_IFACE)
    def StartNotify(self):
        print('📡 Notification başlatıldı')

    @dbus.service.method(GATT_CHRC_IFACE)
    def StopNotify(self):
        print('🛑 Notification durduruldu')

    @dbus.service.signal(DBUS_PROP_IFACE,
                         signature='sa{sv}as')
    def PropertiesChanged(self, interface, changed, invalidated):
        pass

class JSONCharacteristic(Characteristic):
    def __init__(self, bus, index, service):
        Characteristic.__init__(
            self, bus, index,
            'abcd1234-ab12-cd34-ef56-abcdef123456',
            ['read', 'write', 'notify'],
            service)
        
        self.chunk_buffer = {}
        self.session_data = {}

    def handle_write_value(self, data):
        try:
            data_str = data.decode('utf-8')
            print(f"📝 Veri alındı: {len(data_str)} karakter")
            print(f"📄 İçerik: {data_str[:100]}...")
            
            try:
                json_data = json.loads(data_str)
                
                if "sessionId" in json_data:
                    self.handle_chunk(json_data)
                else:
                    self.process_json_data(json_data)
                    
            except json.JSONDecodeError as e:
                print(f"❌ JSON parse hatası: {e}")
                
        except Exception as e:
            print(f"❌ Write handler hatası: {e}")

    def handle_chunk(self, chunk_data):
        try:
            session_id = chunk_data["sessionId"]
            chunk_index = chunk_data["chunkIndex"]
            total_chunks = chunk_data["totalChunks"]
            data = chunk_data["data"]
            
            print(f"📦 Parça alındı: {chunk_index + 1}/{total_chunks} (Session: {session_id})")
            
            if session_id not in self.session_data:
                self.session_data[session_id] = {
                    "chunks": {},
                    "total_chunks": total_chunks,
                    "received_count": 0
                }
            
            self.session_data[session_id]["chunks"][chunk_index] = data
            self.session_data[session_id]["received_count"] += 1
            
            if self.session_data[session_id]["received_count"] == total_chunks:
                print(f"✅ Tüm parçalar alındı: {session_id}")
                
                complete_data = ""
                for i in range(total_chunks):
                    if i in self.session_data[session_id]["chunks"]:
                        complete_data += self.session_data[session_id]["chunks"][i]
                
                del self.session_data[session_id]
                
                try:
                    final_json = json.loads(complete_data)
                    self.process_json_data(final_json)
                    self.send_notification("TAMAM")
                    
                except json.JSONDecodeError as e:
                    print(f"❌ Birleştirilmiş JSON parse hatası: {e}")
                    self.send_notification("HATA")
            else:
                self.send_notification(f"OK_{chunk_index}")
                
        except Exception as e:
            print(f"❌ Chunk işleme hatası: {e}")
            self.send_notification("HATA")

    def process_json_data(self, json_data):
        try:
            print("🔄 JSON verisi işleniyor...")
            
            if "code" in json_data:
                code = json_data["code"]
                code = code.replace("\\n", "\n")
                code = code.replace("\\t", "\t")
                code = code.replace("\\r", "\r")
                code = code.replace("\\'", "'")
                code = code.replace('\\"', '"')
                
                with open("received_code.py", "w", encoding="utf-8") as f:
                    f.write(code)
                
                print("✅ Kod dosyaya kaydedildi: received_code.py")
            
            if "description" in json_data:
                print(f"📝 Açıklama: {json_data['description']}")
            
            if "author" in json_data:
                print(f"👤 Yazar: {json_data['author']}")
                
            print("✅ JSON verisi başarıyla işlendi")
            
        except Exception as e:
            print(f"❌ JSON işleme hatası: {e}")

    def send_notification(self, message):
        try:
            print(f"📤 Bildirim gönderildi: {message}")
            self.value = list(message.encode('utf-8'))
            self.PropertiesChanged(
                GATT_CHRC_IFACE,
                {'Value': dbus.Array(self.value, signature=dbus.Signature('y'))},
                []
            )
        except Exception as e:
            print(f"❌ Bildirim gönderme hatası: {e}")

class JSONService(Service):
    def __init__(self, bus, index):
        Service.__init__(self, bus, index, '12345678-1234-1234-1234-123456789abc', True)
        self.add_characteristic(JSONCharacteristic(bus, 0, self))

class Advertisement(dbus.service.Object):
    PATH_BASE = '/org/bluez/example/advertisement'

    def __init__(self, bus, index, advertising_type):
        self.path = self.PATH_BASE + str(index)
        self.bus = bus
        self.ad_type = advertising_type
        self.service_uuids = None
        self.manufacturer_data = None
        self.solicit_uuids = None
        self.service_data = None
        self.local_name = None
        self.include_tx_power = False
        dbus.service.Object.__init__(self, bus, self.path)

    def get_properties(self):
        properties = dict()
        properties['Type'] = self.ad_type
        if self.service_uuids is not None:
            properties['ServiceUUIDs'] = dbus.Array(self.service_uuids,
                                                    signature='s')
        if self.solicit_uuids is not None:
            properties['SolicitUUIDs'] = dbus.Array(self.solicit_uuids,
                                                    signature='s')
        if self.manufacturer_data is not None:
            properties['ManufacturerData'] = dbus.Dictionary(
                self.manufacturer_data, signature='qv')
        if self.service_data is not None:
            properties['ServiceData'] = dbus.Dictionary(self.service_data,
                                                        signature='sv')
        if self.local_name is not None:
            properties['LocalName'] = dbus.String(self.local_name)
        if self.include_tx_power:
            properties['IncludeTxPower'] = dbus.Boolean(self.include_tx_power)

        return {LE_ADVERTISEMENT_IFACE: properties}

    def get_path(self):
        return dbus.ObjectPath(self.path)

    @dbus.service.method(DBUS_PROP_IFACE,
                         in_signature='s',
                         out_signature='a{sv}')
    def GetAll(self, interface):
        if interface != LE_ADVERTISEMENT_IFACE:
            raise InvalidArgsException()
        return self.get_properties()[LE_ADVERTISEMENT_IFACE]

    @dbus.service.method(LE_ADVERTISEMENT_IFACE,
                         in_signature='',
                         out_signature='')
    def Release(self):
        print('📡 Advertisement serbest bırakıldı')

class JSONAdvertisement(Advertisement):
    def __init__(self, bus, index):
        Advertisement.__init__(self, bus, index, 'peripheral')
        self.add_service_uuid('12345678-1234-1234-1234-123456789abc')
        self.add_local_name('ESP32_JSON_BLE')
        self.include_tx_power = True

    def add_service_uuid(self, uuid):
        if not self.service_uuids:
            self.service_uuids = []
        self.service_uuids.append(uuid)

    def add_local_name(self, name):
        self.local_name = name

def register_ad_cb():
    print('✅ Advertisement kaydedildi')

def register_ad_error_cb(error):
    print(f'❌ Advertisement kayıt hatası: {error}')
    sys.exit(1)

def register_app_cb():
    print('✅ GATT uygulama kaydedildi')

def register_app_error_cb(error):
    print(f'❌ GATT uygulama kayıt hatası: {error}')
    sys.exit(1)

def find_adapter(bus):
    remote_om = dbus.Interface(bus.get_object(BLUEZ_SERVICE_NAME, '/'),
                               DBUS_OM_IFACE)
    objects = remote_om.GetManagedObjects()

    for o, props in objects.items():
        if GATT_MANAGER_IFACE in props.keys():
            print(f"📡 Adapter bulundu: {o}")
            return o

    return None

def main():
    print("🚀 Raspberry Pi BLE JSON Sunucusu (Debug)")
    print("=" * 50)
    
    # Bluetooth durumunu kontrol et
    check_bluetooth_status()
    
    try:
        # D-Bus bağlantısı
        bus = dbus.SystemBus()
        print("✅ D-Bus bağlantısı kuruldu")

        # Adapter bul
        adapter = find_adapter(bus)
        if not adapter:
            print('❌ BLE adapter bulunamadı!')
            print('🔧 Bluetooth servisini yeniden başlatmayı deneyin:')
            print('   sudo systemctl restart bluetooth')
            return

        print(f'📡 BLE Adapter: {adapter}')

        # Servis manager
        service_manager = dbus.Interface(
            bus.get_object(BLUEZ_SERVICE_NAME, adapter),
            GATT_MANAGER_IFACE)

        # Advertisement manager
        ad_manager = dbus.Interface(bus.get_object(BLUEZ_SERVICE_NAME, adapter),
                                    LE_ADVERTISING_MANAGER_IFACE)

        # Uygulama oluştur
        app = Application(bus)
        app.add_service(JSONService(bus, 0))

        # Advertisement oluştur
        adv = JSONAdvertisement(bus, 0)

        print("📋 Servisler kaydediliyor...")
        
        # Servisleri kaydet
        service_manager.RegisterApplication(app.get_path(), {},
                                            reply_handler=register_app_cb,
                                            error_handler=register_app_error_cb)

        # Advertisement'ı kaydet
        ad_manager.RegisterAdvertisement(adv.get_path(), {},
                                         reply_handler=register_ad_cb,
                                         error_handler=register_ad_error_cb)

        print("✅ BLE sunucu hazır!")
        print("📱 Cihaz ismi: ESP32_JSON_BLE")
        print("🔍 Android cihazından tarama yapabilirsiniz...")
        print("🛑 Durdurmak için Ctrl+C")
        
        # Ana döngü
        mainloop = GLib.MainLoop()
        mainloop.run()
        
    except KeyboardInterrupt:
        print("\n🛑 Sunucu durduruldu")
    except Exception as e:
        print(f"❌ Ana hata: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()