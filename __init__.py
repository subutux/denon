#!/usr/bin/env python3
# vim: set encoding=utf-8 tabstop=4 softtabstop=4 shiftwidth=4 expandtab
#
# Copyright 2015 Michael Würtenberger
#
# Denon-Plugin for sh.py
#
# v 0.1
# 
# based on some concepts already made for Denon.
# Removes completely the Telnet Interface.
# using http.lib for communication and etree for xml parsing
# Full command set could be used just by configuration
#

import logging
import threading
import http.client
import xml.etree.ElementTree as et
from plugins.denon.upnp import UPNPDenon
import pydevd

logger = logging.getLogger('Denon')

class Denon():

    # Initialize connection to receiver
    def __init__(self, smarthome, denon_ip, denon_port=80, cycle=3):
        
#        pydevd.settrace('192.168.2.57')
        self._denonIp = denon_ip
        self._denonPort = denon_port
        self._sh = smarthome
        self._cycle = int(cycle)
        # variablen zur steuerung des plugins
        # hier werden alle bekannte items für lampen eingetragen
        self._sendKeys = {'MasterVolume', 'Power', 'Mute', 'InputFuncSelect', 'SurrMode', 'SetAudioURI'}
        self._listenKeys = {'MasterVolume', 'Power', 'Mute', 'InputFuncSelect', 'SurrMode', 'szLine'} 
        self._commandKeys = {'MV<x>', 'Z2<x>','PSBAS <x>','PSTRE <x>','Z2PSBAS <x>','Z2PSTRE <x>'}
        # die Zones werden in der Device übersicht mit 0 = main und 1 = zone2 übertragen
        self._zoneName = {'0' : 'StatusAudio', '1' : 'MAIN ZONE', '2': 'ZONE2'}
        self._zoneXMLCommandURI = {'0' :'formNetAudio_StatusXml.xml', '1' : 'formMainZone_MainZoneXmlStatus.xml', '2': 'formZone2_Zone2XmlStatus.xml'}
        # hier werden alle bekannte items für lampen eingetragen
        self._sendItems = {}
        self._listenItems = {}
        self._commandItems = {}
        self._commandLock = threading.Lock()
        self._upnp = UPNPDenon('192.168.2.27','8080')
#        self._update_status()

    def run(self):
        self.alive = True
        # After power on poll status objects
        self._sh.scheduler.add('denon-status-update', self._update_status, cycle=self._cycle)
        # anstossen des updates zu beginn
        self._sh.trigger('denon-status-update', self._update_status)

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
            denonIndex = denonZone + sendValue
            if sendValue in self._sendKeys:
                item.conf['denon_zone'] = denonZone
                if not denonIndex in self._sendItems:
                    # item in die liste aufnehmen
                    self._commandItems[denonIndex] = item
                    # update methode setzen
                    return self.update_send_item
                else:
                    logger.warning('DENON: parse_item: in denon item [{0}] in denon_send = {1} is duplicated to item [{2}]'.format(item, sendValue, self._sendItems[sendValue]))

        if 'denon_command' in item.conf:
            sendCommand = item.conf['denon_command']
            denonZone = self._find_item_attribute(item, 'denon_zone', 1)
            denonIndex = denonZone + sendCommand
            item.conf['denon_zone'] = denonZone
            if not denonIndex in self._commandItems:
                # item in die liste aufnehmen
                self._commandItems[denonIndex] = item
                # update methode setzen
                return self.update_command_item
            else:
                logger.warning('DENON: parse_item: in denon item [{0}] in denon_command = {1} is duplicated to item [{2}]'.format(item, sendCommand, self._sendItems[sendCommand]))
            
    def parse_logic(self, logic):
        pass

    def _limit_range_int(self, value, minValue, maxValue):
        # kurze routine zur wertebegrenzung
        if value >= maxValue:
            value = int(maxValue)
        elif value < minValue:
            value = int(minValue)
        else:
            value = int(value)
        return value

    def update_send_item(self, item, caller=None, source=None, dest=None):
    # Receive commands, process them and forward them to receiver
        if caller != 'DENON':
            # hier werden die kommandos für bool verwendet, die einen status zurückbringen
            command = item.conf['denon_send']
            zone = item.conf['denon_zone']
            value = item()
            if command == 'Power':
                if item():
                    self._set_command('formiPhoneAppPower.xml?' + zone + '+PowerON')
                else:
                    self._set_command('formiPhoneAppPower.xml?' + zone + '+PowerStandby')
            elif command == 'Mute':
                if item():
                    self._set_command('formiPhoneAppMute.xml?' + zone + '+MuteON')
                else:
                    self._set_command('formiPhoneAppMute.xml?' + zone + '+MuteOFF')
            elif command == 'MasterVolume':
                value = self._limit_range_int(value,0,99)
                self._set_command('formiPhoneAppVolume.xml?' + zone + '+{0}'.format(int(value-80)))
            elif command == 'SetAudioURI':
                logger.warning('DENON: update_send_item: audio uri: {0}'.format(value))
                self._upnp._play(value)
    
    def update_command_item(self, item, caller=None, source=None, dest=None):
    # Receive commands, process them and forward them to receiver
        if caller != 'DENON':
            # ansonsten wird das angewählte kommando verwendet und entsprechend formatiert
            command = item.conf['denon_command']
            # jetzt  bauen wir uns den befehl mit den parametern zusammen
            if not command in self._commandKeys:
                logger.warning('DENON: update_command_item: command {0} is not in the checked list !'.format(command))
            if command.find('<x>'):
                # es ist ein kommando mit parameter. dieser wird durch den Wert des items ersetzt 
                command = command.replace('<x>',str(int(item())))
            # zur übergabe müssen die leerzeichen ersetzt werden
            command = command.replace(' ','%20')
            self._set_command('formiPhoneAppDirect.xml?'+command)
    
    def _set_command(self, command):
        # denon avr mit einem http request GET abfragen bzw. kommando ausgeben
        try:
            self._commandLock.acquire()
            connectionDenon = http.client.HTTPConnection(self._denonIp)
            connectionDenon.request('GET', '/goform/%s' % command)
        except Exception as e:
            logger.error('DENON Main: _request: problem in http.client exception : {0} '.format(e))
            if 'errorstatus' in self._listenItems:
                # wenn der item abgelegt ist, dann kann er auch gesetzt werden
                self._listenItems['errorstatus'](True, 'DENON')
            if connectionDenon:
                connectionDenon.close()
            self._commandLock.release()
        else:
            responseRaw = connectionDenon.getresponse()
            connectionDenon.close()
            self._commandLock.release()
            if 'errorstatus' in self._listenItems:
                # wenn der item abgelegt ist, dann kann er auch rückgesetzt werden
                self._listenItems['errorstatus'](False, 'DENON')
            # rückmeldung 200 ist OK
            if responseRaw.status != 200:
                logger.error('DENON Main: _request: response Raw: Request failed')
                return None
            # lesen, decodieren nach utf-8 
            response = responseRaw.read().decode('utf-8')
            # logger.warning('DENON: Command: /goform/{0} : response: {1}'.format(command, response))
            if len(response) > 0:
                return et.fromstring(response)
            else:
                return None

    def _update_status(self):
    # Poll XML status
    # ToDo müssen alle themen wirklich so abgearbeitet werden, oder kann ich auf ein subset referezieren bei der Abarbeitung des XML
        # status abholen
        # über alles zones, zone 0 ist der Status
        for denonZone in self._zoneName:
            responseEtree = self._set_command(self._zoneXMLCommandURI[denonZone])
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
                        elif node.tag in ['szLine']:
                            # dieser kann aus meherer Zeilen zusammengesetzt sein
                            value = ''
                            for child in node.getchildren():
                                if child.text:
                                    value = value + child.text + '\r\n'
                        self._listenItems[denonListen](value,'DENON')

if __name__ == '__main__':
    
    def __item(value, caller):
        print('DENON: _update_status: value: [{0}]: caller: [{1}]'.format(value,caller))
        
    d = Denon('test','192.168.2.27')
    d._listenItems = {'0szLine' : __item,
                      '1MasterVolume' : __item, '1Power': __item, '1Mute' : __item, '1InputFuncSelect' : __item, '1SurrMode' : __item,
                      '2MasterVolume' : __item, '2Power': __item, '2Mute' : __item, '2InputFuncSelect' : __item, '2SurrMode' : __item
                      }
    d._update_status()
    

            