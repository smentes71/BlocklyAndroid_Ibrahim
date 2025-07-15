#!/bin/bash

echo "🔍 Bluetooth Durum Kontrolü"
echo "=========================="

# Bluetooth servis durumu
echo "📡 Bluetooth Servisi:"
sudo systemctl status bluetooth --no-pager -l

echo -e "\n🔧 Bluetooth Adapter Durumu:"
sudo hciconfig

echo -e "\n📶 Bluetooth Güç Durumu:"
sudo rfkill list bluetooth

echo -e "\n🔍 D-Bus Bluetooth Servisleri:"
dbus-send --system --dest=org.freedesktop.DBus --type=method_call --print-reply /org/freedesktop/DBus org.freedesktop.DBus.ListNames | grep bluez

echo -e "\n📋 Bluetooth Cihazları:"
sudo bluetoothctl list

echo -e "\n🔄 Bluetooth'u Yeniden Başlat:"
sudo systemctl restart bluetooth
sleep 2

echo -e "\n✅ Bluetooth Hazır!"