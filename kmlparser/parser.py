#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import Image
import zipfile
import urllib2
import tempfile
from base64 import urlsafe_b64encode
from osgeo import ogr
import mapnik2 as mapnik
from lxml import objectify

import utils

class Parser:
    def __init__(self, resource, **kwargs):
        self.resource = resource
        self.kmls = []
        self.quiet = kwargs.get('quiet')
        self.verbose = kwargs.get('verbose')
        self.shapefile_datasource = kwargs.get('shapefile_datasource')
        #self.feat_styles = {}
        self.layer_styles = {}
        self.style_names = []
        self.style_maps = {}
        self.has_network_links = False
        self.map = mapnik.Map(1,1)
        #self.map.background = mapnik.Color('white')
        self.names = []
        self.has_style_per_placement = False

    def m(self,msg):
        if self.verbose:
            sys.stderr.write('%s\n' % msg)
        
    def parse(self, resource):
        if '?' in resource:
            resource = resource[:resource.index('?')]
        if resource.startswith('http'):
            ext = os.path.splitext(resource)[1]
            (handle, path) = tempfile.mkstemp(suffix=ext,prefix='kml2mapnik-')
            os.close(handle)
            open(path,'wb').write(urllib2.urlopen(resource).read())
            resource = path
        if resource.endswith('kmz'):
            dirname = os.path.dirname(resource)
            tmpdir = os.path.join(tempfile.gettempdir(),os.path.splitext(os.path.basename(resource))[0])
            zip_ = zipfile.ZipFile(resource, mode="r",allowZip64=True)
            z_files = zip_.namelist()
            for name in z_files:
                if name.endswith('doc.kml'):
                    resource = name
                    break
            if not resource in z_files:
                # we did not find 'doc.kml'
                raise AttributeError("Could not find 'doc.kml' inside %s" % resource)
            def is_file(path):
                if os.path.splitext(path)[1]:
                    return True
                return False
            # work around bug in zipfile module that can't
            # handle directories that are "members"
            members = []
            dirs = []
            for i in z_files:
                if is_file(i):
                    members.append(i)
                else:
                    dirs.append(i)
            #import pdb;pdb.set_trace()
            zip_.extractall(members=members,path=tmpdir)
            #os.system('unzip -q -o -d %s %s' % (tmpdir,kml))
            resource = os.path.join(tmpdir,resource)

        resource = utils.ensure_utf8(resource)
        return (resource,objectify.parse(resource))
    
    def handle_network_links(self,NetworkLinks):
        for nl in NetworkLinks:
            if hasattr(nl,'Link'):
                resource = nl.Link.href
            elif hasattr(nl,'Url'):
                resource = nl.Url.href
            if resource:
                self.kmls.append(unicode(resource))

    def initialize(self):
        kml, tree = self.parse(self.resource)
        root = tree.getroot()

        # xml namespace
        if len(root.tag) > 3:
            self.ns = '{%s}' % root.tag.split('}')[0][1:]
        else:
            self.ns = ''

        if hasattr(root,'Document') and hasattr(root.Document,'NetworkLink'):    
            self.has_network_links = True
            self.m('Network links!')
            self.handle_network_links(root.Document.NetworkLink)
        elif hasattr(root,'NetworkLink'):
            self.has_network_links = True
            self.m('Network links!')
            self.handle_network_links(root.NetworkLink)        
        else:
            self.kmls = [kml]
    
    def stream(self):
        self.initialize()
        for kml_reference in self.kmls:
            self.m('handling %s' % kml_reference)
            kml, tree = self.parse(kml_reference)
            self.m('found kml: %s' % kml)
            root = tree.getroot()
            #self.ogr_ds = ogr.Open(kml)
            #if not self.ogr_ds and not self.has_network_links:
                #sys.exit('Sorry this KML is not a valid datasource, there are no layers!')
            
            kml_name = self.kml_unique_name(kml)

            self.collect_layer_style_maps(kml,tree)

            features = self.get_features(root)

            #self.collect_feature_styles(kml_name,features)
            
            # make sense of stylemapping first
            #if hasattr(root,'Document') and hasattr(root.Document,'StyleMap'):
            style_maps,styles = self.get_all_style_data(tree,root)
            self.collect_style_maps(kml_name,style_maps)
            self.collect_styles(kml,kml_name,styles)
            
            # then collect actual styles
            #if hasattr(root,'Document') and hasattr(root.Document,'Style'):
            #    self.collect_styles(kml,kml_name,root.Document.Style)

            # match stylesmaps to styles
            #if self.style_maps.get(kml_name):
            #    if not self.style_maps[kml_name].get(sty_name): # if not hover...
            #        pass#break

            self.handle_layers(kml,kml_name,features)
            
        if not self.quiet:
            print mapnik.save_map_to_string(self.map)
    
    def get_all_style_data(self,tree,root):
        sm = []
        st = []
        for ele in tree.iter():
            type_ = ele.tag.replace(self.ns,'')
            if type_ == 'StyleMap':
                sm.append(ele)
            elif type_ == 'Style':
                st.append(ele)
        return sm,st    
        
    def get_features(self,root):
        """ attempt to figure out nestedness to collect style <-> layer association
        """
        
        folders = root.findall('%sDocument/%sFolder' % (self.ns,self.ns))
        #folders = root.xpath('/a:Document/a:Folder',namespaces={'a':self.ns})
        
        if root.tag.replace(self.ns,'') == 'Placemark':
            return [root]
        
        if not folders:
            #self.m('not doc folder found, looking for base document...')
            folders = root.findall('%sDocument' % (self.ns))
        
        if len(folders) == 1:
            #self.m('folders found checking out first sub item...')
            folder = folders[0]
            if hasattr(folder,'Placemark'):
                #self.m('folders have placemarks!')
                features = folder.Placemark
            elif hasattr(folder,'Folder'):
                #self.m('folders inside of folders!')
                features = folder.Folder
            else:
                features = folder
        elif len(folders) > 1:
            #self.m('assuming weve got lots of features!')
            features = folders
        else:
            self.m('seems we have no features')
            features = []
        return features

    def kml_unique_name(self,kml):
        # slow!!!
        name = os.path.basename(kml)
        if name in self.names:
            name = os.path.join(os.path.basename(os.path.dirname(kml)),name)
            if name in self.names:
                name = kml
        self.names.append(name)
        return name
    
    def collect_style_urls_for_placemarks(self,Placemarks):
         # goal - just to collect mapping between
         # layer name and styleurls
         
         # assume one-to-one for now
         style_urls_for_layer = []
         for feature in Placemarks:
            if hasattr(feature,'styleUrl'):
                style = unicode(feature.styleUrl).replace('#','')
                style_urls_for_layer.append(style)
                #name = '%s-%s' % (kml_name,unicode(layer_name))
                #stylemap = self.layer_styles[layer_name].get(style)
                #if not stylemap:
                #    stylemap = self.feat_styles[layer_name][style] = []
                #if name not in stylemap:
                #    self.feat_styles[layer_name][style].append(name)
                #self.m('collected feature style: %s:%s' % (str(name),style))
         return style_urls_for_layer
        
    def collect_layer_style_maps(self, kml,tree):
        
        layer_names = [ogr_layer.GetName() for ogr_layer in self.get_layers_via_ogr(kml)]
        for ele in tree.iter():
            type_ = ele.tag.replace(self.ns,'')
            if str(type_) in ('Folder','Document'):
                if hasattr(ele,'name'):
                   ele_name = hasattr(ele,'name')
                   if ele.name in layer_names:
                      mapping = self.collect_style_urls_for_placemarks(ele.Placemark)
                      if mapping:
                          self.layer_styles[str(ele.name)] = mapping
                   #else:
                   #   print ele.name
        
                
    #def collect_feature_styles(self, kml_name, Features):    
    #    for feature in Features:
    #        if hasattr(feature, 'name'):
    #            layer_name = str(feature.name)
    #            self.feat_styles[layer_name] = {}
    #        else:
    #            sys.exit('feature has no name!')
    #        #if hasattr(feature,'Placemark'):
    #        #    feature = feature.Placemark
    #        if hasattr(feature,'styleUrl'):
    #            # slow!!!!
    #            style = unicode(feature.styleUrl).replace('#','')
    #            name = '%s-%s' % (kml_name,unicode(layer_name))
    #            stylemap = self.feat_styles[layer_name].get(style)
    #            if not stylemap:
    #                stylemap = self.feat_styles[layer_name][style] = []
    #            if name not in stylemap:
    #                self.feat_styles[layer_name][style].append(name)
    #            #self.m('collected feature style: %s:%s' % (str(name),style))
    #        #except:
    #        #self.feat_styles[str(name)] = sty_name
    #    if not self.feat_styles[layer_name]:
    #        self.m('no feature styles collected!')
    #   import pdb;pdb.set_trace()
 
    def collect_style_maps(self,kml_name,StyleMaps):
        for sm in StyleMaps:
            style_map_id = sm.get('id')
            for pair in sm.Pair:
                if pair.key == 'normal':
                    #self.style_maps[sm.get('id')] = sm.Pair.styleUrl
                    if hasattr(pair,'Style'):
                        key = unicode(pair.Style)
                    elif hasattr(pair,'styleUrl'):
                        key = unicode(pair.styleUrl).replace('#','')
                    else:
                        sys.exit('ack, missing Style or StylUrl tag!')
                    sty_name = '%s-%s' % (kml_name,key)
                    self.style_maps[style_map_id] = sty_name
        
           
    def line_style(self,Style):
        if hasattr(Style.LineStyle,'width'):
            width = float(Style.LineStyle.width)
        else:
            width = 1 # better default?
        # TOD - if no width - just ignore?
        if hasattr(Style.LineStyle,'color'):
            c_ = Style.LineStyle.color
            #print c_
            # lxml bug!
            print '########### try .text here (line 289)'
            if c_ == 0:
                c_ = '00000000'
            color = utils.kml_hex_to_mapnik_color(c_)
        else:
            color = mapnik.Color('gray')
        stroke = mapnik.Stroke(color,width)
        # need to handle opacity...
        #stroke.opacity = .5
        return mapnik.LineSymbolizer(stroke)

    def poly_style(self,kml,Style):
        # need to not attach if 3d shape!!!
        # or change mapnik to ignore polygon symbolizers put on line geometries
        #if hasattr(s.PolyStyle,'color'):
        poly = None
        if hasattr(Style.PolyStyle,'color'):
            ogr_ds = ogr.Open(kml)
     
            if not ogr_ds:
                sys.exit('Sorry this KML: %s\n\n is not a valid datasource, there are no layers!' % kml)
    
            lyr = ogr_ds.GetLayer(0)
            gname = self.get_geom_type(lyr)
            if 'poly' in gname:
              c_ = Style.PolyStyle.color
              #print c_
              # lxml bug!
              if c_ == 0:
                  c_ = '00000000'
              poly = mapnik.PolygonSymbolizer(utils.kml_hex_to_mapnik_color(c_))
        elif hasattr(Style.PolyStyle,'fill'):
            if Style.PolyStyle.fill == 0:
                pass # no fill
        elif hasattr(Style.Polystyle,'outline'):
            pass # todo
        return poly

    def handle_icon(self,Style,path):
        # TODO - logically resize based on scale
        scale = 0
        if hasattr(Style.IconStyle,'scale'):
            scale = float(Style.IconStyle.scale)
            self.m('scale: %s' % scale)
        
        try:
            im = Image.open(path)
        except IOError, e:
            sys.stderr.write('## WARNING: IOError(%s (%s, from %s))' % (e,path,href))
            return None
        #import pdb;pdb.set_trace()
        if hasattr(Style.IconStyle.Icon,'x') and hasattr(Style.IconStyle.Icon,'x') \
            and hasattr(Style.IconStyle.Icon,'y') \
            and hasattr(Style.IconStyle.Icon,'w') \
            and hasattr(Style.IconStyle.Icon,'h'):
            # the image may be a sprite!
            # so we need to crop out the actual icon
            im = im.crop(im.getbbox())
            x = Style.IconStyle.Icon.x
            y = Style.IconStyle.Icon.y
            w = Style.IconStyle.Icon.w
            h = Style.IconStyle.Icon.h
            # left, upper, right, and lower
            box = (x,y,x+w,y+h)
            cropped = im.crop(box)
            name,ext = os.path.splitext(path)
            path = '%s_%s_%s%s' % (name,x,y,ext)
            cropped.save(path)
            #print path
        else:
            
            #if im.size[1] > 50:
            self.m('resizing!')
            #im = Image.open(path)
            if scale:
                size = int(32*scale*.3)
            else:
                size = 10
            smaller = im.resize((size,size),Image.ANTIALIAS)
            os.unlink(path)
            smaller.save(path)
        return path

        
    def handle_href_icon(self,Style,href):
        img_data = None
        try:
            img_data = urllib2.urlopen(href).read()
        except:
            sys.stderr.write('could not fetch %s\n' % href)
        if img_data:
            (handle, path) = tempfile.mkstemp(suffix='.png',prefix='kml2mapnik-img')
            os.close(handle)
            #path = os.path.basename(href)
            file = open(path,'wb')
            file.write(img_data)
            file.close()
            self.m('saving image: %s' % path)
            #fix_corrupt = True
            # TODO - convert everything to PNG? eg. gifs
            #if fix_corrupt:
            #    Image.open(path).save(path)
            
            return self.handle_icon(Style,path)

    def icon_style(self,Style,kml):
        href = unicode(Style.IconStyle.Icon.href)
        href = utils.fix(href)
        icon = None
        if href.startswith('http'):
            path = self.handle_href_icon(Style,href)
            if path:
                icon = mapnik.PointSymbolizer(mapnik.PathExpression(str(path)))
                icon.allow_overlap = True
        else:
            # local file (maybe bundled with kmz)
            if not os.path.exists(href):
                href = os.path.join(os.path.dirname(kml),href)
            if os.path.exists(href):
                path = self.handle_icon(Style,href)
                if path:
                    icon = mapnik.PointSymbolizer(mapnik.PathExpression(str(path)))
                    icon.allow_overlap = True                
            else:
                sys.stderr.write('could not find %s\n' % href) 
        if not icon:
            icon = mapnik.PointSymbolizer()
            icon.allow_overlap = True
                    
            #else:
            #    im = Image.open(href)
            #    icon = mapnik.PointSymbolizer(mapnik.PathExpression(href))
            #    #icon = mapnik.PointSymbolizer(href, im.format.lower(), im.size[0], im.size[1])
            #    icon.allow_overlap = True
            #    rule.symbols.append(icon)

        return icon
                    
    def collect_styles(self,kml,kml_name,Styles):
        for style in Styles:
            sty = mapnik.Style()
            id_ = style.get('id')
            if not id_:
                self.has_style_per_placement = True
            else:
                sty_name = '%s-%s' % (kml_name,id_)
                #import pdb;pdb.set_trace()
                rule = mapnik.Rule()
                if hasattr(style,'LineStyle'):
                    sym = self.line_style(style)
                    if sym:
                        rule.symbols.append(sym)
                if hasattr(style,'PolyStyle'):
                    sym = self.poly_style(kml,style)
                    if sym:
                        rule.symbols.append(sym)
                if hasattr(style,'IconStyle'):
                    # gotta pass the KML file path here...
                    sym = self.icon_style(style,kml)
                    if sym:
                        rule.symbols.append(sym)                                    
                if len(rule.symbols):
                    sty.rules.append(rule)
                    self.map.append_style(sty_name,sty)
                    self.style_names.append(sty_name)
                else:
                    sys.stderr.write('no valid rules or symbolizers found in style:%s\n' % sty_name)
                    pass#print len(rule.symbols)
                    #raise NotImplementedError('no styles!') 

    #def has_style_per_placement(self):
    #    return True
        
    def get_layers_via_ogr(self,kml):
        ogr_ds = ogr.Open(kml)
 
        if not ogr_ds:
            sys.exit('Sorry this KML: %s\n\n is not a valid datasource, there are no layers!' % kml)

        for idx in range(ogr_ds.GetLayerCount()):
            yield ogr_ds.GetLayer(idx)

    def get_geom_type(self,ogr_layer):
        lay_def = ogr_layer.GetLayerDefn()
        gtype = lay_def.GetGeomType()
        return utils.wkb_types[gtype].lower()
        
    def handle_layers(self,kml,kml_name,features):
        
        kml_layers = []
        ogr_layers = self.get_layers_via_ogr(kml)
        for ogr_layer in ogr_layers:
            # filter layers? maybe stuff into sqlite?
            found_style = False
            name = ogr_layer.GetName()

            layer = mapnik.Layer(name)
            if self.shapefile_datasource:
                layer.datasource = utils.shape_layer(kml,ogr_layer)
            else:
                layer.datasource = utils.ogr_kml_layer(kml,ogr_layer)
            # if we found styles at top level
            #import pdb;pdb.set_trace()
            if self.has_style_per_placement:
                # chlorpleth!
                s = mapnik.Style()
                for feature in features:
                    if hasattr(feature,'Style'):
                        Style = feature.Style
                        found_style = True
                        #print feature
                        r = mapnik.Rule()
                        if hasattr(Style,'LineStyle'):
                            sym = self.line_style(Style)
                            if sym:
                                r.symbols.append(sym)
                        if hasattr(Style,'PolyStyle'):
                            sym = self.poly_style(kml,Style)
                            if sym:
                                r.symbols.append(sym)
                        # other styles?
                        # NOTE!!! 'Name' not 'name'
                        expr = "[Name] = '%s'" % str(feature.name)
                        r.filter = mapnik.Expression(expr)
                        s.rules.append(r)
                if found_style:
                    self.map.append_style('chlorpleth',s)
                    layer.styles.append('chlorpleth')                

            elif self.style_names:
                #import pdb;pdb.set_trace()
                #if they match references in placemarks
                #import pdb;pdb.set_trace()
                ##m_ylw-pushpin and whale
                if self.style_maps:
                    for stylemap, style in self.style_maps.items():
                        # sty should match an actual stylename collected
                        if stylemap in self.layer_styles.get(layer.name):
                            #name = '%s-%s' % (kml_name,layer.name)
                            #import pdb;pdb.set_trace()
                            #lyr_name = self.feat_styles[kml_name][name].replace('#','')
                            #print 'appendin style: %s to %s' % (style,layer.name)
                            layer.styles.append(str(style))
                            found_style = True
                else:
                    # blindly apply styles to map
                    layer.styles.extend(self.style_names)
                    found_style = True
                    
                if not found_style: #attach em all!
                    pass#styles = self.style_names.get(kml_name)
                    #if styles:
                    #    layer.styles.extend(styles)
                    #    found_style = True
                #if FEATURE_RULE:
                #    layer.styles.append('f_s')
            if not found_style: # lets apply default style based on geometry...
                sys.stderr.write('##WARNING: did not find any styles!\n')
                name = name.replace('#','')
                gname = self.get_geom_type(ogr_layer)
                r,s = mapnik.Rule(),mapnik.Style()
                if 'poly' in gname.lower():
                    sym = mapnik.PolygonSymbolizer(mapnik.Color('#BFD5FF'))
                    sym.fill_opacity = .7
                    r.symbols.append(sym)
                    r.symbols.append(mapnik.LineSymbolizer(mapnik.Color('#8C8CFF'),2))
                elif 'line' in gname.lower():
                    r.symbols.append(mapnik.LineSymbolizer(mapnik.Color('white'),1))
                elif 'point' in gname.lower():
                    sym = mapnik.PointSymbolizer()
                    sym.allow_overlap = True
                    r.symbols.append(sym)
                s.rules.append(r)
                layer.styles.append('default_style')
                self.map.append_style('default_style',s)
                    
            kml_layers.insert(0,layer)
        self.map.layers.extend(kml_layers)
