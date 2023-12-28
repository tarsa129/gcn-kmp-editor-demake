import enum
import random
import traceback
from time import sleep
from timeit import default_timer
from io import StringIO
from collections import namedtuple
from math import sin, cos, atan2, radians, degrees, pi, tan
import json

from OpenGL.GL import *
from OpenGL.GLU import *

from PySide6 import QtCore, QtGui, QtOpenGLWidgets, QtWidgets

from helper_functions import calc_zoom_in_factor, calc_zoom_out_factor
from lib.collision import Collision
from widgets.editor_widgets import catch_exception, catch_exception_with_dialog, check_box_convex
from opengltext import draw_collision
from lib.vectors import Matrix4x4, Vector3, Line, Plane, Rotation
from lib.model_rendering import Grid, TransPlane
from gizmo import Gizmo
from lib.object_models import ObjectModels
from editor_controls import UserControl
#from lib.libpath import Paths
from lib.libkmp import KMP, ReplayCameraRoutePoint
import numpy
from editor_preview import *

ObjectSelectionEntry = namedtuple("ObjectSelectionEntry", ["obj", "pos1", "pos2", "pos3", "rotation"])

MOUSE_MODE_NONE = 0
MOUSE_MODE_MOVEWP = 1
MOUSE_MODE_ADDWP = 2
MOUSE_MODE_CONNECTWP = 3

MODE_TOPDOWN = 0
MODE_3D = 1

MKW_FRAMERATE = 59.94

with open("lib/color_coding.json", "r") as f:
    colors_json = json.load(f)
    colors_selection = colors_json["SelectionColor"]
    colors_area  = colors_json["Areas"]
    colors_replayarea = colors_json["ReplayArea"]
    colors_replaycamera = colors_json["ReplayCamera"]

with open("lib/groupedobjects.json", "r") as f:
    grouped_objects_json = json.load(f)

class SelectionQueue(list):
    def queue_selection(self, x, y, width, height, shift_pressed, do_gizmo=False):
        if do_gizmo and any(entry[-1] for entry in self):
            return
        self.append((x, y, width, height, shift_pressed, do_gizmo))

class SnappingMode(enum.Enum):
    VERTICES = 'Vertices'
    EDGE_CENTERS = 'Edge Centers'
    FACE_CENTERS = 'Face Centers'

class KMPMapViewer(QtOpenGLWidgets.QOpenGLWidget):
    mouse_clicked = QtCore.Signal(QtGui.QMouseEvent)
    entity_clicked = QtCore.Signal(QtGui.QMouseEvent, str)
    mouse_dragged = QtCore.Signal(QtGui.QMouseEvent)
    mouse_released = QtCore.Signal(QtGui.QMouseEvent)
    mouse_wheel = QtCore.Signal(QtGui.QWheelEvent)
    position_update = QtCore.Signal(tuple)
    height_update = QtCore.Signal(float)
    select_update = QtCore.Signal()
    move_points = QtCore.Signal(float, float, float)
    move_points_to = QtCore.Signal(float, float, float)
    connect_update = QtCore.Signal(int, int)
    create_waypoint = QtCore.Signal(float, float)
    create_waypoint_3d = QtCore.Signal(float, float, float)

    rotate_current = QtCore.Signal(Vector3)
    scale_current = QtCore.Signal(Vector3)


    def __init__(self, samples, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.editor = None

        # Enable multisampling by setting the number of configured samples in the surface format.
        self.samples = samples
        if self.samples > 1:
            surface_format = self.format()
            surface_format.setSamples(samples)
            self.setFormat(surface_format)

        # Secondary framebuffer (and its associated mono-sampled texture) that is used when
        # multisampling is enabled.
        self.pick_framebuffer = None
        self.pick_texture = None
        self.pick_depth_texture = None

        self._zoom_factor = 80
        self.setFocusPolicy(QtCore.Qt.ClickFocus)

        self.SIZEX = 1024#768#1024
        self.SIZEY = 1024#768#1024

        self.canvas_width, self.canvas_height = self.width(), self.height()
        self.resize(600, self.canvas_height)
        #self.setMinimumSize(QtCore.QSize(self.SIZEX, self.SIZEY))
        #self.setMaximumSize(QtCore.QSize(self.SIZEX, self.SIZEY))
        self.setObjectName("bw_map_screen")

        self.origin_x = self.SIZEX//2
        self.origin_z = self.SIZEY//2

        self.position = Vector3(0, 1000, 0)

        self.left_button_down = False
        self.mid_button_down = False
        self.right_button_down = False
        self.drag_last_pos = None

        self.selected = []
        self.selected_positions = []
        self.selected_rotations = []
        self.selected_scales = []

        self.selectionbox_start = None
        self.selectionbox_end = None

        self.visualize_cursor = None

        self.click_mode = 0

        self.level_image = None

        self.collision = None

        self.highlighttriangle = None

        self.setMouseTracking(True)

        self.level_file:KMP = None

        self.mousemode = MOUSE_MODE_NONE

        self.overlapping_wp_index = 0
        self.editorconfig = None
        self.visibility_menu = None

        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)

        self.alternative_mesh = None
        self.highlight_colltype = None
        self.cull_faces = False

        self.shift_is_pressed = False
        self.rotation_is_pressed = False

        self.last_drag_update = 0
        self.change_height_is_pressed = False
        self.last_mouse_move = None
        self.connecting_mode = False
        self.connecting_start = None
        self.connecting_rotation = None
        self.linedraw_count = 4

        self.timer = QtCore.QTimer()
        self.timer.setInterval(2)
        self.timer.timeout.connect(self.render_loop)
        self.timer.start()
        self._lastrendertime = 0
        self._lasttime = 0

        self.params2d = EditorParams()
        self.preview = None

        self._frame_invalid = False
        self._mouse_pos_changed = False

        self.MOVE_UP = 0
        self.MOVE_DOWN = 0
        self.MOVE_LEFT = 0
        self.MOVE_RIGHT = 0
        self.MOVE_FORWARD = 0
        self.MOVE_BACKWARD = 0
        self.SPEEDUP = 0

        self._wasdscrolling_speed = 1
        self._wasdscrolling_speedupfactor = 3

        self.main_model = None
        self.buffered_deltas = []

        # 3D Setup
        self.mode = MODE_TOPDOWN
        self.camera_horiz = pi*(1/2)
        self.camera_vertical = -pi*(1/4)
        self.last_move = None
        self.backgroundcolor = (255, 255, 255, 255)
        self.skycolor = (200, 200, 200, 255)
        self.fov = 75

        look_direction = Vector3(cos(self.camera_horiz), sin(self.camera_horiz),
                                 sin(self.camera_vertical))
        fac = 1.01 - abs(look_direction.z)
        self.camera_direction = Vector3(look_direction.x * fac, look_direction.y * fac,
                                        look_direction.z)

        #self.selection_queue = []
        self.selectionqueue = SelectionQueue()

        self.selectionbox_projected_start = None
        self.selectionbox_projected_end = None

        #self.selectionbox_projected_2d = None
        self.selectionbox_projected_origin = None
        self.selectionbox_projected_up = None
        self.selectionbox_projected_right = None
        self.selectionbox_projected_coords = None
        self.move_collision_plane = Plane(Vector3(0.0, 0.0, 0.0), Vector3(1.0, 0.0, 0.0), Vector3(0.0, 0.0, 1.0))

        #self.paths = Paths()
        self.usercontrol = UserControl(self)

        self.snapping_enabled = False
        self.snapping_mode = SnappingMode.VERTICES
        self.snapping_last_hash = None
        self.snapping_display_list = None

        self.additional_models = {}

        # Initialize some models
        with open("resources/gizmo.obj", "r") as f:
            self.gizmo = Gizmo.from_obj(f, rotate=True)
        self.models = ObjectModels()
        self.grid = Grid(1000000, 1000000, 10000)

        self.modelviewmatrix = None
        self.projectionmatrix = None

    @catch_exception_with_dialog
    def initializeGL(self):
        self.rotation_visualizer = glGenLists(1)
        glNewList(self.rotation_visualizer, GL_COMPILE)
        glColor4f(0.0, 0.0, 1.0, 1.0)

        glBegin(GL_LINES)
        glVertex3f(0.0, 0.0, 0.0)
        glVertex3f(0.0, 0.0, 40.0)
        glEnd()
        glEndList()

        self.models.init_gl()

        # If multisampling is enabled, a secondary mono-sampled framebuffer needs to be created, as
        # reading pixels from multisampled framebuffers is not a supported GL operation.
        if self.samples > 1:
            self.pick_framebuffer = glGenFramebuffers(1)
            self.pick_texture = glGenTextures(1)
            self.pick_depth_texture = glGenTextures(1)
            glBindFramebuffer(GL_FRAMEBUFFER, self.pick_framebuffer)
            glBindTexture(GL_TEXTURE_2D, self.pick_texture)
            glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, self.canvas_width, self.canvas_height, 0,
                         GL_RGBA, GL_UNSIGNED_BYTE, None)
            glBindTexture(GL_TEXTURE_2D, 0)
            glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D,
                                   self.pick_texture, 0)
            glBindTexture(GL_TEXTURE_2D, self.pick_depth_texture)
            glTexImage2D(GL_TEXTURE_2D, 0, GL_DEPTH_COMPONENT, self.canvas_width,
                         self.canvas_height, 0, GL_DEPTH_COMPONENT, GL_FLOAT, None)
            glBindTexture(GL_TEXTURE_2D, 0)
            glFramebufferTexture2D(GL_FRAMEBUFFER, GL_DEPTH_ATTACHMENT, GL_TEXTURE_2D,
                                   self.pick_depth_texture, 0)
            glBindFramebuffer(GL_FRAMEBUFFER, 0)

    def resizeGL(self, width, height):
        # Called upon window resizing: reinitialize the viewport.
        # update the window size
        self.canvas_width, self.canvas_height = width, height
        # paint within the whole window
        glEnable(GL_DEPTH_TEST)
        glViewport(0, 0, self.canvas_width, self.canvas_height)

        # The mono-sampled texture for the secondary framebuffer needs to be resized as well.
        if self.pick_texture is not None:
            glBindTexture(GL_TEXTURE_2D, self.pick_texture)
            glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, width, height, 0, GL_RGBA, GL_UNSIGNED_BYTE,
                         None)
            glBindTexture(GL_TEXTURE_2D, 0)
        if self.pick_depth_texture is not None:
            glBindTexture(GL_TEXTURE_2D, self.pick_depth_texture)
            glTexImage2D(GL_TEXTURE_2D, 0, GL_DEPTH_COMPONENT, width, height, 0, GL_DEPTH_COMPONENT,
                         GL_FLOAT, None)
            glBindTexture(GL_TEXTURE_2D, 0)

    @catch_exception
    def set_editorconfig(self, config):
        self.editorconfig = config
        self._wasdscrolling_speed = config.getfloat("wasdscrolling_speed")
        self._wasdscrolling_speedupfactor = config.getfloat("wasdscrolling_speedupfactor")
        backgroundcolor = config["3d_background"].split(" ")
        self.backgroundcolor = (int(backgroundcolor[0])/255.0,
                                int(backgroundcolor[1])/255.0,
                                int(backgroundcolor[2])/255.0,
                                1.0)
        self.skycolor = (
            self.backgroundcolor[0] * 0.6,
            self.backgroundcolor[1] * 0.6,
            self.backgroundcolor[2] * 0.6,
            self.backgroundcolor[3] * 0.6,
        )

    def change_from_topdown_to_3d(self):
        if self.mode == MODE_3D:
            return
        else:
            self.params2d.position = self.position.copy()
            self.params2d.zoom = self._zoom_factor

            self.mode = MODE_3D

            if self.mousemode == MOUSE_MODE_NONE:
                self.setContextMenuPolicy(QtCore.Qt.DefaultContextMenu)

            # This is necessary so that the position of the 3d camera equals the middle of the topdown view
            self.position.x += 1
            self.do_redraw()

    def change_from_3d_to_topdown(self):
        if self.mode == MODE_TOPDOWN:
            return
        else:
            self.position = self.params2d.position.copy()
            self._zoom_factor = self.params2d.zoom

            self.mode = MODE_TOPDOWN
            if self.mousemode == MOUSE_MODE_NONE:
                self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
            #self.position.x *= -1
            self.do_redraw()


    #def logic(self, delta, diff):
    #    self.dolphin.logic(self, delta, diff)

    @catch_exception
    def render_loop(self):
        now = default_timer()

        diff = now-self._lastrendertime
        timedelta = now-self._lasttime

        if self.mode == MODE_TOPDOWN:
            self.handle_arrowkey_scroll(timedelta)
        else:
            self.handle_arrowkey_scroll_3d(timedelta)

        #self.logic(timedelta, diff)

        if diff > 1 / MKW_FRAMERATE:
            if self.preview is not None:
                if self.preview.done:
                    self.preview = None
                else:
                    self.preview.advance_frame(diff)

                    self.position = self.preview.position.flip_render()
                    look_vector = self.preview.view_pos.flip_render() - self.position
                    self.camera_horiz, self.camera_vertical = look_vector.to_euler()
                    self.fov = self.preview.zoom
            else:
                self.fov = 75
            check_gizmo_hover_id = self._mouse_pos_changed and self.should_check_gizmo_hover_id()
            self._mouse_pos_changed = False

            if self._frame_invalid or check_gizmo_hover_id or self.preview is not None:
                self.update()
                self._lastrendertime = now
                self._frame_invalid = False
        self._lasttime = now

    def should_check_gizmo_hover_id(self):
        if self.gizmo.hidden or self.gizmo.was_hit_at_all:
            return False

        return (not QtWidgets.QApplication.mouseButtons()
                and not QtWidgets.QApplication.keyboardModifiers())

    def toggle_snapping(self):
        self.snapping_enabled = not self.snapping_enabled
        self.do_redraw()

    def cycle_snapping_mode(self):
        self.snapping_enabled = True
        mode_names = [mode.name for mode in SnappingMode]
        index = mode_names.index(self.snapping_mode.name)
        next_index = (index + 1) % len(SnappingMode)
        self.snapping_mode = SnappingMode[mode_names[next_index]]
        self.do_redraw()

    def set_snapping_mode(self, snapping_mode):
        if isinstance(snapping_mode, SnappingMode):
            self.snapping_mode = snapping_mode
            self.snapping_enabled = True
        elif snapping_mode in [mode.name for mode in SnappingMode]:
            self.snapping_mode = SnappingMode[snapping_mode]
            self.snapping_enabled = True
        elif snapping_mode in [mode.value for mode in SnappingMode]:
            for mode in SnappingMode:
                if mode.value == snapping_mode:
                    self.snapping_mode = mode
                    break
            self.snapping_enabled = True
        else:
            self.snapping_enabled = False
        self.do_redraw()

    def _get_snapping_points(self):
        if self.snapping_mode == SnappingMode.EDGE_CENTERS:
            return self.collision.get_edge_centers()
        if self.snapping_mode == SnappingMode.FACE_CENTERS:
            return self.collision.get_face_centers()
        return self.collision.get_vertices()

    def handle_arrowkey_scroll(self, timedelta):
        if self.selectionbox_projected_coords is not None:
            return

        diff_x = diff_y = 0
        speedup = 1

        if self.shift_is_pressed:
            speedup = self._wasdscrolling_speedupfactor

        if self.MOVE_FORWARD == 1 and self.MOVE_BACKWARD == 1:
            diff_y = 0
        elif self.MOVE_FORWARD == 1:
            diff_y = 1*speedup*self._wasdscrolling_speed*timedelta
        elif self.MOVE_BACKWARD == 1:
            diff_y = -1*speedup*self._wasdscrolling_speed*timedelta

        if self.MOVE_LEFT == 1 and self.MOVE_RIGHT == 1:
            diff_x = 0
        elif self.MOVE_LEFT == 1:
            diff_x = 1*speedup*self._wasdscrolling_speed*timedelta
        elif self.MOVE_RIGHT == 1:
            diff_x = -1*speedup*self._wasdscrolling_speed*timedelta

        if diff_x != 0 or diff_y != 0:
            if self.zoom_factor > 1.0:
                self.position.x += diff_x * (1.0 + (self.zoom_factor - 1.0) / 2.0)
                self.position.z += diff_y * (1.0 + (self.zoom_factor - 1.0) / 2.0)
            else:
                self.position.x += diff_x
                self.position.z += diff_y
            # self.update()

            self.do_redraw()

    def handle_arrowkey_scroll_3d(self, timedelta):
        if self.selectionbox_projected_coords is not None:
            return

        diff_x = diff_y = diff_height = 0
        speedup = 1

        forward_vec = Vector3(cos(self.camera_horiz), sin(self.camera_horiz), 0)
        sideways_vec = Vector3(sin(self.camera_horiz), -cos(self.camera_horiz), 0)

        if self.shift_is_pressed:
            speedup = self._wasdscrolling_speedupfactor

        if self.MOVE_FORWARD == 1 and self.MOVE_BACKWARD == 1:
            forward_move = forward_vec*0
        elif self.MOVE_FORWARD == 1:
            forward_move = forward_vec*(1*speedup*self._wasdscrolling_speed*timedelta)
        elif self.MOVE_BACKWARD == 1:
            forward_move = forward_vec*(-1*speedup*self._wasdscrolling_speed*timedelta)
        else:
            forward_move = forward_vec*0

        if self.MOVE_LEFT == 1 and self.MOVE_RIGHT == 1:
            sideways_move = sideways_vec*0
        elif self.MOVE_LEFT == 1:
            sideways_move = sideways_vec*(-1*speedup*self._wasdscrolling_speed*timedelta)
        elif self.MOVE_RIGHT == 1:
            sideways_move = sideways_vec*(1*speedup*self._wasdscrolling_speed*timedelta)
        else:
            sideways_move = sideways_vec*0

        if self.MOVE_UP == 1 and self.MOVE_DOWN == 1:
            diff_height = 0
        elif self.MOVE_UP == 1:
            diff_height = 1*speedup*self._wasdscrolling_speed*timedelta
        elif self.MOVE_DOWN == 1:
            diff_height = -1 * speedup * self._wasdscrolling_speed * timedelta

        if not forward_move.is_zero() or not sideways_move.is_zero() or diff_height != 0:
            self.position.x += (forward_move.x + sideways_move.x)
            self.position.z += (forward_move.y + sideways_move.y)
            self.position.y += diff_height
            self.do_redraw()

    def set_arrowkey_movement(self, up, down, left, right):
        self.MOVE_UP = up
        self.MOVE_DOWN = down
        self.MOVE_LEFT = left
        self.MOVE_RIGHT = right

    def do_redraw(self, force=False):
        self._frame_invalid = True
        if force:
            self._lastrendertime = 0
            self.update()

    def reset(self, keep_collision=False):
        self.highlight_colltype = None
        self.overlapping_wp_index = 0
        self.shift_is_pressed = False
        self.SIZEX = 1024
        self.SIZEY = 1024
        self.origin_x = self.SIZEX//2
        self.origin_z = self.SIZEY//2
        self.last_drag_update = 0

        self.left_button_down = False
        self.mid_button_down = False
        self.right_button_down = False
        self.drag_last_pos = None

        self.selectionbox_start = None
        self.selectionbox_end = None

        self.selected = []

        if not keep_collision:
            # Potentially: Clear collision object too?
            self.level_image = None
            self.position = Vector3(0, self.position.y, 0)
            self._zoom_factor = 80

        self.mousemode = MOUSE_MODE_NONE
        self.rotation_is_pressed = False
        self.connecting_mode = False
        self.connecting_start = None
        self.additional_models = {}

        self._frame_invalid = False
        self._mouse_pos_changed = False

        self.MOVE_UP = 0
        self.MOVE_DOWN = 0
        self.MOVE_LEFT = 0
        self.MOVE_RIGHT = 0
        self.SPEEDUP = 0

    def set_collision(self, faces, alternative_mesh):
        self.collision = Collision(faces)
        additional_collision = {}
        for mapobject in self.level_file.objects:
            kcl_name = mapobject.get_kcl_name()
            if kcl_name is None:
                continue
            if kcl_name not in self.additional_models.keys():
                collision_model = MapObjectModel(kcl_name, self.editor.read_kcl_file).collision
                if collision_model is None:
                    continue
                additional_collision[mapobject] = collision_model
        self.collision.obj_meshes = additional_collision

        if self.main_model is None:
            self.main_model = glGenLists(1)

        self.alternative_mesh = alternative_mesh

        glNewList(self.main_model, GL_COMPILE)
        #glBegin(GL_TRIANGLES)
        draw_collision(faces)
        #glEnd()
        glEndList()

    def set_mouse_mode(self, mode):
        assert mode in (MOUSE_MODE_NONE, MOUSE_MODE_ADDWP, MOUSE_MODE_CONNECTWP, MOUSE_MODE_MOVEWP)

        self.mousemode = mode

        if self.mousemode == MOUSE_MODE_NONE and self.mode == MODE_TOPDOWN:
            self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        else:
            self.setContextMenuPolicy(QtCore.Qt.DefaultContextMenu)

        cursor_shape = QtCore.Qt.ArrowCursor if mode == MOUSE_MODE_NONE else QtCore.Qt.CrossCursor
        self.setCursor(cursor_shape)

    @property
    def zoom_factor(self):
        return self._zoom_factor/10.0

    def zoom(self, fac):
        if self._zoom_factor <= 60:
            mult = 20.0
        elif self._zoom_factor >= 600:
            mult = 100.0
        else:
            mult = 40.0

        if 10 < (self._zoom_factor + fac*mult):
            self._zoom_factor += int(fac*mult)
            #self.update()
            self.do_redraw()

    def mouse_coord_to_world_coord(self, mouse_x, mouse_y):
        zf = self.zoom_factor
        width, height = self.canvas_width, self.canvas_height
        camera_width = width * zf
        camera_height = height * zf

        topleft_x = -camera_width / 2 - self.position.x
        topleft_y = camera_height / 2 + self.position.z

        relx = mouse_x / width
        rely = mouse_y / height
        res = (topleft_x + relx*camera_width, topleft_y - rely*camera_height)

        return res

    def mouse_coord_to_world_coord_transform(self, mouse_x, mouse_y):
        mat4x4 = Matrix4x4.from_opengl_matrix(*glGetFloatv(GL_PROJECTION_MATRIX))
        width, height = self.canvas_width, self.canvas_height
        result = mat4x4.multiply_vec4(mouse_x-width/2, 0, mouse_y-height/2, 1)

        return result

    #@catch_exception_with_dialog
    #@catch_exception
    def paintGL(self):
        offset_x = self.position.x
        offset_z = self.position.z

        glClearColor(1.0, 1.0, 1.0, 0.0)
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        width, height = self.canvas_width, self.canvas_height

        if self.mode == MODE_TOPDOWN:
            glMatrixMode(GL_PROJECTION)
            glLoadIdentity()
            zf = self.zoom_factor
            #glOrtho(-6000.0, 6000.0, -6000.0, 6000.0, -3000.0, 2000.0)
            camera_width = width*zf
            camera_height = height*zf

            glOrtho(-camera_width / 2 - offset_x, camera_width / 2 - offset_x, -camera_height / 2 + offset_z, camera_height / 2 + offset_z, -120000.0, 80000.0 )
            #glOrtho(-camera_width / 2 - offset_x, camera_width / 2 - offset_x, -120000.0, 80000.0, -camera_height / 2 + offset_z, camera_height / 2 + offset_z,  )

            glMatrixMode(GL_MODELVIEW)
            glLoadIdentity()
        else:
            #glEnable(GL_CULL_FACE)
            # set yellow color for subsequent drawing rendering calls

            glMatrixMode(GL_PROJECTION)
            glLoadIdentity()
            gluPerspective(self.fov, width / height, 256.0, 160000.0)

            glMatrixMode(GL_MODELVIEW)
            glLoadIdentity()
            look_direction = Vector3(cos(self.camera_horiz), sin(self.camera_horiz), sin(self.camera_vertical))
            # look_direction.unify()
            fac = 1.01 - abs(look_direction.z)

            gluLookAt(self.position.x, self.position.z, self.position.y,
                      self.position.x + look_direction.x * fac, self.position.z + look_direction.y * fac,
                      self.position.y + look_direction.z,
                      0, 0, 1)

            self.camera_direction = Vector3(look_direction.x * fac, look_direction.y * fac, look_direction.z)


        self.modelviewmatrix = numpy.transpose(numpy.reshape(glGetFloatv(GL_MODELVIEW_MATRIX), (4,4)))
        self.projectionmatrix = numpy.transpose(numpy.reshape(glGetFloatv(GL_PROJECTION_MATRIX), (4,4)))
        self.mvp_mat = numpy.dot(self.projectionmatrix, self.modelviewmatrix)
        self.modelviewmatrix_inv = numpy.linalg.inv(self.modelviewmatrix)

        campos = Vector3(self.position.x, self.position.y, -self.position.z)
        self.campos = campos

        vismenu: FilterViewMenu = self.visibility_menu

        if self.mode == MODE_TOPDOWN:
            gizmo_scale = 3*zf
        else:
            gizmo_scale = (self.gizmo.position - campos).norm() / 130.0


        self.gizmo_scale = gizmo_scale
        if self.editor.scale_points.isChecked() and self.mode == MODE_TOPDOWN:
            point_scale = Vector3(gizmo_scale/64, gizmo_scale/64, gizmo_scale/64)
        else:
            point_scale = Vector3(1, 1, 1)

        SPHERE_UNITS = 300 * point_scale.x

        check_gizmo_hover_id = self.should_check_gizmo_hover_id()

        # If multisampling is enabled, the draw/read operations need to happen on the mono-sampled
        # framebuffer.
        use_pick_framebuffer = (self.selectionqueue or check_gizmo_hover_id) and self.samples > 1
        if use_pick_framebuffer:
            glBindFramebuffer(GL_FRAMEBUFFER, self.pick_framebuffer)
            glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        gizmo_hover_id = 0xFF
        if not self.selectionqueue and check_gizmo_hover_id:
            self.gizmo.render_collision_check(gizmo_scale, is3d=self.mode == MODE_3D)
            mouse_pos = self.mapFromGlobal(QtGui.QCursor.pos())
            pixels = glReadPixels(mouse_pos.x(), self.canvas_height - mouse_pos.y(), 1, 1, GL_RGB, GL_UNSIGNED_BYTE)
            gizmo_hover_id = pixels[2]

        objectroutes = self.level_file.objects.get_routes()
        cameraroutes = self.level_file.cameras.get_routes()
        replaycameraroutes = self.level_file.replayareas.get_routes()
        arearoutes = self.level_file.areas.get_routes()

        replaycameras = self.level_file.replayareas.get_cameras()

        vismenu: FilterViewMenu = self.visibility_menu

        if self.selectionqueue:
            glClearColor(1.0, 1.0, 1.0, 1.0)
            glDisable(GL_TEXTURE_2D)


        while len(self.selectionqueue) > 0:
            click_x, click_y, clickwidth, clickheight, shiftpressed, do_gizmo = self.selectionqueue.pop()
            click_y = height - click_y

            # Clamp to viewport dimensions.
            if click_x < 0:
                clickwidth += click_x
                click_x = 0
            if click_y < 0:
                clickheight += click_y
                click_y = 0
            clickwidth = max(0, min(clickwidth, width - click_x))
            clickheight = max(0, min(clickheight, height - click_y))
            if not clickwidth or not clickheight:
                continue

            if do_gizmo and clickwidth == 1 and clickheight == 1:
                glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

                self.gizmo.render_collision_check(gizmo_scale, is3d=self.mode == MODE_3D)
                pixels = glReadPixels(click_x, click_y, clickwidth, clickheight, GL_RGB, GL_UNSIGNED_BYTE)

                hit = pixels[2]
                if hit != 0xFF:
                    self.gizmo.run_callback(hit)
                    self.gizmo.was_hit_at_all = True


                    # Clear the potential marquee selection, which may have been just created as a
                    # result of a mouse move event that was processed slightly earlier than this
                    # current paint event.
                    self.selectionbox_start = self.selectionbox_end = None
                    self.selectionbox_projected_origin = self.selectionbox_projected_coords = None


                    self.selectionqueue.clear()
                    break
                continue

            selected = {}
            selected_positions = []
            selected_rotations = []

            continue_picking = not do_gizmo
            while continue_picking:
                glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

                id = 0x100000

                objlist = []
                offset = 0

                #self.dolphin.render_collision(self, objlist)

                if vismenu.enemyroutes.is_selectable():
                    for i, obj in enumerate(obj for obj in self.level_file.enemypointgroups.points() if obj not in selected):
                        objlist.append(
                            ObjectSelectionEntry(obj=obj,
                                                 pos1=obj.position,
                                                 pos2=None,
                                                 pos3=None,
                                                 rotation=None)
                        )
                        self.models.render_generic_position_colored_id(obj.position, id + (offset+i) * 4, point_scale)

                    offset = len(objlist)

                if vismenu.itemroutes.is_selectable():
                    for i, obj in enumerate(obj for obj in self.level_file.itempointgroups.points() if obj not in selected):
                        objlist.append(
                            ObjectSelectionEntry(obj=obj,
                                                 pos1=obj.position,
                                                 pos2=None,
                                                 pos3=None,
                                                 rotation=None)
                        )
                        self.models.render_generic_position_colored_id(obj.position, id + (offset+i) * 4, point_scale)

                    offset = len(objlist)

                if vismenu.objects.is_selectable(): #object routes
                    i = 0
                    for route in objectroutes:
                        for obj in route.points:
                            if obj in selected:
                                continue
                            objlist.append(
                                ObjectSelectionEntry(obj=obj,
                                                 pos1=obj.position,
                                                 pos2=None,
                                                 pos3=None,
                                                 rotation=None))
                            self.models.render_generic_position_colored_id(obj.position, id + (offset+i) * 4, point_scale)
                            i += 1
                    offset = len(objlist)

                if vismenu.objects.is_selectable(): #object routes
                    for i, obj in enumerate(obj for obj in self.level_file.objects if obj not in selected):
                        objlist.append(
                            ObjectSelectionEntry(obj=obj,
                                                pos1=obj.position,
                                                pos2=None,
                                                pos3=None,
                                                rotation=obj.rotation))
                        object_scale = point_scale.scale_vec(obj.scale)
                        self.models.render_generic_position_rotation_colored_id(obj.position, obj.rotation, id + (offset+i) * 4, object_scale)
                        i += 1
                    offset = len(objlist)

                if vismenu.cameras.is_selectable():
                    for i, obj in enumerate(obj for obj in self.level_file.cameras if obj not in selected):
                        objlist.append(
                            ObjectSelectionEntry(obj=obj,
                                                    pos1=obj.position,
                                                    pos2=obj.position2_simple,
                                                    pos3=obj.position3_simple,
                                                    rotation=None))
                        self.models.render_generic_position_colored_id(obj.position,
                                                                                id + (offset + i) * 4, point_scale)
                        self.models.render_generic_position_colored_id(obj.position2_simple, id + (offset + i) * 4 + 1, point_scale)
                        self.models.render_generic_position_colored_id(obj.position3_simple, id + (offset + i) * 4 + 2, point_scale)

                    offset = len(objlist)

                if vismenu.cameras.is_selectable(): #camera routes
                    i = 0
                    for route in cameraroutes:
                        for obj in route.points[1:]:
                            if obj in selected:
                                continue
                            objlist.append(
                                ObjectSelectionEntry(obj=obj,
                                                 pos1=obj.position,
                                                 pos2=None,
                                                 pos3=None,
                                                 rotation=None))
                            self.models.render_generic_position_colored_id(obj.position, id + (offset+i) * 4, point_scale)
                            i += 1

                    offset = len(objlist)

                if vismenu.replaycameras.is_selectable(): #routes
                    i = 0
                    for route in replaycameraroutes:
                        for obj in route.points[1:]:
                            if obj in selected:
                                continue
                            pos = obj.position.render()
                            objlist.append(
                                ObjectSelectionEntry(obj=obj,
                                                 pos1=pos,
                                                 pos2=None,
                                                 pos3=None,
                                                 rotation=None))
                            self.models.render_generic_position_colored_id(pos, id + (offset+i) * 4, point_scale)
                            i += 1

                    offset = len(objlist)

                if vismenu.replaycameras.is_selectable():
                    for i, obj in enumerate(obj for obj in replaycameras if obj not in selected):
                        pos1 = obj.position
                        pos2 = None
                        pos3 = None
                        if (obj.type == 1 and not obj.follow_player) or obj.type == 3:
                            pos2 = obj.position2_simple.render()
                            pos3 = obj.position3_simple.render()
                        if obj.type == 3:
                            pos1 = obj.position.render()
                            pos2 = obj.position2_player.render()
                            pos3 = obj.position3_player.render()
                        objlist.append( ObjectSelectionEntry(obj=obj,
                                                    pos1=pos1,
                                                    pos2=pos2,
                                                    pos3=pos3,
                                                    rotation=None))
                        self.models.render_generic_position_colored_id(pos1, id + (offset + i) * 4, point_scale)
                        if pos2 is not None:
                             self.models.render_generic_position_colored_id(pos2, id + (offset + i) * 4 + 1, point_scale)
                        if pos3 is not None:
                            self.models.render_generic_position_colored_id(pos3, id + (offset + i) * 4 + 2, point_scale)

                    offset = len(objlist)

                if vismenu.areas.is_selectable():

                    i = 0
                    for route in arearoutes:
                        for obj in [point for point in  route.points if point not in selected]:
                            objlist.append(
                                ObjectSelectionEntry(obj=obj,
                                                 pos1=obj.position,
                                                 pos2=None,
                                                 pos3=None,
                                                 rotation=None))
                            self.models.render_generic_position_colored_id(obj.position, id + (offset+i) * 4, point_scale)
                            i += 1

                    offset = len(objlist)

                if vismenu.checkpoints.is_selectable():
                    for i, obj in enumerate(obj for obj in self.level_file.objects_with_2positions() if obj not in selected):
                        objlist.append(
                            ObjectSelectionEntry(obj=obj,
                                             pos1=obj.start,
                                             pos2=obj.end,
                                             pos3=None,
                                             rotation=None))
                        self.models.render_generic_position_colored_id(obj.start, id+(offset+i)*4, point_scale)
                        self.models.render_generic_position_colored_id(obj.end, id+(offset+i)*4 + 1, point_scale)
                    offset = len(objlist)

                for is_selectable, collection in (
                        (vismenu.kartstartpoints.is_selectable(), self.level_file.kartpoints),
                        (vismenu.areas.is_selectable(), self.level_file.areas),
                        (vismenu.objects.is_selectable(), self.level_file.objects.areas),
                        (vismenu.replaycameras.is_selectable(), self.level_file.replayareas),
                        (vismenu.respawnpoints.is_selectable(), self.level_file.respawnpoints),
                        (vismenu.cannonpoints.is_selectable(), self.level_file.cannonpoints),
                        (vismenu.missionsuccesspoints.is_selectable(), self.level_file.missionpoints)

                        ):
                    if not is_selectable:
                        continue

                    for i, obj in enumerate(obj for obj in collection if obj not in selected):
                        objlist.append(
                            ObjectSelectionEntry(obj=obj,
                                                 pos1=obj.position,
                                                 pos2=None,
                                                 pos3=None,
                                                 rotation=obj.rotation))
                        self.models.render_generic_position_rotation_colored_id(obj.position, obj.rotation,
                                                                                id + (offset + i) * 4, point_scale)
                    offset = len(objlist)

                pixels = glReadPixels(click_x, click_y, clickwidth, clickheight, GL_RGB, GL_UNSIGNED_BYTE)

                indexes = set()
                for i in range(0, clickwidth * clickheight):
                    if pixels[i * 3] != 0xFF:
                        upper = pixels[i * 3] & 0x0F
                        index = (upper << 16) | (pixels[i * 3 + 1] << 8) | pixels[i * 3 + 2]
                        indexes.add(index)

                for index in indexes:
                    entry: ObjectSelectionEntry = objlist[index // 4]
                    obj = entry.obj
                    if obj not in selected:
                        selected[obj] = 0

                    elements_exist = selected[obj]

                    if index & 0b11 == 0:  # First object position
                        if entry.pos1 is not None and (elements_exist & 1) == 0:
                            selected_positions.append(entry.pos1.get_base())
                            if entry.rotation is not None:
                                selected_rotations.append(entry.rotation)
                            elements_exist |= 1
                    if index & 0b11 == 1:  # Second object position
                        if entry.pos2 is not None and (elements_exist & 2) == 0:
                            selected_positions.append(entry.pos2.get_base())
                            elements_exist |= 2
                    if index & 0b11 == 2:  # Third object position
                        if entry.pos3 is not None and (elements_exist & 4) == 0:
                            selected_positions.append(entry.pos3.get_base())
                            elements_exist |= 4

                    selected[obj] = elements_exist

                continue_picking = (clickwidth > 1 or clickheight > 1) and indexes

            selected = list(selected)
            if not shiftpressed:
                self.selected = selected
                self.selected_positions = selected_positions
                self.selected_rotations = selected_rotations

            else:
                for obj in selected:
                    if obj not in self.selected:
                        self.selected.append(obj)
                for pos in selected_positions:
                    if pos not in self.selected_positions:
                        self.selected_positions.append(pos)

                for rot in selected_rotations:
                    if rot not in self.selected_rotations:
                        self.selected_rotations.append(rot)
            # Store selection in a logical order that matches the order of the objects in their
            # respective groups. This is relevant to ensure that potentially copied, route-like
            # objects, where order matters, are pasted in the same order.
            # Objects that are not part of the BOL document are kept at the end of the list in
            # the same initial, arbitrary pick order.
            selected = self.selected
            self.selected = []
            selected_set = set(selected)
            for obj in self.level_file.get_all_objects():
                if obj in selected_set:
                    self.selected.append(obj)
                    selected_set.remove(obj)
            for obj in selected:
                if obj in selected_set:
                    self.selected.append(obj)

            self.editor.select_from_3d_to_treeview()

            self.editor.on_document_potentially_changed(update_unsaved_changes=False)

            self.gizmo.move_to_average(self.selected, self.selected_positions)
            if len(selected) == 0:
                self.gizmo.hidden = True

            self.select_update.emit()

            if self.mode == MODE_3D: # In case of 3D mode we need to update scale due to changed gizmo position
                gizmo_scale = (self.gizmo.position - campos).norm() / 130.0

        # Restore the default framebuffer of the GL widget.
        if use_pick_framebuffer:
            glBindFramebuffer(GL_FRAMEBUFFER, self.defaultFramebufferObject())


        #glClearColor(1.0, 1.0, 1.0, 0.0)
        glClearColor(*(self.backgroundcolor if self.mode == MODE_TOPDOWN else self.skycolor))
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

        glEnable(GL_DEPTH_TEST)
        glDisable(GL_TEXTURE_2D)
        glColor4f(1.0, 1.0, 1.0, 1.0)
        if self.main_model is not None:
            if self.alternative_mesh is None:
                glCallList(self.main_model)
            else:
                if self.mode != MODE_TOPDOWN:
                    light0_position = (campos.x, -campos.z, campos.y, 1.0)
                    light0_diffuse = (5.0, 5.0, 5.0, 1.0)
                    light0_specular = (0.8, 0.8, 0.8, 1.0)
                    light0_ambient = (1.8, 1.8, 1.8, 1.0)
                    glLightfv(GL_LIGHT0, GL_POSITION, light0_position)
                    glLightfv(GL_LIGHT0, GL_DIFFUSE, light0_diffuse)
                    glLightfv(GL_LIGHT0, GL_DIFFUSE, light0_specular)
                    glLightfv(GL_LIGHT0, GL_AMBIENT, light0_ambient)
                    glShadeModel(GL_SMOOTH)
                    glEnable(GL_LIGHT0)
                    glEnable(GL_RESCALE_NORMAL)
                    glEnable(GL_NORMALIZE)
                    glEnable(GL_LIGHTING)

                glPushMatrix()
                glScalef(1.0, -1.0, 1.0)
                self.alternative_mesh.render(selectedPart=self.highlight_colltype,
                                             cull_faces=self.cull_faces)
                glPopMatrix()

                if self.mode != MODE_TOPDOWN:
                    glDisable(GL_LIGHTING)

        additional_collision = {}
        if self.visibility_menu.objects.is_visible():
            for mapobject in self.level_file.objects:
                kcl_name = mapobject.get_kcl_name()
                if kcl_name is None:
                    continue
                if kcl_name not in self.additional_models.keys():
                    self.additional_models[kcl_name] = MapObjectModel(kcl_name, self.editor.read_kcl_file)
                visual_model = self.additional_models[kcl_name].visual_mesh

                if visual_model is None:
                    continue

                glPushMatrix()
                glTranslatef(mapobject.position.x, -mapobject.position.z, mapobject.position.y)
                glMultMatrixf( mapobject.rotation.get_render(False) )
                glScalef(mapobject.scale.x, -mapobject.scale.z, mapobject.scale.y)

                visual_model.render(selectedPart=self.highlight_colltype,
                                    cull_faces=self.cull_faces)

                glPopMatrix()

                additional_collision[mapobject] = self.additional_models[kcl_name].collision
        if self.collision is not None: self.collision.obj_meshes = additional_collision

        if self.snapping_enabled and self.collision is not None:
            snapping_hash = hash((self.snapping_mode, self.collision.hash))
            if self.snapping_last_hash != snapping_hash:
                self.snapping_last_hash = snapping_hash

                # Clear previous display list.
                if self.snapping_display_list is not None:
                    glDeleteLists(self.snapping_display_list, 1)
                    self.snapping_display_list = None

                # Create and compile the display list.
                self.snapping_display_list = glGenLists(1)
                glNewList(self.snapping_display_list, GL_COMPILE)

                glDisable(GL_DEPTH_TEST)

                glDisable(GL_ALPHA_TEST)
                glEnable(GL_BLEND)
                glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

                # Draw wireframe.
                glColor4f(0.1, 0.1, 0.1, 0.3)
                glBegin(GL_LINES)
                for triangle in self.collision.get_triangles():
                    glVertex3f(triangle.origin.x, triangle.origin.y, triangle.origin.z)
                    glVertex3f(triangle.p2.x, triangle.p2.y, triangle.p2.z)
                    glVertex3f(triangle.origin.x, triangle.origin.y, triangle.origin.z)
                    glVertex3f(triangle.p3.x, triangle.p3.y, triangle.p3.z)
                    glVertex3f(triangle.p2.x, triangle.p2.y, triangle.p2.z)
                    glVertex3f(triangle.p3.x, triangle.p3.y, triangle.p3.z)
                glEnd()

                glBlendFunc(GL_ONE, GL_ZERO)
                glDisable(GL_BLEND)
                glEnable(GL_ALPHA_TEST)

                # Draw points.
                glPointSize(5)
                glColor3f(0.0, 0.0, 0.0)
                glBegin(GL_POINTS)
                points = self._get_snapping_points()
                for point in points:
                    glVertex3f(point.x, point.y, point.z)
                glEnd()
                glPointSize(3)
                glColor3f(1.0, 1.0, 1.0)
                glBegin(GL_POINTS)
                for point in points:
                    glVertex3f(point.x, point.y, point.z)
                glEnd()
                glPointSize(1)

                glEnable(GL_DEPTH_TEST)

                glEndList()

            glCallList(self.snapping_display_list)

        if self.mode != MODE_TOPDOWN:
            glMatrixMode(GL_PROJECTION)
            glPushMatrix()
            glLoadIdentity()
            gluPerspective(75, width / height, 100.0, 10000000.0)

            glEnable(GL_FOG)
            glFogfv(GL_FOG_COLOR, self.skycolor)
            glFogi(GL_FOG_MODE, GL_LINEAR)
            glFogf(GL_FOG_START, 1000)
            glHint(GL_FOG_HINT, GL_DONT_CARE)
            glFogf(GL_FOG_END, 200000)

        self.grid.render()

        if self.mode != MODE_TOPDOWN:
            glFogf(GL_FOG_END, 500000)

            glColor4f(*self.backgroundcolor)
            glBegin(GL_QUADS)
            glVertex3f(10000000, 10000000, -500)
            glVertex3f(10000000, -10000000, -500)
            glVertex3f(-10000000, -10000000, -500)
            glVertex3f(-10000000, 10000000, -500)
            glEnd()

            glDisable(GL_FOG)

            glPopMatrix()
            glMatrixMode(GL_MODELVIEW)

        glColor4f(1.0, 1.0, 1.0, 1.0)

        if self.mode == MODE_TOPDOWN:
            #glDisable(GL_DEPTH_TEST)
            glClear(GL_DEPTH_BUFFER_BIT)

        glEnable(GL_ALPHA_TEST)
        glAlphaFunc(GL_GEQUAL, 0.5)

        if self.preview is not None:
            glColor3f(0.0, 0.0, 0.0)
            self.models.draw_sphere(self.preview.view_pos, 2 * SPHERE_UNITS)

        #do rendering of the points
        if self.level_file is not None:
            selected = self.selected
            positions = self.selected_positions

            select_optimize = {x:True for x in selected}

            if vismenu.enemyroutes.is_visible():
                enemypoints_to_highlight = set()
                all_groups = self.level_file.enemypointgroups.groups
                selected_groups = [False] * len(all_groups) #used to determine if a group should be selected - use instead of group_selected

                #figure out based on area type 4:
                type_4_areas = self.level_file.areas.get_type(4)
                points_to_circle = [ area.enemypoint for area in type_4_areas if (area in select_optimize)  ]

                point_index = 0

                #draw each individual group - points first, and then connections between points within the group
                for i, group in enumerate(all_groups):
                    if len(group.points) == 0:
                        continue

                    if group in self.selected:
                        selected_groups[i] = True

                    for j, point in enumerate(group.points):
                        if point in select_optimize:
                            selected_groups[i] = True
                            glColor3f(0.3, 0.3, 0.3)
                            self.models.draw_sphere(point.position, point.scale * 50)

                        if point_index in enemypoints_to_highlight:
                            glColor3f(1.0, 1.0, 0.0)
                            self.models.draw_sphere(point.position, SPHERE_UNITS)

                        if point in points_to_circle:
                            glColor3f(0.0, 0.0, 1.0)
                            self.models.draw_sphere(point.position, 2 * SPHERE_UNITS)

                        point_type = "enemypoint"
                        if i == 0 and j == 0:
                            point_type = "enemypointfirst"

                        self.models.render_generic_position_colored(point.position, point in select_optimize, point_type, point_scale)

                        enemyaction_colors = [ [1.0, 0.0, 0.0], [0.5, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.5, 0.0]    ]
                        if point.enemyaction in [1, 2, 3, 4]:
                            glColor3f(  *enemyaction_colors[point.enemyaction - 1]  )
                            self.models.draw_cylinder(point.position, 400, 400)
                        enemyaction2_colors = [ [0.0, 0.0, 0.5], [0.0, 0.0, 0.75], [0.0, 0.0, 0.1]  ]
                        if point.enemyaction2 in [1, 2, 3]:
                            glColor3f(  *enemyaction2_colors[point.enemyaction2 - 1]  )
                            self.models.draw_cylinder(point.position, 600, 600)


                        point_index += 1

                    # Draw the connections between each enemy point.

                    if selected_groups[i]:
                        glLineWidth(3.0)

                    glBegin(GL_LINE_STRIP)
                    glColor3f(*colors_json["EnemyRoutes"][:3])
                    prev_point = None
                    for point in group.points:
                        pos = point.position
                        glVertex3f(pos.x, -pos.z, pos.y)
                    glEnd()

                    prev_point = None
                    for point in group.points:
                        if prev_point is not None:
                            self.draw_arrow_head(prev_point, point.position)
                        prev_point = point.position

                    if selected_groups[i] :
                        glLineWidth(1.0)

                #draw connections between groups
                for i, group in enumerate( all_groups ):
                    if len(group.points) == 0:
                        continue
                    # Draw the connections between each enemy point group.
                    # draw to nextgroup only
                    prevpoint = group.points[-1]
                    #stores (group index, point)
                    nextpoints = [ (grp, grp.points[0]) for grp in group.nextgroup if len(grp.points) > 0]
                    if len(nextpoints) == 0:
                        continue

                    #draw arrows
                    glColor3f(*colors_json["EnemyRoutes"][:3])
                    for group, point in nextpoints:
                        if selected_groups[i]: #or selected_groups[groupgroup]:
                            glLineWidth(3.0)
                        glBegin(GL_LINES)
                        glVertex3f(prevpoint.position.x, -prevpoint.position.z, prevpoint.position.y)
                        glVertex3f(point.position.x, -point.position.z, point.position.y)
                        glEnd()

                        self.draw_arrow_head(prevpoint.position, point.position)

                        if selected_groups[i]: #or selected_groups[group]:
                            glLineWidth(1.0)
            if vismenu.itemroutes.is_visible():
                enemypoints_to_highlight = set()

                all_groups = self.level_file.itempointgroups.groups
                selected_groups = [False] * len(all_groups)

                point_index = 0
                for i, group in enumerate( all_groups ):
                    if len(group.points) == 0:
                        continue


                    if group in self.selected:
                        selected_groups[i] = True

                    for j, point in enumerate(group.points):
                        if point in select_optimize:
                            selected_groups[i] = True
                            glColor3f(0.3, 0.3, 0.3)
                            self.models.draw_sphere(point.position, point.scale * 50)

                        if point_index in enemypoints_to_highlight:
                            glColor3f(1.0, 1.0, 0.0)
                            self.models.draw_sphere(point.position, SPHERE_UNITS)

                        point_type = "itempoint"
                        if i == 0 and j == 0:
                            point_type = "itempointfirst"

                        self.models.render_generic_position_colored(point.position, point in select_optimize, point_type, point_scale)


                        billaction_colors = [ [1.0, 0.0, 0.0], [0.5, 0.5, 0.5], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]  ]
                        glColor3f(*billaction_colors[point.setting1])
                        self.models.draw_cylinder(point.position, 400, 400)

                        if point.dontdrop != 0:
                            glColor3f(1.0, 0.0, 0.0)
                            self.models.draw_cylinder(point.position, 600, 600)
                        if point.lowpriority != 0:
                            glColor3f(1.0, 0.0, 0.0)
                            self.models.draw_cylinder(point.position, 800, 800)

                        if point.scale > 0 and point in select_optimize:
                            self.models.draw_sphere(point.position, point.scale * 50)


                        point_index += 1

                    if selected_groups[i]:
                        glLineWidth(3.0)

                    glBegin(GL_LINE_STRIP)
                    glColor3f(*colors_json["ItemRoutes"][:3])
                    prev_point = None
                    for point in group.points:
                        pos = point.position
                        glVertex3f(pos.x, -pos.z, pos.y)
                    glEnd()

                    prev_point = None
                    for point in group.points:
                        if prev_point is not None:
                            self.draw_arrow_head(prev_point, point.position)
                        prev_point = point.position

                    if selected_groups[i] and len(all_groups) > 1:
                        glLineWidth(1.0)

                for i, group in enumerate( all_groups ):
                    if len(group.points) == 0:
                        continue
                    # Draw the connections between each enemy point group.
                    prevpoint = group.points[-1]
                    #stores (group index, point)
                    nextpoints = [ (grp, grp.points[0]) for grp in group.nextgroup if len(grp.points) > 0]
                    if len(nextpoints) == 0:
                        continue

                    glColor3f(*colors_json["ItemRoutes"][:3])
                    for group, point in nextpoints:

                        if selected_groups[i]: #or selected_groups[group]:
                            glLineWidth(8.0)

                        glBegin(GL_LINES)
                        glVertex3f(prevpoint.position.x, -prevpoint.position.z, prevpoint.position.y)
                        glVertex3f(point.position.x, -point.position.z, point.position.y)
                        glEnd()

                        self.draw_arrow_head(prevpoint.position, point.position)

                        if selected_groups[i]: #or selected_groups[group]:
                            glLineWidth(4.0)

            #for checkpoints
            all_groups = self.level_file.checkpoints.groups
            selected_groups = [False] * len(all_groups)

            respawns_to_highlight = set()

            highligh_sp_width = 8.0
            highligh_cp_width = 4.0
            highligh_cp_lengt = 4.0
            normal_width = 1.0

            #draw checkpoint groups first the points themselves and then the connections
            if vismenu.checkpoints.is_visible():
                checkpoints_to_highlight = set()
                count = 0
                for i, group in enumerate(all_groups):
                    prev = None
                    #draw checkpoint points
                    for checkpoint in group.points:
                        start_point_selected = checkpoint.start in positions
                        end_point_selected = checkpoint.end in positions
                        self.models.render_generic_position_colored(checkpoint.start, start_point_selected, "checkpointleft", point_scale)
                        self.models.render_generic_position_colored(checkpoint.end, end_point_selected, "checkpointright", point_scale)

                        if start_point_selected or end_point_selected:
                            respawns_to_highlight.add(checkpoint.respawn_obj)
                            checkpoints_to_highlight.add(count)

                        if checkpoint.respawn_obj is not None and checkpoint.respawn_obj in select_optimize:

                            checkpoints_to_highlight.add(count)

                        count += 1
                    glColor3f(*colors_json["Checkpoint"][:3])

                    #draw the lines between the points and between successive points
                    for j, checkpoint in enumerate(group.points):
                        pos1 = checkpoint.start
                        pos2 = checkpoint.end

                        #draw the line for each singular checkpoint
                        glLineWidth(normal_width)
                        glColor3f(*colors_json["Checkpoint"][:3])

                        if (checkpoint.type == 1 or checkpoint.lapcounter == 1) and selected_groups[i] :
                            glLineWidth(highligh_sp_width)
                        elif checkpoint.type == 1 or selected_groups[i] or checkpoint.lapcounter == 1:
                            glLineWidth(highligh_cp_width)

                        concave_next = j + 1 < len(group.points) and check_box_convex(checkpoint, group.points[j+1])
                        concave_prev = j - 1 >= 0 and check_box_convex(checkpoint, group.points[j-1])
                        if concave_next or concave_prev:
                            glColor3f( 1.0, 0.0, 0.0 )

                        elif checkpoint.lapcounter == 1:
                            glColor3f( 1.0, 0.5, 0.0 )
                        elif checkpoint.type == 1:
                            glColor3f( 1.0, 1.0, 0.0 )

                        glBegin(GL_LINES)
                        glVertex3f(pos1.x, -pos1.z, pos1.y)
                        glVertex3f(pos2.x, -pos2.z, pos2.y)
                        glEnd()

                        #draw lines between successive checkpoints
                        if not concave_prev:
                            glColor3f(*colors_json["Checkpoint"][:3])
                        glLineWidth(normal_width)
                        glBegin(GL_LINES)
                        if prev is not None:
                            pos3 = prev.start
                            pos4 = prev.end

                            glVertex3f(pos1.x, -pos1.z, pos1.y)
                            glVertex3f(pos3.x, -pos3.z, pos3.y)
                            glVertex3f(pos2.x, -pos2.z, pos2.y)
                            glVertex3f(pos4.x, -pos4.z, pos4.y)

                        glEnd()
                        prev = checkpoint

                #draw thicker lines for selected ones
                if checkpoints_to_highlight or any(selected_groups):

                    point_index = 0
                    for i, group in enumerate(self.level_file.checkpoints.groups):
                        for checkpoint in group.points:
                            if point_index in checkpoints_to_highlight or selected_groups[i]:
                                pos1 = checkpoint.start
                                pos2 = checkpoint.end

                                glColor3f(*colors_json["Checkpoint"][:3])
                                if checkpoint.lapcounter == 1:
                                    glColor3f( 1.0, 0.5, 0.0 )
                                    glLineWidth(highligh_sp_width)
                                elif checkpoint.type == 1:
                                    glLineWidth(highligh_sp_width)
                                    glColor3f( 1.0, 1.0, 0.0 )
                                else:
                                    glLineWidth(highligh_cp_width)


                                glBegin(GL_LINES)
                                glVertex3f(pos1.x, -pos1.z, pos1.y)
                                glVertex3f(pos2.x, -pos2.z, pos2.y)
                                glEnd()
                            point_index += 1
                glLineWidth(normal_width)

            glPushMatrix()

            #draw the arrow head between successive checkpoints in the same group
            if vismenu.checkpoints.is_visible():
                for i, group in enumerate(self.level_file.checkpoints.groups):
                    if selected_groups[i]:
                        glLineWidth(normal_width)

                    glColor3f(*colors_json["Checkpoint"][:3])
                    prev = None
                    for checkpoint in group.points:
                        if prev is None:
                            prev = checkpoint
                        else:
                            mid1 = (prev.start + prev.end) / 2.0
                            mid2 = (checkpoint.start + checkpoint.end) / 2.0

                            self.draw_arrow_head(mid1, mid2)
                            #lines.append((mid1, mid2))
                            prev = checkpoint

                    if selected_groups[i]:
                        glLineWidth(normal_width)
            #draw the arrow body between sucessive checkpoints
            if vismenu.checkpoints.is_visible():
                for i, group in enumerate( self.level_file.checkpoints.groups ) :
                    if selected_groups[i]:
                        glLineWidth(highligh_cp_lengt)
                    glColor3f(*colors_json["Checkpoint"][:3])
                    prev = None
                    for checkpoint in group.points:
                        if prev is None:
                            prev = checkpoint
                        else:
                            mid1 = (prev.start+prev.end)/2.0
                            mid2 = (checkpoint.start+checkpoint.end)/2.0
                            glBegin(GL_LINES)
                            glVertex3f(mid1.x, -mid1.z, mid1.y)
                            glVertex3f(mid2.x, -mid2.z, mid2.y)
                            prev = checkpoint
                            glEnd()
                    if selected_groups[i]:
                        glLineWidth(normal_width)

            #draw arrows between groups
            if vismenu.checkpoints.is_visible():
                all_groups = self.level_file.checkpoints.groups
                for i, group in enumerate( all_groups ):
                    if len(group.points) == 0:
                        continue
                    # Draw the connections between each enemy point group.
                    # draw to nextgroup only
                    prevpoint = group.points[-1]
                    #stores (group index, point)
                    nextpoints = [ (grp, grp.points[0]) for grp in group.nextgroup if len(grp.points) > 0]
                    if len(nextpoints) == 0:
                        continue

                    glColor3f(0,0,0)
                    for group, point in nextpoints:
                        if selected_groups[i]: #or selected_groups[group]:
                            glLineWidth(highligh_cp_lengt)

                        glBegin(GL_LINES)
                        glVertex3f(prevpoint.start.x, -prevpoint.start.z, prevpoint.start.y)
                        glVertex3f(point.start.x, -point.start.z, point.start.y)
                        glEnd()

                        self.draw_arrow_head(prevpoint.start, point.start)

                        glBegin(GL_LINES)
                        glVertex3f(prevpoint.end.x, -prevpoint.end.z, prevpoint.end.y)
                        glVertex3f(point.end.x, -point.end.z, point.end.y)
                        glEnd()

                        self.draw_arrow_head(prevpoint.end, point.end)

                        if selected_groups[i] :#or selected_groups[group]:
                            glLineWidth(normal_width)
                if self.editor.next_checkpoint_start_position is not None:
                    self.models.render_generic_position_colored(
                    Vector3(*self.editor.next_checkpoint_start_position), True,
                    "checkpointleft", point_scale)
            glPopMatrix()
            #go between the groups
            if vismenu.objects.is_visible():
                for object in self.level_file.objects:
                    object_scale = point_scale.scale_vec(object.scale)
                    self.models.render_generic_position_rotation_colored("objects",
                                                                 object.position, object.rotation,
                                                                 object in select_optimize,
                                                                 object_scale)

                routes_to_highlight = set()

                for obj in self.level_file.objects:
                    if obj.route_obj is not None and obj in select_optimize:
                        routes_to_highlight.add(obj.route_obj)

                routepoints_to_circle = [x.routepoint for x in self.level_file.objects if x in select_optimize]

                objs_to_highlight = set()

                for i, route in enumerate(objectroutes):

                    selected = route in routes_to_highlight

                    if route in self.selected:
                        selected = True

                    last_point = None
                    used_by = self.level_file.route_used_by(route)

                    render_type = "objectpoint" if used_by else "unusedobjectpoint"

                    for point in route.points:
                        point_selected = point in select_optimize
                        if point_selected:
                            objs_to_highlight.update( used_by )
                        self.models.render_generic_position_colored(point.position, point_selected, render_type, point_scale)
                        selected = selected or point_selected

                        if last_point is not None:
                            self.draw_arrow_head(last_point.position, point.position)
                        last_point = point

                        if point in routepoints_to_circle:
                            glColor3f(*colors_json["ObjectRoutes"][:3])
                            self.models.draw_sphere(point.position, SPHERE_UNITS)
                    if selected:
                        glLineWidth(3.0)

                    glBegin(GL_LINE_STRIP)
                    glColor3f(*colors_json["ObjectRoutes"][:3])
                    if len(route.points) == 2 and route.smooth != 0:
                        glColor3f(1.0, 0.0, 0.0 )
                    for point in route.points:
                        pos = point.position
                        glVertex3f(pos.x, -pos.z, pos.y)
                    glEnd()
                    if selected:
                        glLineWidth(1.0)

                for obj in objs_to_highlight:
                    glColor3f(*colors_json["Objects"][:3])
                    self.models.draw_sphere(obj.position, SPHERE_UNITS)

                object_areas = self.level_file.objects.areas

                selected_object_areas = list(set([area.setting1 for area in object_areas if area in select_optimize]))
                for object in object_areas:
                    self.models.render_generic_position_rotation_colored("objectarea",
                                                                object.position, object.rotation,
                                                                object in select_optimize, point_scale)
                    if object in select_optimize:
                        glColor4f(*colors_selection)
                        glLineWidth(3.0)
                    else:
                        glColor4f(*colors_area)
                        glLineWidth(1.0)

                    glColor3f(1.0, 0.0, 1.0)
                    if object.setting1 in selected_object_areas:
                        glColor3f(1.0, 0.0, 0.0)
                        if object.type == 8:
                            glColor3f(0.0, 1.0, 0.0)
                        self.models.draw_sphere(object.position, SPHERE_UNITS)

                    if object.shape == 0:
                        self.models.draw_wireframe_cube(object.position, object.rotation, object.scale*100 * 100)
                    else:
                        self.models.draw_wireframe_cylinder(object.position, object.rotation, object.scale*50 * 100)

                glColor3f(0.0, 1.0, 0.0)
                load_areas_selected = [area for area in object_areas
                                       if area.setting1 in selected_object_areas and area.type == 8]
                for object in [obj for obj in self.level_file.objects if obj.objectid in grouped_objects_json]:
                    for area in load_areas_selected:
                        if area.check(object.position):
                            self.models.draw_sphere( object.position, SPHERE_UNITS)
                            break

            if vismenu.kartstartpoints.is_visible():
                for object in self.level_file.kartpoints:
                    self.models.render_generic_position_rotation_colored("startpoints",
                                                                object.position, object.rotation,
                                                                object in select_optimize, point_scale)
                    z_scale = 4800 if self.level_file.kartpoints.start_squeeze else 5300
                    self.models.draw_wireframe_cube( object.position,
                                                        object.rotation,
                                                        Vector3( 2000, 50, z_scale   ), kartstart = True)
            if vismenu.areas.is_visible():
                for object in self.level_file.areas:
                    self.models.render_generic_position_rotation_colored("areas",
                                                                object.position, object.rotation,
                                                                object in select_optimize, point_scale)
                    if object in select_optimize:
                        glColor4f(*colors_selection)
                        glLineWidth(3.0)
                    else:
                        glColor4f(*colors_area)
                        glLineWidth(1.0)
                    if object.shape == 0:
                        self.models.draw_wireframe_cube(object.position, object.rotation, object.scale*100 * 100)
                    else:
                        self.models.draw_wireframe_cylinder(object.position, object.rotation, object.scale*50 * 100)

                type_3_areas = self.level_file.areas.get_type(3)
                routes_to_circle = set([ area.route_obj for area in type_3_areas if (area in select_optimize)  ])

                for i, route in enumerate(arearoutes):

                    #selected = route in select_optimize
                    selected = False
                    circle = route in routes_to_circle

                    last_point = None
                    if self.level_file.route_used_by(route):
                        for point in route.points:
                            point_selected = point in select_optimize
                            self.models.render_generic_position_colored(point.position, point_selected, "areapoint", point_scale)
                            if circle:
                                glColor3f(*colors_json["Areas"][:3])
                                self.models.draw_sphere(point.position, 2 * SPHERE_UNITS)
                            selected = selected or point_selected
                            if last_point is not None:
                                self.draw_arrow_head(last_point.position, point.position)
                            last_point = point
                    else:
                        for point in route.points:
                            point_selected = point in select_optimize
                            self.models.render_generic_position_colored(point.position, point_selected, "unusedpoint", point_scale)
                            selected = selected or point_selected
                            if last_point is not None:
                                self.draw_arrow_head(last_point.position, point.position)
                            last_point = point

                    if selected or circle:
                        glLineWidth(3.0)
                    glBegin(GL_LINE_STRIP)
                    glColor3f(*colors_json["AreaRoutes"][:3])
                    if len(route.points) == 2 and route.smooth != 0:
                        glColor3f(1.0, 0.0, 0.0 )
                    for point in route.points:
                        pos = point.position
                        glVertex3f(pos.x, -pos.z, pos.y)
                    glEnd()
                    if selected or circle:
                        glLineWidth(1.0)

            if vismenu.replaycameras.is_visible():
                #define levels of :

                #stuff that is directly selected by a user
                selected_areas = [area for area in self.level_file.replayareas if area in select_optimize]
                selected_cameras = [camera for camera in replaycameras if camera in select_optimize]
                selected_points = [thing for thing in select_optimize if isinstance(thing, ReplayCameraRoutePoint)]
                selected_routes = list(set([self.level_file.get_route_of_point(x) for x in selected_points]))

                linked_cameras = []
                [linked_cameras.extend(self.level_file.route_used_by(x)) for x in selected_routes]
                linked_cameras.extend([area.camera for area in selected_areas])

                linked_areas = []
                for collec in (selected_cameras, linked_cameras):
                    linked_areas.extend([area for area in self.level_file.replayareas if area.camera in collec])
                linked_areas = list(set(linked_areas))

                linked_routes = []
                for collec in (selected_cameras, linked_cameras):
                    linked_routes.extend([cam.route_obj for cam in collec if cam.route_info() and cam.route_obj is not None])
                linked_routes = list(set(linked_routes))


                for object in self.level_file.replayareas:
                    bolded = object in linked_areas
                    self.models.render_generic_position_rotation_colored( "replayareas",
                                                                object.position, object.rotation,
                                                                bolded, point_scale)
                    if bolded:
                        glColor4f(*colors_selection)
                        glLineWidth(3.0)
                    else:
                        glColor4f(*colors_replayarea)
                        glLineWidth(1.0)

                    if object.shape == 0:
                        self.models.draw_wireframe_cube(object.position, object.rotation, object.scale*100 * 100)
                    else:
                        self.models.draw_wireframe_cylinder(object.position, object.rotation, object.scale*50 * 100)

                #render cameras
                for i, object in enumerate(replaycameras):
                    selected = object in selected_cameras
                    bolded = object in linked_cameras

                    if object.type == 1:
                        self.models.render_generic_position_colored(object.position, bolded, "replaycameras", point_scale)
                        if not object.follow_player:
                            glColor4f(*colors_replaycamera)
                            pos2 = object.position2_simple.render() #if absolute_poses else object.position2.absolute()
                            pos3 = object.position3_simple.render() #if absolute_poses else object.position3.absolute()

                            self.models.draw_sphere(pos2, SPHERE_UNITS)
                            self.models.draw_sphere(pos3, SPHERE_UNITS)

                            if bolded:
                                glLineWidth(3.0)
                            else:
                                glLineWidth(1.0)
                            glColor3f(*colors_json["ReplayCamera"][:3])
                            glBegin(GL_LINE_STRIP)

                            glVertex3f(pos2.x, -pos2.z, pos2.y)
                            glVertex3f(pos3.x, -pos3.z, pos3.y)
                            glEnd()
                            self.draw_arrow_head(pos2, pos3)

                    elif object.type == 3:
                        self.models.render_generic_position_colored(object.position,
                                                                bolded, "replaycamerasplayer", point_scale)
                        pos2 = object.position2_player.render()
                        pos3 = object.position3_player.render()
                        self.models.draw_sphere(pos2, SPHERE_UNITS)
                        self.models.draw_sphere(pos3, SPHERE_UNITS)
                        glBegin(GL_LINE_STRIP)

                        glVertex3f(pos2.x, -pos2.z, pos2.y)
                        glVertex3f(pos3.x, -pos3.z, pos3.y)
                        glEnd()

                for i, route in enumerate(replaycameraroutes):
                    selected = route in selected_routes
                    bolded = route in linked_routes

                    last_point = route.points[0]
                    for point in route.points[1:]:
                        self.models.render_generic_position_colored(point.position.render(), bolded, "replaycamerapoint", point_scale)
                        if last_point is not None:
                            self.draw_arrow_head(last_point.position.render(), point.position.render())
                        last_point = point
                    if bolded:
                        glLineWidth(3.0)
                    glBegin(GL_LINE_STRIP)
                    glColor3f(*colors_json["ReplayCameraRoute"][:3])
                    if len(route.points) == 2 and route.smooth != 0:
                        glColor3f(1.0, 0.0, 0.0 )
                    for point in route.points:
                        pos = point.position.render()
                        glVertex3f(pos.x, -pos.z, pos.y)
                    glEnd()
                    if bolded:
                        glLineWidth(1.0)

            if vismenu.cameras.is_visible():
                for i, object in enumerate(self.level_file.cameras):
                    if object.type == 0:
                        continue
                    self.models.render_generic_position_colored(object.position,
                                                                 object in select_optimize,
                                                                 "camera", point_scale)
                    if object in select_optimize:
                        glColor3f(*colors_json["Camera"][:3])
                    else:
                        glColor3f(*colors_json["CameraUnselected"][:3])
                    pos1 = object.position2_simple
                    pos2 = object.position3_simple
                    self.models.draw_sphere(pos1, SPHERE_UNITS)
                    self.models.draw_sphere(pos2, SPHERE_UNITS)
                    glLineWidth(2.0)
                    glBegin(GL_LINES)
                    glVertex3f(pos1.x, -pos1.z, pos1.y)
                    glVertex3f(pos2.x, -pos2.z, pos2.y)
                    glEnd()
                    self.draw_arrow_head(pos1, pos2)

                    if object.nextcam_obj is not None:
                        pos1 = object.position
                        pos2 = object.nextcam_obj.position
                        glLineWidth(2.0)
                        glBegin(GL_LINES)
                        glColor3f(*colors_json["Camera"][:3])
                        glVertex3f(pos1.x, -pos1.z, pos1.y)
                        glVertex3f(pos2.x, -pos2.z, pos2.y)
                        glEnd()
                        self.draw_arrow_head(pos1, pos2)

                    if object == self.level_file.cameras.startcam:
                        glColor3f(*colors_json["Camera"][:3])
                        self.models.draw_sphere(object.position, 2 * SPHERE_UNITS)

                routes_to_highlight = set( [camera.route_obj for camera in self.level_file.cameras if camera in select_optimize]  )
                glLineWidth(1.0)
                for i, route in enumerate(cameraroutes):
                    selected = route in routes_to_highlight or route in self.selected

                    last_point = None
                    for point in route.points:
                        point_selected = point in select_optimize
                        self.models.render_generic_position_colored(point.position, point_selected, "camerapoint", point_scale)
                        selected = selected or point_selected
                        if last_point is not None:
                            self.draw_arrow_head(last_point.position, point.position)
                        last_point = point

                    if selected:
                        glLineWidth(3.0)
                    glBegin(GL_LINE_STRIP)
                    glColor3f(*colors_json["CameraRoutes"][:3])
                    if len(route.points) == 2 and route.smooth != 0:
                        glColor3f(1.0, 0.0, 0.0 )
                    for point in route.points:
                        pos = point.position
                        glVertex3f(pos.x, -pos.z, pos.y)
                    glEnd()
                    if selected:
                        glLineWidth(1.0)
            if vismenu.respawnpoints.is_visible():
                used_respawns = self.level_file.checkpoints.get_used_respawns()
                for i, object in enumerate( self.level_file.respawnpoints):
                    render_type = "unusedrespawn"
                    if object in used_respawns:
                        render_type = "respawn"
                    self.models.render_generic_position_rotation_colored(render_type,
                                                                object.position, object.rotation,
                                                                object in select_optimize, point_scale)

                    if object in respawns_to_highlight:
                        glColor3f(*colors_json["Respawn"][:3]) # will be replaced with the respawn color
                        self.models.draw_sphere(object.position, 2 * SPHERE_UNITS)
                    self.models.draw_wireframe_cube( object.position,
                                                        object.rotation,
                                                        Vector3( 900, 50, 600   ), kartstart = True)

            if vismenu.cannonpoints.is_visible():
                for object in self.level_file.cannonpoints:
                    self.models.render_generic_position_rotation_colored("cannons",
                                                                object.position, object.rotation,
                                                                 object in select_optimize, point_scale)
            if vismenu.missionsuccesspoints.is_visible():
                for object in self.level_file.missionpoints:
                    self.models.render_generic_position_rotation_colored("mission",
                                                                object.position, object.rotation,
                                                                 object in select_optimize, point_scale)

        if self.level_file is not None:
            if vismenu.replaycameras.is_visible():
                for object in self.level_file.replayareas:
                    color = colors_json["SelectedReplayAreaFill"] if object in select_optimize else colors_json["ReplayAreaFill"]
                    if object.shape == 0 and self.mode == MODE_TOPDOWN:
                        TransPlane.render_srt(object.position, object.rotation, object.scale,
                                              Vector3(-100, 0, -100), Vector3(100, 0, 100),
                                              color)
                    elif object.shape == 0:
                        TransPlane.render_box_srt(object.position, object.rotation, object.scale, color)
                    else:
                        glColor4f(*color)
                        self.models.render_trans_cylinder(object.position, object.rotation, object.scale*50 * 100)
            if vismenu.areas.is_visible():
                for object in self.level_file.areas:
                    color = colors_json["SelectedAreaFill"] if object in select_optimize else colors_json["AreaFill"]
                    if object.shape == 0 and self.mode == MODE_TOPDOWN:
                            TransPlane.render_srt(object.position, object.rotation, object.scale,
                                                Vector3(-100, 0, -100), Vector3(100, 0, 100),
                                                color)
                    elif object.shape == 0:
                        TransPlane.render_box_srt(object.position, object.rotation, object.scale, color)
                    else:
                        glColor4f(*color)
                        self.models.render_trans_cylinder(object.position, object.rotation, object.scale*50 * 100)

            if vismenu.objects.is_visible():
                for object in self.level_file.objects.areas:
                    if object.type == 8:
                        color = colors_json["ObjectArea8FillSelected"] if object in select_optimize else colors_json["ObjectArea8Fill"]
                    else:
                        color = colors_json["ObjectArea9FillSelected"] if object in select_optimize else colors_json["ObjectArea9Fill"]
                    if object.shape == 0 and self.mode == MODE_TOPDOWN:
                            TransPlane.render_srt(object.position, object.rotation, object.scale,
                                                Vector3(-100, 0, -100), Vector3(100, 0, 100),
                                                color)
                    elif object.shape == 0:
                        TransPlane.render_box_srt(object.position, object.rotation, object.scale, color)
                    else:
                        glColor4f(*color)
                        self.models.render_trans_cylinder(object.position, object.rotation, object.scale*50 * 100)
            if vismenu.checkpoints.is_visible() and self.mode == MODE_3D:
                glEnable(GL_CULL_FACE)
                rotation = Rotation.from_euler(Vector3(0, 90, 0))
                for group in self.level_file.checkpoints.groups:
                    for point in group.points:
                        if point in select_optimize or point.type:
                            color = (1, 1, 0, .3)
                        elif point.lapcounter:
                            color = (1, 0.5, 0, .3)
                        else:
                            color = (0, 0, 1, .3)
                        horiz, _verti = (point.end - point.start).to_euler()
                        rotation = Rotation.from_euler(Vector3(0, -horiz * 180/3.14 - 90, 0))
                        scale = Vector3(1, 1,  ((point.end - point.start).norm()) / 100)
                        TransPlane.render_srt(point.get_mid(), rotation, scale,
                                        Vector3(-1, 0, 0), Vector3(1, 1000, 0),
                                        color)
                glDisable(GL_CULL_FACE)
                color = (0, 0, 1, .3)
                for group in self.level_file.checkpoints.groups:
                    for point, next_point in zip(group.points, group.points[1:]):
                        horiz, _verti = (next_point.start - point.start).to_euler()
                        rotation = Rotation.from_euler(Vector3(0, -horiz * 180/3.14 - 90, 0))
                        scale = Vector3(1, 1,  ((next_point.start - point.start).norm()) / 100)
                        position = (next_point.start + point.start) / 2
                        TransPlane.render_srt(position, rotation, scale,
                                        Vector3(-1, 0, 0), Vector3(1, 1000, 0),
                                        color)

                        horiz, _verti = (next_point.end - point.end).to_euler()
                        rotation = Rotation.from_euler(Vector3(0, -horiz * 180/3.14 - 90, 0))
                        scale = Vector3(1, 1,  ((next_point.end - point.end).norm()) / 100)
                        position = (next_point.end + point.end) / 2
                        TransPlane.render_srt(position, rotation, scale,
                                        Vector3(-1, 0, 0), Vector3(1, 1000, 0),
                                        color)

        #render evrything absolute
        self.gizmo.render_scaled(gizmo_scale,
                                    is3d=self.mode == MODE_3D,
                                    hover_id=gizmo_hover_id)

        glDisable(GL_DEPTH_TEST)
        if self.connecting_mode:
            mouse_pos = self.mapFromGlobal(QtGui.QCursor.pos())
            if self.mode == MODE_TOPDOWN:
                mapx, mapz = self.mouse_coord_to_world_coord(mouse_pos.x(), mouse_pos.y())
                pos2 = Vector3( mapx, 0, -mapz)
            elif self.mode == MODE_3D:
                pos2 = self.get_3d_coordinates(mouse_pos.x(), mouse_pos.y())
                pos2 = Vector3(pos2.x, pos2.z, -pos2.y)

            if pos2 is not None:
                for pos1 in self.connecting_start:
                    if self.mode == MODE_TOPDOWN:
                        pos2.y = pos1.y
                    glLineWidth(5.0)
                    glBegin(GL_LINES)
                    glColor3f(0.0, 0.0, 0.0)
                    glVertex3f(pos1.x, -pos1.z, pos1.y)
                    glVertex3f(pos2.x, -pos2.z, pos2.y)
                    glEnd()
                    self.draw_arrow_head(pos1, pos2)
        else: 
            if self.selectionbox_start is not None and self.selectionbox_end is not None:
                startx, startz = self.selectionbox_start
                endx, endz = self.selectionbox_end
                glColor4f(1.0, 0.0, 0.0, 1.0)
                glLineWidth(2.0)
                glBegin(GL_LINE_LOOP)
                glVertex3f(startx, startz, 0)
                glVertex3f(startx, endz, 0)
                glVertex3f(endx, endz, 0)
                glVertex3f(endx, startz, 0)

                glEnd()
                glLineWidth(1.0)

            if self.selectionbox_projected_origin is not None and self.selectionbox_projected_coords is not None:
                origin = self.selectionbox_projected_origin
                point2, point3, point4 = self.selectionbox_projected_coords
                glColor4f(1.0, 0.0, 0.0, 1.0)
                glLineWidth(2.0)

                point1 = origin

                glBegin(GL_LINE_LOOP)
                glVertex3f(point1.x, point1.y, point1.z)
                glVertex3f(point2.x, point2.y, point2.z)
                glVertex3f(point3.x, point3.y, point3.z)
                glVertex3f(point4.x, point4.y, point4.z)
                glEnd()

                glLineWidth(1.0)

        glEnable(GL_DEPTH_TEST)

        #connections?
        if self.connecting_mode:
            mouse_pos = self.mapFromGlobal(QtGui.QCursor.pos())
            if self.mode == MODE_TOPDOWN:
                mapx, mapz = self.mouse_coord_to_world_coord(mouse_pos.x(), mouse_pos.y())
                pos2 = Vector3( mapx, 0, -mapz)
            elif self.mode == MODE_3D:
                pos2 = self.get_3d_coordinates(mouse_pos.x(), mouse_pos.y())
                pos2 = Vector3(pos2.x, pos2.z, -pos2.y)

            if pos2 is not None:
                for pos1 in self.connecting_start:
                    if self.mode == MODE_TOPDOWN:
                        pos2.y = pos1.y
                    glLineWidth(5.0)
                    glBegin(GL_LINES)
                    glColor3f(0.0, 0.0, 0.0)
                    glVertex3f(pos1.x, -pos1.z, pos1.y)
                    glVertex3f(pos2.x, -pos2.z, pos2.y)
                    glEnd()
                    self.draw_arrow_head(pos1, pos2)
                    if self.connecting_mode == "linedraw":
                        diff = pos2 - pos1
                        for i in range(1, 1 + self.linedraw_count):
                            position = diff * (i/self.linedraw_count) + pos1
                            self.models.render_generic_position_rotation_colored("objects",
                                position, self.connecting_rotation,
                                object in select_optimize, point_scale)

        glFinish()
        #now = default_timer() - start

    def draw_arrow_head(self, startpos, endpos):
        mid_position = (startpos + endpos) / 2
        if self.mode == MODE_TOPDOWN:
            scale = self.zoom_factor / 16
            up_dir = Vector3(0.0, 1.0, 0.0)
        else:
            up_dir = (mid_position - self.campos).normalized()
            scale = (mid_position - self.campos).norm() / 8192
        self.models.draw_arrow_head(startpos, mid_position, up_dir, scale)

    def do_selection(self):
        pass

    @catch_exception
    def mousePressEvent(self, event):
        self.usercontrol.handle_press(event)

    @catch_exception
    def mouseMoveEvent(self, event):
        self.usercontrol.handle_move(event)

        self._mouse_pos_changed = True

    @catch_exception
    def mouseReleaseEvent(self, event):
        self.usercontrol.handle_release(event)

    def wheelEvent(self, event):
        wheel_delta = event.angleDelta().y()

        if self.editorconfig is not None:
            invert = self.editorconfig.getboolean("invertzoom")
            if invert:
                wheel_delta = -1*wheel_delta

        if wheel_delta < 0:
            self.zoom_out()

        elif wheel_delta > 0:
            self.zoom_in()

    def zoom_in(self):
        if self.mode == MODE_TOPDOWN:
            current = self.zoom_factor
            fac = calc_zoom_out_factor(current)
            self.zoom(fac)
        else:
            self.zoom_inout_3d(True)

    def zoom_out(self):
        if self.mode == MODE_TOPDOWN:
            current = self.zoom_factor
            fac = calc_zoom_in_factor(current)
            self.zoom(fac)
        else:
            self.zoom_inout_3d(False)

    def zoom_inout_3d(self, zoom_in):
        speedup = 1 if zoom_in else -1
        if self.shift_is_pressed:
            speedup *= self._wasdscrolling_speedupfactor
        speed = self._wasdscrolling_speed / 2

        self.camera_direction.normalize()
        view = self.camera_direction.copy()
        view = view * speed * speedup

        self.position += Vector3(view.x, view.z, view.y)

        self.do_redraw()

    def create_ray_from_mouseclick(self, mousex, mousey, yisup=False):
        self.camera_direction.normalize()
        height = self.canvas_height
        width = self.canvas_width

        view = self.camera_direction.copy()

        h = view.cross(Vector3(0, 0, 1))
        v = h.cross(view)

        h.normalize()
        v.normalize()

        rad = 75 * pi / 180.0
        vLength = tan(rad / 2) * 1.0
        hLength = vLength * (width / height)

        v *= vLength
        h *= hLength

        x = mousex - width / 2
        y = height - mousey- height / 2

        x /= (width / 2)
        y /= (height / 2)
        camerapos = Vector3(self.position.x, self.position.z, self.position.y)

        pos = camerapos + view * 1.0 + h * x + v * y
        dir = pos - camerapos

        if yisup:
            tmp = pos.y
            pos.y = -pos.z
            pos.z = tmp

            tmp = dir.y
            dir.y = -dir.z
            dir.z = tmp

        return Line(pos, dir)

    def get_3d_coordinates(self, mousex, mousey):
        ray = self.create_ray_from_mouseclick(mousex, mousey)
        pos2 = None

        if self.collision is not None:
            pos2 = self.collision.collide_ray(ray)

        if pos2 is None:
            plane = Plane.xy_aligned(Vector3(0.0, 0.0, 0.0))

            collision = ray.collide_plane(plane)
            if collision is not False:
                pos2, _ = collision

        return pos2

    def preview_opening_cameras(self, cameras):
        if not cameras:
            return
        self.preview = OpeningPreview(cameras)
        self.mode = MODE_3D

    def preview_replay_cameras(self, areas, enemies, singlearea=False):
        if not areas:
            return
        self.preview = ReplayPreview(areas, enemies, singlearea)
        self.mode = MODE_3D

    def get_closest_snapping_point(self, mousex, mousey, is3d=True):
        if is3d:
            ray = self.create_ray_from_mouseclick(mousex, mousey)
        else:
            mapx, mapz = self.mouse_coord_to_world_coord(mousex, mousey)
            ray = Line(Vector3(mapx, mapz, 99999999.0), Vector3(0.0, 0.0, -1.0))
        return self.collision.get_closest_point(ray, self._get_snapping_points())

    def set_hidden_coltypes(self, hidden_coltypes, hidden_colgroups):
        Collision.hidden_coltypes = hidden_coltypes
        Collision.hidden_colgroups = hidden_colgroups


def create_object_type_pixmap(canvas_size: int, directed: bool,
                              colors: 'tuple[tuple[int]]') -> QtGui.QPixmap:
    border = int(canvas_size * 0.12)
    size = canvas_size // 2 - border
    margin = (canvas_size - size) // 2

    pixmap = QtGui.QPixmap(canvas_size, canvas_size)
    pixmap.fill(QtCore.Qt.transparent)

    painter = QtGui.QPainter(pixmap)
    painter.setRenderHints(QtGui.QPainter.Antialiasing)

    pen = QtGui.QPen()
    pen.setJoinStyle(QtCore.Qt.RoundJoin)
    pen.setWidth(border)
    painter.setPen(pen)

    main_color = QtGui.QColor(colors[0][0], colors[0][1], colors[0][2])

    if directed:
        polygon = QtGui.QPolygonF((
            QtCore.QPointF(margin - size // 2, margin),
            QtCore.QPointF(margin - size // 2, margin + size),
            QtCore.QPointF(margin + size - size // 2, margin + size),
            QtCore.QPointF(margin + size + size - size // 2, margin + size - size // 2),
            QtCore.QPointF(margin + size - size // 2, margin),
        ))
        head = QtGui.QPolygonF((
            QtCore.QPointF(margin + size - size // 2 + size // 4, margin + size - size // 4),
            QtCore.QPointF(margin + size + size - size // 2, margin + size - size // 2),
            QtCore.QPointF(margin + size - size // 2 + size // 4, margin + size // 4),
        ))

        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(main_color)
        painter.drawPolygon(polygon)
        head_color = QtGui.QColor(9, 147, 0)
        painter.setBrush(head_color)
        painter.drawPolygon(head)

        painter.setPen(pen)
        painter.setBrush(QtCore.Qt.transparent)
        painter.drawPolygon(polygon)
    else:
        polygon = QtGui.QPolygonF((
            QtCore.QPointF(margin, margin),
            QtCore.QPointF(margin, margin + size),
            QtCore.QPointF(margin + size, margin + size),
            QtCore.QPointF(margin + size, margin),
        ))

        if len(colors) > 1:
            secondary_color = QtGui.QColor(colors[1][0], colors[1][1], colors[1][2])
            painter.setBrush(secondary_color)
            painter.drawPolygon(polygon.translated(size // 3, size // 3))
            painter.setBrush(main_color)
            painter.drawPolygon(polygon.translated(-size // 3, -size // 3))
        else:
            painter.setBrush(main_color)
            painter.drawPolygon(polygon)

    del painter

    return pixmap


class ObjectViewSelectionToggle(object):
    def __init__(self, name, menuparent, directed, colors):
        self.name = name
        self.menuparent = menuparent

        icon = QtGui.QIcon()
        for size in (16, 22, 24, 28, 32, 40, 48, 64, 80, 96):
            icon.addPixmap(create_object_type_pixmap(size, directed, colors))

        self.action_view_toggle = QtGui.QAction("{0}".format(name), menuparent)
        self.action_select_toggle = QtGui.QAction("{0} selectable".format(name), menuparent)
        self.action_view_toggle.setCheckable(True)
        self.action_view_toggle.setChecked(True)
        self.action_view_toggle.setIcon(icon)
        self.action_select_toggle.setCheckable(True)
        self.action_select_toggle.setChecked(True)
        self.action_select_toggle.setIcon(icon)

        self.action_view_toggle.triggered.connect(self.handle_view_toggle)
        self.action_select_toggle.triggered.connect(self.handle_select_toggle)

        menuparent.addAction(self.action_view_toggle)
        menuparent.addAction(self.action_select_toggle)

    def change_view_status(self):
        if self.is_visible():
            self.action_view_toggle.setChecked(False)
            self.action_select_toggle.setChecked(False)
        else:
            self.action_view_toggle.setChecked(True)

    def change_select_status(self):
        if self.is_selectable():
            #self.action_view_toggle.setChecked(False)
            self.action_select_toggle.setChecked(False)
        else:
            self.action_view_toggle.setChecked(True)
            self.action_select_toggle.setChecked(True)

    def handle_view_toggle(self, val):
        if not val:
            self.action_select_toggle.setChecked(False)
        else:
            self.action_select_toggle.setChecked(True)

    def handle_select_toggle(self, val):
        if val:
            self.action_view_toggle.setChecked(True)

    def is_visible(self):
        return self.action_view_toggle.isChecked()

    def is_selectable(self):
        return self.action_select_toggle.isChecked()


class FilterViewMenu(QtWidgets.QMenu):
    filter_update = QtCore.Signal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setTitle("Filter View")

        self.show_all = QtGui.QAction("Show All", self)
        self.show_all.triggered.connect(self.handle_show_all)
        self.addAction(self.show_all)

        self.hide_all = QtGui.QAction("Hide All", self)
        self.hide_all.triggered.connect(self.handle_hide_all)
        self.addAction(self.hide_all)

        self.addSeparator()

        with open("lib/color_coding.json", "r") as f:
            colors = json.load(f)
            colors = {k: (round(r * 255), round(g * 255), round(b * 255)) for k, (r, g, b, _a) in colors.items()}

        self.kartstartpoints = ObjectViewSelectionToggle("Kart Start Points", self, True,
                                                         [colors["StartPoints"]])

        self.enemyroutes = ObjectViewSelectionToggle("Enemy Path", self, False,
                                                    [colors["EnemyRoutes"]])
        self.itemroutes = ObjectViewSelectionToggle("Item Path", self, False,
                                                    [colors["ItemRoutes"]])
        self.checkpoints = ObjectViewSelectionToggle(
            "Checkpoints", self, False, [colors["CheckpointLeft"], colors["CheckpointRight"]])
        self.respawnpoints = ObjectViewSelectionToggle("Respawn Points", self, True,
                                                       [colors["Respawn"]])
        self.objects = ObjectViewSelectionToggle("Objects", self, True, [colors["Objects"]])
        self.areas = ObjectViewSelectionToggle("Areas", self, True, [colors["Areas"]])
        self.replaycameras = ObjectViewSelectionToggle("ReplayCameras", self, True, [colors["Camera"]])
        self.cameras = ObjectViewSelectionToggle("Cameras", self, True, [colors["Camera"]])

        self.cannonpoints = ObjectViewSelectionToggle("Cannon Points", self, True, [colors["Cannons"]])
        self.missionsuccesspoints = ObjectViewSelectionToggle("Mission Success Points", self, True, [colors["Missions"]])

        for action in self.get_entries():
            action.action_view_toggle.triggered.connect(self.emit_update)
            action.action_select_toggle.triggered.connect(self.emit_update)

    def get_entries(self):
        return (self.enemyroutes,
                self.itemroutes,
                self.checkpoints,
                self.respawnpoints,
                self.objects,
                self.areas,
                self.replaycameras,
                self.cameras,
                self.kartstartpoints,
                self.cannonpoints,
                self.missionsuccesspoints
               )


    def handle_show_all(self):
        for action in self.get_entries():
            action.action_view_toggle.setChecked(True)
            action.action_select_toggle.setChecked(True)
        self.filter_update.emit()

    def handle_hide_all(self):
        for action in self.get_entries():
            action.action_view_toggle.setChecked(False)
            action.action_select_toggle.setChecked(False)
        self.filter_update.emit()

    def emit_update(self, val):
        self.filter_update.emit()

    def mouseReleaseEvent(self, e):
        try:
            action = self.activeAction()
            if action and action.isEnabled():
                action.trigger()
            else:
                QtWidgets.QMenu.mouseReleaseEvent(self, e)
        except:
            traceback.print_exc()

class MapObjectModel(object):
    def __init__(self, filepath, read_kcl_file) -> None:
        faces, model = read_kcl_file(filepath, True)
        if faces is None:
            self.collision = None
            self.visual_mesh = None
        else:
            self.collision = Collision(faces)
            self.visual_mesh = model

