import os
import json
from OpenGL.GL import *
from .model_rendering import (GenericObject, Model, TexturedModel, Cube, TransModel)
from lib.vectors import Vector3

with open("lib/color_coding.json", "r") as f:
    colors = json.load(f)


def do_rotation(rotation):
    glMultMatrixf( rotation.get_render() )
    scale = 10.0
    glScalef(scale, scale, scale ** 2)



class ObjectModels(object):
    def __init__(self):
        self.models = {}

        self.cube = Cube()
        self.enemypoint = Cube(colors["EnemyRoutes"])
        self.enemypointfirst = Cube(colors["FirstEnemyPoint"])
        self.itempoint = Cube(colors["ItemRoutes"])
        self.itempointfirst = Cube(colors["FirstItemPoint"])

        self.checkpointleft = Cube(colors["CheckpointLeft"])
        self.checkpointright = Cube(colors["CheckpointRight"])

        self.respawn = GenericObject(colors["Respawn"])
        self.unusedrespawn = GenericObject(colors["UnusedRespawn"])

        self.objects = GenericObject(colors["Objects"])
        self.objectpoint = Cube(colors["ObjectRoutes"])
        self.unusedobjectpoint = Cube(colors["UnusedObjectRoutes"])

        self.camera = GenericObject(colors["Camera"])
        self.camerapoint = Cube(colors["CameraRoutes"])

        self.replayareas = GenericObject(colors["ReplayArea"])
        self.replaycameras = GenericObject(colors["ReplayCamera"])
        self.replaycamerapoint = Cube(colors["ReplayCameraRoute"])

        self.areas = GenericObject(colors["Areas"])
        self.areapoint = Cube(colors["AreaRoutes"])

        self.startpoints = GenericObject(colors["StartPoints"])
        self.cannons = GenericObject(colors["Cannons"])
        self.missions = GenericObject(colors["Missions"])

        with open("resources/unitsphere.obj", "r") as f:
            self.sphere = Model.from_obj(f, rotate=True)

        with open("resources/unitcylinder.obj", "r") as f:
            self.cylinder = Model.from_obj(f, rotate=True)

        with open("resources/unitcylinder.obj", "r") as f:
            self.wireframe_cylinder = Model.from_obj(f, rotate=True)

        with open("resources/unitcube_wireframe.obj", "r") as f:
            self.wireframe_cube = Model.from_obj(f, rotate=True)

        with open("resources/arrow_head.obj", "r") as f:
            self.arrow_head = Model.from_obj(f, rotate=True, scale=500.0)

        with open("resources/solidcylinder.obj", "r") as f:
            self.trans_cylinder = TransModel.from_obj(f, rotate=True)

    def init_gl(self):
        for cube in (self.cube,
                     self.enemypoint, self.enemypointfirst, self.itempoint, self.itempointfirst,
                     self.checkpointleft, self.checkpointright,
                     self.respawn, self.unusedrespawn,
                     self.objects, self.objectpoint, self.unusedobjectpoint,
                     self.camera, self.camerapoint,
                     self.replayareas, self.replaycameras, self.replaycamerapoint,
                     self.areas, self.areapoint,
                     self.startpoints, self.cannons, self.missions):
            cube.generate_displists()

    def draw_arrow_head(self, frompos, topos):
        glPushMatrix()
        dir = topos-frompos
        if not dir.is_zero():
            dir.normalize()
            glMultMatrixf([dir.x, -dir.z, 0, 0,
                           -dir.z, -dir.x, 0, 0,
                           0, 0, 1, 0,
                           topos.x, -topos.z, topos.y, 1])
        else:
            glTranslatef(topos.x, -topos.z, topos.y)
        self.arrow_head.render()
        glPopMatrix()
        #glBegin(GL_LINES)
        #glVertex3f(frompos.x, -frompos.z, frompos.y)
        #glVertex3f(topos.x, -topos.z, topos.y)
        #glEnd()

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

        self.cylinder.render()
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

        self.cylinder.render()
        glPopMatrix()

    def render_generic_position(self, position, selected):
        self._render_generic_position(self.cube, position, selected)

    def render_generic_position_colored(self, position, selected, cubename):
        self._render_generic_position(getattr(self, cubename), position, selected)

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

    def _render_generic_position(self, cube, position, selected):
        glPushMatrix()
        glTranslatef(position.x, -position.z, position.y)
        #glTranslatef(position.x, position.y, position.z)
        cube.render(selected=selected)

        glPopMatrix()

    def render_generic_position_colored_id(self, position, id, scale=Vector3(1, 1, 1)):
        glPushMatrix()
        glTranslatef(position.x, -position.z, position.y)
        glScalef(scale.x, scale.z, scale.y)
        self.cube.render_coloredid(id)
        glPopMatrix()

    def render_generic_position_rotation_colored_id(self, position, rotation, id, scale=Vector3(1, 1, 1)):
        glPushMatrix()
        glTranslatef(position.x, -position.z, position.y)
        do_rotation(rotation)
        glScalef(scale.x, scale.z, scale.y)
        self.cube.render_coloredid(id)

        glPopMatrix()

    def render_trans_cylinder(self, position, rotation, scale):
        glPushMatrix()
        glTranslatef(position.x, -position.z, position.y)
        do_rotation(rotation)
        glTranslatef(0, 0, scale.y / 2)
        glScalef(scale.z, scale.x, scale.y)
        self.trans_cylinder.render()
        glPopMatrix()


