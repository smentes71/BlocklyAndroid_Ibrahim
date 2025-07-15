#!/usr/bin/env python3

from bluezero import peripheral
import threading
import time
import json

class BLEServer:
    def __init__(self):
        self.connected = False
        self.chunk_buffer = {}
        self.session_data = {}
        
        # BLE aygıt ismi
        self.adv_name = 'RPI_BLE_JSON'
        
        # Servis ve karakteristik UUID'leri (Android kodunuzla aynı)
        self.service_uuid = '12345678-1234-1234-1234-123456789abc'
        self.char_uuid = 'abcd1234-ab12-cd34-ef56-abcdef123456'
        
        self.setup_ble()
    
    def setup_ble(self):
        """BLE servis ve karakteristik kurulumu"""
        
        # Karakteristik tanımı - hem okuma hem yazma destekli
        self.my_characteristic = peripheral.Characteristic(
            uuid=self.char_uuid,
            properties=['read', 'write', 'notify'],  # Yazma ve bildirim eklendi
            secure=[],  # Güvenlik kaldırıldı (isteğe bağlı)
            value=[0x00],  # Başlangıç değeri
            read_callback=self.read_callback,
            write_callback=self.write_callback  # Yazma callback'i eklendi
        )
        
        # Servis tanımı
        self.my_service = peripheral.Service(
            uuid=self.service_uuid,
            primary=True
        )
        self.my_service.add_characteristic(self.my_characteristic)
        
        # BLE sunucu oluştur
        self.my_device = peripheral.Peripheral(
            adapter_name='hci0',  # Bluetooth adaptör adı
            local_name=self.adv_name
        )
        
        self.my_device.add_service(self.my_service)
        
        # Bağlantı callback'leri
        self.my_device.on_connect = self.on_connect
        self.my_device.on_disconnect = self.on_disconnect
    
    def read_callback(self):
        """Karakteristik okunduğunda çağrılır"""
        print("📥 Karakteristik okundu")
        status = {
            "connected": self.connected,
            "active_sessions": len(self.chunk_buffer)
        }
        return list(json.dumps(status).encode('utf-8'))
    
    def write_callback(self, value):
        """Karakteristik yazıldığında çağrılır"""
        try:
            # Byte array'i string'e çevir
            data = bytes(value).decode('utf-8')
            print(f"📝 Veri alındı: {len(data)} karakter")
            
            # JSON parse et
            try:
                json_data = json.loads(data)
                
                # Parçalı veri kontrolü
                if "sessionId" in json_data:
                    self.handle_chunk(json_data)
                else:
                    # Tek parça veri
                    self.process_json_data(json_data)
                    
            except json.JSONDecodeError as e:
                print(f"❌ JSON parse hatası: {e}")
                print(f"Gelen veri: {data[:100]}...")
                
        except Exception as e:
            print(f"❌ Write callback hatası: {e}")
    
    def handle_chunk(self, chunk_data):
        """Parçalı veri işleme"""
        try:
            session_id = chunk_data["sessionId"]
            chunk_index = chunk_data["chunkIndex"]
            total_chunks = chunk_data["totalChunks"]
            data = chunk_data["data"]
            
            print(f"📦 Parça alındı: {chunk_index + 1}/{total_chunks} (Session: {session_id})")
            
            # Session verilerini başlat
            if session_id not in self.session_data:
                self.session_data[session_id] = {
                    "chunks": {},
                    "total_chunks": total_chunks,
                    "received_count": 0
                }
            
            # Parçayı kaydet
            self.session_data[session_id]["chunks"][chunk_index] = data
            self.session_data[session_id]["received_count"] += 1
            
            # Tüm parçalar alındı mı?
            if self.session_data[session_id]["received_count"] == total_chunks:
                print(f"✅ Tüm parçalar alındı: {session_id}")
                
                # Parçaları birleştir
                complete_data = ""
                for i in range(total_chunks):
                    if i in self.session_data[session_id]["chunks"]:
                        complete_data += self.session_data[session_id]["chunks"][i]
                
                # Session verilerini temizle
                del self.session_data[session_id]
                
                # Birleştirilmiş veriyi işle
                try:
                    final_json = json.loads(complete_data)
                    self.process_json_data(final_json)
                    
                    # Başarı bildirimi gönder
                    self.send_notification("TAMAM")
                    
                except json.JSONDecodeError as e:
                    print(f"❌ Birleştirilmiş JSON parse hatası: {e}")
                    self.send_notification("HATA")
            else:
                # Parça alındı bildirimi
                self.send_notification(f"OK_{chunk_index}")
                
        except Exception as e:
            print(f"❌ Chunk işleme hatası: {e}")
            self.send_notification("HATA")
    
    def process_json_data(self, json_data):
        """JSON verisini işle"""
        try:
            print("🔄 JSON verisi işleniyor...")
            
            # Kod varsa dosyaya kaydet
            if "code" in json_data:
                code = json_data["code"]
                
                # Escape karakterleri düzelt
                code = code.replace("\\n", "\n")
                code = code.replace("\\t", "\t")
                code = code.replace("\\r", "\r")
                code = code.replace("\\'", "'")
                code = code.replace('\\"', '"')
                
                # Dosyaya kaydet
                with open("received_code.py", "w", encoding="utf-8") as f:
                    f.write(code)
                
                print("✅ Kod dosyaya kaydedildi: received_code.py")
            
            # Diğer verileri işle
            if "description" in json_data:
                print(f"📝 Açıklama: {json_data['description']}")
            
            if "author" in json_data:
                print(f"👤 Yazar: {json_data['author']}")
                
            print("✅ JSON verisi başarıyla işlendi")
            
        except Exception as e:
            print(f"❌ JSON işleme hatası: {e}")
    
    def send_notification(self, message):
        """Android'e bildirim gönder"""
        try:
            if self.connected:
                # Mesajı byte array'e çevir
                data = list(message.encode('utf-8'))
                self.my_characteristic.set_value(data)
                print(f"📤 Bildirim gönderildi: {message}")
        except Exception as e:
            print(f"❌ Bildirim gönderme hatası: {e}")
    
    def on_connect(self):
        """Cihaz bağlandığında çağrılır"""
        print("📱 BLE cihaz bağlandı")
        self.connected = True
        self.chunk_buffer.clear()
        self.session_data.clear()
    
    def on_disconnect(self):
        """Cihaz ayrıldığında çağrılır"""
        print("🔌 BLE cihaz ayrıldı")
        self.connected = False
        self.chunk_buffer.clear()
        self.session_data.clear()
    
    def start_server(self):
        """BLE sunucuyu başlat"""
        print("🚀 BLE sunucu başlatılıyor...")
        print(f"📡 Cihaz adı: {self.adv_name}")
        print(f"🔧 Servis UUID: {self.service_uuid}")
        print(f"📝 Karakteristik UUID: {self.char_uuid}")
        print("⏳ Android cihazından bağlantı bekleniyor...")
        
        try:
            self.my_device.run()
        except KeyboardInterrupt:
            print("\n🛑 Sunucu durduruldu")
        except Exception as e:
            print(f"❌ Sunucu hatası: {e}")

def main():
    """Ana fonksiyon"""
    try:
        # BLE sunucuyu başlat
        ble_server = BLEServer()
        ble_server.start_server()
        
    except Exception as e:
        print(f"❌ Ana hata: {e}")

if __name__ == "__main__":
    main()