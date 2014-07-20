#!/usr/bin/python

""" 
Provides additional utilities for data transfer using REST interfaces,
specifically helpers for converting between Python and JSON formats.
"""

# define authorship information
__authors__         = ['Eric Hulser']
__author__          = ','.join(__authors__)
__credits__         = []
__copyright__       = 'Copyright (c) 2011, Projex Software'
__license__         = 'LGPL'

__maintainer__      = 'Projex Software'
__email__           = 'team@projexsoftware.com'

import datetime
import logging
import re
import projex.text

from xml.etree import ElementTree

try:
    import json
except ImportError:
    try:
        import simplejson as json
    except ImportError:
        json is None

try:
    import pytz
except ImportError:
    pytz = None

logger = logging.getLogger(__name__)

_encoders = []
_decoders = []

RESPONSE_FORMATS = {}

#----------------------------------------------------------------------

class JSONObject(object):
    def __init__(self, **data):
        self._data = data

    def __json__(self, *args):
        return self.json()

    def json(self):
        out = {}
        for k, v in self._data.items():
            try:
                out[k] = py2json(v)
            except TypeError:
                out[k] = v
        return out

#----------------------------------------------------------------------

def json2py(json_obj):
    """
    Converts the inputed JSON object to a python value.
    
    :param      json_obj | <variant>
    """
    for key, value in json_obj.items():
        if type(value) not in (str, unicode):
            continue
                
        # restore a datetime
        if re.match('^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}:\d+$', value):
            value = datetime.datetime.strptime(value, '%Y-%m-%d %H:%M:%S:%f')
        elif re.match('^\d{4}-\d{2}-\d{2}$', value):
            year, month, day = map(int, value.split('-'))
            value = datetime.date(year, month, day)
        elif re.match('^\d{2}:\d{2}:\d{2}:\d+$', value):
            hour, minute, second, micro = map(int, value.split(':'))
            value = datetime.time(hour, minute, second, micro)
        else:
            found = False
            for decoder in _decoders:
                success, new_value = decoder(value)
                if success:
                    value = new_value
                    found = True
                    break
            
            if not found:
                continue
        
        json_obj[key] = value
    return json_obj

def jsonify(py_data):
    """
    Converts the inputed Python data to JSON format.
    
    :param      py_data | <variant>
    """
    return json.dumps(py_data, default=py2json)

def py2json(py_obj):
    """
    Converts the inputed python object to JSON format.
    
    :param      py_obj | <variant>
    """
    if type(py_obj) == datetime.datetime:
        return py_obj.strftime('%Y-%m-%d %H:%M:%S:%f')
    elif type(py_obj) == datetime.date:
        return py_obj.strftime('%Y-%m-%d')
    elif type(py_obj) == datetime.time:
        return py_obj.strftime('%H:%M:%S:%f')
    else:
        # look through custom plugins
        for encoder in _encoders:
            success, value = encoder(py_obj)
            if success:
                return value
        
        opts = (py_obj, type(py_obj))
        raise TypeError('Unserializable object {} of type {}'.format(*opts))

def register(encoder=None, decoder=None):
    """
    Registers an encoder method and/or a decoder method for processing
    custom values.  Encoder and decoders should take a single argument
    for the value to encode or decode, and return a tuple of (<bool>
    success, <variant> value).  A successful decode or encode should
    return True and the value.
    
    :param      encoder | <callable> || None
                decoder | <callable> || None
    """
    if encoder:
        _encoders.append(encoder)
    if decoder:
        _decoders.append(decoder)

def response(py_data, format='json'):
    """
    Converts the inputed python data to a given format.  Valid formats can
    be found in the FORMATS dictionary.  If the format is not valid, then
    a KeyError will be raised.
    
    :param      py_data | <variant>
                format | <str>
    
    :return     <variant>
    """
    return RESPONSE_FORMATS[format](py_data)

def unjsonify(json_data):
    """
    Converts the inputed JSON data to Python format.
    
    :param      json_data | <variant>
    """
    return json.loads(json_data, object_hook=json2py)

def xmlresponse(py_data):
    """
    Generates an XML formated method repsonse for the given python
    data.
    
    :param      py_data | <variant>
    """
    xroot = ElementTree.Element('methodResponse')
    xparams = ElementTree.SubElement(xroot, 'params')
    xparam = ElementTree.SubElement(xparams, 'param')
    
    type_map = {'bool': 'boolean',
                'float': 'double',
                'str': 'string',
                'unicode': 'string',
                'datetime': 'dateTime.iso8601',
                'date': 'date.iso8601',
                'time': 'time.iso8601'}
    
    def xobj(xparent, py_obj):
        # convert a list of information
        if type(py_obj) in (tuple, list):
            xarr = ElementTree.SubElement(xparent, 'array')
            xdata = ElementTree.SubElement(xarr, 'data')
            for val in py_obj:
                xval = ElementTree.SubElement(xdata, 'value')
                xobj(xval, val)
        
        # convert a dictionary of information
        elif type(py_obj) == dict:
            xstruct = ElementTree.SubElement(xparent, 'struct')
            for key, val in py_obj.items():
                xmember = ElementTree.SubElement(xstruct, 'member')
                xname = ElementTree.SubElement(xmember, 'name')
                xname.text = key
                xval = ElementTree.SubElement(xmember, 'value')
                xobj(xval, val)
        
        # convert a None value
        elif py_obj is None:
            ElementTree.SubElement(xparent, 'nil')
        
        # convert a basic value
        else:
            typ = type(py_obj).__name__
            typ = type_map.get(typ, typ)
            xitem = ElementTree.SubElement(xparent, typ)
            
            # convert a datetime/date/time
            if isinstance(py_obj, datetime.date) or \
               isinstance(py_obj, datetime.time) or \
               isinstance(py_obj, datetime.datetime):
                
                if py_obj.tzinfo and pytz:
                    data = py_obj.astimezone(pytz.utc).replace(tzinfo=None)
                    xitem.text = data.isoformat()
                else:
                    xitem.text = py_obj.isoformat()
            
            # convert a boolean
            elif type(py_obj) == bool:
                xitem.text = str(int(py_obj))
            
            # convert a non-string object
            elif not type(py_obj) in (str, unicode):
                xitem.text = str(py_obj)
            
            # convert a string object
            else:
                xitem.text = py_obj
    
    xobj(xparam, py_data)
    projex.text.xmlindent(xroot)
    return ElementTree.tostring(xroot)
    

RESPONSE_FORMATS['json'] = jsonify
RESPONSE_FORMATS['xml'] = xmlresponse