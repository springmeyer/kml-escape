# -*- coding: utf-8 -*-

import os
import chardet
import mapnik2 as mapnik
from osgeo import ogr

def ensure_utf8(content):
    encoding = chardet.detect(content)['encoding']
    if encoding != 'utf-8':
        content = content.decode(encoding, 'replace').encode('utf-8')
    return content
    
def ogr_kml_layer(kml,ogr_layer):
    name = ogr_layer.GetName()
    index = '%s.index' % os.path.splitext(kml)[0] 
    if os.path.exists(index):
        os.unlink(index)
    return mapnik.Ogr(file=kml,layer=name)    

def shape_layer(kml,ogr_layer):
    shape = '%s.shp' % os.path.splitext(kml)[0].replace(' ','_')
    if os.path.exists(shape):
        os.unlink(shape)
    # convert to shapefile
    os.system('ogr2ogr -skipfailures "%s" "%s"' % (shape,kml))
    # index the shapefile
    os.system('shapeindex %s' % os.path.splitext(shape)[0])
    return mapnik.Shapefile(file=shape)


def kml_hex_to_mapnik_color(key_color):
    """Convert a kml color string to a mapnik.Color"""
    c = str(key_color)
    a,b,g,r = tuple(map(lambda s: int(s, 16),(c[:2],c[2:4],c[4:6],c[6:])))
    if mapnik.mapnik_version() >= 800:
        pass #a *= 255
    #print a,b,g,r
    #return (r,g,b)
    return mapnik.Color(r,g,b,a)

# not used
def hex8_to_rgba(hex8):
    """
    Takes an 8 digit hex color string (used by Google Earth) and converts it to RGBA colorspace
    * 8-digit hex codes use AABBGGRR (R - red, G - green, B - blue, A - alpha transparency)
    """
    hex8 = str(hex8.replace('#',''))
    if len(hex8) != 8:
        raise Exception("Hex8 value must be exactly 8 digits")
    hex_values = [hex8[i:i+2:1] for i in xrange(0, len(hex8), 2)]
    rgba_values = [int(x,16) for x in hex_values]
    rgba_values.reverse()
    return rgba_values

def fix(href):
    find = 'root://icons/'
    replace = '/Applications/Google Earth.app/Contents/Resources/'
    return href.replace(find,replace)

                     
zooms = {
     1: (200000000, 500000000),
     2: (100000000, 200000000),
     3: (50000000, 100000000),
     4: (25000000, 50000000),
     5: (12500000, 25000000),
     6: (6500000, 12500000),
     7: (3000000, 6500000),
     8: (1500000, 3000000),
     9: (750000, 1500000),
    10: (400000, 750000),
    11: (200000, 400000),
    12: (100000, 200000),
    13: (50000, 100000),
    14: (25000, 50000),
    15: (12500, 25000),
    16: (5000, 12500),
    17: (2500, 5000),
    18: (1000, 2500)
    }

wkb_types = { ogr.wkbPoint:'Point',
              ogr.wkbPoint25D:'3D Point',
              ogr.wkbLineString: 'LineString',
              ogr.wkbLineString25D:'3D LineString',
              ogr.wkbPolygon: 'Polygon',
              ogr.wkbPolygon25D:'3D Polygon',
              ogr.wkbMultiPoint: 'MultiPoint',
              ogr.wkbMultiPoint25D: '3D MultiPoint',
              ogr.wkbMultiLineString: 'MultiLineString',
              ogr.wkbMultiLineString25D: '3D MultiLineString',
              ogr.wkbMultiPolygon: 'MultiPolygon',
              ogr.wkbMultiPolygon25D: '3D MultiPolygon',
              ogr.wkbGeometryCollection: 'GeometryCollection',
              ogr.wkbGeometryCollection25D: '3D GeometryCollection',
              ogr.wkbNone: 'None',
              ogr.wkbUnknown:'Unknown (any)',
}