$d = Get-Disk | Where-Object { $_.BusType -eq 'USB' -and $_.Size -gt 30GB -and $_.Size -lt 70GB }
if (-not $d) { "NO MATCHING USB DISK - aborting" | Out-File C:\Users\Minhsnguhoa\pmca-re\fmt_result.txt -Encoding ascii; exit 1 }
if ($d.Number -ne 1) { ("WARNING disk number is " + $d.Number + " not 1 - aborting") | Out-File C:\Users\Minhsnguhoa\pmca-re\fmt_result.txt -Encoding ascii; exit 1 }
("Formatting Disk " + $d.Number + " (" + [math]::Round($d.Size/1GB) + "GB) to FAT32") | Out-File C:\Users\Minhsnguhoa\pmca-re\fmt_result.txt -Encoding ascii -Append
$d | Clear-Disk -RemoveData -Confirm:$false
$d | Initialize-Disk -PartitionStyle MBR
$p = New-Partition -DiskNumber $d.Number -UseMaximumSize -AssignDriveLetter
Format-Volume -Partition $p -FileSystem FAT32 -NewFileSystemLabel 'SONYFW' -Confirm:$false -Force
"DONE" | Out-File C:\Users\Minhsnguhoa\pmca-re\fmt_result.txt -Encoding ascii -Append
Get-Disk | Where-Object { $_.BusType -eq 'USB' } | Select-Object Number,PartitionStyle,OperationalStatus | Format-Table -AutoSize | Out-String | Out-File C:\Users\Minhsnguhoa\pmca-re\fmt_result.txt -Encoding ascii -Append
