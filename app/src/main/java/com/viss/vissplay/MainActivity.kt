package com.viss.vissplay

import android.Manifest
import android.annotation.SuppressLint
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothGatt
import android.bluetooth.BluetoothGattCallback
import android.bluetooth.BluetoothGattCharacteristic
import android.bluetooth.BluetoothGattDescriptor
import android.bluetooth.BluetoothGattService
import android.bluetooth.BluetoothManager
import android.bluetooth.BluetoothProfile
import android.bluetooth.le.BluetoothLeScanner
import android.bluetooth.le.ScanCallback
import android.bluetooth.le.ScanResult
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.webkit.JavascriptInterface
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import org.json.JSONObject
import java.util.UUID

class MainActivity : AppCompatActivity() {
    private lateinit var webView: WebView
    private lateinit var bluetoothManager: BluetoothManager
    private lateinit var bluetoothAdapter: BluetoothAdapter
    private var bluetoothLeScanner: BluetoothLeScanner? = null
    private var bluetoothGatt: BluetoothGatt? = null
    private var bluetoothGattCharacteristic: BluetoothGattCharacteristic? = null
    private var isScanning = false
    private var isConnected = false
    private val handler = Handler(Looper.getMainLooper())
    
    // ESP32 Service ve Characteristic UUID'leri
    private val SERVICE_UUID = UUID.fromString("12345678-1234-1234-1234-123456789abc")
    private val CHARACTERISTIC_UUID = UUID.fromString("abcd1234-ab12-cd34-ef56-abcdef123456")
    
    companion object {
        private const val PERMISSION_REQUEST_CODE = 1
        private const val TAG = "MainActivity"
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.KITKAT) {
            WebView.setWebContentsDebuggingEnabled(true)
        }

        // Bluetooth Manager ve Adapter
        bluetoothManager = getSystemService(Context.BLUETOOTH_SERVICE) as BluetoothManager
        bluetoothAdapter = bluetoothManager.adapter
        
        webView = WebView(this)
        setContentView(webView)
        
        // WebView ayarları
        webView.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            allowFileAccess = true
            allowContentAccess = true
            setSupportZoom(true)
            builtInZoomControls = false
            displayZoomControls = false
        }
        
        // JavaScript Interface ekle
        webView.addJavascriptInterface(BluetoothBridge(), "AndroidBluetooth")
        
        // WebViewClient ayarla
        webView.webViewClient = WebViewClient()
        
        // Assets'teki index.html'i yükle
        webView.loadUrl("file:///android_asset/index.html")
        
        // Bluetooth izinlerini kontrol et
        checkBluetoothPermissions()
    }
    
    private fun checkBluetoothPermissions() {
        val permissions = mutableListOf<String>()
        
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            permissions.addAll(arrayOf(
                Manifest.permission.BLUETOOTH_CONNECT,
                Manifest.permission.BLUETOOTH_SCAN
            ))
        } else {
            permissions.addAll(arrayOf(
                Manifest.permission.BLUETOOTH,
                Manifest.permission.BLUETOOTH_ADMIN
            ))
        }
        
        permissions.addAll(arrayOf(
            Manifest.permission.ACCESS_FINE_LOCATION,
            Manifest.permission.ACCESS_COARSE_LOCATION
        ))
        
        val missingPermissions = permissions.filter {
            ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED
        }
        
        if (missingPermissions.isNotEmpty()) {
            ActivityCompat.requestPermissions(this, missingPermissions.toTypedArray(), PERMISSION_REQUEST_CODE)
        }
    }
    
    inner class BluetoothBridge {
        
        @JavascriptInterface
        fun connectToESP32() {
            Log.d(TAG, "ESP32 bağlantısı başlatılıyor...")
            
            // Önce mevcut bağlantıyı temizle
            if (bluetoothGatt != null) {
                bluetoothGatt?.close()
                bluetoothGatt = null
                isConnected = false
            }
            
            // İzinleri kontrol et
            val permissions = mutableListOf<String>()
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                permissions.addAll(arrayOf(
                    Manifest.permission.BLUETOOTH_CONNECT,
                    Manifest.permission.BLUETOOTH_SCAN
                ))
            } else {
                permissions.addAll(arrayOf(
                    Manifest.permission.BLUETOOTH,
                    Manifest.permission.BLUETOOTH_ADMIN
                ))
            }
            permissions.addAll(arrayOf(
                Manifest.permission.ACCESS_FINE_LOCATION,
                Manifest.permission.ACCESS_COARSE_LOCATION
            ))
            
            val missingPermissions = permissions.filter {
                ContextCompat.checkSelfPermission(this@MainActivity, it) != PackageManager.PERMISSION_GRANTED
            }
            
            if (missingPermissions.isNotEmpty()) {
                callJavaScript("showAlert('Bluetooth izinleri gerekli! Lütfen uygulamayı yeniden başlatın.', 'error')")
                callJavaScript("onConnectionFailed()")
                return
            }
            
            if (!bluetoothAdapter.isEnabled) {
                callJavaScript("showAlert('Bluetooth kapalı! Lütfen açın.', 'error')")
                callJavaScript("onConnectionFailed()")
                return
            }
            
            // Location servislerinin açık olup olmadığını kontrol et
            val locationManager = getSystemService(Context.LOCATION_SERVICE) as android.location.LocationManager
            val isLocationEnabled = locationManager.isProviderEnabled(android.location.LocationManager.GPS_PROVIDER) ||
                    locationManager.isProviderEnabled(android.location.LocationManager.NETWORK_PROVIDER)
            
            if (!isLocationEnabled && Build.VERSION.SDK_INT < Build.VERSION_CODES.S) {
                callJavaScript("showAlert('Konum servisleri kapalı! BLE tarama için gerekli.', 'error')")
                callJavaScript("onConnectionFailed()")
                return
            }
            
            bluetoothLeScanner = bluetoothAdapter.bluetoothLeScanner
            if (bluetoothLeScanner != null) {
                callJavaScript("addLog('🔍 Bluetooth LE Scanner hazır')")
                startScan()
            } else {
                callJavaScript("showAlert('Bluetooth LE tarama desteklenmiyor!', 'error')")
                callJavaScript("onConnectionFailed()")
            }
        }
        
        @JavascriptInterface
        fun sendChunkedData(jsonData: String) {
            Log.d(TAG, "Parçalı veri gönderimi başlıyor: ${jsonData.length} karakter")
            
            if (!isConnected || bluetoothGattCharacteristic == null) {
                callJavaScript("showAlert('ESP32 ile bağlantı yok!', 'error')")
                return
            }
            
            Thread {
                sendDataInChunks(jsonData)
            }.start()
        }
        
        @JavascriptInterface
        fun isBluetoothConnected(): Boolean {
            return isConnected
        }
    }
    
    @SuppressLint("MissingPermission")
    private fun startScan() {
        if (isScanning) return
        
        isScanning = true
        callJavaScript("addLog('🔍 ESP32 cihazı aranıyor...')")
        
        // Scan callback'i sınıf seviyesinde tanımla
        val scanCallback = createScanCallback()
        
        try {
            bluetoothLeScanner?.startScan(scanCallback)
            callJavaScript("addLog('✅ Bluetooth tarama başlatıldı')")
        } catch (e: Exception) {
            Log.e(TAG, "Scan başlatma hatası: ${e.message}")
            callJavaScript("showAlert('Bluetooth tarama başlatılamadı: ${e.message}', 'error')")
            callJavaScript("onConnectionFailed()")
            isScanning = false
            return
        }
        
        // 15 saniye sonra taramayı durdur (10'dan 15'e çıkardık)
        handler.postDelayed({
            if (isScanning) {
                stopScan()
                callJavaScript("showAlert('ESP32 cihazı bulunamadı! Tekrar deneyin.', 'error')")
                callJavaScript("onConnectionFailed()")
            }
        }, 15000)
    }
    
    private fun createScanCallback(): ScanCallback {
        val scanCallback = object : ScanCallback() {
            override fun onScanResult(callbackType: Int, result: ScanResult?) {
                result?.let { scanResult ->
                    val device = scanResult.device
                    val deviceName = device.name
                    
                    Log.d(TAG, "Cihaz bulundu: $deviceName, MAC: ${device.address}")
                    callJavaScript("addLog('📱 Cihaz bulundu: ${deviceName ?: "Bilinmeyen"} (${device.address})')")
                    
                    // ESP32 cihaz adını daha esnek kontrol et
                    if (deviceName != null && (deviceName.contains("ESP32") || deviceName == "ESP32_JSON_BLE")) {
                        stopScan()
                        callJavaScript("addLog('📱 ESP32 cihazı bulundu: $deviceName')")
                        connectToDevice(device)
                    } else if (deviceName == null) {
                        // Cihaz adı null ise MAC adresine göre kontrol et (opsiyonel)
                        callJavaScript("addLog('⚠️ İsimsiz cihaz bulundu: ${device.address}')")
                    }
                }
            }
            
            override fun onScanFailed(errorCode: Int) {
                Log.e(TAG, "Bluetooth tarama başarısız: $errorCode")
                isScanning = false
                val errorMessage = when(errorCode) {
                    SCAN_FAILED_ALREADY_STARTED -> "Tarama zaten başlatılmış"
                    SCAN_FAILED_APPLICATION_REGISTRATION_FAILED -> "Uygulama kaydı başarısız"
                    SCAN_FAILED_FEATURE_UNSUPPORTED -> "BLE özelliği desteklenmiyor"
                    SCAN_FAILED_INTERNAL_ERROR -> "İç hata"
                    else -> "Bilinmeyen hata: $errorCode"
                }
                callJavaScript("showAlert('Bluetooth tarama başarısız: $errorMessage', 'error')")
                callJavaScript("onConnectionFailed()")
            }
        }
        return scanCallback
    }
    
    @SuppressLint("MissingPermission")
    private fun stopScan() {
        if (!isScanning) return
        isScanning = false
        try {
            bluetoothLeScanner?.stopScan(object : ScanCallback() {})
            callJavaScript("addLog('🛑 Bluetooth tarama durduruldu')")
        } catch (e: Exception) {
            Log.e(TAG, "Scan durdurma hatası: ${e.message}")
        }
    }
    
    @SuppressLint("MissingPermission")
    private fun connectToDevice(device: BluetoothDevice) {
        Log.d(TAG, "Cihaza bağlanılıyor: ${device.name}")
        callJavaScript("addLog('🔗 ESP32 ile bağlantı kuruluyor...')")
        
        val gattCallback = object : BluetoothGattCallback() {
            override fun onConnectionStateChange(gatt: BluetoothGatt?, status: Int, newState: Int) {
                if (status != BluetoothGatt.GATT_SUCCESS) {
                    Log.e(TAG, "GATT bağlantı hatası: $status")
                    callJavaScript("showAlert('ESP32 ile bağlantı hatası!', 'error')")
                    callJavaScript("onConnectionFailed()")
                    return
                }
                
                when (newState) {
                    BluetoothProfile.STATE_CONNECTED -> {
                        Log.d(TAG, "GATT bağlantısı kuruldu")
                        isConnected = true
                        callJavaScript("addLog('✅ GATT bağlantısı kuruldu')")
                        callJavaScript("updateStatus('ESP32 ile bağlantı kuruldu!', true)")
                        // Servis keşfi için kısa bir bekleme
                        handler.postDelayed({
                            gatt?.discoverServices()
                        }, 1000)
                    }
                    BluetoothProfile.STATE_DISCONNECTED -> {
                        Log.d(TAG, "GATT bağlantısı kesildi")
                        isConnected = false
                        bluetoothGattCharacteristic = null
                        callJavaScript("addLog('❌ GATT bağlantısı kesildi')")
                        callJavaScript("updateStatus('ESP32 ile bağlantı kesildi', false)")
                        callJavaScript("onConnectionFailed()")
                        gatt?.close()
                    }
                }
            }
            
            override fun onServicesDiscovered(gatt: BluetoothGatt?, status: Int) {
                if (status == BluetoothGatt.GATT_SUCCESS) {
                    val service: BluetoothGattService? = gatt?.getService(SERVICE_UUID)
                    bluetoothGattCharacteristic = service?.getCharacteristic(CHARACTERISTIC_UUID)
                    
                    if (bluetoothGattCharacteristic != null) {
                        Log.d(TAG, "Characteristic bulundu")
                        callJavaScript("addLog('🔍 Characteristic bulundu')")
                        callJavaScript("showAlert('ESP32 ile başarıyla bağlantı kuruldu!', 'success')")
                        callJavaScript("onConnectionSuccess()")
                        
                        // Notification'ları etkinleştir
                        enableNotifications(gatt, bluetoothGattCharacteristic!!)
                    } else {
                        Log.e(TAG, "Characteristic bulunamadı")
                        callJavaScript("showAlert('ESP32 servisi bulunamadı!', 'error')")
                        callJavaScript("onConnectionFailed()")
                    }
                } else {
                    Log.e(TAG, "Service discovery başarısız: $status")
                    callJavaScript("showAlert('ESP32 servisleri bulunamadı!', 'error')")
                    callJavaScript("onConnectionFailed()")
                }
            }
            
            override fun onCharacteristicChanged(gatt: BluetoothGatt?, characteristic: BluetoothGattCharacteristic?) {
                characteristic?.let {
                    val receivedData = String(it.value)
                    Log.d(TAG, "Veri alındı: $receivedData")
                    callJavaScript("addLog('📥 ESP32 yanıtı: $receivedData')")
                    
                    when (receivedData) {
                        "TAMAM" -> callJavaScript("showAlert('ESP32 tarafından onaylandı: ✅ TAMAM', 'success')")
                        "HATA" -> callJavaScript("showAlert('ESP32 HATA mesajı gönderdi ❌', 'error')")
                        else -> callJavaScript("showAlert('ESP32 mesajı: $receivedData', 'success')")
                    }
                }
            }
        }
        
        bluetoothGatt = device.connectGatt(this, false, gattCallback)
    }
    
    @SuppressLint("MissingPermission")
    private fun enableNotifications(gatt: BluetoothGatt?, characteristic: BluetoothGattCharacteristic) {
        gatt?.setCharacteristicNotification(characteristic, true)
        
        val descriptor = characteristic.getDescriptor(UUID.fromString("00002902-0000-1000-8000-00805f9b34fb"))
        descriptor?.let {
            it.value = BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE
            gatt?.writeDescriptor(it)
        }
    }
    
    @SuppressLint("MissingPermission")
    private fun sendDataInChunks(jsonData: String) {
        try {
            val sessionId = generateSessionId()
            val chunkSize = 80
            val chunks = jsonData.chunked(chunkSize)
            
            callJavaScript("addLog('📦 Veri ${chunks.size} parçaya bölündü (Session: $sessionId)')")
            
            for (i in chunks.indices) {
                val chunkJson = JSONObject().apply {
                    put("sessionId", sessionId)
                    put("chunkIndex", i)
                    put("totalChunks", chunks.size)
                    put("data", chunks[i])
                }.toString()
                
                bluetoothGattCharacteristic?.let { characteristic ->
                    characteristic.value = chunkJson.toByteArray()
                    val success = bluetoothGatt?.writeCharacteristic(characteristic) ?: false
                    
                    if (success) {
                        val progress = ((i + 1) * 100) / chunks.size
                        callJavaScript("addLog('📤 Parça ${i + 1}/${chunks.size} gönderildi')")
                        callJavaScript("updateProgress($progress)")
                        
                        // Parçalar arası bekleme
                        Thread.sleep(200)
                    } else {
                        callJavaScript("showAlert('Veri gönderimi başarısız!', 'error')")
                        callJavaScript("onSendFailed()")
                        return
                    }
                }
            }
            
            callJavaScript("addLog('✅ Tüm parçalar başarıyla gönderildi!')")
            callJavaScript("showAlert('${chunks.size} parça halinde JSON başarıyla gönderildi!', 'success')")
            callJavaScript("onSendComplete()")
            
        } catch (e: Exception) {
            Log.e(TAG, "Veri gönderimi hatası: ${e.message}")
            callJavaScript("showAlert('Veri gönderimi hatası: ${e.message}', 'error')")
            callJavaScript("onSendFailed()")
        }
    }
    
    private fun generateSessionId(): String {
        return (1..9).map { ('a'..'z').random() }.joinToString("")
    }
    
    private fun callJavaScript(script: String) {
        handler.post {
            webView.evaluateJavascript(script, null)
        }
    }
    
    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        
        if (requestCode == PERMISSION_REQUEST_CODE) {
            val allPermissionsGranted = grantResults.all { it == PackageManager.PERMISSION_GRANTED }
            if (!allPermissionsGranted) {
                callJavaScript("showAlert('Bluetooth izinleri gerekli!', 'error')")
                callJavaScript("addLog('❌ Bluetooth izinleri reddedildi')")
            } else {
                callJavaScript("addLog('✅ Bluetooth izinleri verildi')")
            }
        }
    }
    
    override fun onBackPressed() {
        if (webView.canGoBack()) {
            webView.goBack()
        } else {
            super.onBackPressed()
        }
    }
    
    @SuppressLint("MissingPermission")
    override fun onDestroy() {
        super.onDestroy()
        bluetoothGatt?.close()
    }
}