[app]
title = PrunerDash
package.name = prunerdash
package.domain = org.prunerdash
source.dir = .
android.api = 33
android.permissions = BLUETOOTH, BLUETOOTH_ADMIN, BLUETOOTH_SCAN, BLUETOOTH_CONNECT, ACCESS_FINE_LOCATION
source.include_exts = py,png,jpg,kv,txt
version = 1.0
requirements = python3,kivy,numpy,obd,pyserial,pint,flexcache,flexparser,typing_extensions,platformdirs,packaging,pyjnius,setuptools, requests
orientation = portrait
fullscreen = 1

# (str) Icon of the application
icon.filename = %(source.dir)s/icon.png

# (str) Presplash of the application
presplash.filename = %(source.dir)s/presplash.png

[buildozer]
log_level = 2
