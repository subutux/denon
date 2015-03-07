# Denon Plugin 
based in X3000, but should work on some Marantz as well

## New development of DENON plugin for use in smarthome.py (C) Michael Würtenberger 2015
## first beta releases just at your own risk ! feedback welcome in smarthome.py forum
version 0.52
### Targets: 
- no use of telnet interface anymore
- using xml - webapp interface
- adding some upnp capabilities (setting of audio streaming source directly)
- still keeping the full telnet interface command set ( in case of anybody would like to use it)
- multiple zone support (at least 2)

# Requirements
none

#changelog
v0.52
- _get_deviceInfo nur in der run() abfrage solange alive = true
- update readme zu den item einträgen

## Supported Hardware
DENON AVR, tested with X3000 model.

# Configuration
## plugin.conf
Typical configuration for a receiver
<pre>
[denon]
    class_name = Denon
    class_path = plugins.denon
    denon_ip = 192.168.2.27
    denon_port = 80 (optional)
    cycle = 10 (optional)
</pre>

### denon_ip
IP or host name of the avr. There is no default, please us a valid ip address.

### denon_port
Port number of the avr. 
Default 80. Normally there is no need to change that.

## items.conf
#### Examples of Denon send/listen commands
<pre>
Attribute            Type   Range                           Readable    Writable
'Power'              bool   False / True                    yes         yes
'MasterVolume'       num    0-99                            yes         yes
'Mute'               bool   False / True                    yes         yes
'InputFuncSelect'    str                                    yes         yes
'SurrMode'           str                                    yes         yes
'ModelName'          str                                    yes         no
'DeviceZones'        str    '1' - '2'                       yes         no
'MacAddress'         str    'aabbccddee'                    yes         no
</pre>

#### Configuration API (Plugin related)
<pre>
Attribute            Type   Range                           Readable    Writable
'errorstatus'        bool   False / True                    yes         no
</pre>

#### Examples Surround Modes
<pre>
Attribute            
'DIRECT'  'STEREO'   'PURE DIRECT'   'DOLBY Surrounds'   'DTS Surrounds'
'MULTI CH STEREO'   'ROCK ARENA'   'JAZZ CLUB'   'MONO MOVIE'   'VIDEO GAME'
'MATRIX'   'VIRTUAL'
</pre>

### denon_send
Specifies the writable attribute which is send to the avr when this item is altered.
In addition to denon_send an denon_zone (optional for one zone) has to be set. 

### denon_listen
Specifies the readable attribute which is updated on a scheduled timer from the avr.
In addition to denon_send an denon_zone (optional for one zone) has to be set. 
If you would like to read status messages as well, in addition denon_zone 0 has to be defined.

### denon_command
Specifies the writable command, which is send to the avr when this item is altered. 
Nearly every command of the telnet interface decription could be used. Ther is no readback capability ! 
If you would like to use a parameter, please define the parameter with <x>. If set, the actual item value
is written to the command parameter. 

## Example
#### items/test.conf
<pre>
[mm]
    [[denon]]

    	[[[status]]]
    		denon_zone = 0
    		# device infos -> received once per start
	        [[[[ModelName]]]]
	            type = str
	            denon_listen = ModelName
	        [[[[DeviceZones]]]]
	            type = str
	            denon_listen = DeviceZones
	        [[[[MacAddress]]]]
	            type = str
	            denon_listen = MacAddress
	        # staus objects received cyclic
	        [[[[nowPlaying]]]]
	            type = str
	            denon_listen = szLine
	        [[[[errorstatus]]]]
	            type = str
	            denon_listen = errorstatus

    	[[[main]]]
    		denon_zone = 1
	        [[[[Power]]]]
	            type = bool
	            denon_send = Power
	            denon_listen = Power
	        [[[[MasterVolume]]]]
	            type = num
	            denon_send = MasterVolume
	            denon_listen = MasterVolume
	        [[[[Mute]]]]
	            type = bool
	            denon_send = Mute
	            denon_listen = Mute
	        [[[[Input]]]]
	            type = str
	            denon_command = '/<x/>'
	            denon_listen = InputFuncSelect
	        [[[[SurrMode]]]]
	            type = str
	            denon_command = '<x>'
	            denon_listen = SurrMode
	        [[[[seturi]]]]
	            type = str
	            denon_send = SetAudioURI
	            enforce_updates = true 
	        [[[[Treble]]]]
	            type = num
	            denon_command = 'Z2PSTRE <x>'
	        [[[[Bass]]]]
	            type = num
	            denon_command = 'PSBAS <x>'

    	[[[zone2]]]
    		denon_zone = 2
	        [[[[Power]]]]
	            type = bool
	            denon_send = Power
	            denon_listen = Power
	        [[[[MasterVolume]]]]
	            type = num
	            denon_send = MasterVolume
	            denon_listen = MasterVolume
	        [[[[Mute]]]]
	            type = bool
	            denon_send = Mute
	            denon_listen = Mute
	        [[[[Input]]]]
	            type = str
	            denon_command = '<x>'
	            denon_listen = InputFuncSelect
	        [[[[seturi]]]]
	            type = str
	            denon_send = SetAudioURI
	            enforce_updates = true 

</pre>

## logic.conf
No logic attributes.

