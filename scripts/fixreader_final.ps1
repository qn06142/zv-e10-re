$out = @()
$out += (pnputil /delete-driver oem42.inf /uninstall /force 2>&1 | Out-String -Width 200)
pnputil /scan-devices 2>&1 | Out-Null
Start-Sleep -Seconds 4
$id='USB\VID_1908&PID_0226\7&3709A3A6&0&3'
$svc=(Get-PnpDeviceProperty -InstanceId $id -KeyName 'DEVPKEY_Device_Service' -EA 0).Data
$st=(Get-PnpDevice -InstanceId $id -EA 0).Status
$out += "AFTER: Service='$svc' Status='$st'"
$out | Out-File -FilePath C:\Users\Minhsnguhoa\pmca-re\fixreader_final.txt -Encoding ascii
