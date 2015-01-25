#!/usr/bin/env python
# encoding: utf-8
#
#  Copyright (C) 2015 Michael Würtenberger
#
#  Version 0.1 develop
#
# upnp implementierung auf wirklich ganz rohen und nicht vollständiger basis
# um eineige features des denon avr zusätzlich zu seine xml web schnittstelle nutzbar zu machen 
# in anlehnung an der lösung con Rui Carmo on 2011-01-09 https://github.com/rcarmo/pyairplay.git
# 
# wesentlicher bestandteil zunächst die uri eines audio streams an den avr zu übergeben 
#
#  APL2.0
# 
import http.client
import logging
import xml.etree.ElementTree as et

logger = logging.getLogger('upnp')

class UPNPDenon:
    
    def __init__(self, host, port):
        # definition der header und der body für die upnp abfrage
        # definiert wurde erst einmal nur die befehler SetAVTransportURI und 'Play'
        self._upnp = {
            'SetAVTransportURI': { 
                'headers': {
                    'SOAPACTION': '"urn:schemas-upnp-org:service:AVTransport:1#SetAVTransportURI"',
                    'CONTENT-TYPE' : 'text/xml; charset="utf-8"',
                    'USER-AGENT' :'MacOS/10.10.1, UPnP/1.0, PlugPlayer/4.2.1' 
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
            },
            'Play': {
                'headers': {
                    'SOAPACTION': '"urn:schemas-upnp-org:service:AVTransport:1#Play"',
                    'CONTENT-TYPE' : 'text/xml; charset="utf-8"',
                    'USER-AGENT' :'MacOS/10.10.1, UPnP/1.0, PlugPlayer/4.2.1' 
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
        }
        self._host = host
        self._port = port
        # self.connection = httplib.HTTPConnection(self.address)
        self._uriCommand = "/AVTransport/ctrl"

    def _request(self, method, path, data, header):
        # denon avr mit einem http request abfragen
        try:
            connectionUpnp = http.client.HTTPConnection(self._host, self._port)
            connectionUpnp.request(method, path, data.encode(), header)
        except Exception as e:
            logger.error('DENON: _request: problem in http.client exception : {0} '.format(e))
#           if 'errorstatus' in self._listenItems:
                # wenn der item abgelegt ist, dann kann er auch gesetzt werden
#               self._listenItems['errorstatus'](True,'DENON')
            if connectionUpnp:
                connectionUpnp.close()
        else:
            responseRaw = connectionUpnp.getresponse()
            connectionUpnp.close()
#            if 'errorstatus' in self._listenItems:
                # wenn der item abgelegt ist, dann kann er auch rückgesetzt werden
#                self._listenItems['errorstatus'](False,'DENON')
            # rückmeldung 200 ist OK
            if responseRaw.status != 200:
                logger.error('DENON UPNP: _request: response Raw: Request failed')
                return None
            else:
                response= responseRaw.read().decode('utf-8')
                if len(response) > 0:
                    return et.fromstring(response)
                else:
                    return None

    def _play(self, uriAudioSource):
        # setzen des bodys mit der uri für die source
        body =  self._upnp['SetAVTransportURI']['body'].format(uriAudioSource)
        # setzen und anpassen der headers
        header = self._upnp['SetAVTransportURI']['headers']
        header['Content-Length'] = len(body)
        header['HOST'] = self._host + ':' + self._port
        # abfrage der daten per request
        self._request("POST", self._uriCommand, body, header)
        
        # 2. teil mit dem play
        header = self._upnp['Play']['headers']
        body =  self._upnp['Play']['body']   
        header['Content-Length'] = len(body)
        header['HOST'] = self._host + ':' + self._port
        # abfrage der daten per request
        self._request("POST", self._uriCommand, body, header)


if __name__ == '__main__':
    d = UPNPDenon('192.168.2.27','8080')
    d._play('http://streams.br.de/bayern3_2.m3u')
    
