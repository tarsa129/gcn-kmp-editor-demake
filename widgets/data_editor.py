import os
import json
from copy import copy, deepcopy
import widgets.tooltip_list as ttl

from PySide6 import QtCore, QtGui, QtWidgets
from math import inf
from lib.libkmp import *
from lib.vectors import Vector3
from widgets.data_editor_options import *

def set_attr_mult(objs, attr, value):
    for obj in objs:
        if isinstance(obj, list):
            for this_obj in obj:
                setattr(this_obj, attr, value)
        else:
            setattr(obj, attr, value)
def set_subattrs_mult(objs, attrs, value):
    for obj in objs:
        element = obj
        for attr in attrs[:-1]:
            element = element[int(attr)] if isinstance(element, list) else getattr(element, attr)
        setattr( element, attrs[-1], value)
def set_userdata_mult(objs:list[MapObject], idx, value):
    for obj in objs:
        obj.userdata[idx] = value

#make a common thing to find all common, esp if copy is going to be used
def get_cmn_obj(objs, kmp_file=None):
    if isinstance(objs[0], (KartStartPoints, Cameras)):
        return objs[0]

    try:
        cmn_obj = objs[0].copy()
    except:
        cmn_obj = deepcopy(objs[0])

    if hasattr(cmn_obj, "route_obj"):
        cmn_obj.route_obj = [objs[0].route_obj]
        cmn_obj.route_obj = [x for x in cmn_obj.route_obj if x is not None]

    if len(objs) == 1:
        return cmn_obj

    members = [attr for attr in dir(cmn_obj) if not callable(getattr(cmn_obj, attr)) and not attr.startswith("__")]

    for obj in objs[1:]:
        for member in members:
            if member == "route_obj" and obj.route_info():
                getattr(cmn_obj, member).append(  getattr(obj, member) )
            elif getattr(cmn_obj, member) is not None and getattr(obj, member) is not None:
                if type( getattr(cmn_obj, member) ) == list:
                    cmn_list = getattr(cmn_obj, member)
                    obj_list = getattr(obj, member)
                    if len(cmn_list) != len(obj_list):
                        continue
                    for i in range(len(cmn_list)):
                        if cmn_list[i] != obj_list[i]:
                            cmn_list[i] = None
                elif isinstance( getattr(cmn_obj, member), (Vector3, Rotation) ):
                    cmn_vec = getattr(cmn_obj, member)
                    obj_vec = getattr(obj, member)
                    cmn_vec.x = None if cmn_vec.x != obj_vec.x else cmn_vec.x
                    cmn_vec.y = None if cmn_vec.y != obj_vec.y else cmn_vec.y
                    cmn_vec.z = None if cmn_vec.z != obj_vec.z else cmn_vec.z
                elif isinstance( getattr(cmn_obj, member), (FOV)):
                    cmn_fov = getattr(cmn_obj, member)
                    obj_fov = getattr(obj, member)
                    cmn_fov.start = None if cmn_fov.start != obj_fov.start else cmn_fov.start
                    cmn_fov.end = None if cmn_fov.end != obj_fov.end else cmn_fov.end
                elif getattr(obj, member) != getattr(cmn_obj, member):
                    setattr(cmn_obj, member, None)

    if hasattr(cmn_obj,"route_obj"):
        cmn_obj.route_obj = list(set(cmn_obj.route_obj ))
        cmn_obj.route_obj = [x for x in cmn_obj.route_obj if x is not None]
    return cmn_obj

def load_parameter_names(objectid):
    if (objectid is None) or (not objectid in OBJECTNAMES):
            return None
    name = OBJECTNAMES[objectid]
    path = os.path.join("object_parameters", name+".json")
    with open(path, "r") as f:
        data = json.load(f)
    return data

def clear_layout(layout):
    while layout.count():
        child = layout.itemAt(0)
        if child.widget():
            child.widget().deleteLater()
        if child.layout():
            clear_layout(child.layout())
            child.layout().deleteLater()
        layout.takeAt(0)

class PythonIntValidator(QtGui.QValidator):
    def __init__(self, min, max, parent):
        super().__init__(parent)
        self.min = min
        self.max = max

    def validate(self, p_str, p_int):
        if p_str == "" or p_str == "-":
            return QtGui.QValidator.Intermediate, p_str, p_int

        try:
            result = int(p_str)
        except:
            return QtGui.QValidator.Invalid, p_str, p_int

        if self.min <= result <= self.max:
            return QtGui.QValidator.Acceptable, p_str, p_int
        else:
            return QtGui.QValidator.Invalid, p_str, p_int

    def fixup(self, s):
        pass


class SpinBox(QtWidgets.QSpinBox):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        policy = self.sizePolicy()
        policy.setHorizontalPolicy(QtWidgets.QSizePolicy.Expanding)
        self.setSizePolicy(policy)

    def setValueQuiet(self, value: int):
        with QtCore.QSignalBlocker(self):
            self.setValue(value)


class DoubleSpinBox(QtWidgets.QDoubleSpinBox):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        policy = self.sizePolicy()
        policy.setHorizontalPolicy(QtWidgets.QSizePolicy.Expanding)
        self.setSizePolicy(policy)

        self.setDecimals(4)

        # No buttons in floating-point fields. The decimap part can do with the extra space.
        self.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)

    def setValueQuiet(self, value: float):
        with QtCore.QSignalBlocker(self):
            self.setValue(value)


class ClickableLabel(QtWidgets.QLabel):

    clicked = QtCore.Signal()

    def mouseReleaseEvent(self, event):

        if self.rect().contains(event.pos()):
            event.accept()
            self.clicked.emit()


class ColorPicker(ClickableLabel):

    color_changed = QtCore.Signal(QtGui.QColor)
    color_picked = QtCore.Signal(QtGui.QColor)

    def __init__(self, with_alpha=False):
        super().__init__()

        height = int(self.fontMetrics().height() / 1.5)
        pixmap = QtGui.QPixmap(height, height)
        pixmap.fill(QtCore.Qt.black)
        self.setPixmap(pixmap)
        self.setFixedWidth(height)

        self.color = QtGui.QColor(0, 0, 0, 0)
        self.with_alpha = with_alpha
        self.tmp_color = QtGui.QColor(0, 0, 0, 0)

        self.clicked.connect(self.show_color_dialog)

    def show_color_dialog(self):
        dialog = QtWidgets.QColorDialog(self)
        dialog.setOption(QtWidgets.QColorDialog.DontUseNativeDialog, True)
        if self.with_alpha:
            dialog.setOption(QtWidgets.QColorDialog.ShowAlphaChannel, True)
        dialog.setCurrentColor(self.color)
        dialog.currentColorChanged.connect(self.update_color)
        dialog.currentColorChanged.connect(self.color_changed)

        color = self.color

        accepted = dialog.exec()
        if accepted:
            self.color = dialog.currentColor()
            self.color_picked.emit(self.color)
        else:
            self.color = color
            self.update_color(self.color)
            self.color_changed.emit(self.color)

    def update_color(self, color):
        self.tmp_color = color
        color = QtGui.QColor(color)
        color.setAlpha(255)
        pixmap = self.pixmap()
        pixmap.fill(color)
        self.setPixmap(pixmap)


class DataEditor(QtWidgets.QWidget):
    emit_3d_update = QtCore.Signal()

    def __init__(self, parent, bound_to, kmp_file=None):
        super().__init__(parent)
        self.bound_to = bound_to
        self.vbox = QtWidgets.QVBoxLayout(self)
        self.vbox.setContentsMargins(0, 0, 0, 0)
        self.vbox.setSpacing(3)
        if kmp_file:
            self.kmp_file = kmp_file
        else:
            self.kmp_file = parent.parent().parent().level_file
        self.setup_widgets()

    def catch_text_update(self):
        self.emit_3d_update.emit()

    def setup_widgets(self):
        pass

    def update_data(self):
        pass

    def create_label(self, text):
        label = QtWidgets.QLabel(self)
        label.setText(text)
        return label

    def create_button(self, text):
        button = QtWidgets.QPushButton(self)
        button.setValue(text)
        return button

    def add_label(self, text):
        label = self.create_label(text)
        self.vbox.addWidget(label)
        return label

    def create_labeled_widget(self, parent, text, widget):
        layout = QtWidgets.QHBoxLayout()
        layout.setSpacing(5)
        label = self.create_label(text)
        label.setText(text)
        label.setOpenExternalLinks(True)
        layout.addWidget(label)
        layout.addWidget(widget)
        return layout

    def create_labeled_widgets(self, parent, text, widgetlist):
        layout = QtWidgets.QHBoxLayout()
        layout.setSpacing(5)
        label = self.create_label(text)
        label.setText(text)
        layout.addWidget(label)
        if len(widgetlist) > 1:
            child_layout = QtWidgets.QHBoxLayout()
            child_layout.setSpacing(1)
            child_layout.setContentsMargins(0, 0, 0, 0)
            for widget in widgetlist:
                child_layout.addWidget(widget)
            layout.addLayout(child_layout)
        elif widgetlist:
            layout.addWidget(widgetlist[0])
        return layout, label

    def create_clickable_widgets(self, parent, text, widgetlist):
        layout = QtWidgets.QHBoxLayout()
        label = self.create_button(text)
        layout.addWidget(label)
        for widget in widgetlist:
            layout.addWidget(widget)
        return layout

    def add_checkbox(self, text, attribute, off_value, on_value, return_both=False):
        checkbox = QtWidgets.QCheckBox(self)
        layout = self.create_labeled_widget(self, text, checkbox)

        def checked(state):
            if state == 0:
                set_attr_mult(self.bound_to, attribute, off_value)
            else:
                set_attr_mult(self.bound_to, attribute, on_value)

        checkbox.stateChanged.connect(checked)
        self.vbox.addLayout(layout)

        if return_both:
            return checkbox, layout.itemAt(0).widget()
        return checkbox

    def add_integer_input(self, text, attribute, min_val, max_val, return_both=False):
        spinbox = SpinBox(self)
        spinbox.setRange(min_val, max_val)

        def on_spinbox_valueChanged(value):
            set_attr_mult(self.bound_to, attribute, value)

        spinbox.valueChanged.connect(on_spinbox_valueChanged)

        layout = self.create_labeled_widget(self, text, spinbox)

        self.vbox.addLayout(layout)
        if return_both:
            return spinbox, layout.itemAt(0).widget()
        return spinbox

    def add_integer_input_index(self, text, attribute, index, min_val, max_val):
        line_edit = QtWidgets.QLineEdit(self)
        layout = self.create_labeled_widget(self, text, line_edit)

        line_edit.setValidator(QtGui.QIntValidator(min_val, max_val, self))

        def input_edited():
            text = line_edit.text()
            for obj in self.bound_to:
                mainattr = getattr(obj, attribute)
                mainattr[index] = int(text)

        line_edit.editingFinished.connect(input_edited)
        label = layout.itemAt(0).widget()
        self.vbox.addLayout(layout)

        return label, line_edit

    def add_decimal_input(self, text, attribute, min_val, max_val):
        spinbox = SpinBox(self)
        spinbox.setRange(min_val, max_val)

        def on_spinbox_valueChanged(value):
            set_attr_mult(self.bound_to, attribute, value)

        spinbox.valueChanged.connect(on_spinbox_valueChanged)

        layout = self.create_labeled_widget(self, text, spinbox)
        self.vbox.addLayout(layout)

        return spinbox

    def add_types_widget_index(self, layout, text, attribute, index, widget_type):
        # Certain widget types will be accompanied with arguments.
        if isinstance(widget_type, (list, tuple)):
            widget_type, *widget_type_args = widget_type

        def set_value(value, index=index):
            for obj in self.bound_to:
                getattr(obj, attribute)[index] = value

        if widget_type == "checkbox":
            widget = QtWidgets.QCheckBox()
            widget.stateChanged.connect(lambda state: set_userdata_mult(self.bound_to, index, int(bool(state))))
        elif widget_type == "combobox":
            widget = QtWidgets.QComboBox()
            policy = widget.sizePolicy()
            policy.setHorizontalPolicy(QtWidgets.QSizePolicy.Expanding)
            widget.setSizePolicy(policy)
            widget.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
            for key, value in widget_type_args[0].items():
                widget.addItem(key, value)
            widget.currentIndexChanged.connect(
                lambda index: set_value(widget.itemData(index)))
        else:
            widget = QtWidgets.QSpinBox()
            policy = widget.sizePolicy()
            policy.setHorizontalPolicy(QtWidgets.QSizePolicy.Expanding)
            widget.setSizePolicy(policy)
            widget.setRange(MIN_SIGNED_SHORT, MAX_SIGNED_SHORT)
            widget.valueChanged.connect(set_value)

        layout.addLayout(self.create_labeled_widget(None, text, widget))

        return widget

    def add_text_input(self, text, attribute, maxlength, return_both=False):
        line_edit = QtWidgets.QLineEdit(self)
        layout = self.create_labeled_widget(self, text, line_edit)

        line_edit.setMaxLength(maxlength)

        def input_edited():
            text = line_edit.text()
            text = text.rjust(maxlength)
            set_attr_mult(self.bound_to, attribute, text)

        line_edit.editingFinished.connect(input_edited)
        self.vbox.addLayout(layout)

        if return_both:
            return line_edit, layout.itemAt(0).widget()
        else:
            return line_edit

    def add_dropdown_input(self, text, attribute, keyval_dict, return_both = False):
        #create the combobox
        combobox = QtWidgets.QComboBox(self)
        for key, val in keyval_dict.items():
            combobox.addItem(key, val)

        tt_dict = getattr(ttl, attribute, None)
        try:
            defaultitem = list(tt_dict)[0]
        except TypeError:
            pass
        else:
            if tt_dict is not None and combobox.currentText() == defaultitem:
                combobox.setToolTip(tt_dict[defaultitem])
        policy = combobox.sizePolicy()
        policy.setHorizontalPolicy(QtWidgets.QSizePolicy.Expanding)
        combobox.setSizePolicy(policy)
        #create the layout and label
        layout = self.create_labeled_widget(self, text, combobox)

        def item_selected(index):
            val = combobox.itemData(index)
            if "." in attribute:
                set_subattrs_mult(self.bound_to, attribute.split('.'), val)
            else:
                set_attr_mult(self.bound_to, attribute, val)

            item = combobox.itemText(index)
            if tt_dict is not None and item in tt_dict:
                combobox.setToolTip(tt_dict[item])
            else:
                combobox.setToolTip('')

        combobox.currentIndexChanged.connect(lambda index: item_selected(index))

        self.vbox.addLayout(layout)
        if return_both:
            return combobox, layout.itemAt(0).widget()
        return combobox

    def add_dropdown_spinbox_input(self, text, attribute, keyval_dict, min_val, max_val):
        combobox = QtWidgets.QComboBox(self)
        for val in keyval_dict:
            combobox.addItem(val)

        layout = self.create_labeled_widget(self, text, combobox)

        def item_selected(item):
            val = keyval_dict[item]
            set_attr_mult(self.bound_to, attribute, val)

            tt_dict = getattr(ttl, attribute, None)
            if tt_dict is not None and item in tt_dict:
                combobox.setToolTip(tt_dict[item])
            else:
                combobox.setToolTip('')

        combobox.currentTextChanged.connect(item_selected)

        spinbox = SpinBox(self)
        spinbox.setRange(min_val, max_val)

        def input_edited(value):
            set_attr_mult(self.bound_to, attribute, value)

        spinbox.editingFinished.connect(input_edited)
        layout.addWidget(spinbox)

        self.vbox.addLayout(layout)

        return combobox, spinbox

    def add_multiple_integer_input(self, text, attribute, subattributes, min_val, max_val):
        spinboxes = []
        for subattr in subattributes:
            spinbox = SpinBox(self)

            if max_val <= MAX_UNSIGNED_BYTE:
                spinbox.setMaximumWidth(90)

            spinbox.setRange(min_val, max_val)

            if attribute is not None:
                input_edited = create_setter(spinbox, self.bound_to, attribute, subattr, self.catch_text_update, isFloat=False)
            else:
                def sub_input_edited():
                    value = spinbox.value()
                    set_attr_mult(self.bound_to, value)
                input_edited = sub_input_edited

            spinbox.editingFinished.connect(input_edited)
            spinboxes.append(spinbox)

        layout, labels = self.create_labeled_widgets(self, text, spinboxes)
        self.vbox.addLayout(layout)


        return spinboxes

    def add_multiple_decimal_input(self, text, attribute, subattributes, min_val, max_val, return_both = False):
        spinboxes = []
        for subattr in subattributes:
            spinbox = DoubleSpinBox(self)

            if attribute in ('position', 'start', 'end'):
                spinbox.setSingleStep(10)

            spinbox.setRange(min_val, max_val)

            input_edited = create_setter(spinbox, self.bound_to, attribute, subattr, self.catch_text_update, isFloat=True)
            spinbox.valueChanged.connect(input_edited)
            spinboxes.append(spinbox)

        layout, labels = self.create_labeled_widgets(self, text, spinboxes)
        self.vbox.addLayout(layout)

        if return_both:
            return spinboxes, labels
        return spinboxes

    def add_multiple_integer_input_list(self, text, attribute, min_val, max_val):
        spinboxes = []
        fieldlist = getattr(self.bound_to, attribute)
        for i in range(len(fieldlist)):
            spinbox = SpinBox(self)
            spinbox.setMaximumWidth(self.fontMetrics().averageCharWidth() * 4)
            spinbox.setRange(min_val, max_val)

            input_edited = create_setter_list(spinbox, self.bound_to, attribute, i)
            spinbox.valueChanged.connect(input_edited)
            spinboxes.append(spinbox)

        layout, labels = self.create_labeled_widgets(self, text, spinboxes)
        self.vbox.addLayout(layout)

        return spinboxes

    def add_color_input(self, text, attribute, with_alpha=False):
        spinboxes = []
        input_edited_callbacks = []

        for subattr in ["r", "g", "b", "a"] if with_alpha else ["r", "g", "b"]:
            spinbox = SpinBox(self)
            spinbox.setMaximumWidth(self.fontMetrics().averageCharWidth() * 4)
            spinbox.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
            spinbox.setRange(0, 255)
            input_edited = create_setter(spinbox, self.bound_to,
                                         attribute, subattr,
                                           self.catch_text_update, isFloat=False)
            input_edited_callbacks.append(input_edited)
            spinbox.valueChanged.connect(input_edited)
            spinboxes.append(spinbox)

        color_picker = ColorPicker(with_alpha=with_alpha)

        def on_spinbox_valueChanged(value: int):
            _ = value
            r = spinboxes[0].value()
            g = spinboxes[1].value()
            b = spinboxes[2].value()
            a = spinboxes[3].value() if len(spinboxes) == 4 else 255
            color_picker.color = QtGui.QColor(r, g, b, a)
            color_picker.update_color(color_picker.color)

        for spinbox in spinboxes:
            spinbox.valueChanged.connect(on_spinbox_valueChanged)

        def on_color_changed(color):
            spinboxes[0].setValue(color.red())
            spinboxes[1].setValue(color.green())
            spinboxes[2].setValue(color.blue())
            if len(spinboxes) == 4:
                spinboxes[3].setValue(color.alpha())

        def on_color_picked(color):
            values = [color.red(), color.green(), color.blue()]
            if len(spinboxes) == 4:
                values.append(color.alpha())
            for callback, value in zip(input_edited_callbacks, values):
                callback(value)

        color_picker.color_changed.connect(on_color_changed)
        color_picker.color_picked.connect(on_color_picked)

        layout, label = self.create_labeled_widgets(self, text, spinboxes + [color_picker])
        self.vbox.addLayout(layout)

        return spinboxes, label, color_picker

    def update_rotation(self, xang, yang, zang):
        cmn_obj = get_cmn_obj(self.bound_to)
        rotation = cmn_obj.rotation
        euler_angs = rotation.get_euler()

        xang.setValue(round(euler_angs[0], 4))
        yang.setValue(round(euler_angs[1], 4))
        zang.setValue(round(euler_angs[2], 4))

        #self.bound_to.rotation = Rotation.from_euler(Vector3(x_ang, y_ang, z_ang))
        self.catch_text_update()

    def add_rotation_input(self):

        angle_edits = [] #these are the checkboxes
        for attr in ("x", "y", "z"):
            line_edit = DoubleSpinBox(self)
            line_edit.setRange(-360.0, 360.0)
            angle_edits.append(line_edit)

        def change_angle():
            newup = Vector3(*[(v.value()) for v in angle_edits])
            for obj in self.bound_to:
                obj.rotation = Rotation.from_euler(newup)

            self.update_rotation(*angle_edits)

        for edit in angle_edits:
            edit.editingFinished.connect(change_angle)




        layout, labels = self.create_labeled_widgets(self, "Angles", angle_edits)



        self.vbox.addLayout(layout)

        #return forward_edits, up_edits, left_edits
        return angle_edits

    def update_name(self):
        for obj in self.bound_to:
            if hasattr(obj, "widget") and obj.widget is not None:
                obj.widget.update_name()
                if hasattr(obj.widget, "parent") and obj.widget.parent() is not None:
                    obj.widget.parent().sort()
                obj.widget.setSelected(True)

    def update_vector3(self, attr, vec):
        inputs = getattr(self, attr)
        if vec.x is not None:
            inputs[0].setValue(round(vec.x, 3))
        if vec.y is not None:
            inputs[1].setValue(round(vec.y, 3))
        if vec.z is not None:
            inputs[2].setValue(round(vec.z, 3))

class RoutedEditor(DataEditor):
    def setup_widgets(self):
        super().setup_widgets()
        self.main_thing = QtWidgets.QTabWidget()
        self.vbox.addWidget(self.main_thing)

    def update_route(self):
        route_obj = get_cmn_obj(self.bound_to).route_obj
        clear_layout(self.route_edit.vbox)
        self.route_edit.bound_to = route_obj
        if route_obj:
            self.route_edit.setup_widgets()
            self.route_edit.update_data()
        self.main_thing.setTabEnabled(1, len(route_obj) > 0)

    def update_data(self):
        self.camera_edit.update_data()
        route_obj = get_cmn_obj(self.bound_to).route_obj
        if route_obj:
            self.route_edit.update_data()

def create_setter_list(lineedit, bound_to, attribute, index):
    def input_edited():
        text = lineedit.text()
        mainattr = getattr(bound_to, attribute)
        mainattr[index] = int(text)

    return input_edited

def create_setter(lineedit, bound_to, attribute, subattr, update3dview, isFloat):
    if isFloat:
        def input_edited(text=None):
            text = lineedit.text() if not text else text
            #mainattr = getattr(get_cmn_obj(bound_to), attribute)

            set_subattrs_mult(bound_to, [attribute, subattr], float(text))
            update3dview()
        return input_edited
    else:
        def input_edited(text=None):
            text = lineedit.text() if not text else text
            #mainattr = getattr(get_cmn_obj(bound_to), attribute)

            set_subattrs_mult(bound_to, [attribute, subattr], int(text))
            update3dview()
        return input_edited

MIN_SIGNED_BYTE = -128
MAX_SIGNED_BYTE = 127
MIN_SIGNED_SHORT = -2**15
MAX_SIGNED_SHORT = 2**15 - 1
MIN_SIGNED_INT = -2**31
MAX_SIGNED_INT = 2**31 - 1

MIN_UNSIGNED_BYTE = MIN_UNSIGNED_SHORT = MIN_UNSIGNED_INT = 0
MAX_UNSIGNED_BYTE = 255
MAX_UNSIGNED_SHORT = 2**16 - 1
MAX_UNSIGNED_INT = 2**32 - 1


def choose_data_editor(obj):
    if isinstance(obj, EnemyPoint):
        return EnemyPointEdit
    elif isinstance(obj, EnemyPointGroup):
        return EnemyPointGroupEdit
    elif isinstance(obj, ItemPoint):
        return ItemPointEdit
    elif isinstance(obj, ItemPointGroup):
        return ItemPointGroupEdit
    elif isinstance(obj, CheckpointGroup):
        return CheckpointGroupEdit
    elif isinstance(obj, MapObject):
        return RoutedObjectEdit
    elif isinstance(obj, Checkpoint):
        return CheckpointEdit
    elif isinstance(obj, Route):
        return RouteEdit
    elif isinstance(obj, RoutePoint):
        return ObjectRoutePointEdit
    elif isinstance(obj, KMP):
        return KMPEdit
    elif isinstance(obj, KartStartPoint):
        return KartStartPointEdit
    elif isinstance(obj, KartStartPoints):
        return KartStartPointsEdit
    elif isinstance(obj, Area):
        if obj.type == 0:
            return ReplayAreaEdit
        else:
            return SpecialAreaEdit
    elif isinstance(obj, ReplayCamera):
        return RoutedReplayCameraEdit
    elif isinstance(obj, OpeningCamera):
        return RoutedOpeningCameraEdit
    elif isinstance(obj, GoalCamera):
        return OpeningCameraEdit
    elif isinstance(obj, Cameras):
        return CamerasEdit
    elif isinstance(obj, JugemPoint):
        return RespawnPointEdit
    elif isinstance(obj, CannonPoint):
        return CannonPointEdit
    elif isinstance(obj, MissionPoint):
        return MissionPointEdit
    else:
        return None

class EnemyPointGroupEdit(DataEditor):
    def setup_widgets(self):
        self.groupid = self.add_integer_input("Group ID", "id", MIN_UNSIGNED_BYTE, MAX_UNSIGNED_BYTE)

        self.prevgroup = self.add_multiple_integer_input_list("Previous Groups", "prevgroup",
                                                              MIN_SIGNED_SHORT, MAX_SIGNED_SHORT)
        self.nextgroup = self.add_multiple_integer_input_list("Next Groups", "nextgroup",
                                                              MIN_SIGNED_SHORT, MAX_SIGNED_SHORT)

        self.groupid.setReadOnly(True)
        for widget in self.prevgroup:
            widget.setReadOnly(True)
        for widget in self.nextgroup:
            widget.setReadOnly(True)

    def update_data(self):
        obj : EnemyPointGroup = self.bound_to

        self.groupid.setValue(self.bound_to.id)
        for i, widget in enumerate(self.prevgroup):
            widget.setValue(obj.prevgroup[i])
        for i, widget in enumerate(self.nextgroup):
            widget.setValue(obj.nextgroup[i])

class EnemyPointEdit(DataEditor):
    def setup_widgets(self, group_editable=False):
        self.position = self.add_multiple_decimal_input("Position", "position", ["x", "y", "z"],
                                                        -inf, +inf)
        self.scale = self.add_decimal_input("Scale", "scale", 0, 100000)
        self.scale.setToolTip(ttl.enemypoints["Scale"])

        self.enemyaction = self.add_dropdown_input("Enemy Action 1", "enemyaction", ENPT_Setting1)
        self.enemyaction2 = self.add_dropdown_input("Enemy Action 2", "enemyaction2", ENPT_Setting2)

        self.unknown = self.add_integer_input("Unknown", "unknown",
                                            MIN_UNSIGNED_BYTE, MAX_UNSIGNED_BYTE)

    def update_data(self):
        obj: EnemyPoint = get_cmn_obj(self.bound_to)
        self.update_vector3("position", obj.position)

        if obj.scale is not None:
            self.scale.setValue(obj.scale)
        if obj.enemyaction  is not None:
            if obj.enemyaction < len(ENPT_Setting1):
                self.enemyaction.setCurrentIndex(obj.enemyaction)
            else:
                self.enemyaction.setCurrentIndex(-1)
        if obj.enemyaction2 is not None:
            if obj.enemyaction2 < len(ENPT_Setting2):
                self.enemyaction2.setCurrentIndex(obj.enemyaction2)
            else:
                self.enemyaction2.setCurrentIndex(-1)
        if self.unknown is not None: self.unknown.setValue(obj.unknown)

class ItemPointGroupEdit(DataEditor):
    def setup_widgets(self):
        #self.groupid = self.add_integer_input("Group ID", "id", MIN_UNSIGNED_BYTE, MAX_UNSIGNED_BYTE)

        self.prevgroup = self.add_multiple_integer_input_list("Previous Groups", "prevgroup",
                                                              MIN_SIGNED_SHORT, MAX_SIGNED_SHORT)
        self.nextgroup = self.add_multiple_integer_input_list("Next Groups", "nextgroup",
                                                              MIN_SIGNED_SHORT, MAX_SIGNED_SHORT)

    def update_data(self):
        obj = self.bound_to
        for i, widget in enumerate(self.prevgroup):
            widget.setValue(obj.prevgroup[i])
        for i, widget in enumerate(self.nextgroup):
            widget.setValue(obj.nextgroup[i])

class ItemPointEdit(DataEditor):
    def setup_widgets(self, group_editable=False):
        self.position = self.add_multiple_decimal_input("Position", "position", ["x", "y", "z"],
                                                        -inf, +inf)
        self.scale = self.add_decimal_input("Bullet Bill Range", "scale", 0, 100000)

        self.setting1 = self.add_dropdown_input("Enemy Action 1", "setting1", ITPT_Setting1)
        self.unknown = self.add_checkbox("Unknown", "unknown", off_value=0, on_value=1)
        self.lowpriority = self.add_checkbox("Low Priority", "lowpriority", off_value=0, on_value=1)
        self.dontdrop = self.add_checkbox("Don't Drop Bill", "dontdrop", off_value=0, on_value=1)


    def update_data(self):
        obj: ItemPoint = get_cmn_obj(self.bound_to)
        self.update_vector3("position", obj.position)

        if obj.setting1 < len(ITPT_Setting1):
            self.setting1.setCurrentIndex(obj.setting1)
        else:
            self.setting1.setCurrentIndex(-1)

        if obj.scale is not None: self.scale.setValue(obj.scale)

        self.unknown.setChecked( obj.unknown !=0 )
        self.lowpriority.setChecked( obj.lowpriority !=0 )
        self.dontdrop.setChecked( obj.dontdrop !=0 )

class CheckpointGroupEdit(DataEditor):


    def setup_widgets(self):
        #self.id = self.add_integer_input("Group ID", "id", MIN_UNSIGNED_SHORT, MAX_UNSIGNED_SHORT)
        self.prevgroup = self.add_multiple_integer_input_list("Previous Groups", "prevgroup",
                                                              MIN_SIGNED_SHORT, MAX_SIGNED_SHORT)
        self.nextgroup = self.add_multiple_integer_input_list("Next Groups", "nextgroup",
                                                              MIN_SIGNED_SHORT, MAX_SIGNED_SHORT)

    def update_data(self):
        obj = self.bound_to
        for i, widget in enumerate(self.prevgroup):
            widget.setValue(obj.prevgroup[i])
        for i, widget in enumerate(self.nextgroup):
            widget.setValue(obj.nextgroup[i])

class CheckpointEdit(DataEditor):
    def setup_widgets(self):
        self.start = self.add_multiple_decimal_input("Start", "start", ["x", "z"],
                                                        -inf, +inf)
        self.end = self.add_multiple_decimal_input("End", "end", ["x", "z"],
                                                     -inf, +inf)

        self.lapcounter = self.add_checkbox("Lap Counter", "lapcounter",
                                      0, 1)
        self.type = self.add_checkbox("Key Checkpoint", "type",
                                      0, 1)
        self.lapcounter.stateChanged.connect(self.update_checkpoint_types)
        self.type.stateChanged.connect(self.update_checkpoint_types)

    def update_data(self):
        obj: Checkpoint = get_cmn_obj(self.bound_to)

        if obj.start.x is not None:
            self.start[0].setValue(round(obj.start.x, 3))
        if obj.start.z is not None:
            self.start[1].setValue(round(obj.start.z, 3))

        if obj.end.x is not None:
            self.end[0].setValue(round(obj.end.x, 3))
        if obj.end.z is not None:
            self.end[1].setValue(round(obj.end.z, 3))

        if obj.lapcounter is not None:
            self.lapcounter.setChecked(obj.lapcounter != 0)
        if obj.type is not None:
            self.type.setChecked(obj.type != 0)

        self.update_checkpoint_types()

    def update_checkpoint_types(self):
        obj: Checkpoint = get_cmn_obj(self.bound_to)
        self.type.setDisabled( obj.lapcounter != 0 )
        self.lapcounter.setDisabled( obj.type != 0)
        self.update_name()

    def update_name(self):
        super().update_name()

class RouteEdit(DataEditor):
    def setup_widgets(self):
        self.smooth = self.add_dropdown_input("Sharp/Smooth motion", "smooth", POTI_Setting1)
        self.cyclic = self.add_dropdown_input("Cyclic/Back and forth motion", "cycle", POTI_Setting2)

    def update_data(self):
        obj: Route = get_cmn_obj(self.bound_to)
        if obj.smooth is not None:
            self.smooth.setCurrentIndex( min(obj.smooth, 1))
        if obj.cyclic is not None:
            self.cyclic.setCurrentIndex( min(obj.cyclic, 1))
        has_twopoint = all(len(obj.points) > 2 for obj in self.bound_to )
        self.smooth.setDisabled(not has_twopoint)


class CameraRouteEdit(RouteEdit):
    def setup_widgets(self):
        if len(self.bound_to) == 0:
            return
        super().setup_widgets()
        self.widgets = []

        if len(self.bound_to) != 1 or self.bound_to[0] is None:
            return
        for i, point in enumerate(self.bound_to[0].points):
            routepointedit = CameraRoutePointEdit(self.parent(), [point], i, self.kmp_file)
            self.vbox.addWidget(routepointedit)
            self.widgets.append(routepointedit)

    def update_data(self):
        super().update_data()
        for widget in self.widgets:
            widget.update_data()

class AreaRouteEdit(RouteEdit):
    def setup_widgets(self):
        if len(self.bound_to) == 0:
            return
        super().setup_widgets()
        self.widgets = []

        if len(self.bound_to) != 1:
            return
        for i, point in enumerate(self.bound_to[0].points):
            routepointedit = AreaRoutePointEdit(self.parent(), [point], i, self.kmp_file)
            self.vbox.addWidget(routepointedit)
            self.widgets.append(routepointedit)

    def update_data(self):
        super().update_data()
        for widget in self.widgets:
            widget.update_data()

class ObjectRoutePointEdit(DataEditor):
    def setup_widgets(self):
        self.position = self.add_multiple_decimal_input("Position", "position", ["x", "y", "z"],
                                                        -inf, +inf)
        labels = [[], []]

        #obj: RoutePoint = get_cmn_obj(self.bound_to, self.kmp_file)
        routes = []
        for point in self.bound_to:
            routes.append(self.kmp_file.get_route_of_point(point))

        used_by = []
        for route in routes:
            used_by.extend(self.kmp_file.route_used_by(route))

        for mapobject in used_by:
            point_labels = mapobject.get_route_text()
            if point_labels is not None:
                if point_labels[0] is not None and not point_labels[0] in labels[0]:
                    labels[0].append(point_labels[0])
                if point_labels[1] is not None and not point_labels[1] in labels[1]:
                    labels[1].append(point_labels[1])

        labels[0] = ", ".join(labels[0]) if labels[0] else "Setting 1"
        labels[1] = ", ".join(labels[1]) if labels[1] else "Setting 2"

        self.unk1 = self.add_integer_input(labels[0], "unk1",
                                              MIN_UNSIGNED_SHORT, MAX_UNSIGNED_SHORT)
        self.unk2 = self.add_integer_input(labels[1], "unk2",
                                              MIN_UNSIGNED_SHORT, MAX_UNSIGNED_SHORT)

    def update_data(self):
        obj: RoutePoint = get_cmn_obj(self.bound_to, self.kmp_file)
        self.update_vector3("position", obj.position)
        if obj.unk1 is not None:
            self.unk1.setValue(obj.unk1)
        if obj.unk2 is not None:
            self.unk2.setValue(obj.unk2)

class KMPEdit(DataEditor):
    def setup_widgets(self):

        self.lap_count = self.add_integer_input("Lap Count", "lap_count",
                                        MIN_UNSIGNED_BYTE, MAX_UNSIGNED_BYTE)

        #self.speed_modifier = self.add_decimal_input("Speed Modifier", "speed_modifier", 0, 10000)



        self.lens_flare = self.add_checkbox("Enable Lens Flare", "lens_flare",
                                            off_value=0, on_value=1)
        self.lens_flare.stateChanged.connect(self.set_flare_visible)

        self.flare_color, self.flare_color_label, self.fc_picker = self.add_color_input("Flare Color", "flare_color")
        self.flare_alpha, self.flare_alpha_label = self.add_integer_input("Flare Alpha %", "flare_alpha",
                                           MIN_UNSIGNED_BYTE, MAX_UNSIGNED_BYTE, return_both=True)


    def update_data(self):
        obj: KMP = self.bound_to[0]
        self.lap_count.setValueQuiet(obj.lap_count)
        self.lens_flare.setChecked(obj.lens_flare != 0)

        self.flare_color[0].setValueQuiet(obj.flare_color.r)
        self.flare_color[1].setValueQuiet(obj.flare_color.g)
        self.flare_color[2].setValueQuiet(obj.flare_color.b)
        self.flare_alpha.setValueQuiet(obj.flare_alpha)

        self.set_flare_visible()
        #self.speed_modifier.setValue(obj.speed_modifier)

    def set_flare_visible(self):
        self.flare_color[0].setVisible(self.lens_flare.isChecked())
        self.flare_color[1].setVisible(self.lens_flare.isChecked())
        self.flare_color[2].setVisible(self.lens_flare.isChecked())
        self.flare_color_label.setVisible(self.lens_flare.isChecked())
        self.fc_picker.setVisible(self.lens_flare.isChecked())
        self.flare_alpha.setVisible(self.lens_flare.isChecked())
        self.flare_alpha_label.setVisible(self.lens_flare.isChecked())


    def open_color_picker_light(self, attrib):
        obj = self.bound_to[0]


        color_dia = QtWidgets.QColorDialog(self)

        color = color_dia.getColor()
        if color.isValid():
            color_comps = color.getRgbF()
            color_vec = getattr(obj, attrib )

            color_vec.r = int(color_comps[0] * 255)
            color_vec.g = int(color_comps[1] * 255)
            color_vec.b = int(color_comps[2] * 255)

            self.update_data()

class RoutedObjectEdit(RoutedEditor):
    def setup_widgets(self):
        super().setup_widgets()
        self.camera_edit = ObjectEdit(self.parent(), self.bound_to)
        route_obj = get_cmn_obj(self.bound_to).route_obj
        self.route_edit = RouteEdit(self.parent(), route_obj)

        self.main_thing.addTab(self.camera_edit, "Object")
        self.main_thing.addTab(self.route_edit, "Route")

        self.main_thing.setTabEnabled(1, len(route_obj) > 0)

class ObjectEdit(DataEditor):
    #want it so that in the making stage, changing the id changes the defaults
    #once the object has been created fully, then changing the id changes the defaults

    def setup_widgets(self, inthemaking = False):
        self.position = self.add_multiple_decimal_input("Position", "position", ["x", "y", "z"],
                                                        -inf, +inf)
        self.scale = self.add_multiple_decimal_input("Scale", "scale", ["x", "y", "z"],
                                                    -inf, +inf)
        self.rotation = self.add_rotation_input()
        self.objectid, self.objectid_edit = self.add_dropdown_spinbox_input("Object Type", "objectid", REVERSEOBJECTNAMES, 1, 755)
        self.objectid.currentTextChanged.disconnect()
        self.objectid_edit.editingFinished.disconnect()

        self.single = self.add_checkbox("Enable in single player mode", "single", 0, 1)
        self.double = self.add_checkbox("Enable in two player mode", "double", 0, 1)
        self.triple = self.add_checkbox("Enable in three/four player mode", "triple", 0, 1)

        self.userdata = [None] * 8
        self.userdata_layout = QtWidgets.QVBoxLayout()
        self.vbox.addLayout(self.userdata_layout)

        self.objectid.currentTextChanged.connect(self.object_id_combo_changed)
        self.objectid_edit.editingFinished.connect(self.object_id_edit_changed)

        if (inthemaking):
            self.set_default_values()

        self.description = self.add_label("")
        self.description.setWordWrap(True)
        self.description.setOpenExternalLinks(True)
        hint = self.description.sizePolicy()
        hint.setVerticalPolicy(QtWidgets.QSizePolicy.Minimum)
        self.description.setSizePolicy(hint)


        self.assets = self.add_label("Required Assets: Unknown")
        self.assets.setWordWrap(True)
        hint = self.assets.sizePolicy()
        hint.setVerticalPolicy(QtWidgets.QSizePolicy.Minimum)
        self.assets.setSizePolicy(hint)

    def object_id_edit_changed(self):
        new = self.objectid_edit.value() #grab value from the lineedit
        if new not in REVERSEOBJECTNAMES.values():
            if self.old_objectid is not None:
                self.update_lineedit(self.old_objectid)
            return

        self.update_combobox(new) #use it to update the combobox
        self.update_name(new) #do the main editing
        self.rename_object_parameters( new, True )

    def object_id_combo_changed(self):
        new = REVERSEOBJECTNAMES[ self.objectid.currentText() ] #grab id from combobox
        self.update_lineedit(new)
        self.update_name( new )
        self.rename_object_parameters( new, True )

    def update_name(self, new):
        for obj in self.bound_to:
            obj.objectid = new
        if self.bound_to[0].route_info() == 2:
            for obj in self.bound_to:
                obj.create_route(True, None, True)
        self.set_default_values()

        super().update_name()

    def get_objectname(self, objectid):
        if objectid not in OBJECTNAMES:
            return "INVALID"
        else:
            return OBJECTNAMES[objectid]

    def update_lineedit(self, objectid):
        with QtCore.QSignalBlocker(self.objectid_edit):
            if objectid is not None:
                self.objectid_edit.setValue(objectid)

    def update_combobox(self, objectid):
        with QtCore.QSignalBlocker(self.objectid):
            name = self.get_objectname(objectid)
            index = self.objectid.findText(name)
            self.objectid.setCurrentIndex(index)

    def rename_object_parameters(self, current, load_defaults=False):
        for i in range(8):
            self.userdata[i] = None
        clear_layout(self.userdata_layout)

        json_data = load_parameter_names(current)
        if json_data is None:
            parameter_names = ["Unknown"] * 8
            tooltips = [None] * 8
            widgets = [None] * 8
            assets = None
            description = None
        else:
            parameter_names = json_data["Object Parameters"]
            tooltips = json_data["Tooltips"] if "Tooltips" in json_data else [None] * 8
            widgets = json_data["Widgets"] if "Widgets" in json_data else [None] * 8
            assets = json_data["Assets"]
            description = json_data["Description"]
        tuples = zip(parameter_names, tooltips, widgets)

        for i, (parameter_name, tooltip, widget_type) in enumerate(tuples):
            if parameter_name == "Unused":
                continue

            widget = self.add_types_widget_index(self.userdata_layout, parameter_name, 'userdata',
                                                 i, widget_type)
            widget.setToolTip(tooltip)
            self.userdata[i] = widget

        if load_defaults:
            self.set_default_values()

        if not description:
            self.description.setText("")
        else:
            self.description.setText(description)

        if not assets:
            self.assets.setText("Required Assets: None")
        else:
            self.assets.setText("Required Assets: {0}".format(", ".join(assets)))

    def set_default_values(self):

        objs = self.bound_to
        if not MapObject.all_of_same_id(objs):
            self.update_data()
            return

        first_obj = objs[0]

        if first_obj.objectid in OBJECTNAMES:

            defaults = first_obj.get_default_values()

            if defaults is not None:
                defaults = [0 if x is None else x for x in defaults]
            else:
                defaults = [None] * 8

            for obj in objs:
                obj.userdata = defaults.copy()

            self.update_userdata_widgets(first_obj)

        self.update_data()
    def update_data(self, load_defaults = False):
        obj: MapObject = get_cmn_obj(self.bound_to)

        self.update_vector3("position", obj.position)
        self.update_vector3("rotation", obj.rotation)
        self.update_vector3("scale", obj.scale)

        self.update_combobox(obj.objectid)
        if self.objectid is not None:
            self.update_lineedit(obj.objectid)

        self.old_objectid = obj.objectid

        self.rename_object_parameters( obj.objectid )

        self.single.setChecked( obj.single != 0 and obj.single != None)
        self.double.setChecked( obj.double != 0 and obj.double != None)
        self.triple.setChecked( obj.triple != 0 and obj.triple != None)

        if load_defaults:
            self.set_default_values()
        else:
            self.update_userdata_widgets(obj)
        """
        obj: Route = obj.route_obj

        if len(obj) == 1:
            self.smooth.setCurrentIndex( min(obj[0].smooth, 1))
            self.cyclic.setCurrentIndex( min(obj[0].cyclic, 1))

        
        has_route = len(obj) > 0
        self.smooth.setVisible(has_route)
        self.smooth_label.setVisible(has_route)
        self.cyclic.setVisible(has_route)
        self.cyclic_label.setVisible(has_route)"""
    def update_userdata_widgets(self, obj, values=None):
        if values is None:
            values = obj.userdata
        for i, value in enumerate(values):
            widget = self.userdata[i]
            if widget is None or value is None:
                continue
            with QtCore.QSignalBlocker(widget):
                if isinstance(widget, QtWidgets.QCheckBox):
                    widget.setChecked(bool(value))
                elif isinstance(widget, QtWidgets.QComboBox):
                    index = widget.findData(value)
                    widget.setCurrentIndex(index if index != -1 else 0)
                elif isinstance(widget, QtWidgets.QSpinBox):
                    widget.setValue(value)

class BooEdit(ObjectEdit):
    def setup_widgets(self, inthemaking = False):
        super().setup_widgets()
        self.objectid.setVisible(False)
        self.objectid_edit.setVisible(False)


class KartStartPointsEdit(DataEditor):
    def setup_widgets(self):
        self.pole_position = self.add_dropdown_input("Pole Position", "pole_position", POLE_POSITIONS )
        self.start_squeeze = self.add_dropdown_input("Start Distance", "start_squeeze", START_SQUEEZE )

        self.pole_position.currentIndexChanged.connect(self.update_starting_info)
        self.start_squeeze.currentIndexChanged.connect(self.update_starting_info)
    def update_data(self):
        obj: KartStartPoints = self.bound_to[0]
        self.pole_position.setCurrentIndex( min(1, obj.pole_position) )
        self.start_squeeze.setCurrentIndex( min(1, obj.start_squeeze) )

    def update_starting_info(self):
        #self.bound_to[0].pole_position = self.pole_position.currentIndex()
        #self.bound_to[0].start_squeeze = self.start_squeeze.currentIndex()
        self.update_name()

class KartStartPointEdit(DataEditor):
    def setup_widgets(self):
        self.position = self.add_multiple_decimal_input("Position", "position", ["x", "y", "z"],
                                                        -inf, +inf)
        self.rotation = self.add_rotation_input()

        self.playerid = self.add_integer_input("Player ID", "playerid",
                                               MIN_UNSIGNED_BYTE, MAX_UNSIGNED_BYTE)


    def update_data(self):
        obj: KartStartPoint = get_cmn_obj(self.bound_to)
        self.update_vector3("position", obj.position)
        self.update_vector3("rotation", obj.rotation)
        self.playerid.setValue(obj.playerid)

class AreaEdit(DataEditor):

    def setup_widgets(self):
        self.position = self.add_multiple_decimal_input("Position", "position", ["x", "y", "z"],
                                                        -inf, +inf)
        self.scale = self.add_multiple_decimal_input("Scale", "scale", ["x", "y", "z"],
                                                     0, +inf)
        self.rotation = self.add_rotation_input()

        self.area_type, self.area_type_label = self.add_dropdown_input("Area Type", "type", AREA_Type, True)

        self.shape = self.add_dropdown_input("Shape", "shape", AREA_Shape)

        self.priority = self.add_integer_input("Priority", "priority",
                                           MIN_UNSIGNED_BYTE, MAX_UNSIGNED_BYTE)

        self.setting1, self.setting1_label = self.add_integer_input("Setting 1", "setting1", MIN_UNSIGNED_SHORT, MAX_UNSIGNED_SHORT, True)
        self.setting2, self.setting2_label = self.add_integer_input("Setting 2", "setting2", MIN_UNSIGNED_SHORT, MAX_UNSIGNED_SHORT, True)

        self.area_type.currentIndexChanged.connect(self.update_name)

    def update_data(self):
        obj: Area = get_cmn_obj(self.bound_to)
        self.update_vector3("position", obj.position)
        self.update_vector3("rotation", obj.rotation)
        self.update_vector3("scale", obj.scale)

        if obj.type != 0:
            typeindex = self.area_type.findData(obj.type )
            with QtCore.QSignalBlocker(self.area_type):
                self.area_type.setCurrentIndex(typeindex if typeindex != -1 else 1)

        self.area_type.setVisible(obj.type != 0)
        self.area_type_label.setVisible(obj.type != 0)

        if obj.shape is not None: self.shape.setCurrentIndex( obj.shape )

        if obj.priority is not None: self.priority.setValue(obj.priority)

        if obj.setting1 is not None: self.setting1.setValue(obj.setting1)
        if obj.setting2 is not None: self.setting2.setValue(obj.setting2)

        self.set_settings_visible()

    def set_settings_visible(self):
        obj: Area = get_cmn_obj(self.bound_to)
        if obj is not None:

            setting1_labels = { 2: "BFG Entry", 3: "Acceleration Modifier", 6: "BBLM Entry", 8: "Group ID", 9: "Group ID" }
            self.setting1.setVisible(obj.type in setting1_labels )
            if obj.type in setting1_labels:
                self.setting1_label.setText(setting1_labels[ obj.type ])
            self.setting1_label.setVisible(obj.type in setting1_labels)

            setting2_labels = { 3: "Moving Water Speed", 6: "Transition Time (frames)"}
            self.setting2.setVisible(obj.type in setting2_labels)
            if obj.type in setting2_labels:
                self.setting2_label.setText( setting2_labels[obj.type]   )
            self.setting2_label.setVisible(obj.type in setting2_labels)
        else:
            self.setting1_label.setText("Setting 1")
            self.setting1_label.setVisible(True)
            self.setting1_label.setText("Setting 2")
            self.setting2_label.setVisible(True)

    def update_name(self):
        self.set_settings_visible()
        for area in self.bound_to:
            area.change_type(area.type)
        super().update_name()

class ReplayAreaEdit(DataEditor):

    def setup_widgets(self):
        self.main_thing = QtWidgets.QTabWidget()
        self.vbox.addWidget(self.main_thing)

        self.area_edit = AreaEdit(self.parent(), self.bound_to)
        cameras = [x.camera for x in self.bound_to]
        self.camera_edit = ReplayCameraEdit(self.parent(), cameras)
        #the problem call
        route_obj = get_cmn_obj(cameras).route_obj
  
        self.route_edit = CameraRouteEdit(self.parent(), route_obj)

        self.main_thing.addTab(self.area_edit, "Area")
        self.main_thing.addTab(self.camera_edit, "Camera")
        self.main_thing.addTab(self.route_edit, "Route")

        self.main_thing.setTabEnabled(2, len(route_obj) > 0)
    def update_data(self):
        self.area_edit.update_data()
        self.camera_edit.update_data()
        cameras = [x.camera for x in self.bound_to]
        route_obj = get_cmn_obj(cameras).route_obj

        if route_obj:
            self.route_edit.update_data()

    def update_route(self):
        cameras = [x.camera for x in self.bound_to]
        route_obj = get_cmn_obj(cameras).route_obj
        clear_layout(self.route_edit.vbox)
        self.route_edit.bound_to = route_obj
        if route_obj:
            self.route_edit.setup_widgets()
            self.route_edit.update_data()
        self.main_thing.setTabEnabled(2, len(route_obj) > 0)

class RoutedOpeningCameraEdit(RoutedEditor):
    def setup_widgets(self):
        super().setup_widgets()
        self.camera_edit = OpeningCameraEdit(self.parent(), self.bound_to)
        route_obj = get_cmn_obj(self.bound_to).route_obj
        self.route_edit = CameraRouteEdit(self.parent(), route_obj)

        self.main_thing.addTab(self.camera_edit, "Camera")
        self.main_thing.addTab(self.route_edit, "Route")

        self.main_thing.setTabEnabled(1, len(route_obj) > 0)

class RoutedReplayCameraEdit(ReplayAreaEdit):
    def __init__(self, parent, bound_to, kmp_file=None):
        if kmp_file:
            self.kmp_file = kmp_file
        else:
            self.kmp_file = parent.parent().parent().level_file
        areas = []
        for cam in bound_to:
            areas.extend(self.kmp_file.camera_used_by(cam))

        super().__init__(parent, areas, kmp_file)
    def setup_widgets(self):
        super().setup_widgets()
        self.main_thing.setCurrentIndex(1)

class CameraEdit(DataEditor):
    def setup_widgets(self):

        self.position, self.position_label = self.add_multiple_decimal_input("Position", "position", ["x", "y", "z"],
                                                        -inf, +inf, True)

        self.follow_player, self.follow_player_label = self.add_checkbox("Follow Player", "follow_player", 0, 1, True)

        self.pos2_simp, self.pos2_l_simp = self.add_multiple_decimal_input("Start Point", "position2_simple", ["x", "y", "z"],
                                                        -inf, +inf, True)
        self.pos3_simp, self.pos3_l_simp = self.add_multiple_decimal_input("End Point", "position3_simple", ["x", "y", "z"],
                                                        -inf, +inf, True)
        self.pos2_play, self.pos2_l_play = self.add_multiple_decimal_input("Start Point", "position2_player", ["x", "y", "z"],
                                                        -inf, +inf, True)
        self.pos3_play, self.pos3_l_play= self.add_multiple_decimal_input("End Point", "position3_player", ["x", "y", "z"],
                                                        -inf, +inf, True)
        self.viewspeed, self.viewspeed_label = self.add_integer_input("View Speed", "viewspeed", MIN_UNSIGNED_SHORT, MAX_UNSIGNED_SHORT, True)

        self.type, self.type_label = self.add_dropdown_input("Camera Type", "type", CAME_Type, True)

        self.fov = self.add_multiple_integer_input("Start/End FOV", "fov", ["start", "end"],
                                                   MIN_UNSIGNED_SHORT, MAX_UNSIGNED_SHORT)
        self.zoomspeed = self.add_integer_input("Zoom Speed", "zoomspeed", MIN_UNSIGNED_SHORT, MAX_UNSIGNED_SHORT)

        self.routespeed, self.routespeed_label = self.add_integer_input("Route Speed", "routespeed", MIN_UNSIGNED_SHORT, MAX_UNSIGNED_SHORT, True)
        self.shake = self.add_integer_input("Shake", "shake", MIN_UNSIGNED_BYTE, MAX_UNSIGNED_BYTE)
        #self.startflag = self.add_integer_input("Start Flag", "startflag", MIN_UNSIGNED_BYTE, MAX_UNSIGNED_BYTE)
        #self.movieflag = self.add_integer_input("Movie Flag", "movieflag", MIN_UNSIGNED_BYTE, MAX_UNSIGNED_BYTE)

        self.type.currentIndexChanged.connect(self.update_name)
        self.type.currentIndexChanged.connect(lambda index: self.update_positions(index))
        self.follow_player.stateChanged.connect(lambda _index: self.update_positions(None))

        self.simp_widgets = self.pos2_simp + self.pos3_simp + [self.pos2_l_simp, self.pos3_l_simp, self.viewspeed, self.viewspeed_label, self.follow_player, self.follow_player_label]
        self.play_widgets = self.pos2_play + self.pos3_play + [self.pos2_l_play, self.pos3_l_play]

    def update_data(self):
        obj: Camera = get_cmn_obj(self.bound_to)
        with QtCore.QSignalBlocker(self.follow_player):
            if obj.follow_player:
                self.follow_player.setChecked(True)

        typeindex = self.type.findData(obj.type )
        with QtCore.QSignalBlocker(self.type):
            self.type.setCurrentIndex(typeindex if typeindex != -1 else 1)

        self.set_visible_followplayer(obj.type, self.follow_player.isChecked())

        obj: Camera = get_cmn_obj(self.bound_to)
        self.update_vector3("position", obj.position)

        self.update_vector3("pos2_simp", obj.position2_simple)
        self.update_vector3("pos3_simp", obj.position3_simple)
        self.update_vector3("pos2_play", obj.position2_player)
        self.update_vector3("pos3_play", obj.position3_player)

        if obj.shake is not None: self.shake.setValue(obj.shake)
        if obj.routespeed is not None: self.routespeed.setValue(obj.routespeed)
        if obj.zoomspeed is not None: self.zoomspeed.setValue(obj.zoomspeed)
        if obj.viewspeed is not None: self.viewspeed.setValue(obj.viewspeed)

        if obj.fov.start is not None: self.fov[0].setValue(obj.fov.start)
        if obj.fov.end is not None: self.fov[1].setValue(obj.fov.end)


        obj: Route = obj.route_obj
        has_route = len(obj) > 0
        self.set_visible_route(has_route)

    def update_positions(self, index):
        type = self.type.itemData(index)
        follow_player = self.follow_player.isChecked()
        self.set_visible_followplayer( type, follow_player )
        self.update_data()

    def set_visible_followplayer(self, type, follow_player):
        #different configurations:
        #1-2 doesn't use pos2, pos3, or viewspeed
        #4-5 uses pos2, pos3 and viewspeed
        #3,6 uses pos2, pos3, and viewspeed.
        if type < 2:
            [widget.setVisible(not follow_player) for widget in self.simp_widgets]
            [widget.setVisible(False) for widget in self.play_widgets]
        elif type == 3:
            [widget.setVisible(True) for widget in self.play_widgets]
            [widget.setVisible(False) for widget in self.simp_widgets]

    def set_visible_route(self, vis_value):
        self.routespeed.setVisible(vis_value)
        self.routespeed_label.setVisible(vis_value)

class ReplayCameraEdit(CameraEdit):

    def setup_widgets(self):
        super().setup_widgets()

    def update_data(self):
        super().update_data()
        obj: Camera = get_cmn_obj(self.bound_to)
        [widget.setVisible(obj.type == 1) for widget in self.position]
        self.position_label.setVisible(obj.type == 1)

    def update_name(self):
        super().update_name()

        type: Camera = get_cmn_obj(self.bound_to).type
        self.follow_player.setVisible(type == 1)
        self.follow_player_label.setVisible(type == 1)

        [widget.setVisible(type == 1) for widget in self.position]
        self.position_label.setVisible(type == 1)

    def update_positions(self, index=None):
        if index is None:
            index = self.type.currentIndex()
        super().update_positions(index)
        type = self.type.itemData(index)
        [widget.setVisible(type == 1) for widget in (self.follow_player, self.follow_player_label)]
        [widget.setVisible(type == 1) for widget in self.position]
        self.position_label.setVisible(type == 1)
        for camera in self.bound_to:
            camera.handle_type_change()

class OpeningCameraEdit(CameraEdit):
    def setup_widgets(self):
        super().setup_widgets()
        self.camduration = self.add_integer_input("Camera Duration", "camduration",
                                                  MIN_UNSIGNED_SHORT, MAX_UNSIGNED_SHORT)
        self.type.setVisible(False)
        self.type_label.setVisible(False)
        self.follow_player.setVisible(False)
        self.follow_player_label.setVisible(False)

    def update_data(self):
        super().update_data()
        obj: Camera = get_cmn_obj(self.bound_to)
        self.camduration.setValue(obj.camduration)

class GoalCameraEdit(CameraEdit):
    def setup_widgets(self):
        super().setup_widgets()
        self.camduration = self.add_integer_input("Camera Duration", "camduration",
                                    MIN_UNSIGNED_SHORT, MAX_UNSIGNED_SHORT)
        self.type.setVisible(False)
        self.type_label.setVisible(False)
        self.follow_player.setVisible(False)
        self.follow_player_label.setVisible(False)

    def update_data(self):
        super().update_data()
        obj: Camera = get_cmn_obj(self.bound_to)
        self.camduration.setValue(obj.camduration)

class CamerasEdit(DataEditor):
    def setup_widgets(self):
        goalcam = self.bound_to[0].goalcam
        self.bound_to = self.bound_to[0]
        self.main_thing = QtWidgets.QTabWidget()
        self.vbox.addWidget(self.main_thing)

        self.seq_edit = OpeningCamerasEdit(self.parent(), self.bound_to)
        self.camera_edit = GoalCameraEdit(self.parent(), [goalcam])

        self.main_thing.addTab(self.seq_edit, "Opening Cameras")
        self.main_thing.addTab(self.camera_edit, "Goal Camera")

    def update_data(self):
        self.seq_edit.update_data()
        self.camera_edit.update_data()

class CameraSummaryEdit(DataEditor):
    def setup_widgets(self):
        self.camduration = self.add_integer_input("Camera Duration", "camduration",
                                    MIN_UNSIGNED_SHORT, MAX_UNSIGNED_SHORT)
    def update_data(self):
        self.camduration.setValue(self.bound_to[0].camduration)

class OpeningCamerasEdit(DataEditor):
    def setup_widgets(self):
        self.widgets = []

        for obj in self.bound_to:
            editor = CameraSummaryEdit(self.parent(), [obj])
            self.vbox.addWidget(editor)
            self.widgets.append(editor)

    def update_data(self):
        for widget in self.widgets:
            widget.update_data()

class CameraRoutePointEdit(DataEditor):
    def __init__(self, parent, bound_to, idx=-1, kmp_file=None):
        self.idx = idx
        super().__init__(parent, bound_to, kmp_file)

    def setup_widgets(self):
        disp_string = f"Point {self.idx} Speed" if self.idx > -1 else "Speed"

        self.unk1 = self.add_integer_input(disp_string, "unk1",
                                              MIN_UNSIGNED_SHORT, MAX_UNSIGNED_SHORT)

    def update_data(self):
        obj = self.bound_to[0]
        self.unk1.setValue((obj.unk1))

class SpecialAreaEdit(DataEditor):
    def setup_widgets(self):
        self.main_thing = QtWidgets.QTabWidget()
        self.vbox.addWidget(self.main_thing)

        self.area_edit = AreaEdit(self.parent(), self.bound_to)

        self.area_edit.area_type.currentIndexChanged.connect(self.update_data)

        self.route_edit = QtWidgets.QWidget()
        self.object_edit = QtWidgets.QWidget()

        route_obj = get_cmn_obj(self.bound_to).route_obj
        has_boo_areas = any([area.type == 7 for area in self.bound_to])

        self.main_thing.addTab(self.area_edit, "Area")

        if route_obj:
            self.route_edit = AreaRouteEdit(self.parent(), route_obj)
        if has_boo_areas:
            self.object_edit = BooEdit(self.parent(), [self.kmp_file.areas.boo_obj])

        self.main_thing.addTab(self.route_edit, "Route")
        self.main_thing.setTabVisible(1, len(route_obj) > 0)
        self.main_thing.addTab(self.object_edit, "Boo Object")
        self.main_thing.setTabVisible(2, has_boo_areas)

    def update_data(self):
        self.area_edit.update_data()
        route_obj = get_cmn_obj(self.bound_to).route_obj
        has_boo_areas = any([area.type == 7 for area in self.bound_to])

        if isinstance(route_obj, DataEditor) and self.route_edit:
            self.route_edit.update_data()
        elif route_obj:
            self.route_edit = AreaRouteEdit(self.parent(), route_obj, self.kmp_file)
            self.route_edit.update_data()
            self.main_thing.removeTab(1)
            self.main_thing.insertTab(1, self.route_edit, "Route")
        else:
            self.route_edit = QtWidgets.QWidget()

        if isinstance(self.object_edit, DataEditor) and has_boo_areas:
            self.object_edit.update_data()
        elif has_boo_areas:
            self.object_edit = BooEdit(self.parent(), [self.kmp_file.areas.boo_obj], self.kmp_file)
            self.object_edit.update_data()
            self.main_thing.removeTab(2)
            self.main_thing.addTab(self.object_edit, "Boo Object")
        else:
            self.object_edit = QtWidgets.QWidget()

        self.main_thing.setTabVisible(1, len(route_obj) > 0 )
        self.main_thing.setTabVisible(2, has_boo_areas)

class AreaRoutePointEdit(DataEditor):
    def __init__(self, parent, bound_to, idx=-1, kmp_file=None):
        self.idx = idx
        super().__init__(parent, bound_to, kmp_file)

    def setup_widgets(self):
        disp_string = f"Point {self.idx} Settings" if self.idx > -1 else "Settings"

        self.unk1, self.unk2 = self.add_multiple_integer_input(disp_string, None, ["unk1", "unk2"],
                                              MIN_UNSIGNED_SHORT, MAX_UNSIGNED_SHORT)

    def update_data(self):
        obj = self.bound_to[0]
        self.unk1.setValue(obj.unk1)
        self.unk2.setValue(obj.unk2)

class RespawnPointEdit(DataEditor):
    def setup_widgets(self):
        self.position = self.add_multiple_decimal_input("Position", "position", ["x", "y", "z"],
                                                        -inf, +inf)
        self.rotation = self.add_rotation_input()

        #self.respawn_id = self.add_integer_input("Respawn ID", "respawn_id", MIN_UNSIGNED_SHORT, MAX_UNSIGNED_SHORT)
        self.range = self.add_integer_input("Range", "range",
                                           MIN_SIGNED_SHORT, MAX_SIGNED_SHORT)

    def update_data(self):
        obj: JugemPoint = get_cmn_obj(self.bound_to)
        self.update_vector3("position", obj.position)
        self.update_vector3("rotation", obj.rotation)
        if obj.range is not None: self.range.setValue(obj.range)

class CannonPointEdit(DataEditor):
    def setup_widgets(self):
        self.position = self.add_multiple_decimal_input("Position", "position", ["x", "y", "z"],
                                                        -inf, +inf)
        self.rotation = self.add_rotation_input()
        self.cannon_id = self.add_integer_input("Cannon ID", "id",  MIN_UNSIGNED_SHORT, MAX_UNSIGNED_SHORT)
        self.shooteffect = self.add_dropdown_input("Shoot Effect", "shoot_effect", CNPT_ShootEffect)


    def update_data(self):
        obj: CannonPoint = get_cmn_obj(self.bound_to)
        self.update_vector3("position", obj.position)
        self.update_vector3("rotation", obj.rotation)
        self.cannon_id.setValue(obj.id)
        self.shooteffect.setCurrentIndex( obj.shoot_effect )

class MissionPointEdit(DataEditor):
    def setup_widgets(self):
        self.position = self.add_multiple_decimal_input("Position", "position", ["x", "y", "z"],
                                                        -inf, +inf)
        self.rotation = self.add_rotation_input()
        #self.mission_id = self.add_integer_input("Mission Success ID", "mission_id", MIN_UNSIGNED_SHORT, MAX_UNSIGNED_SHORT)
        self.unk = self.add_integer_input("Next Enemy Point", "unk",
                                           MIN_UNSIGNED_SHORT, MAX_UNSIGNED_SHORT)

    def update_data(self):
        obj: MissionPoint = get_cmn_obj(self.bound_to)

        self.update_vector3("position", obj.position)
        self.update_vector3("rotation", obj.rotation)
        self.unk.setValue(obj.unk)
