import os
import json
from OpenGL.GL import *
from .model_rendering import (GenericObject, Model, TexturedModel, Cube, TransModel, Cylinder)
from .vectors import Vector3, rotation_matrix_with_up_dir
import numpy

with open("lib/color_coding.json", "r") as f:
    colors = json.load(f)


def do_rotation(rotation):
    glMultMatrixf( rotation.get_render() )
    scale = 10.0
    glScalef(scale, scale, scale ** 2)



class ObjectModels(object):
    def __init__(self):
        self.models = {}

        self.generic = GenericObject()
        self.cube = Cube()
        self.cylinder = Cylinder()
        self.enemypoint = Cylinder(colors["EnemyRoutes"])
        self.enemypointfirst = Cylinder(colors["FirstEnemyPoint"])
        self.itempoint = Cylinder(colors["ItemRoutes"])
        self.itempointfirst = Cylinder(colors["FirstItemPoint"])

        self.checkpointleft = Cylinder(colors["CheckpointLeft"])
        self.checkpointright = Cylinder(colors["CheckpointRight"])

        self.respawn = GenericObject(colors["Respawn"])
        self.unusedrespawn = GenericObject(colors["UnusedRespawn"])

        self.objects = GenericObject(colors["Objects"])
        self.objectpoint = Cylinder(colors["ObjectRoutes"])
        self.unusedobjectpoint = Cylinder(colors["UnusedObjectRoutes"])
        self.objectarea = GenericObject(colors["ObjectAreas"])

        self.camera = Cube(colors["Camera"])
        self.camerapoint = Cylinder(colors["CameraRoutes"])

        self.replayareas = GenericObject(colors["ReplayArea"])
        self.replaycameras = Cube(colors["ReplayCamera"])
        self.replaycamerasplayer = Cube(colors["ReplayCameraPlayer"])
        self.replaycamerapoint = Cylinder(colors["ReplayCameraRoute"])

        self.areas = GenericObject(colors["Areas"])
        self.areapoint = Cylinder(colors["AreaRoutes"])

        self.minimapareas = GenericObject(colors["MinimapArea"])

        self.startpoints = GenericObject(colors["StartPoints"])
        self.cannons = GenericObject(colors["Cannons"])
        self.missions = GenericObject(colors["Missions"])

        with open("resources/unitsphere.obj", "r") as f:
            self.sphere = Model.from_obj(f, rotate=True)

        with open("resources/unitcylinder.obj", "r") as f:
            self.unitcylinder = Model.from_obj(f, rotate=True)

        with open("resources/unitcylinder.obj", "r") as f:
            self.wireframe_cylinder = Model.from_obj(f, rotate=True)

        with open("resources/unitcube_wireframe.obj", "r") as f:
            self.wireframe_cube = Model.from_obj(f, rotate=True)

        with open("resources/arrow_head.obj", "r") as f:
            self.arrow_head = Model.from_obj(f, rotate=True, scale=500.0)

        with open("resources/solidcylinder.obj", "r") as f:
            self.trans_cylinder = TransModel.from_obj(f, rotate=True)

    def init_gl(self):
        for cube in (self.cylinder, self.cube,
                     self.enemypoint, self.enemypointfirst, self.itempoint, self.itempointfirst,
                     self.checkpointleft, self.checkpointright,
                     self.respawn, self.unusedrespawn,
                     self.objects, self.objectpoint, self.unusedobjectpoint, self.objectarea,
                     self.camera, self.camerapoint,
                     self.replayareas, self.replaycameras, self.replaycamerasplayer, self.replaycamerapoint,
                     self.areas, self.areapoint,
                     self.minimapareas,
                     self.startpoints, self.cannons, self.missions):
            cube.generate_displists()

    def draw_arrow_head(self, frompos, topos, up_dir, scale):
        # Convert to GL base.
        frompos = Vector3(frompos.x, -frompos.z, frompos.y)
        topos = Vector3(topos.x, -topos.z, topos.y)
        up_dir = Vector3(up_dir.x, -up_dir.z, up_dir.y)

        glPushMatrix()

        glTranslatef(topos.x, topos.y, topos.z)

        direction = topos - frompos
        if not direction.is_zero() and not up_dir.is_zero():
            matrix = rotation_matrix_with_up_dir(Vector3(-1, 0, 0), direction, up_dir)
            glMultMatrixf(matrix.flatten())

        glScale(scale, scale, scale)

        self.arrow_head.render()

        glPopMatrix()

    def draw_sphere(self, position, scale):
        glPushMatrix()

        glTranslatef(position.x, -position.z, position.y)

        glScalef(scale, scale, scale)

        self.sphere.render()
        glPopMatrix()

    def draw_sphere_last_position(self, scale):
        glPushMatrix()

        glScalef(scale, scale, scale)

        self.sphere.render()
        glPopMatrix()

    def draw_cylinder(self,position, radius, height):
        glPushMatrix()

        glTranslatef(position.x, -position.z, position.y)
        glScalef(radius, height, radius)

        self.unitcylinder.render()
        glPopMatrix()

    def draw_wireframe_cylinder(self, position, rotation, scale):
        glPushMatrix()
        glTranslatef(position.x, -position.z, position.y)
        do_rotation(rotation)
        glTranslatef(0, 0, scale.y / 2)
        glScalef(scale.z, scale.x, scale.y)
        self.wireframe_cylinder.render()
        glPopMatrix()

    def draw_wireframe_cube(self, position, rotation, scale, kartstart = False):
        glPushMatrix()
        glTranslatef(position.x, -position.z, position.y)
        do_rotation(rotation)
        glTranslatef(0, 0, scale.y/2)

        if kartstart:
            glTranslatef(-scale.z / 2, 0, 0)

        glScalef(scale.z, scale.x, scale.y)
        self.wireframe_cube.render()
        glPopMatrix()

    def draw_cylinder_last_position(self, radius, height):
        glPushMatrix()

        glScalef(radius, radius, height)

        self.unitcylinder.render()
        glPopMatrix()

    def render_generic_position(self, position, selected):
        self._render_generic_position(self.cylinder, position, selected)

    def render_generic_position_colored(self, position, selected, cubename, scale=Vector3(1, 1, 1)):
        self._render_generic_position(getattr(self, cubename), position, selected, scale)

    def render_generic_position_rotation(self, position, rotation, selected, scale=Vector3(1, 1, 1)):
        self._render_generic_position_rotation("generic", position, rotation, selected, scale)

    def render_generic_position_rotation_colored(self, objecttype, position, rotation, selected, scale=Vector3(1, 1, 1)):
        self._render_generic_position_rotation(objecttype, position, rotation, selected, scale)

    def _render_generic_position_rotation(self, name, position, rotation, selected, scale):
        glPushMatrix()
        glTranslatef(position.x, -position.z, position.y)
        do_rotation(rotation)

        glColor3f(0.0, 0.0, 0.0)
        glBegin(GL_LINE_STRIP)
        glVertex3f(0.0, 0.0, 750.0)
        glVertex3f(0.0, 0.0, 0.0)
        glVertex3f(1000.0, 0.0, 0.0)
        glEnd()

        glScalef(scale.x, scale.z, scale.y)
        getattr(self, name).render(selected=selected)

        glPopMatrix()

    def _render_generic_position(self, cube, position, selected, scale):
        glPushMatrix()
        glTranslatef(position.x, -position.z, position.y)
        glScalef(scale.x, scale.z, scale.y)
        cube.render(selected=selected)

        glPopMatrix()

    def render_generic_position_colored_id(self, position, id, scale=Vector3(1, 1, 1)):
        glPushMatrix()
        glTranslatef(position.x, -position.z, position.y)
        glScalef(scale.x, scale.z, scale.y)
        self.cylinder.render_coloredid(id)
        glPopMatrix()

    def render_generic_position_rotation_colored_id(self, position, rotation, id, scale=Vector3(1, 1, 1)):
        glPushMatrix()
        glTranslatef(position.x, -position.z, position.y)
        do_rotation(rotation)
        glScalef(scale.x, scale.z, scale.y)
        self.cylinder.render_coloredid(id)

        glPopMatrix()

    def render_trans_cylinder(self, position, rotation, scale):
        glPushMatrix()
        glTranslatef(position.x, -position.z, position.y)
        do_rotation(rotation)
        glTranslatef(0, 0, scale.y / 2)
        glScalef(scale.z, scale.x, scale.y)
        self.trans_cylinder.render()
        glPopMatrix()

