import os
import re
import json
import ebrains_drive
import numpy as np

from io import StringIO
from uuid import uuid1, UUID

class Annotation:
    annotations = {}
    drive_directory = 'Siibra annotations'

    """Create new annotation
    Parameters
    --------
    type : str
        Type of annotation 
        Choose one of ('point' | 'line' | 'polygon')
    spaceId : str
        id of corresponding space
    coordinates : list
        Coordinates points of the annotation in mm
    """

    def create(self, space_id, category=None, coordinates=None, name=None):

        if category is None or category.lower() not in ['point', 'line', 'polygon']:
            for i in range(0, 10):
                category_input = input('Please choose the category of annotation: ').lower()
                if category_input not in ['point', 'line', 'polygon']:
                    continue
                category = category_input
                break

        if coordinates is None:
            coordinates = self._input_coordinates(category)

        adding_annotation = {}

        if category == 'point':
            adding_annotation = {
                '@id': uuid1(),
                '@type': 'https://openminds.ebrains.eu/sands/CoordinatePoint',
                'coordinateSpace': {
                    '@id': space_id
                },
                'coordinates': [self._get_coord(coordinates[0] / 1e6), self._get_coord(coordinates[1] / 1e6),
                                self._get_coord(coordinates[2] / 1e6)]
            }
            if name is None:
                name = 'Unnamed point'
        elif category == 'line':
            adding_annotation = {
                '@id': uuid1(),
                '@type': "tmp/line",
                'coordinateSpace': {
                    '@id': space_id
                },
                'coordinatesFrom': [self._get_coord(coordinates[0][0] / 1e6), self._get_coord(coordinates[0][1] / 1e6),
                                    self._get_coord(coordinates[0][2] / 1e6)],
                'coordinatesTo': [self._get_coord(coordinates[1][0] / 1e6), self._get_coord(coordinates[1][1] / 1e6),
                                  self._get_coord(coordinates[1][2] / 1e6)],
            }
            if name is None:
                name = 'Unnamed line'
        elif category == 'polygon':
            adding_annotation = {
                '@id': uuid1(),
                '@type': 'tmp/poly',
                'coordinateSpace': {
                    '@id': space_id
                },
                'coordinates': [[self._get_coord(coord[0] / 1e6),
                                 self._get_coord(coord[1] / 1e6),
                                 self._get_coord(coord[2] / 1e6)] for coord in coordinates]
            }
            if name is None:
                name = 'Unnamed polygon'

        self.annotations[name] = adding_annotation
        # print(self.annotations)

        store_ann = input('Save annotation on Ebrains drive? (y/N)').lower()
        if store_ann == 'y':
            self.store_annotation(adding_annotation, category, name)

    def _input_coordinates(self, category):

        return_value = []

        if category == 'point':
            return_value = self._input_single_coord('Input  coordinates for point. [x,y,z] in mm: ')
            if not validate_coordinates('point', return_value):
                print('Point coordinates are invalid')
                return None

        if category == 'line':
            point1 = self._input_single_coord('Input first coordinates for the line. [x,y,z] in mm: ')
            point2 = self._input_single_coord('Input second coordinates for the line. [x,y,z] in mm: ')
            return_value = [point1, point2]
            if not validate_coordinates('line', return_value):
                print('Line coordinates are invalid')
                return None

        if category == 'polygon':
            first_point = self._input_single_coord('Input first coordinate for the polygon. [x,y,z] in mm: ')
            return_value.append(first_point)
            while True:
                coord = self._input_single_coord(
                    'Input next coordinate for the polygon. [x,y,z] in mm. (Enter to finish):', True)
                if coord == 'finished':
                    break
                else:
                    return_value.append(coord)
            if not validate_coordinates('polygon', return_value):
                print('Polygon coordinates are invalid')
                return None

        return return_value

    # def update(self, annotation, name):
    # """Update annotation
    # Parameters
    # --------
    # annotation : {name: annotation}
    #     Dictionary where key is the name of an annotation and value is annotation object in SANDS format
    # name : str (optional)
    #     To change annotation name
    # """

    """Remove annotation
    Parameters
    --------
    anno_id : str
        If of annotation to remove
    name : str (optional)
        Name of annotation (for removing faster)
    """

    def remove(self, anno_id, name=''):
        self.annotations = {key: val for key, val in self.annotations if val['@id'] != anno_id}
        self.remove_annotation_from_drive(anno_id, name)

    """Plot annotations
    template_id : str
        id of template to filter annotations before plot
    annotation_id : str
        id to plot single annotation
    view : boolean
        False - plot annotations on 2D view
        True - plot annotations on 3D view
    """

    def plot(self, template_id=None, annotation_id=None, view=False):

        if len(self.annotations):
            from nilearn import plotting

            coord, matrix = self._unite_annotations_for_plot(template_id, annotation_id)

            if not view:
                return plotting.plot_connectome(matrix, coord, title="Annotations")
            else:
                return plotting.view_connectome(matrix, coord, title="Annotations")

    def _unite_annotations_for_plot(self, template_id=None, annotation_id=None):

        coord = []
        matrix = []

        for ann in self.annotations.values():
            # Filter by template if id exists
            if (template_id and template_id != ann['coordinateSpace']['@id']) \
                    or (annotation_id and annotation_id != ann['@id']):
                continue

            # Append coordinates and matrix for point annotation
            if ann['@type'] == 'https://openminds.ebrains.eu/sands/CoordinatePoint':
                coord.append(tuple((p['value'] * 1e6) for p in ann['coordinates']))
                if len(matrix) > 0:
                    matrix = [item + [0] for item in matrix]
                    matrix.append([0] * (len(coord) - 1) + [1])
                else:
                    matrix = [[1]]
            # Append coordinates and matrix for line annotation
            if ann['@type'] == 'tmp/line':
                coord.append(tuple((p['value'] * 1e6) for p in ann['coordinatesFrom']))
                coord.append(tuple((p['value'] * 1e6) for p in ann['coordinatesTo']))
                if len(matrix) > 0:
                    matrix = [item + [0] * 2 for item in matrix]
                    matrix.append([0] * (len(coord) - 1) + [1, 1] + [1, 1])
                else:
                    matrix = [[1, 1], [1, 1]]
            # Append coordinates and matrix for polygon annotation
            elif ann['@type'] == 'tmp/poly':
                poly_len = len(ann['coordinates'])
                poly_matrix = np.full((poly_len, poly_len), 0).tolist()

                for i in range(poly_len):
                    if i == 0:
                        # connect second element
                        poly_matrix[0][i + 1] = 1
                        # connect last element
                        poly_matrix[0][(poly_len - 1)] = 1
                    elif 0 < i < (poly_len - 1):
                        # connect prev element
                        poly_matrix[i][i - 1] = 1
                        # connect next element
                        poly_matrix[i][i + 1] = 1
                    else:
                        # connect prev element
                        poly_matrix[i][i - 1] = 1
                        # connect first element
                        poly_matrix[i][0] = 1

                if len(matrix) > 0:
                    matrix = [item + [0] * poly_len for item in matrix]
                    for j in range(poly_len):
                        matrix.append([0] * (len(coord)) + poly_matrix[j])
                else:
                    matrix = poly_matrix

                for poly_coord in ann['coordinates']:
                    coord.append(tuple((p['value'] * 1e6) for p in poly_coord))

        return coord, matrix

    @staticmethod
    def _input_single_coord(message, cancelable=False):

        coord = []

        for i in range(0, 10):
            coord_input = input(message)
            if cancelable and coord_input.lower() in [None, '', 'q', 'quite' 'e', 'end', 'exit', 'f', 'finish', 'z']:
                return 'finished'
                break
            coord = re.findall(r"[-+]?(?:\d*\.\d+|\d+)", coord_input)
            coord = [float(i) for i in coord]
            if not validate_coordinates('point', coord):
                print("Please enter right coordinates.\nSeparate them with commas and use points for decimals")
                continue
            break
        return coord

    @staticmethod
    def _get_coord(value):
        coord = {
            '@id': uuid1(),
            '@type': 'https://openminds.ebrains.eu/core/QuantitativeValue',
            'value': value,
            'unit': {
                '@id': 'id.link/mm'
            }
        }
        return coord

    drive_ready = False
    token = None
    repo_obj = None
    annotation_dir = None

    """Load annotations from ebrains drive
    """
    def load_from_drive(self):
        if self.drive_ready is False:
            self.prepare_drive()

        anno_files = [anno for anno in self.annotation_dir.ls()
                      if isinstance(anno, ebrains_drive.files.SeafFile)]

        for file in anno_files:
            anno_file = self.repo_obj.get_file(file.path)
            anno_obj = json.loads(anno_file.get_content())
            anno_name = os.path.splitext(anno_file.name)[0]
            self.annotations[anno_name] = anno_obj

    """Store annotation on ebrains drive
    annotaion : obj
        Annotation object
    name : str
        name of annotation (will saved as filename on the browser)
    """

    def store_annotation(self, annotation, name):
        if not self.drive_ready:
            self.prepare_drive()

        annotation_file = StringIO(json.dumps(annotation, indent=4, sort_keys=True, cls=self.UUIDEncoder))
        self.annotation_dir.upload(annotation_file, f'{name}.json')

    """Remove annotation from ebrains drive
    anno_id : str
        Id of annotation
    name : str
        name of annotation (optional)
    """
    def remove_annotation_from_drive(self, anno_id, name=''):

        if self.drive_ready is False:
            self.prepare_drive()

        anno_files = [anno for anno in self.annotation_dir.ls()
                      if isinstance(anno, ebrains_drive.files.SeafFile) and name in anno.path.split('/')[-1]]

        for file in anno_files:
            anno_file = self.repo_obj.get_file(file.path)
            file_id = json.loads(anno_file.get_content())['@id']
            if anno_id == file_id:
                anno_file.delete()
                break

    def prepare_drive(self):

        if not self.token:
            self.token = input('Please enter the token to access collab drive: ')

        client = ebrains_drive.connect(token=self.token)
        list_repos = client.repos.list_repos()
        self.repo_obj = client.repos.get_repo(list_repos[0].id)

        root_dir = self.repo_obj.get_dir('/')
        if not root_dir.check_exists(self.drive_directory):
            root_dir.mkdir(self.drive_directory)

        self.annotation_dir = self.repo_obj.get_dir(f'/{self.drive_directory}')
        self.drive_ready = True

    class UUIDEncoder(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, UUID):
                return obj.hex
            return json.JSONEncoder.default(self, obj)


def validate_coordinates(category, coordinates):
    if category == 'point':
        return len(coordinates) == 3 and all(type(item) == int or float for item in coordinates)
    elif category == 'line':
        if len(coordinates) == 2:
            point_1_valid = len(coordinates[0]) == 3 and all(type(item) == int or float for item in coordinates[0])
            point_2_valid = len(coordinates[1]) == 3 and all(type(item) == int or float for item in coordinates[0])
            return point_1_valid and point_2_valid
        else:
            return False
    elif category == 'polygon':
        return len(coordinates) > 0 and all(
            (len(coord) == 3 and all(type(item) == int or float for item in coord) for coord in coordinates))
    else:
        return False
