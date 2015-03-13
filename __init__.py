#!/usr/bin/env python3
# vim: set encoding=utf-8 tabstop=4 softtabstop=4 shiftwidth=4 expandtab
#
# Copyright 2015 Michael Würtenberger
#
# Denon-Plugin for sh.py
#
# v 0.52
# changelog:
# - bugfixing
# - refactoring of some code
# - surrmode check
# - preparation ssdp 
# - conncection logs reduced
# 
# based on some concepts already made for Denon.
# removes completely the Telnet Interface.
# using http.lib for communication and etree for xml parsing
# full command set could be used just by configuration
#

import logging
import threading
import time
import http.client
import xml.etree.ElementTree as et
import html.parser
import pydevd

logger = logging.getLogger('Denon')

class Denon():

    # Initialize connection to receiver
    def __init__(self, smarthome, denon_ip, denon_port = '80', denon_upnp_port = '8080', cycle = 5):
        
#        pydevd.settrace('192.168.2.57')
        self._denonIp = denon_ip
        self._denonPort = denon_port
        self._denonUpnpPort = denon_upnp_port
        self._sh = smarthome
        self._cycle = int(cycle)
        # lower limit cycle 
        if self._cycle < 1:
            self._cycle = 1
        # variablen zur steuerung des plugins
        # hier werden alle bekannte items für lampen eingetragen
        self._sendKeys = {'MasterVolume', 'Power', 'Mute', 'InputFuncSelect', 'SurrMode', 'SetAudioURI'}
        self._listenKeys = {'MasterVolume', 'Power', 'Mute', 'InputFuncSelect', 'SurrMode', 'szLine',
                            'DeviceZones', 'MacAddress', 'ModelName'} 
        # die Zones werden in der Device übersicht mit 0 = main und 1 = zone2 übertragen
        self._zoneName = {'0' : 'Status', '1' : 'MAIN ZONE', '2': 'ZONE2'}
        self._zoneXMLCommandURI = {'0' :'/goform/formNetAudio_StatusXml.xml', '1' : '/goform/formMainZone_MainZoneXmlStatus.xml', '2': '/goform/formZone2_Zone2XmlStatus.xml'}
        self._XMLDeviceInfoURI = {'0': '/goform/Deviceinfo.xml'}
        # hier werden alle bekannte items für den denon eingetragen
        # items, die fürs senden konfiguriert sind 
        self._sendItems = {}
        # items, die fürs empfangen konfiguriert sind 
        self._listenItems = {}
        # merker, welche zone konfiguriert wurde. ich möchte keine abfragen, die nicht konfiguriert ist
        self._configuredZones = {} 
        # lock, um mehrfache zugriffe auf request zu seriealisieren
        self._requestLock = threading.Lock()
        # die uri für denupnp command channel gilt für den x3000
        # evt. muss hier über einen discovery mechanismus die richtig herausgefunden werden
        # im moment wird die konfiguration statisch gebaut bzw. vorgegeben. in einem erweiterungsschritt
        # könnte man die xml SOAP nachrichten per eTree zusammenbauen.
        self._uriCommand = "/AVTransport/ctrl"
        self._SetAVTransportURI = { 
            'headers': {
                'SOAPACTION': '"urn:schemas-upnp-org:service:AVTransport:1#SetAVTransportURI"',
                'CONTENT-TYPE' : 'text/xml; charset="utf-8"',
                'USER-AGENT' :'smarthome/denon plugin v0.1' 
                        },
            'body': '<?xml version="1.0" encoding="utf-8"?>\r\n'
                '<s:Envelope s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/" xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">\r\n'
                    '<s:Body>'
                        '<u:SetAVTransportURI xmlns:u="urn:schemas-upnp-org:service:AVTransport:1">\r\n'
                            '<InstanceID>0</InstanceID>\r\n'
                            '<CurrentURI>{0}</CurrentURI>\r\n'
                            '<CurrentURIMetaData>' 
                            '</CurrentURIMetaData>\r\n'
                        '</u:SetAVTransportURI>\r\n'
                    '</s:Body>\r\n'
                '</s:Envelope>\r\n' 
            }
        self._Play = {
            'headers': {
                'SOAPACTION': '"urn:schemas-upnp-org:service:AVTransport:1#Play"',
                'CONTENT-TYPE' : 'text/xml; charset="utf-8"',
                'USER-AGENT' :'smarthome/denon plugin v0.1' 
                },
            'body': '<?xml version="1.0" encoding="utf-8"?>\r\n'
                '<s:Envelope s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/" xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">\r\n'
                    '<s:Body>'
                        '<u:Play xmlns:u="urn:schemas-upnp-org:service:AVTransport:1">\r\n'
                            '<InstanceID>0</InstanceID>\r\n'
                            '<Speed>1</Speed>\r\n'
                        '</u:Play>\r\n'
                    '</s:Body>\r\n'
                '</s:Envelope>\r\n' 
        } 
        
    def run(self):
        self.alive = True
        # einmalig zum start die Device info abholen
        if self.alive:
            self._get_deviceinfo()
        # ich hole regelmässig im polling den wert der zonen
        while self.alive:
            # allerdings nur für die konfigurierten zonen
            for zone in self._configuredZones:
                self._update_status(zone)
            time.sleep(self._cycle)

    def stop(self):
        self.alive = False

    def _find_item_attribute(self, item, attribute, attributeDefault):
        # zwischenspeichern für die loggerausgabe
        itemSearch = item
        # schleife bis ich ganz oben angekommen bin
        while (not attribute in itemSearch.conf):
            # eine Stufe in den ebenen nach oben
            itemSearch = itemSearch.return_parent()                    
            if (itemSearch is self._sh):
                logger.warning('DENON: _find_item_attribute: could not find [{0}  ] for item [{1}], setting defined default value {2}'.format(attribute, item, attributeDefault))
                return str(attributeDefault)
        itemAttribute = int(itemSearch.conf[attribute])
        return str(itemAttribute)
    
    def _limit_range_int(self, value, minValue, maxValue):
        # kurze routine zur wertebegrenzung
        if value >= maxValue:
            value = int(maxValue)
        elif value < minValue:
            value = int(minValue)
        else:
            value = int(value)
        return value

    def parse_item(self, item):
    # Parse items and bind commands to plugin
        # die kommandos denon_send und denon command können nur alternativ vorkommen, das kommando
        # denon_listen kann parallel parallel vorkommen
        if 'denon_send' in item.conf and 'denon_command' in item.conf:
            logger.warning('DENON: parse_item: in denon item [{0}] denon_send and denon_command is used at the same time'.format(item))
            return None

        # zuerst müssen die listen items geparsed werden, weil die parallel gelten können
        if 'denon_listen' in item.conf:
            listenValue = item.conf['denon_listen']
            denonZone = self._find_item_attribute(item, 'denon_zone', 1)
            # test, ob konfigurierte zone existiert
            if not denonZone in self._zoneName:
                logger.warning('DENON: parse_item: zone number exceeds limit for item [{0}]'.format(item))
                denonZone = '1'
            # jede konfigurierte Zone wird eingetragen
            self._configuredZones[denonZone] = 'ON'
            denonIndex = denonZone + listenValue
            if listenValue in self._listenKeys:
                # wir haben ein listen commando. hier werden informationen zurückgeschrieben
                item.conf['denon_zone'] = denonZone
                if not denonIndex in self._listenItems:
                    # item in die liste aufnehmen
                    self._listenItems[denonIndex] = item
#                    logger.warning('DENON: parse_item: item: [{0}], command: {1}'.format(item, listenValue))
                else:
                    logger.warning('DENON: parse_item: in denon item [{0}] in denon_listen = {1} is duplicated to item [{2}]'.format(item, listenValue, self._listenItems[listenValue]))

        # danach kommen die anteile, die eine return struktur mit angeben und damit den parser beenden
        if 'denon_send' in item.conf:
            sendValue = item.conf['denon_send'] 
            denonZone = self._find_item_attribute(item, 'denon_zone', 1)
            # test, ob konfigurierte zone existiert
            if not denonZone in self._zoneName:
                logger.warning('DENON: parse_item: zone number exceeds limit for item [{0}]'.format(item))
                denonZone = '1'
            # jede konfigurierte Zone wird eingetragen
            self._configuredZones[denonZone] = 'ON'
            denonIndex = denonZone + sendValue
            if sendValue in self._sendKeys:
                item.conf['denon_zone'] = denonZone
                if not denonIndex in self._sendItems:
                    # item in die liste aufnehmen
                    self._sendItems[denonIndex] = item
                    # update methode setzen
                    return self.update_send_item
                else:
                    logger.warning('DENON: parse_item: in denon item [{0}] in denon_send = {1} is duplicated to item [{2}]'.format(item, sendValue, self._sendItems[sendValue]))

        if 'denon_command' in item.conf:
            # update methode setzen
            return self.update_command_item
            
    def parse_logic(self, logic):
        pass

    def update_send_item(self, item, caller=None, source=None, dest=None):
    # Receive commands, process them and forward them to receiver
        if caller != 'DENON':
            # hier werden die kommandos für bool verwendet, die einen status zurückbringen
            command = item.conf['denon_send']
            zone = item.conf['denon_zone']
            value = item()
            if command == 'Power':
                if item():
                    self._request(self._denonIp, self._denonPort, 'GET', '/goform/formiPhoneAppPower.xml?' + zone + '+PowerON')
                else:
                    self._request(self._denonIp, self._denonPort, 'GET', '/goform/formiPhoneAppPower.xml?' + zone + '+PowerStandby')
            elif command == 'Mute':
                if item():
                    self._request(self._denonIp, self._denonPort, 'GET', '/goform/formiPhoneAppMute.xml?' + zone + '+MuteON')
                else:
                    self._request(self._denonIp, self._denonPort, 'GET', '/goform/formiPhoneAppMute.xml?' + zone + '+MuteOFF')
            elif command == 'MasterVolume':
                value = self._limit_range_int(value,0,99)
                self._request(self._denonIp, self._denonPort, 'GET', '/goform/formiPhoneAppVolume.xml?' + zone + '+{0}'.format(int(value-80)))
            elif command == 'SetAudioURI':
                self._upnp_set_uri(value)
                self._upnp_play()
    
    def update_command_item(self, item, caller=None, source=None, dest=None):
    # Receive commands, process them and forward them to receiver
        if caller != 'DENON':
            # ansonsten wird das angewählte kommando verwendet und entsprechend formatiert
            command = item.conf['denon_command']
            # jetzt  bauen wir uns den befehl mit den parametern zusammen
            if command.find('<x>') != -1:
                # es ist ein kommando mit parameter. dieser wird durch den Wert des items ersetzt 
                command = command.replace('<x>',item())
            # zur übergabe müssen die leerzeichen ersetzt werden
            command = command.replace(' ','%20')
            self._request(self._denonIp, self._denonPort, 'GET', '/goform/formiPhoneAppDirect.xml?'+command)

    def _request(self, ip, port, method, path, data=None, header=None):
        # denon avr mit einem http request abfragen
        response = None
        try:
            connection = http.client.HTTPConnection(ip, port, timeout = 3)
            if method == 'GET':
                connection.request(method, path)
            else:
                connection.request(method, path, data.encode(), header)
        except Exception as e:
            if (e.args[0] == 'timed out') or (e.args[1] == 'Host is down'):
                if 'errorstatus' in self._listenItems:
                    # wenn der item abgelegt ist, dann kann er auch gesetzt werden
                    self._listenItems['errorstatus'](True,'DENON')
            else:
                logger.error('DENON: _request: problem in http.client exception : {0} '.format(e))
                
        else:
            responseRaw = connection.getresponse()
            if 'errorstatus' in self._listenItems:
                # wenn der item abgelegt ist, dann kann er auch rückgesetzt werden
                self._listenItems['errorstatus'](False,'DENON')
            # rückmeldung 200 ist OK
            if responseRaw.status != 200:
                logger.warning('DENON: _request: Request failed, error code: {0}',format(responseRaw.status))
            else:
                response = responseRaw.read()
                # in fehlerfällen kommen manchmal strings vor, die 0xc0 enthalten, eine nicht valide utf-8 codierung
                # konkret bei Last <BrandCode>\xc0</BrandCode>
                try:
                    response = response.decode('utf-8')
                except:
                    # lassischer fehler unter last vom webserver des Denon
                    logger.warning('DENON: _request: utf-8 decode failed !')
                    response = None
                finally:
                    if response is not None:
                        # unter last macht der webserver auch im XML noch fehler, muss abgefangen werden
                        try:
                            # jetzt wird der xml string nach dict geparsed 
                            response = et.fromstring(response)
                        except:
                            response = None
        finally:
            if connection:
                connection.close()
            return response
                
    def _update_status(self, denonZone):
        # Poll XML status
        # ToDo müssen alle themen wirklich so abgearbeitet werden, oder kann ich auf ein subset referezieren bei der Abarbeitung des XML
        # status abholen
        self._requestLock.acquire()
        responseEtree = self._request(self._denonIp, self._denonPort, 'GET', self._zoneXMLCommandURI[denonZone])
        self._requestLock.release()
        # im falle eines fehlers wird None zurückgeliefert
        if responseEtree is not None:
            # durchinterieren über alle einträge für das listen
            # es ist nur die erste ebene !
            for node in responseEtree:
                returnItemIndex = denonZone + node.tag
                for denonListen in self._listenItems:
                    if denonListen == returnItemIndex:
                        value = node.getchildren()[0].text
                        # wenn die beiden gleich sind, dann kan nich den wert zuweisen
                        if node.tag in ['POWER', 'MUTE']:
                            value = bool((True if value.upper() == 'ON' else False))
                        elif node.tag in ['MasterVolume']:
                            # wenn das volume 0 ist, dann wird im xml '--' zurückgegeben !
                            if value == '--':
                                value = 0
                            else:
                                value = int(float(value) + 80)
                        elif node.tag == 'szLine':
                            if value == 'Now Playing':
                                # für now playing. ansonsten kann auch menueinträge dort stattfinden
                                # dieser kann aus meherer Zeilen zusammengesetzt sein
                                value = ''
                                # wir starten ab dem 2. element -> das ist [1:], da das erste ja "Now Playing" sagt
                                for child in node.getchildren()[1:]:
                                    # wenn noch einträge vorhanden sind
                                    if child.text :
                                        value = value + child.text
                            else:
                                # sonst bekomme ich vom denon menus zum auswählen. hier wird auch die komplette
                                # bedienung rüber abgewickelt. die will ich mir nicht ansehen
                                value = ''
                            # da ist der Text im XML mehrfach daneben codiert. als erstes müssen die  HTML codiert 
                            # geschickt umgebaut werden, dann sind immer noch die Umlaute verstümmelt
                            # das bekommen wird mit dem Trick encode / decode wieder hin.
                            value = html.parser.HTMLParser().unescape(value)
                            # es gibt ab und zu einmal eine exception, weil es verschiedenste formate gibt
                            try:
                                # erst wird versucht klassisch nach utf-8 zu decodieren
                                returnValue = value.encode('raw_unicode_escape').decode('utf-8')
                            except:
                                try:  
                                    # dann nach ISO-8859-1
                                    returnValue = value.encode('raw_unicode_escape').decode('ISO-8859-1')
                                except:
                                    # hier schreibe ich es direkt in die anzeige, dann sehe ich das sofort
                                    # künftig sicherlich eher eine warning, passiert aber zu selten.
                                    returnValue ='Decode Problem'   
                            finally:
                                value = returnValue
                        self._listenItems[denonListen](value,'DENON')

    def _get_deviceinfo(self): 
        self._requestLock.acquire()
        responseEtree = self._request(self._denonIp, self._denonPort, 'GET', self._XMLDeviceInfoURI['0'])
        self._requestLock.release()
        # im falle eines fehlers wird None zurückgeliefert
        if responseEtree is not None:
            # durchinterieren über alle einträge für das listen
            # es ist nur die erste ebene !
            for node in responseEtree:
                returnItemIndex = '0' + node.tag
                for denonListen in self._listenItems:
                    if denonListen == returnItemIndex:
                        value = node.text
                        self._listenItems[denonListen](value,'DENON')

    def _upnp_set_uri(self, uriAudioSource):
        # setzen des bodys mit der uri für die source
        body =  self._SetAVTransportURI['body'].format(uriAudioSource)
        # setzen und anpassen der headers
        header = self._SetAVTransportURI['headers']
        header['Content-Length'] = len(body)
        header['HOST'] = self._denonIp + ':' + self._denonUpnpPort
        # abfrage der daten per request
        self._requestLock.acquire()
        self._request(self._denonIp, self._denonUpnpPort,'POST', self._uriCommand, body, header)
        self._requestLock.release()

    def _upnp_play(self):
        header = self._Play['headers'] 
        body =  self._Play['body']   
        header['Content-Length'] = len(body)
        header['HOST'] = self._denonIp + ':' + self._denonUpnpPort
        # abfrage der daten per request
        self._requestLock.acquire()
        self._request(self._denonIp, self._denonUpnpPort, 'POST', self._uriCommand, body, header)
        self._requestLock.release()
        