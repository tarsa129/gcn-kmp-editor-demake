import os
import json

from collections import OrderedDict
from typing import Any
from PyQt5.QtWidgets import QSizePolicy, QWidget, QVBoxLayout, QPushButton, QGridLayout, QLabel, QScrollArea, QFrame
from lib.vectors import Vector3
from PyQt5.QtCore import pyqtSignal
from lib.libkmp import *
from widgets.tree_view import KMPHeader, EnemyRoutePoint
from widgets.objlists import *
from copy import copy
#will create buttons based on the current selection
#when something selected: add to it from the end

def clear_layout(layout):
    while layout.count():
        widget = layout.takeAt(0).widget()
        if widget is not None:
            widget.deleteLater()

class ButtonSelectPanel(QWidget):
    def __init__(self, text, revealed, options):
        super().__init__()

        vbox = QVBoxLayout(self)
        label = QLabel("Add from " + text)
        vbox.addWidget(label)

        options_widg = QWidget()
        options_grid = QGridLayout(options_widg)

        specific_widg = QWidget()
        specific_grid = QGridLayout(specific_widg)
        grid_widgets = (options_widg, specific_widg)

        #add buttons to reveal / hide the whole thing
        course_btn_ctrl = QPushButton(self)
        if revealed:
            course_btn_ctrl.setText("Hide " + text)
            course_btn_ctrl.clicked.connect(
                lambda: self.hide_self(True, course_btn_ctrl, grid_widgets, text ) )
        else:
            course_btn_ctrl.setText("Reveal " + text)
            course_btn_ctrl.clicked.connect(
                lambda: self.hide_self(False, course_btn_ctrl, grid_widgets, text) )
            for widget in grid_widgets:
                widget.setHidden(True)
        specific_widg.setHidden(True)

        #always have the menu buttons
        for idx, crs in enumerate(options):
            options_grid.addWidget( self.add_obj_group_button(crs, specific_widg),
                                    0 + int(idx / 4), idx % 4 )

        vbox.addWidget(course_btn_ctrl)
        vbox.addWidget(options_widg)
        vbox.addWidget(specific_widg)

    def hide_self(self, hidden_status, btn, widgets, text):
        for widget in widgets:
            widget.setHidden(hidden_status)
        if hidden_status:
            btn.setText("Reveal " + text)
            btn.clicked.connect(
                lambda: self.hide_self(False, btn, widgets, text ))
        else:
            btn.setText("Reveal " + text)
            btn.clicked.connect(
                lambda: self.hide_self(True, btn, widgets, text ))

    def add_obj_group_button(self, text, widget, objids = (101, 102)):
        new_enemy_group = QPushButton(self)
        new_enemy_group.setText(text)
        if text in objidlist.keys():
            objids = objidlist[text]
        new_enemy_group.clicked.connect(
            lambda: self.add_obj_buttons(objids, widget) )
        return new_enemy_group

    def add_obj_buttons(self, objids, widget):
        widget.setHidden(False)
        layout = widget.layout()
        clear_layout(layout)
        for i, objid in enumerate(objids):
            new_object_button = QPushButton(self)
            new_object_button.setText("Add " + OBJECTNAMES[objid])
            new_object_button.clicked.connect( self.geneditor_add(objid))
            layout.addWidget(new_object_button, int(i/2), i % 2)

    def geneditor_add(self, obj):
        gen_editor = self.parent().parent().parent().parent()
        return lambda: gen_editor.button_add_object( obj )

class MoreButtons(QWidget):
    def __init__(self, parent, option = 0):
        super().__init__(parent)
        #self.parent = parent

        self.vbox = QVBoxLayout(self)

    def add_label(self, text):
        label = QLabel( text)
        self.vbox.addWidget(label)

    def add_button(self, text, option, obj):
        new_enemy_group = QPushButton(self)
        new_enemy_group.setText(text)
        gen_editor = self.parent().parent().parent()
        new_enemy_group.clicked.connect(
            lambda: gen_editor.button_add_from_addi_options(option, obj) )
        self.vbox.addWidget(new_enemy_group)

    def add_multi_button(self, text, option, objs):
        new_enemy_group = QPushButton(self)
        new_enemy_group.setText(text)
        gen_editor = self.parent().parent().parent()
        new_enemy_group.clicked.connect(
            lambda: gen_editor.button_add_from_addi_options_multi(option, objs) )
        self.vbox.addWidget(new_enemy_group)

    def add_course_buttons(self, objgrid, obj, btn, speflayout):
        obj.is_revealed = True

        btn.setText("Hide Course Buttons")
        btn.clicked.connect(
            lambda: self.remove_course_buttons(objgrid, obj, btn) )

    #where the list of buttons is defined
    def add_buttons(self, obj = None):
        clear_layout(self.vbox)

        if obj is None or isinstance(obj, KMPHeader):
            return

        if isinstance(obj, (KMPPoint, PointGroup, PointGroups)):
            point_type = "Enemy"
            if isinstance(obj, (ItemPoint, ItemPointGroup, ItemPointGroups) ):
                point_type = "Item"
            if isinstance(obj, (Checkpoint, CheckpointGroup, CheckpointGroups) ):
                point_type = "Checkpoint"

            self.add_label(point_type + " Actions")

            if isinstance(obj, PointGroups):
                self.add_button("v: Add New" + point_type + " Points", "add_enemygroup", obj)

            elif isinstance(obj, KMPPoint):
                self.add_button("v: Add " + point_type + " Points Here", "new_enemy_points", obj)

        if isinstance(obj, (EnemyPointGroups, ItemPointGroups)):
            action_text = "Copy To Item Paths" if isinstance(obj, EnemyPointGroups) else "Copy From Enemy Paths"
            self.add_button(action_text, "copy_enemy_item", obj)

        elif isinstance(obj, CheckpointGroups):
            self.add_button("Auto Key Checkpoints", "auto_keycheckpoints", obj)
            self.add_button("Assign to Closest Respawn", "assign_jgpt_ckpt", obj)

        elif isinstance(obj, Checkpoint):
            self.add_button("Assign to Closest Respawn", "assign_jgpt_ckpt", obj)

        elif isinstance(obj, RoutePoint):
            self.add_button("v: Add Route Points Here", "add_routepoints", obj)

        elif isinstance(obj, MapObjects):
            self.add_label("Objects Actions")
            self.add_button("Auto Route All Objects", "auto_route", obj)

            #add constant objects
            general_groups = ("Gen Use", "Tree", "Enemies", "Audience",
                              "Flying", "KCL", "Misc Hazards", "-",)
            cons_options = ButtonSelectPanel("Object Groups", True, general_groups)
            self.vbox.addWidget(cons_options)

            courses = ("LC", "MMM", "MG", "TF", "MC", "CM", "DKSC", "WGM",
                       "DC", "KC", "MT", "GV", "DDR", "MH", "BC", "RR",
                       "rPB", "rYF", "rGV2", "rMR", "rSL", "rSGB", "rDS", "rWS",
                       "rDS", "rBC3", "rDKJP", "rMC", "rMC3", "rPG", "rDKM", "rBC")
            crs_options = ButtonSelectPanel("Course Groups", False, courses)
            self.vbox.addWidget(crs_options)

        elif isinstance(obj, MapObject):

            route_stuff = obj.route_info

            if route_stuff:
                self.add_button("v: Add Points to End of Route", "add_routepoints_end", obj)
                self.add_button("Auto Route", "auto_route_single", obj)
                self.add_button("Copy and Place Current Object (Same Route)", "generic_copy", obj.copy())
                self.add_button("Copy and Place Current Object (New Route)", "generic_copy_routed", obj.copy())
            else:
                self.add_button("Copy and Place Current Object", "generic_copy", obj.copy())

        elif isinstance(obj, ReplayAreas):
            self.add_button("Add Area/Stationary Cam", "add_rarea_stat", obj)
            self.add_button("Add Area/Stationary Cam", "add_rarea_rout", obj)
            self.add_button("Preview Cameras", "add_rarea_rout", obj)

        elif isinstance(obj, Areas):
            self.add_button("Add Environment Effect Area", "add_area_gener", 1)
            self.add_button("Add BFG Swapper Area", "add_area_gener", 2)
            self.add_button("Add Moving Road Area With Route", "add_area_gener", 3)
            self.add_button("Add Destination Point Area", "add_area_gener", 4)
            self.add_button("Add Minimap Control Area", "add_area_gener", 5)
            self.add_button("Add BBLM Swapper", "add_area_gener", 6)
            self.add_button("Add Flying Boos Area", "add_area_gener", 7)
            self.add_button("Add Object Grouper/Unloading Areas", "add_area_objs", obj)
            self.add_button("Add Fall Boundary Area", "add_area_gener", 10)

        elif isinstance(obj, Area):
            area : Area = obj
            if area.type == 0:
                self.add_button("Copy With Same Camera", "copy_area_camera", obj)
            elif area.type == 3:
                self.add_button("Copy With Same Route", "copy_area_camera", obj)
            elif area.type == 4:
                self.add_button("Assign to Closest Enemypoint", "assign_closest_enemy", obj)

        elif isinstance(obj, OpeningCamera):

            if obj.has_route():
                self.add_button("Copy and Place Camera (New Route)", "generic_copy_routed", obj.copy())
            else:
                self.add_button("Copy and Place Camera", "generic_copy", obj.copy())

        elif isinstance(obj, Cameras):
            self.add_button("Remove Unused Cameras", "remove_unused_cams", obj)
            self.add_button("Add Opening Camera Type 4 (KartPathFollow)", "add_camera", 4)
            self.add_button("Add Opening Camera Type 5 with Route (OP_FixMoveAt)", "add_camera", 5)

            if not obj.get_type(0):
                self.add_button("Add Goal Camera", "add_camera", 0)

            self.add_button("Preview Opening Cams (Not Functional)", "preview_opening", obj)

        elif isinstance(obj, ObjectContainer) and obj.assoc is JugemPoint:
            self.add_button("v: Add Respawn and Assign to Closest Checkpoints", "add_jgpt", True)
            self.add_button("Auto Respawns (Create from Checkpoints)", "autocreate_jgpt", obj)
            self.add_button("Add Respawn", "add_jgpt", False)
            self.add_button("Auto Respawns (Assign All Where Closest)", "assign_jgpt_ckpt", obj)
            self.add_button("Remove Unused Respawn Points", "removed_unused_jgpt", obj)

        elif isinstance(obj, JugemPoint):
            self.add_button("Assign to Checkpoints Where Closest", "assign_jgpt_ckpt", obj)

    def add_buttons_multi(self, objs):
        clear_layout(self.vbox)
        options= self.check_options(objs)
        #item box fill in - two item box

        #align to x and z should always be options
        self.add_multi_button("Align on X Axis", "align_x", objs)
        self.add_multi_button("Align on Z Axis", "align_z", objs)

        if 0 in options:
            self.add_multi_button("Add Item Boxes Between", "aliadd_items_between", options[0])
            self.add_multi_button("Add Item Boxes Between", "add_items_between_ground", options[0])

        if 3 in options:
            self.add_multi_button("Decrease Scale by 5", "dec_enemy_scale", options[3])
            self.add_multi_button("Increase Scale by 5", "inc_enemy_scale", options[3])

    def check_options(self, objs):
        #item box check for fill in
        options = {}
        item_boxes = self.check_objects(objs, (MapObject), "objectid", 101)
        if len(item_boxes) == 2:
            options[0] = item_boxes

        checkpoints = self.check_objects(objs, (Checkpoint))
        if len(checkpoints) > 0 :
            options[2] = checkpoints

        enemy_points = self.check_objects(objs, (EnemyPoint))
        if len(enemy_points) > 0:
            options[3] = enemy_points

        item_points = self.check_objects(objs, (ItemPoint))
        if len(item_points) > 0:
            options[4] = item_points


        return options

    def check_objects(self, objs, obj_types, option_name = None, option = None):
        valid_objs = []
        for obj in objs:
            valid_type = isinstance(obj, obj_types)
            if valid_type:
                if option_name is not None and hasattr(obj, option_name) and getattr(obj, option_name) == option:
                    valid_objs.append(obj)
                elif option_name is None:
                    valid_objs.append(obj)
        return valid_objs

