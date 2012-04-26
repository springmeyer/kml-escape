#!/usr/bin/env python


import os
import sys
import optparse

__version__ = '0.1.0'

parser = optparse.OptionParser(usage="""%prog <kml> [options]

Example usage
-------------

Full help:
 $ %prog -h (or --help for possible options)

Read KML, output stylesheet:
 $ %prog <kml> > mapnik.xml


""", version='%prog ' + __version__)

parser.add_option('-q', dest='quiet',
                  action='store_true', default=False,
                  help='be quiet')

parser.add_option('-v', dest='verbose',
                  action='store_true', default=False,
                  help='be noisy')    

parser.add_option('-s', dest='shapefile_datasource',
                  action='store_true', default=False,
                  help='shapefile for datasource')
                  
if __name__ == '__main__':
    (options, args) = parser.parse_args(sys.argv)

    if not len(args) > 1:
        parser.error('please provide an input kml or kmz file')
    
    kml = args[1]
    
    xml = None
    if len(args) > 2:
        xml = args[2]
    
    from kmlparser.parser import Parser

    # handle kmz
    # convert styles
    # convert layer
    
    #import pdb;pdb.set_trace()
    p = Parser(kml,**options.__dict__)
    if xml:
        open('xml','wb').write(p.stream())
    else:
        p.stream()