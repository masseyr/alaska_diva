from osgeo import ogr, osr, gdal
import math
import json
import sys
import os
from common import *

__all__ = ['Vector']


class Vector(object):
    """
    Class for vector objects
    """

    def __init__(self,
                 filename=None,
                 name='Empty',
                 spref=None,
                 spref_str=None,
                 epsg=None,
                 proj4=None,
                 layer_index=0,
                 geom_type=None,
                 in_memory=False,
                 verbose=False,
                 primary_key='fid',
                 feat_limit=None,
                 attr_def=None):
        """
        Constructor for class Vector
        :param filename: Name of the vector file (shapefile) with full path
        :param layer_index: Index of the vector layer to pull (default: 0)
        """

        self.filename = filename
        self.datasource = None

        self.features = list()
        self.attributes = list()
        self.wktlist = list()

        self.precision = 16  # Precision is set only for float attributes
        self.width = 50  # Width is set for string characters
        self.epsg = epsg  # EPSG SRID
        self.proj4 = proj4

        self.layer = None
        self.spref = spref
        self.spref_str = spref_str
        self.type = self.ogr_geom_type(geom_type) if geom_type is not None else None

        self.name = name
        self.nfeat = 0
        self.fields = list()
        self.data = dict()
        self.attr_def = attr_def

        if filename is not None and os.path.isfile(filename):

            # open vector file
            self.datasource = ogr.Open(self.filename)
            file_layer = self.datasource.GetLayerByIndex(layer_index)

            if in_memory:
                out_driver = ogr.GetDriverByName('Memory')
                out_datasource = out_driver.CreateDataSource('mem_source')
                self.layer = out_datasource.CopyLayer(file_layer, 'mem_source')
                self.datasource = out_datasource
                file_layer = None

            else:
                # get layer
                self.layer = file_layer

            # spatial reference
            self.spref = self.layer.GetSpatialRef()

            if spref_str is not None:
                dest_spref = osr.SpatialReference()
                res = dest_spref.ImportFromWkt(spref_str)

                if self.spref.IsSame(dest_spref) == 1:
                    dest_spref = None
            else:
                dest_spref = None

            self.spref_str = self.spref.ExportToWkt()

            # other layer metadata
            self.type = self.layer.GetGeomType()
            self.name = self.layer.GetName()

            # number of features
            self.nfeat = self.layer.GetFeatureCount()

            if verbose:
                sys.stdout.write('Reading vector {} of type {} with {} features\n'.format(self.name,
                                                                                          str(self.type),
                                                                                          str(self.nfeat)))

            # get field defintions
            layer_definition = self.layer.GetLayerDefn()
            self.fields = [layer_definition.GetFieldDefn(i) for i in range(0, layer_definition.GetFieldCount())]

            # if the vector should be initialized in some other spatial reference
            if dest_spref is not None:
                transform_tool = osr.CoordinateTransformation(self.spref,
                                                              dest_spref)
                self.spref = dest_spref
            else:
                transform_tool = None

            # iterate thru features and append to list
            feat = self.layer.GetNextFeature()

            feat_count = 0
            while feat:
                if feat_limit is not None:
                    if feat_count >= feat_limit:
                        break

                # extract feature attributes
                all_items = feat.items()

                # and feature geometry feature string
                geom = feat.GetGeometryRef()

                # close rings if polygon
                if geom_type == 3:
                    geom.CloseRings()

                # convert to another projection and write new features
                if dest_spref is not None:
                    geom.Transform(transform_tool)

                    new_feat = ogr.Feature(layer_definition)
                    for attr, val in all_items.items():
                        new_feat.SetField(attr, val)
                    new_feat.SetGeometry(geom)
                else:
                    new_feat = feat

                if verbose:
                    attr_dict = json.dumps(all_items)
                    sys.stdout.write('Feature {} of {} : attr {}\n'.format(str(feat_count+1),
                                                                           str(self.nfeat),
                                                                           attr_dict))

                self.attributes.append(all_items)
                self.features.append(new_feat)
                self.wktlist.append(geom.ExportToWkt())
                feat_count += 1

                feat = self.layer.GetNextFeature()

            self.nfeat = len(self.features)

            if verbose:
                sys.stdout.write("\nInitialized Vector {} of type {} ".format(self.name,
                                                                              self.ogr_geom_type(self.type)) +
                                 "with {} feature(s) and {} attribute(s)\n\n".format(str(self.nfeat),
                                                                                   str(len(self.fields))))
        else:
            if in_memory:
                out_driver = ogr.GetDriverByName('Memory')
                out_datasource = out_driver.CreateDataSource('mem_source')
                self.datasource = out_datasource

                if self.spref_str is not None:
                    self.spref = osr.SpatialReference()
                    res = self.spref.ImportFromWkt(spref_str)
                elif self.epsg is not None:
                    self.spref = osr.SpatialReference()
                    res = self.spref.ImportFromEPSG(self.epsg)
                    self.spref_str = self.spref.ExportToWkt()
                elif self.proj4 is not None:
                    self.spref = osr.SpatialReference()
                    res = self.spref.ImportFromEPSG(self.proj4)
                    self.spref_str = self.spref.ExportToWkt()
                else:
                    raise ValueError("No spatial reference provided")

                self.layer = self.datasource.CreateLayer('mem_layer',
                                                         srs=self.spref,
                                                         geom_type=self.type)

                if attr_def is not None:
                    for attr_name, attr_type in attr_def.items():
                        temp_attr = ogr.FieldDefn(attr_name, OGR_FIELD_DEF[attr_type])
                        if attr_type == 'str':
                            temp_attr.SetWidth(self.width)
                        if attr_type in ('float', 'int'):
                            temp_attr.SetPrecision(self.precision)

                        self.layer.CreateField(temp_attr)
                        self.fields.append(temp_attr)

                if primary_key is not None:
                    fid = ogr.FieldDefn(primary_key, )
                    fid.SetPrecision(9)
                    self.layer.CreateField(fid)
                    self.fields.append(fid)

            if verbose:
                sys.stdout.write("\nInitialized empty Vector\n")

    def __repr__(self):
        return "<Vector {} of type {} ".format(self.name,
                                               str(self.type)) + \
               "with {} feature(s) and {} attribute(s)>".format(str(self.nfeat),
                                                                str(len(self.fields)))

    @staticmethod
    def ogr_data_type(x):
        """
        Method to get OGR data type, for use in creating OGR geometry fields
        :param x: Any data input
        :return: OGR data type
        """
        val = type(x).__name__.lower()
        try:
            return OGR_FIELD_DEF[val]
        except (KeyError, NameError):
            return OGR_FIELD_DEF['none']

    @staticmethod
    def ogr_geom_type(x):
        """
        Method to return OGR geometry type from input string
        :param x: String to convert to OGR geometry type code
        :return: OGR geometry type code
        """

        if type(x).__name__ == 'str':
            comp_str = x.lower()
            try:
                return OGR_TYPE_DEF[comp_str]
            except (KeyError, NameError):
                return None

        elif type(x).__name__ == 'int' or type(x).__name__ == 'float':
            try:
                return OGR_GEOM_DEF[int(x)].upper()
            except (KeyError, NameError):
                return None

        else:
            raise(ValueError('Invalid format'))

    @staticmethod
    def string_to_ogr_type(x):
        """
        Method to return name of the data type
        :param x: input item
        :return: string
        """
        if type(x).__name__ != 'str':
            return Vector.ogr_data_type(x)
        else:
            try:
                val = int(x)
            except ValueError:
                try:
                    val = float(x)
                except ValueError:
                    try:
                        val = str(x)
                    except:
                        val = None

            return Vector.ogr_data_type(val)

    @staticmethod
    def wkt_from_coords(coords,
                        geom_type='point'):

        """
        Method to return WKT string representation from a list
        :param coords: List of tuples [(x1,y1),(x2,y2),...] for multipoint
                       or a single tuple (x, y) in case of 'point'
                       x=longitude, y=latitude and so on
        :param geom_type: multipoint, point,
        :return: WKT string representation
        """

        if geom_type.upper() == 'POINT':
            tempstring = ' '.join([str(coord) for coord in coords])
            wktstring = 'POINT({})'.format(tempstring)

        elif geom_type.upper() == 'MULTIPOINT':
            tempstring = '), ('.join(list(' '.join([str(x), str(y)]) for (x, y) in coords))
            wktstring = 'MULTIPOINT(({}))'.format(tempstring)

        elif geom_type.upper() == 'POLYGON':

            tempstring = ', '.join(list(' '.join([str(x), str(y)]) for (x, y) in coords))
            wktstring = 'POLYGON(({}))'.format(tempstring)

        elif geom_type.upper() == 'LINESTRING' or geom_type.upper() == 'LINE':

            tempstring = ', '.join(list(' '.join([str(x), str(y)]) for (x, y) in coords))
            wktstring = 'LINESTRING({})'.format(tempstring)

        else:
            raise ValueError("Unknown geometry type")

        return wktstring

    @staticmethod
    def get_osgeo_geom(geom_string,
                       geom_type='wkt'):
        """
        Method to return a osgeo geometry object
        :param geom_string: Wkt or json string
        :param geom_type: 'wkt', 'json', or 'wkb
        :return: osgeo geometry object
        """
        if geom_type == 'wkt':
            try:
                return ogr.CreateGeometryFromWkt(geom_string)
            except:
                return
        elif geom_type == 'json':
            try:
                return ogr.CreateGeometryFromJson(geom_string)
            except:
                return
        elif geom_type == 'wkb':
            try:
                return ogr.CreateGeometryFromWkb(geom_string)
            except:
                return
        else:
            raise ValueError("Unsupported geometry type")

    def add_feat(self,
                 geom,
                 primary_key='fid',
                 attr=None):

        """
        Add geometry as a feature to a Vector in memory
        :param geom: osgeo geometry object
        :param primary_key: primary key for the attribute table
        :param attr: Attributes
        :return: None
        """

        feat = ogr.Feature(self.layer.GetLayerDefn())
        feat.SetGeometry(geom)

        if attr is not None:
            for k, v in attr.items():
                feat.SetField(k, v)
            if primary_key is not None:
                if primary_key not in attr:
                    feat.SetField(primary_key, self.nfeat)
        else:
            if primary_key is not None:
                feat.SetField(primary_key, self.nfeat)

        self.layer.CreateFeature(feat)
        self.features.append(feat)
        self.wktlist.append(geom.ExportToWkt())
        if attr is not None:
            if primary_key is not None:
                attr.update({primary_key: self.nfeat})
            self.attributes.append(attr)
        elif primary_key is not None:
            self.attributes.append({primary_key: self.nfeat})

        self.nfeat += 1

    def merge(self,
              vector,
              remove=False):

        """
        Method to merge two alike vectors. This method only works for vectors
        that have same spref or spref_str, attribute keys, and geom types
        :param vector: Vector to merge in self
        :param remove: if the vector should be removed after merging
        :return: None
        """

        for i, feat in enumerate(vector.features):
            geom = feat.GetGeometryRef()
            attr = feat.items()

            self.add_feat(geom=geom,
                          attr=attr)

        if len(vector.data) > 0:
            self.data.update(vector.data)

        if remove:
            vector = None

    def write_vector(self,
                     outfile=None,
                     in_memory=False):
        """
        Method to write the vector object to memory or to file
        :param outfile: File to write the vector object to
        :param in_memory: If the vector object should be written in memory (default: False)
        :return: Vector object if written to memory else NoneType
        """

        if in_memory:

            driver_type = 'Memory'

            if outfile is not None:
                outfile = os.path.basename(outfile).split('.')[0]
            else:
                outfile = 'in_memory'

            out_driver = ogr.GetDriverByName(driver_type)
            out_datasource = out_driver.CreateDataSource(outfile)
            out_layer = out_datasource.CopyLayer(self.layer, outfile)

            out_vector = Vector()

            out_vector.datasource = out_datasource
            out_vector.mem_source = out_datasource

            return out_vector

        else:

            if outfile is None:
                outfile = self.filename
                if self.filename is None:
                    raise ValueError("No filename for output")

            if os.path.basename(outfile).split('.')[-1] == 'json':
                driver_type = 'GeoJSON'
            elif os.path.basename(outfile).split('.')[-1] == 'csv':
                driver_type = 'Comma Separated Value'
            else:
                driver_type = 'ESRI Shapefile'

            out_driver = ogr.GetDriverByName(driver_type)
            out_datasource = out_driver.CreateDataSource(outfile)

            out_layer = out_datasource.CreateLayer(os.path.basename(outfile).split('.')[0],
                                                   srs=self.spref,
                                                   geom_type=self.type)

            for field in self.fields:
                out_layer.CreateField(field)

            layer_defn = out_layer.GetLayerDefn()

            if len(self.wktlist) > 0:
                for i, wkt_geom in enumerate(self.wktlist):
                    geom = ogr.CreateGeometryFromWkt(wkt_geom)
                    feat = ogr.Feature(layer_defn)
                    feat.SetGeometry(geom)

                    for attr, val in self.attributes[i].items():
                        feat.SetField(attr, val)

                    out_layer.CreateFeature(feat)

            elif len(self.features) > 0:
                for feature in self.features:
                    out_layer.CreateFeature(feature)

            else:
                sys.stdout.write('No features found... closing file.\n')

            out_datasource = out_driver = None

    def get_intersecting_vector(self,
                                query_vector,
                                filter_query=False,
                                index=False):
        """
        Gets tiles intersecting with the given geometry (any type).
        This method returns an initialized Vector object. The first argument (or self) should be Polygon type.
        :param query_vector: Initialized vector object to query with (geometry could be any type)
        :param index: If the index of self vector where intersecting, should be returned
        :returns: Vector object of polygon features from self
        """

        query_list = list()

        # determine if same coordinate system
        if self.spref.IsSame(query_vector.spref) == 1:

            index_list = list()

            # determine which features intersect
            for j in range(0, query_vector.nfeat):
                qgeom = query_vector.features[j].GetGeometryRef()

                for i in range(0, self.nfeat):

                    feat = self.features[i]
                    geom = feat.GetGeometryRef()

                    if geom.Intersects(qgeom):
                        if filter_query:
                            index_list.append(j)
                        else:
                            index_list.append(i)

            intersect_index = sorted(set(index_list))

            for feat_index in intersect_index:
                if filter_query:
                    feat = query_vector.features[feat_index]
                else:
                    feat = self.features[feat_index]

                temp_feature = dict()
                temp_feature['feat'] = feat
                temp_feature['attr'] = feat.items()

                query_list.append(temp_feature)

            # create output vector in memory
            out_vector = Vector()

            # create a vector in memory
            memory_driver = ogr.GetDriverByName('Memory')
            temp_datasource = memory_driver.CreateDataSource('out_vector')

            # relate memory vector source to Vector object
            out_vector.mem_source = temp_datasource
            out_vector.datasource = temp_datasource
            out_vector.wktlist = list()

            # update features and crs
            out_vector.nfeat = len(query_list)
            out_vector.type = query_vector.type if filter_query else self.type
            out_vector.spref = query_vector.spref if filter_query else self.spref
            out_vector.fields = query_vector.fields if filter_query else self.fields
            out_vector.name = query_vector.name if filter_query else self.name

            # create layer in memory
            temp_layer = temp_datasource.CreateLayer('temp_layer',
                                                     srs=query_vector.spref if filter_query else self.spref,
                                                     geom_type=query_vector.type if filter_query else self.type)

            out_fields = query_vector.fields if filter_query else self.fields

            # create the same attributes in the temp layer as the input Vector layer
            for k in range(0, len(out_fields)):
                temp_layer.CreateField(out_fields[k])

            # fill the features in output layer
            for i in range(0, len(query_list)):

                # create new feature
                temp_feature = ogr.Feature(temp_layer.GetLayerDefn())

                # fill geometry
                temp_geom = query_list[i]['feat'].GetGeometryRef()
                temp_feature.SetGeometry(temp_geom)

                # get attribute dictionary from query list
                attr_dict = dict(query_list[i]['attr'].items())

                # set attributes for the feature
                for j in range(0, len(out_fields)):
                    name = out_fields[j].GetName()
                    temp_feature.SetField(name, attr_dict[name])

                out_vector.features.append(temp_feature)
                out_vector.wktlist.append(temp_geom.ExportToWkt())
                out_vector.attributes.append(attr_dict)

                # create new feature in output layer
                temp_layer.CreateFeature(temp_feature)

            out_vector.layer = temp_layer

            if index:
                return out_vector, intersect_index
            else:
                return out_vector

        else:
            raise RuntimeError("Coordinate system or object type mismatch")

    def reproject(self,
                  epsg=None,
                  dest_spatial_ref_str=None,
                  dest_spatial_ref_str_type=None,
                  destination_spatial_ref=None,
                  _return=False):
        """
        Transfrom a geometry using OSR library (which is based on PROJ4)
        :param dest_spatial_ref_str: Destination spatial reference string
        :param dest_spatial_ref_str_type: Destination spatial reference string type
        :param destination_spatial_ref: OSR spatial reference object for destination feature
        :param epsg: Destination EPSG SRID code
        :return: Reprojected vector object
        """

        vector = Vector()
        vector.type = self.type
        vector.nfeat = self.nfeat

        if destination_spatial_ref is None:
            destination_spatial_ref = osr.SpatialReference()

            if dest_spatial_ref_str is not None:
                if dest_spatial_ref_str_type == 'wkt':
                    res = destination_spatial_ref.ImportFromWkt(dest_spatial_ref_str)
                elif dest_spatial_ref_str_type == 'proj4':
                    res = destination_spatial_ref.ImportFromProj4(dest_spatial_ref_str)
                elif dest_spatial_ref_str_type == 'epsg':
                    res = destination_spatial_ref.ImportFromEPSG(dest_spatial_ref_str)
                else:
                    raise ValueError("No spatial reference string type specified")
            elif epsg is not None:
                res = destination_spatial_ref.ImportFromEPSG(epsg)

            else:
                raise ValueError("Destination spatial reference not specified")

        vector.spref = destination_spatial_ref
        vector.spref_str = destination_spatial_ref.ExportToWkt()

        # get source spatial reference from Spatial reference WKT string in self
        source_spatial_ref = self.spref

        # create a transform tool (or driver)
        transform_tool = osr.CoordinateTransformation(source_spatial_ref,
                                                      destination_spatial_ref)

        # Create a memory layer
        memory_driver = ogr.GetDriverByName('Memory')
        vector.datasource = memory_driver.CreateDataSource('out')

        # create a layer in memory
        vector.layer = vector.datasource.CreateLayer('temp',
                                                     srs=source_spatial_ref,
                                                     geom_type=self.type)

        # initialize new feature list
        vector.features = list()
        vector.fields = list()
        vector.name = self.name

        # input layer definition
        in_layer_definition = self.layer.GetLayerDefn()

        # add fields
        for i in range(0, in_layer_definition.GetFieldCount()):
            field_definition = in_layer_definition.GetFieldDefn(i)
            vector.layer.CreateField(field_definition)
            vector.fields.append(field_definition)

        # layer definition with new fields
        temp_layer_definition = vector.layer.GetLayerDefn()

        vector.wktlist = list()
        vector.attributes = self.attributes

        # convert each feature
        for feat in self.features:

            # transform geometry
            temp_geom = feat.GetGeometryRef()
            temp_geom.Transform(transform_tool)

            vector.wktlist.append(temp_geom.ExportToWkt())

            # create new feature using geometry
            temp_feature = ogr.Feature(temp_layer_definition)
            temp_feature.SetGeometry(temp_geom)

            # fill geometry fields
            for i in range(0, temp_layer_definition.GetFieldCount()):
                field_definition = temp_layer_definition.GetFieldDefn(i)
                temp_feature.SetField(field_definition.GetNameRef(), feat.GetField(i))

            # add the feature to the shapefile
            vector.layer.CreateFeature(temp_feature)

            vector.features.append(temp_feature)
            vector.epsg = epsg

        if _return:
            return vector
        else:
            self.layer = vector.layer
            self.features = vector.features
            self.fields = vector.fields
            self.datasource = vector.datasource
            self.wktlist = vector.wktlist
            self.spref_str = vector.spref_str

    @staticmethod
    def reproj_geom(geoms,
                    source_spref_str,
                    dest_spref_str):

        """
        Method to reproject geometries
        :param geoms: List of osgeo geometries or a single geometry
        :param source_spref_str: Source spatial reference string
        :param dest_spref_str: Destination spatial reference string
        :return: osgeo geometry
        """

        source_spref = osr.SpatialReference()
        dest_spref = osr.SpatialReference()

        res = source_spref.ImportFromWkt(source_spref_str)
        res = dest_spref.ImportFromWkt(dest_spref_str)
        transform_tool = osr.CoordinateTransformation(source_spref,
                                                      dest_spref)

        if type(geoms).__name__ == 'list':
            for geom in geoms:
                geom.Transfrom(transform_tool)
        else:
            geoms.Transform(transform_tool)
        return geoms

    def split(self):
        """
        Method to split (or flatten) multi-geometry vector to multiple single geometries vector.
        The vector can have single or multiple multi-geometry features
        :return: Vector object with all single type geometries
        """

        if self.type < 4:
            return self
        else:

            # get layer information
            layr = self.layer

            # get field (attribute) information
            feat_defns = layr.GetLayerDefn()
            nfields = feat_defns.GetFieldCount()
            field_defs = list(feat_defns.GetFieldDefn(i) for i in range(0, nfields))

            # create list of features with geometries and attributes
            out_feat_list = list()

            out_type = None

            # loop thru all the feature and all the multi-geometries in each feature
            for feat in self.features:

                geom_ref = feat.GetGeometryRef()
                n_geom = geom_ref.GetGeometryCount()

                feat_attr = dict()
                for field in field_defs:
                    feat_attr[field.GetName()] = feat.GetField(field.GetName())

                # create list of features from multi-geometries
                for j in range(0, n_geom):
                    temp_feat_dict = dict()
                    temp_feat_dict['geom'] = geom_ref.GetGeometryRef(j)
                    temp_feat_dict['attr'] = feat_attr

                    # find output geometry type
                    if out_type is None:
                        out_type = temp_feat_dict['geom'].GetGeometryType()

                    # append to output list
                    out_feat_list.append(temp_feat_dict)

            # get driver to write to memory
            memory_driver = ogr.GetDriverByName('Memory')
            temp_datasource = memory_driver.CreateDataSource('out')
            temp_layer = temp_datasource.CreateLayer('temp_layer',
                                                     srs=self.spref,
                                                     geom_type=out_type)

            # initialize vector
            temp_vector = Vector()

            # update features and crs
            temp_vector.nfeat = len(out_feat_list)
            temp_vector.type = out_type
            temp_vector.crs = self.spref
            temp_vector.spref = self.spref
            temp_vector.layer = temp_layer
            temp_vector.data_source = temp_datasource
            temp_vector.wkt_list = list()

            # create field in layer
            for field in field_defs:
                res = temp_layer.CreateField(field)
                temp_vector.fields.append(field)

            temp_layer_definition = temp_layer.GetLayerDefn()

            # create new features using geometry
            for out_feat in out_feat_list:

                # add geometry and attributes
                temp_feature = ogr.Feature(temp_layer_definition)
                temp_feature.SetGeometry(out_feat['geom'])

                for field_name, field_val in out_feat['attr'].items():
                    temp_feature.SetField(field_name,
                                          field_val)

                # create feature in layer
                temp_layer.CreateFeature(temp_feature)

                temp_vector.features.append(temp_feature)
                temp_vector.wkt_list.append(out_feat['geom'].ExportToWkt())

            return temp_vector

    @classmethod
    def vector_from_string(cls,
                           geom_strings,
                           geom_string_type='wkt',
                           spref=None,
                           spref_string=None,
                           spref_string_type='wkt',
                           vector_type=None,
                           out_epsg=4326,
                           attributes=None,
                           attribute_types=None,
                           verbose=False):
        """
        Make a vector object from a list of geometries in string (json, wkt, or wkb) format.
        :param geom_strings: Single or a list of geometries in WKT format
        :param geom_string_type: Geometry string type (e.g. 'wkt', 'json', 'wkb'; default: 'wkt)
        :param spref: OSR Spatial reference object
        :param spref_string: WKT representation of the spatial reference for the Vector object
        :param spref_string_type: Spatial reference string type (e.g. 'wkt', 'proj4', 'epsg'; default: 'wkt)
        :param vector_type: Type of vector geometry (e.g. 'point','polygon','multipolygon','line'; default: 'polygon')
        :param out_epsg: EPSG SRID for the geometry object
        :param attributes: Dictionary or list of dictionaries of feature attributes.
                           The 'key' names in this list of dicts should match exactly with attribute_types
        :param attribute_types: Dictionary of feature attribute names with their OGR datatypes.
                                This is the attribute definition dictionary.
                                This dictionary must match the 'attributes'.
        :return: Vector object
        """

        vector = cls()

        if verbose:
            print('Creating Vector...')

        if type(geom_strings).__name__ == 'str':
            vector.nfeat = 1
        elif type(geom_strings).__name__ == 'list':
            vector.nfeat = len(geom_strings)
        else:
            raise ValueError('Number of features not attributable')

        if type(geom_strings).__name__ != 'list':
            geom_strings = [geom_strings]

        if attributes is not None:
            if type(attributes).__name__ != 'list':
                attributes = [attributes]

        if geom_string_type == 'wkt':
            geoms = list(ogr.CreateGeometryFromWkt(geom_string) for geom_string in geom_strings)
        elif geom_string_type == 'json':
            geoms = list(ogr.CreateGeometryFromJson(geom_string) for geom_string in geom_strings)
        elif geom_string_type == 'wkb':
            geoms = list(ogr.CreateGeometryFromWkb(geom_string) for geom_string in geom_strings)
        else:
            raise TypeError("Unsupported geometry type")

        if spref is None:
            spref = osr.SpatialReference()

            if spref_string is not None:
                if spref_string_type == 'wkt':
                    res = spref.ImportFromWkt(spref_string)
                elif spref_string_type == 'proj4':
                    res = spref.ImportFromProj4(spref_string)
                elif spref_string_type == 'epsg':
                    res = spref.ImportFromEPSG(spref_string)
                else:
                    raise RuntimeError("No spatial reference")
            else:
                res = spref.ImportFromEPSG(out_epsg)

        vector.spref = spref

        # get driver to write to memory
        memory_driver = ogr.GetDriverByName('Memory')
        temp_datasource = memory_driver.CreateDataSource('out')
        vector.data_source = temp_datasource

        if vector_type is None:
            geom_type = geoms[0].GetGeometryType()
        elif type(vector_type).__name__ == 'str':
            geom_type = OGR_TYPE_DEF[vector_type]
        elif type(vector_type).__name__ == 'int' or \
                type(vector_type).__name__ == 'long':
            geom_type = vector_type
        else:
            raise ValueError("Invalid geometry type")

        vector.type = geom_type

        # create layer in memory
        temp_layer = temp_datasource.CreateLayer('temp_layer',
                                                 srs=spref,
                                                 geom_type=geom_type)
        vector.layer = temp_layer
        vector.fields = list()
        vector.attribute_def = attribute_types

        if (attributes is not None) != (attribute_types is not None):
            raise RuntimeError('One of attribute values or attribute definitions is missing')
        elif attributes is not None and attribute_types is not None:
            for attr_name, attr_val in attributes[0].items():
                if attr_name not in attribute_types:
                    raise RuntimeError('Attribute values supplied for undefined attributes')
        else:
            attribute_types = {'GeomID': 'int'}
            attributes = list({'GeomID': i} for i in range(0, len(geom_strings)))

        # create the attribute fields in the layer
        for attr_name, attr_type in attribute_types.items():
            fielddefn = ogr.FieldDefn(attr_name, OGR_FIELD_DEF[attr_type])
            vector.fields.append(fielddefn)
            res = temp_layer.CreateField(fielddefn)

        # layer definition with new fields
        temp_layer_definition = temp_layer.GetLayerDefn()
        vector.wktlist = list()
        vector.attributes = attributes

        if verbose:
            print('Adding geometries...\n')

        for i, geom in enumerate(geoms):
            # create new feature using geometry
            temp_feature = ogr.Feature(temp_layer_definition)
            temp_feature.SetGeometry(geom)

            if verbose:
                print('geometry {} of {}'.format(str(i+1),
                                                 str(len(geoms))))

            # copy attributes to each feature, the order is the order of features
            for attribute in attributes:
                for attrname, attrval in attribute.items():
                    temp_feature.SetField(attrname, attrval)

            # create feature in layer
            temp_layer.CreateFeature(temp_feature)

            vector.features.append(temp_feature)
            vector.wktlist.append(geom.ExportToWkt())

        return vector

    @staticmethod
    def polygon_bound_grid(coords_list,
                           div=10,
                           intersect_check=False):

        """
        Method to get square grid intersecting a polygon
        This function only accepts a list of coordinates: [[x1,y1],[x2,y2],...]
        :param coords_list: list of coordinates: [[x1,y1],[x2,y2],...]
        :param div: Number of divisions along x or y (default: 10)
        :param intersect_check: If only the intersecting coordinates should be returned
        :return: List of list of coordinates (square)
        """

        temp_coords_list = Opt.__copy__(coords_list)

        if temp_coords_list[-1][0] != temp_coords_list[0][0] or temp_coords_list[-1][1] != temp_coords_list[0][1]:
            temp_coords_list.append(temp_coords_list[0])

        bounds_wkt = Vector.wkt_from_coords(temp_coords_list,
                                            geom_type='polygon')
        bounds_geom = Vector.get_osgeo_geom(bounds_wkt)

        bounds_maxx = max(list(coord[0] for coord in temp_coords_list))
        bounds_minx = min(list(coord[0] for coord in temp_coords_list))
        bounds_maxy = max(list(coord[1] for coord in temp_coords_list))
        bounds_miny = min(list(coord[1] for coord in temp_coords_list))

        xcoords = Sublist.frange(bounds_minx, bounds_maxx, div=div)
        ycoords = Sublist.frange(bounds_miny, bounds_maxy, div=div).reverse()

        geom_list = list()

        for i in range(len(xcoords) - 1):
            for j in range(len(ycoords) - 1):
                geom_list.append([[xcoords[i], ycoords[j]],
                                  [xcoords[i + 1], ycoords[j]],
                                  [xcoords[i + 1], ycoords[j + 1]],
                                  [xcoords[i], ycoords[j + 1]],
                                  [xcoords[i], ycoords[j]]])

        if intersect_check:
            wkt_list = list(Vector.wkt_from_coords(geom_coords, geom_type='polygon')
                            for geom_coords in geom_list)

            index = list()

            for i, geom_wkt in enumerate(wkt_list):
                temp_geom = Vector.get_osgeo_geom(geom_wkt)
                if temp_geom.Intersects(bounds_geom):
                    index.append(i)

            return list(geom_list[i] for i in index)

        else:
            return geom_list

    def rasterize(self,
                  outfile=None,
                  pixel_size=None,
                  out_type=gdal.GDT_Byte,
                  nodatavalue=0,
                  extent=None):

        """
        Method to rasterize a vector layer
        :param outfile: Output file name
        :param pixel_size: Pixel size (x, y) in spatial ref units
        :param out_type: Output data type: gdal.GDT_Byte or 1, etc.
        :param nodatavalue: No data Value
        :param extent: Extent in spatial ref units (x_min, x_max, y_min, y_max)
        :return: None
        """

        if pixel_size is None:
            pixel_size = (30, 30)

        if outfile is None:
            outfile = self.filename.split('.')[0] + '_.tif'

        if extent is None:
            x_min, x_max, y_min, y_max = self.layer.GetExtent()
        else:
            x_min, x_max, y_min, y_max = extent

        cols = int(math.ceil((x_max - x_min) / pixel_size[1]))
        rows = int(math.ceil((y_max - y_min) / pixel_size[0]))

        target_ds = gdal.GetDriverByName('GTiff').Create(outfile,
                                                         cols,
                                                         rows,
                                                         1,
                                                         out_type)

        target_ds.SetGeoTransform((x_min,
                                  pixel_size[0],
                                  0,
                                  y_max,
                                  0,
                                  -1.0*pixel_size[1]))

        target_ds_srs = self.spref
        target_ds.SetProjection(target_ds_srs.ExportToWkt())

        band = target_ds.GetRasterBand(1)
        band.SetNoDataValue(nodatavalue)

        gdal.RasterizeLayer(target_ds,
                            [1],
                            self.layer,
                            None,
                            None,
                            [1],
                            ['ALL_TOUCHED=TRUE'])

        target_ds = None

    @staticmethod
    def partition_bounds(coords,
                         nparts=5,
                         part='vert'):
        """
        partition a bounds rectangle vertically or horizontally
        :param coords: input bound coordinates list of (x,y)
        :param nparts: number of partitions
        :param part: type of partition - 'vert' or 'horiz' -tally stacked parts
        :return: list of bound rectangles - subset from original
        """

        minx = min(list(coord[0] for coord in coords))
        miny = min(list(coord[1] for coord in coords))
        maxx = max(list(coord[0] for coord in coords))
        maxy = max(list(coord[1] for coord in coords))

        out_coords_list = list()

        if part == 'horiz':
            ypart_list = Sublist.frange(miny, maxy, div=nparts)
            ypart_tup = ypart_list.tuple_by_pairs()

            for tup in ypart_tup:
                coords_ = [[minx, tup[0]],
                           [minx, tup[1]],
                           [maxx, tup[1]],
                           [maxx, tup[0]],
                           [minx, tup[0]]]

                out_coords_list.append(coords_)

        if part == 'vert':
            xpart_list = Sublist.frange(minx, maxx, div=nparts)
            xpart_tup = xpart_list.tuple_by_pairs()

            for tup in xpart_tup:
                coords_ = [[tup[0], miny],
                           [tup[0], maxy],
                           [tup[1], maxy],
                           [tup[1], miny],
                           [tup[0], miny]]

                out_coords_list.append(coords_)

        return out_coords_list












