from PySide6 import QtCore, QtGui, QtWidgets
from lib.libkmp import KMP,  get_kmp_name, KMPPoint, Area, Camera, PointGroups, MapObject
from widgets.data_editor_options import AREA_TYPES, CAME_TYPES, routed_cameras
import widgets.tooltip_list as ttl

class BaseTreeWidgetItem(QtWidgets.QTreeWidgetItem):

    def get_index_in_parent(self):
        return self.parent().indexOfChild(self)

class ToggleButton(QtWidgets.QPushButton):
    def __init__(self, text, status) -> None:
        super().__init__()

        if text == "V":
            self.yes_icon = QtGui.QIcon('resources/visible.png')
            self.no_icon = QtGui.QIcon('resources/novis.png')
        elif text == "S":
            self.yes_icon = QtGui.QIcon('resources/select.png')
            self.no_icon = QtGui.QIcon('resources/noselec.png')

        self.set_state(status)

    def set_state(self, status):
        self.status = status
        if self.status:
            self.setIcon(self.yes_icon)
        else:
            self.setIcon(self.no_icon)

class VisiSelecButtons(QtWidgets.QWidget):
    def __init__(self, signal, element, status):
        super().__init__()
        self.hlayout = QtWidgets.QHBoxLayout()
        self.visbutton = ToggleButton("V", status[0])
        self.visbutton.clicked.connect(lambda: self.emit_change(0))
        self.visplusbutton = ToggleButton("V", status[0])
        self.visplusbutton.clicked.connect(lambda: self.emit_change(2))
        self.selbutton = ToggleButton("S", status[1])
        self.selbutton.clicked.connect(lambda: self.emit_change(1))
        self.hlayout.addWidget(self.visbutton)
        self.hlayout.addWidget(self.visplusbutton)
        self.hlayout.addWidget(self.selbutton)
        self.setLayout(self.hlayout)

        self.emitter = signal
        self.element = element.replace(" ", "").lower()
    def emit_change(self, index):
        if index == 0:
            if self.visbutton.status: #turning visbutton off
                self.visbutton.set_state(False)
                self.selbutton.set_state(False)
            else: #turning visbutton on
                self.visbutton.set_state(True)
        elif index == 1:
            if self.selbutton.status: #turning selbuton off
                #self.visbutton.set_state(False)
                self.selbutton.set_state(False)
            else: #turning selbutton true
                self.visbutton.set_state(True)
                self.selbutton.set_state(True)
        elif index == 2:
            if self.visplusbutton.status:
                self.visplusbutton.set_state(False)
            else:
                self.visplusbutton.set_state(True)

        self.emitter.emit(self.element, index)

class KMPHeader(QtWidgets.QTreeWidgetItem):
    def __init__(self):
        super().__init__()

        self.setText(0, "Track Settings")


class ObjectGroup(BaseTreeWidgetItem):
    def __init__(self, name, parent=None, bound_to=None):
        if parent is None:
            super().__init__()
        else:
            super().__init__(parent)
        self.setText(1, name)
        self.bound_to = bound_to

    def remove_children(self):
        self.takeChildren()

    def sort(self):
        return

class ObjectGroupObjects(ObjectGroup):
    def sort(self):

        """items = []
        for i in range(self.childCount()):
            items.append(self.takeChild(0))

        items.sort(key=lambda x: x.bound_to.objectid)

        for item in items:
            self.addChild(item)"""
        self.sortChildren(0, QtCore.Qt.SortOrder.AscendingOrder)

class ObjectGroupKartPoints(ObjectGroup):
    def set_name(self):

        if self.bound_to is not None:
            display_string = "Kart Start Points: "
            display_string += "Left, " if self.bound_to.pole_position == 0 else "Right, "
            display_string += "Normal" if self.bound_to.start_squeeze == 0 else "Narrow"

            self.setText(1, display_string)

    def update_name(self):
        self.set_name()
class PointGroup( ObjectGroup):
    def __init__(self, name, parent=None, bound_to=None):
        super().__init__(name, parent, bound_to)

# Groups
class EnemyPointGroup(PointGroup):
    def __init__(self, parent, bound_to):
        super().__init__("Enemy Path", parent=parent, bound_to=bound_to)
        self.update_name()

    def update_name(self):
        index = self.parent().indexOfChild(self)

        self.setText(
            1,
            "Enemy Path {0}".format(index,          self.bound_to.id))

class ItemPointGroup(PointGroup):
    def __init__(self, parent, bound_to):
        super().__init__("Item Path", parent=parent, bound_to=bound_to)
        self.update_name()

    def update_name(self):
        index = self.parent().indexOfChild(self)

        self.setText(
            0,
            "Item Path {0}".format(index,          self.bound_to.id))

class CheckpointGroup(PointGroup):
    def __init__(self, parent, bound_to):
        super().__init__("Checkpoint Group", parent=parent, bound_to=bound_to)
        self.update_name()

    def update_name(self):
        index = self.parent().indexOfChild(self)
        self.setText(0, "Checkpoint Group {0}".format(index))

class ObjectPointGroup(ObjectGroup):
    def __init__(self, parent, bound_to):
        super().__init__("Object Path", parent=parent, bound_to=bound_to)
        self.update_name()

    def update_name(self):
        index = self.parent().indexOfChild(self)
        self.setText(0, "Object Path {0}".format(index))

class CameraPointGroup(ObjectGroup):
    def __init__(self, parent, bound_to):
        super().__init__("Camera Path", parent=parent, bound_to=bound_to)
        self.update_name()

    def update_name(self):
        index = self.parent().indexOfChild(self)
        self.setText(0, "Camera Path {0}".format(index))
# Entries in groups or entries without groups
class NamedItem(BaseTreeWidgetItem):
    def __init__(self, parent, name, bound_to, index=None):
        super().__init__(parent)
        #self.setText(0, name)
        self.bound_to = bound_to
        self.index = index
        self.update_name()

    def update_name(self):
        pass

class RoutePoint(NamedItem):
    def __init__(self, parent, name, bound_to, index=None):
        super().__init__(parent, name, bound_to, index)

class EnemyRoutePoint(RoutePoint):
    def update_name(self):
        group_item = self.parent()
        group = group_item.bound_to
        offset = 0
        groups_item = group_item.parent()

        for i in range(groups_item.childCount()):
            other_group_item = groups_item.child(i)
            if other_group_item == group_item:
                break
            else:
                group_object = other_group_item.bound_to
                offset += len(group_object.points)


        index = group.points.index(self.bound_to)
        #point = group.points[index]


        self.setText(0, "Enemy Point {0} (pos={1})".format(index + offset, index))

class ItemRoutePoint(RoutePoint):
    def update_name(self):
        group_item = self.parent()
        group = group_item.bound_to
        offset = 0
        groups_item = group_item.parent()

        for i in range(groups_item.childCount()):
            other_group_item = groups_item.child(i)
            if other_group_item == group_item:
                break
            else:
                group_object = other_group_item.bound_to
                offset += len(group_object.points)


        index = group.points.index(self.bound_to)
        #point = group.points[index]


        self.setText(0, "Item Point {0} (pos={1})".format(index + offset, index))

class Checkpoint(RoutePoint):
    def __init__(self, parent, name, bound_to):
        super().__init__(parent, name, bound_to)
        bound_to.widget = self

    def update_name(self):
        offset = 0
        group_item = self.parent()
        groups_item = group_item.parent()
        for i in range(groups_item.childCount()):
            other_group_item = groups_item.child(i)
            if other_group_item == group_item:
                break
            else:
                group_object = other_group_item.bound_to
                offset += len(group_object.points)

        group = group_item.bound_to

        index = group.points.index(self.bound_to)

        disp_string = "Checkpoint {0} (pos={1})".format(index+offset, index)
        checkpoint = self.bound_to
        if checkpoint.lapcounter != 0:
            disp_string += ", Lap Counter"
        elif checkpoint.type != 0:
            disp_string += ", Key Checkpoint"
        self.setText(0, disp_string)

class ObjectRoutePoint(NamedItem):
    def update_name(self):
        group_item = self.parent()
        group = group_item.bound_to

        index = group.points.index(self.bound_to)

        self.setText(0, "Object Point {0}".format(index))

class CameraRoutePoint(NamedItem):
    def update_name(self):
        group_item = self.parent()
        group = group_item.bound_to

        index = group.points.index(self.bound_to)

        self.setText(0, "Camera Point {0}".format(index))

class ObjectEntry(NamedItem):
    def __init__(self, parent, name, bound_to):
        super().__init__(parent, name, bound_to)
        bound_to.widget = self

    def update_name(self):
        name = get_kmp_name(self.bound_to.objectid)
        text_descrip = name
        route_info = self.bound_to.route_info()
        obj : MapObject = self.bound_to

        if route_info > 1:
            if obj.route_obj is None:
                text_descrip += " (NEEDS A ROUTE)"
            else:
                text_descrip += " (Routed)"
        elif route_info == 1 and obj.route_obj is not None:
            text_descrip += " (Routed)"

        self.setText(1, text_descrip)
        self.setToolTip(1, self.bound_to.get_description())


    def __lt__(self, other):
        return self.bound_to.objectid < other.bound_to.objectid

class KartpointEntry(NamedItem):
    def update_name(self):
        playerid = self.bound_to.playerid
        if playerid == 0xFF:
            result = "All"
        else:
            result = "ID:{0}".format(playerid)
        self.setText(1, "{0}".format(result))

class AreaEntry(NamedItem):
    def __init__(self, parent, name, bound_to):
        super().__init__(parent, name, bound_to)
        bound_to.widget = self

    def update_name(self):
        area : Area = self.bound_to
        if area.type < len(AREA_TYPES) and area.type >= 0:
            if area.type == 0:
                disp_string = ""
                if area.camera is None:
                    disp_string += "(NEEDS A CAMERA)"
            else:
                disp_string = "{0}".format(AREA_TYPES[area.type])
                if area.type == 2:
                    disp_string += ", (BFG: {0})".format(area.setting1)
                elif area.type == 3:
                    if area.route_obj is not None:
                        disp_string += ", (Routed)"
                    else:
                        disp_string += ", (NEEDS A ROUTE)"
                elif area.type == 4:
                    if area.enemypoint is not None:
                        disp_string += ", (Connected to an enemy point)"
                    else:
                        disp_string += ", (NEEDS AN ENEMY POINT)"
                elif area.type == 6:
                    disp_string += ", (BBLM: {0})".format(area.setting1)
                elif area.type in (8, 9):
                    disp_string += ", (Group: {0})".format(area.setting1)
        else:
            disp_string = "INVALID"
        self.setText(1, disp_string)

class CameraEntry(NamedItem):
    def __init__(self, parent, name, bound_to, index):
        super().__init__(parent, name, bound_to, index)
        bound_to.widget = self

    def update_name(self):
        text_descrip = ""
        camera : Camera = self.bound_to
        if camera.type < len(CAME_TYPES) and camera.type >= 0:
            text_descrip += "{1}".format( camera.type, CAME_TYPES[camera.type])
            if camera.type in routed_cameras:
                if camera.route_obj is not None:
                    text_descrip += " (Routed)"
                else:
                    text_descrip += " (NEEDS A ROUTE)"
        else:
            text_descrip += "INVALID"
        self.setText(1, text_descrip)

class RespawnEntry(NamedItem):
    def update_name(self):
        for i in range(self.parent().childCount()):
            if self == self.parent().child(i):
                #self.setText(0, "Respawn Point {0} (ID: {1})".format(i, self.bound_to.respawn_id))
                self.setText(0, "Respawn ID: {0}".format(i))
                break

class CannonEntry(NamedItem):
    def update_name(self):
        for i in range(self.parent().childCount()):
            if self == self.parent().child(i):
                self.setText(1, "Cannon ID: ({0})".format(self.bound_to.id))
                break

class MissionEntry(NamedItem):
    def update_name(self):
        for i in range(self.parent().childCount()):
            if self == self.parent().child(i):

                self.setText(0, "Mission ID: ({0})".format(self.bound_to.mission_id))
                break

class LevelDataTreeView(QtWidgets.QTreeWidget):
    select_all = QtCore.Signal(ObjectGroup)
    reverse = QtCore.Signal(ObjectGroup)
    duplicate = QtCore.Signal(ObjectGroup)
    split = QtCore.Signal(PointGroup, RoutePoint)
    remove_type = QtCore.Signal(NamedItem)
    select_type = QtCore.Signal(NamedItem)
    remove_all = QtCore.Signal(PointGroups)

    visible_changed = QtCore.Signal(str, int)
    #split_checkpoint = QtCore.Signal(CheckpointGroup, Checkpoint)

    def __init__(self, editor, central_widget, vis_menu):
        super().__init__(central_widget)
        self.vis_menu = vis_menu
        self.editor = editor
        #self.setMaximumWidth(600)
        self.resize(200, self.height())
        self.setColumnCount(2)
        self.setHeaderLabel("Track Data Entries")
        self.setHeaderHidden(True)
        self.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)

        self.kmpheader = self._add_group("Track Info")# MPHeader()
        #self.addTopLevelItem(self.kmpheader)

        self.kartpoints = self._add_group("Kart Start Points", ObjectGroupKartPoints)
        self.enemyroutes = self._add_group("Enemy Routes")
        self.itemroutes = self._add_group("Item Routes")

        self.checkpointgroups = self._add_group("Checkpoints")
        self.respawnpoints = self._add_group("Respawn Points")

        self.objects = self._add_group("Objects", ObjectGroupObjects)
        self.objectareas = self._add_group("Object Areas")

        self.areas = self._add_group("Areas")
        self.replayareas = self._add_group("Replay Cameras")
        self.cameras = self._add_group("Cameras")
        self.cannons = self._add_group("Cannon Points")
        self.missions = self._add_group("Mission Success Points")

        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.run_context_menu)

    def run_context_menu(self, pos):
        item = self.itemAt(pos)

        if isinstance(item, (EnemyRoutePoint, ItemRoutePoint, Checkpoint)):
            context_menu = QtWidgets.QMenu(self)
            split_action = QtGui.QAction("Split Group At", self)

            def emit_current_split():
                item = self.itemAt(pos)
                group_item = item.parent()
                self.split.emit(group_item, item)

            split_action.triggered.connect(emit_current_split)

            context_menu.addAction(split_action)
            context_menu.exec(self.mapToGlobal(pos))
            context_menu.destroy()
            del context_menu
        elif isinstance(item, (EnemyPointGroup, ItemPointGroup, ObjectPointGroup, CameraPointGroup, CheckpointGroup)):
            context_menu = QtWidgets.QMenu(self)
            remove_all_type = QtGui.QAction("Select All", self)
            reverse_action = QtGui.QAction("Reverse", self)

            def emit_remove_tupeall():
                item = self.itemAt(pos)
                self.select_all.emit(item)

            def emit_current_reverse():
                item = self.itemAt(pos)
                self.reverse.emit(item)

            remove_all_type.triggered.connect(emit_remove_tupeall)
            reverse_action.triggered.connect(emit_current_reverse)

            context_menu.addAction(remove_all_type)
            context_menu.addAction(reverse_action)

            if isinstance(item, (EnemyPointGroup, ItemPointGroup) ):
                def emit_current_duplicate():
                    item = self.itemAt(pos)
                    self.duplicate.emit(item)

                duplicate_action = QtGui.QAction("Duplicate", self)
                duplicate_action.triggered.connect(emit_current_duplicate)
                context_menu.addAction(duplicate_action)

            context_menu.exec(self.mapToGlobal(pos))
            context_menu.destroy()
            del context_menu
        elif isinstance(item, (ObjectEntry, AreaEntry)):
            context_menu = QtWidgets.QMenu(self)
            remove_all_type = QtGui.QAction("Remove All of Type", self)
            select_all_type = QtGui.QAction("Select All of Type", self)

            def emit_remove_typeall():
                item = self.itemAt(pos)
                self.remove_type.emit(item)

            def emit_select_typeall():
                item = self.itemAt(pos)
                self.select_type.emit(item)

            remove_all_type.triggered.connect(emit_remove_typeall)
            select_all_type.triggered.connect(emit_select_typeall)

            context_menu.addAction(remove_all_type)
            context_menu.addAction(select_all_type)

            context_menu.exec(self.mapToGlobal(pos))
            context_menu.destroy()
            del context_menu
        elif isinstance(item, ObjectGroup) and isinstance( item.bound_to, PointGroups):
            context_menu = QtWidgets.QMenu(self)
            remove_all = QtGui.QAction("Delete All", self)
            def emit_remove_all_points():
                self.remove_all.emit(item.bound_to)

            remove_all.triggered.connect(emit_remove_all_points)
            context_menu.addAction(remove_all)
            context_menu.exec(self.mapToGlobal(pos))
            context_menu.destroy()
            del context_menu

    def _add_group(self, name, customgroup=None):
        if customgroup is None:
            group = ObjectGroup(name)
        else:
            group = customgroup(name)
        self.addTopLevelItem(group)

        status = self.get_status(name)

        self.setItemWidget(group, 0, VisiSelecButtons(self.visible_changed, name, status))
        return group

    def reset(self):
        self.enemyroutes.remove_children()
        self.itemroutes.remove_children()
        self.checkpointgroups.remove_children()
        self.objects.remove_children()
        self.objectareas.remove_children()
        self.kartpoints.remove_children()
        self.areas.remove_children()
        self.replayareas.remove_children()
        self.cameras.remove_children()
        self.respawnpoints.remove_children()
        self.cannons.remove_children()
        self.missions.remove_children()

    def set_objects(self, kmpdata: KMP):

        # Compute the location (based on indexes) of the currently selected item, if any.
        selected_item_indexes_list = []
        for item in self.selectedItems():
            selected_item_indexes = []
            while item is not None:
                parent_item = item.parent()
                if parent_item is not None:
                    selected_item_indexes.insert(0, parent_item.indexOfChild(item))
                else:
                    selected_item_indexes.insert(0, self.indexOfTopLevelItem(item))
                item = parent_item
            if selected_item_indexes:
                selected_item_indexes_list.append(selected_item_indexes)

        if selected_item_indexes_list:
            initial_item_count = self.count_items()


        # Preserve the expansion state of the top-level items that can have nested groups.
        #enemyroutes_expansion_states = self._get_expansion_states(self.enemyroutes)
        #checkpointgroups_expansion_states = self._get_expansion_states(self.checkpointgroups)

        self.reset()

        for object in kmpdata.objects:
            object_item = ObjectEntry(self.objects, "Object", object)
        
        for objectarea in kmpdata.object_areas:
            item = AreaEntry(self.objectareas, "Object Areas", objectarea)

        self.sort_objects()

        for kartpoint in kmpdata.kartpoints:
            item = KartpointEntry(self.kartpoints, "Kartpoint", kartpoint)

        for area in kmpdata.areas:
            item = AreaEntry(self.areas, "Area", area)

        for cannon in kmpdata.cannonpoints:
            item = CannonEntry(self.cannons, "Cannon Points", cannon)

        for mission in kmpdata.missionpoints:
            item = MissionEntry(self.missions, "Mission Success Point", mission)

        # Restore expansion states.
        #self._set_expansion_states(self.enemyroutes, enemyroutes_expansion_states)
        #self._set_expansion_states(self.itemroutes, enemyroutes_expansion_states)
        #self._set_expansion_states(self.checkpointgroups, checkpointgroups_expansion_states)

        # And restore previous selection.
        items_to_select = []
        if selected_item_indexes_list and initial_item_count == self.count_items():
            for selected_item_indexes in selected_item_indexes_list:
                item = self.topLevelItem(selected_item_indexes.pop(0))
                while selected_item_indexes:
                    index = selected_item_indexes.pop(0)
                    if index < item.childCount():
                        item = item.child(index)
                    else:
                        break
                items_to_select.append(item)

            # Effectively select items without relying on signals which could trigger a considerate
            # number of events for each item.
            with QtCore.QSignalBlocker(self):
                for item in items_to_select:
                    item.setSelected(True)
        self.editor.tree_select_object(items_to_select)
        self.bound_to_group(kmpdata)

    def sort_objects(self):
        self.objects.sort()
        """items = []
        for i in range(self.objects.childCount()):
            items.append(self.objects.takeChild(0))

        items.sort(key=lambda x: x.bound_to.objectid)

        for item in items:
            self.objects.addChild(item)"""

    def bound_to_group(self, levelfile):
        self.kmpheader.bound_to = levelfile
        self.enemyroutes.bound_to = levelfile.enemypointgroups
        self.itemroutes.bound_to = levelfile.itempointgroups
        self.checkpointgroups.bound_to = levelfile.checkpoints
        self.objects.bound_to = levelfile.objects
        self.objectareas.bound_to = levelfile.object_areas
        self.kartpoints.bound_to = levelfile.kartpoints
        levelfile.kartpoints.widget = self.kartpoints
        self.kartpoints.set_name()
        self.areas.bound_to = levelfile.areas
        self.replayareas.bound_to = levelfile.replayareas
        self.cameras.bound_to = levelfile.cameras
        self.respawnpoints.bound_to = levelfile.respawnpoints
        self.cannons.bound_to = levelfile.cannonpoints
        self.missions.bound_to = levelfile.missionpoints

    def _get_expansion_states(self, parent_item: QtWidgets.QTreeWidgetItem) -> 'tuple[bool]':
        expansion_states = []
        for i in range(parent_item.childCount()):
            item = parent_item.child(i)
            expansion_states.append(item.isExpanded())
        return expansion_states

    def _set_expansion_states(self, parent_item: QtWidgets.QTreeWidgetItem, expansion_states: 'tuple[bool]'):
        item_count = parent_item.childCount()
        if item_count != len(expansion_states):
            # If the number of children has changed, it is not possible to reliably restore the
            # state without being very wrong in some cases.
            return

        for i in range(item_count):
            item = parent_item.child(i)
            item.setExpanded(expansion_states[i])

    def get_status(self, name):

        if hasattr(self.vis_menu, name.replace(" ", "").lower() ):
            toggle = getattr(self.vis_menu, name.replace(" ", "").lower() )
            return (toggle.is_visible(), toggle.is_selectable())
        return (None, None)
    
    def count_items(self):
        count = 0

        pending_items = []
        for i in range(self.topLevelItemCount()):
            pending_items.append(self.topLevelItem(i))

        while pending_items:
            item = pending_items.pop()
            count += 1

            for i in range(item.childCount()):
                pending_items.append(item.child(i))

        return count