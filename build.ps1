$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

python -m pip install -r requirements.txt pyinstaller
python -c "import spotify_ad_muter as m; m.ICONS['on'].save('icon.ico', sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])"
python -m PyInstaller --noconfirm --onefile --windowed --name SpotifyAdMuter --icon icon.ico spotify_ad_muter.py

Write-Host "Built dist\SpotifyAdMuter.exe"
