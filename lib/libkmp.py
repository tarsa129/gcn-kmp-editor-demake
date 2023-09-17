import json
from numpy import arctan, argmin, array
from struct import unpack, pack
from .vectors import Vector3, Vector2, Rotation, Vector3Relative
from collections import OrderedDict
from io import BytesIO
from copy import deepcopy, copy

import os

def all_of_same_type(objs):
    all_same =  all( [ isinstance(x, type(objs[0])) for x in objs])
    if not (all_same):
        return False
    if isinstance(objs[0], Area):
        types = [obj.type for obj in objs]
        if 0 in types and not all([type == 0 for type in types]):
            return False
    return True


def read_uint8(f):
    return unpack(">B", f.read(1))[0]

def read_int8(f):
    return unpack(">b", f.read(1))[0]

def read_int16(f):
    return unpack(">h", f.read(2))[0]

def read_uint16(f):
    return unpack(">H", f.read(2))[0]


def read_uint32(f):
    return unpack(">I", f.read(4))[0]


def read_float(f):
    return unpack(">f", f.read(4))[0]


def read_string(f):
    start = f.tell()

    next = f.read(1)
    n = 0

    if next != b"\x00":
        next = f.read(1)
        n += 1
    if n > 0:
        curr = f.tell()
        f.seek(start)
        string = f.read(n)
        f.seek(curr)
    else:
        string = ""

    return string


def write_uint16(f, val):
    f.write(pack(">H", val))


PADDING = b"This is padding data to align"


def write_padding(f, multiple):
    next_aligned = (f.tell() + (multiple - 1)) & ~(multiple - 1)

    diff = next_aligned - f.tell()

    for i in range(diff):
        pos = i % len(PADDING)
        f.write(PADDING[pos:pos + 1])


class ObjectContainer(list):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.assoc = None

    @classmethod
    def from_empty(cls):
        container = cls()
        return container

    @classmethod
    def from_file(cls, f, count, objcls):
        container = cls()


        for i in range(count):
            obj = objcls.from_file(f)
            container.append(obj)

        return container

    @classmethod
    def from_file(cls, f, count, objcls):
        container = cls()


        for i in range(count):
            obj = objcls.from_file(f)
            container.append(obj)

        return container

class ColorRGB(object):
    def __init__(self, r, g, b):
        self.r = r
        self.g = g
        self.b = b

    @classmethod
    def from_file(cls, f):
        return cls(read_uint8(f), read_uint8(f), read_uint8(f))

    def write(self, f):
        f.write(pack(">BBB", self.r, self.g, self.b))

class ColorRGBA(ColorRGB):
    def __init__(self, r, g, b, a):
        super().__init__(r, g, b)
        self.a = a

    @classmethod
    def from_file(cls, f):
        return cls(*unpack(">BBBB", f.read(4)))

    def write(self, f):
        super().write(f)
        f.write(pack(">B", self.a))

class PositionedObject(object):
    def __init__(self, position) -> None:
        self.position = position

class RotatedObject(PositionedObject):
    def __init__(self, position, rotation) -> None:
        super().__init__(position)
        for axis in ['x', 'y', 'z']:
            value = getattr(rotation, axis)
            while value > 360:
                value -= 360
            while value < -360:
                value += 360
            setattr(rotation, axis, value)
        self.rotation = rotation


class RoutedObject(PositionedObject):
    def __init__(self, position):
        self.position = position
        self.route_obj = None
        self.route = -1
        self.routeclass = Route

    def create_route(self, add_points=False, ref_points=None, absolute_pos=False, overwrite=False):
        if self.route_info() < 1:
            return
        if not (overwrite or self.route_obj is None):
            return
        self.route_obj = self.routeclass()
        if add_points:
            self.route_obj.add_points(self.position, absolute_pos, ref_points)

    def route_info(self):
        return 0

    def has_route(self):
        return self.route_obj is not None and self.route_obj.points

    def __iadd__(self, other):
        self.position += other.position

        if not other.route_obj:
            return self
        if self.route_obj and not isinstance(self.route_obj, list):
            self.route_obj = [self.route_obj]
        elif self.route_obj:
            self.route_obj.append(other.route_obj)


class KMPPoint(PositionedObject):
    def __init__(self, position):
        super().__init__(position)

class PointGroup(object):
    def __init__(self):
        self.points = []
        self.prevgroup = []
        self.nextgroup = []

    def insert_point(self, enemypoint, index=-1):
        self.points.insert(index, enemypoint)

    def move_point(self, index, targetindex):
        point = self.points.pop(index)
        self.points.insert(targetindex, point)

    def copy_group(self, group):
        for point in self.points:
            #new_point = deepcopy(point)
            group.points.append(point)

        group.prevgroup = self.prevgroup.copy()
        group.nextgroup = self.nextgroup.copy()

        return group

    def copy_group_after(self, point, new_group):
        pos = self.points.index(point)

        # Check if the element is the last element
        if not len(self.points)-1 == pos:
            for point in self.points[pos+1:]:
                new_group.points.append(point)

        #this is the new group
        new_group.nextgroup = self.nextgroup.copy()
        new_group.prevgroup = [self]

        #this is the current group
        self.nextgroup = [new_group]
        self.prevgroup = [new_group if group == self else group for group in self.prevgroup]

        return new_group

    def remove_after(self, point):
        pos = self.points.index(point)
        self.points = self.points[:pos+1]

    def copy_into_group(self, group):
        self.points.extend(group.points)

    def num_prev(self):
        return len(self.prevgroup)

    def num_next(self):
        return len(self.nextgroup)

    def add_new_prev(self, new_group):
        if new_group is None or self.num_prev() == 6 or new_group in self.prevgroup:
            return False
        self.prevgroup.append(new_group)

    def add_new_next(self, new_group):
        if new_group is None or self.num_next() == 6 or new_group in self.nextgroup:
            return False
        self.nextgroup.append(new_group)

    def remove_prev(self, group):
        if group in self.prevgroup:
            self.prevgroup.remove(group)

    def remove_next(self, group):
        if group in self.nextgroup:
            self.nextgroup.remove(group)

class PointGroups(object):
    def __init__(self):
        self.groups = []
        self._group_ids = {}

    def points(self):
        for group in self.groups:
            for point in group.points:
                yield point

    def split_group(self, group : PointGroup, point : KMPPoint):
        new_group = self.get_new_group()
        new_group = group.copy_group_after(point, new_group)

        self.groups.append(new_group)
        group.remove_after(point)

        for other_group in self.groups:
            if group in other_group.prevgroup:
                other_group.prevgroup = [new_group if grp == group else grp for grp in other_group.prevgroup ]

    def find_group_of_point(self, point):
        for i, group in enumerate(self.groups):
            for j, curr_point in enumerate(group.points):
                if point == curr_point:
                    return i, group, j
        return None, None, None

    def merge_groups(self):
        if len(self.groups) < 2:
            return

        for group in self.groups[1:]:
            if len(group.points) == 0:
                self.remove_group(group, False)

        first_group = self.groups[0]
        i = 0
        while i < len(self.groups):
            if len(self.groups) < 2:
                return
            group = self.groups[i]
            #if this group only has one next, and the nextgroup only has one prev, they can be merged
            if group.num_next() == 1 and group.nextgroup[0].num_prev() == 1:
                print(i, first_group, group)
                if first_group in group.nextgroup:
                    i += 1 #do not merge with the start
                    continue
                del_group = group.nextgroup[0]
                if group == del_group:
                    print("ERROR: TRYING TO MERGE INTO ITSELF", i)
                    return
                    #continue

                group.copy_into_group( del_group )

                self.groups.remove(del_group)

                #replace this group's next with the deleted group's next
                group.nextgroup = del_group.nextgroup.copy()

                for this_group in self.groups:
                    #replace links to the deleted group with the group it was merged into
                    this_group.prevgroup = [ group if grp == del_group else grp for grp in this_group.prevgroup]
            else:
                i += 1

    def get_new_point(self):
        return KMPPoint.new()

    def get_new_group(self):
        return PointGroup.new()

    def add_new_group(self):
        new_group = self.get_new_group()
        self.groups.append( new_group )

        if len(self.groups) == 1:
            new_group.add_new_next(new_group)
            new_group.add_new_prev(new_group)

    def remove_group(self, del_group, merge = True):
        self.groups.remove(del_group)

        for group in self.groups :

            #remove previous links to the deleted group
            group.prevgroup = [ grp for grp in group.prevgroup if grp != del_group]
            group.nextgroup = [ grp for grp in group.nextgroup if grp != del_group]


        if merge:
            self.merge_groups()

        if len(self.groups) == 1:
            self.groups[0].add_new_next(self.groups[0])
            self.groups[0].add_new_prev(self.groups[0])

    def remove_point(self, point):
        group_idx, group, point_idx = self.find_group_of_point(point)
        if len(group.points) == 1:
            self.remove_group(group)
        else:
            group.points.remove(point)

    def remove_unused_groups(self):
        #remove empty
        to_delete = [ group for group in self.groups if len(group.points) == 0 ]
        for group in to_delete:
            self.remove_group(group)

        #remove those that do not follow the main path
        to_visit = [0]
        visited = []

        while len(to_visit) > 0:

            idx = to_visit[0]
            if idx in visited:
                to_visit.pop(0)
            visited.append(idx)

            to_visit.extend( [grp for grp in to_visit.nextgroup if grp not in visited] )

        unused_groups = [grp for grp in self.groups if grp not in visited]
        for group in unused_groups:
            if group in self.groups:
                #do not merge until the end
                self.remove_group( group, False   )
        self.merge_groups()

    def num_total_points(self):
        return sum( [len(group.points) for group in self.groups]  )

    def get_point_from_index(self, idx):
        for group in self.groups:
            points_in_group = len(group.points)
            if idx < points_in_group:
                return group.points[idx]
            idx -= points_in_group
        return None

    def get_index_from_point(self, point):
        id = 0
        for group in self.groups:
            for curr_point in group.points:
                if point == curr_point:
                    return id
                id += 1
        return -1

    def reset_ids(self):
        for i, group in enumerate(self.groups):
            group.id = i

    def get_idx(self, group):
        return self.groups.index(group)

    def remove_all(self):
        self.groups = []

    def set_this_as_first(self, point: KMPPoint):
        if self.get_index_from_point(point) == 0:
            return
        group_idx, group, point_idx = self.find_group_of_point(point)
        if point_idx == 0:
            self.groups.remove(group)
            self.groups.insert(0, group)
        else:
            self.split_group(group, group.points[point_idx - 1])
            new_group = self.groups.pop()
            self.groups.insert(0, new_group)

        self.merge_groups()


# Section 1
# Enemy/Item Route Code Start
class EnemyPoint(KMPPoint):
    def __init__(self,
                 position,
                 scale,
                 enemyaction,
                 enemyaction2,
                 unknown):
        super().__init__(position)

        self.scale = scale
        self.enemyaction = enemyaction
        self.enemyaction2 = enemyaction2
        self.unknown = unknown

    @classmethod
    def new(cls):
        return cls(
            Vector3(0.0, 0.0, 0.0),
            10, 0, 0, 0
        )

    @classmethod
    def from_file(cls, f):
        point = cls.new()
        point.position = Vector3.from_file(f)
        point.scale = read_float(f)
        point.enemyaction = read_uint16(f)
        point.enemyaction2 = read_uint8(f)
        point.unknown = read_uint8(f)

        return point


    def write(self, f):

        self.position.write(f)
        f.write(pack(">f", self.scale ) )
        f.write(pack(">H", self.enemyaction) )
        f.write(pack(">bB", self.enemyaction2, self.unknown) )

    def copy(self):
        return deepcopy(self)

    def __iadd__(self, other):
        self.position += other.position
        self.scale += other.scale
        self.enemyaction = self.enemyaction if self.enemyaction == other.enemyaction else 0
        self.enemyaction2 = self.enemyaction2 if self.enemyaction == other.enemyaction2 else 0
        self.unknown = self.unknown if self.unknown == other.unknown else 0

        return self

    def __itruediv__(self, scale):
        self.position /= scale
        self.scale /= scale

        return self

class EnemyPointGroup(PointGroup):
    def __init__(self):
        super().__init__()

    @classmethod
    def new(cls):
        return cls()

    @classmethod
    def from_file(cls, f, idx, points):
        group = cls()
        group.id = idx
        start_idx = read_uint8(f)
        len = read_uint8(f)


        group.prevgroup = list(unpack(">bbbbbb", f.read(6)) )
        group.nextgroup = list(unpack(">bbbbbb", f.read(6)) )
        f.read( 2)

        for i in range(start_idx, start_idx + len):
            group.points.append(points[i])

        return group

    def copy_group(self):
        group = EnemyPointGroup()
        return super().copy_group( group)

    def copy_group_after(self, point, group):
        group = EnemyPointGroup()
        return super().copy_group_after(point, group)

    def write_points_enpt(self, f):
        for point in self.points:
            point.write(f)
        return len(self.points)

    def write_enph(self, f, index, groups):
        f.write(pack(">B", index) )
        f.write(pack(">B", len(self.points) ) )
        for grp in self.prevgroup:
           f.write(pack(">B", groups.get_idx(grp)))
        for i in range( 6 - len(self.prevgroup) ):
           f.write(pack(">b", -1))

        for grp in self.nextgroup:
           f.write(pack(">B", groups.get_idx(grp)))
        for i in range( 6 - len(self.nextgroup) ):
           f.write(pack(">b", -1))

        f.write(pack(">H",  0) )

class EnemyPointGroups(PointGroups):
    level_file = None
    def __init__(self):
        super().__init__()

    def get_new_point(self):
        return EnemyPoint.new()

    def get_new_group(self):
        return EnemyPointGroup.new()

    def remove_point(self, del_point):
        super().remove_point(del_point)

        type_4_areas : list[Area] = __class__.level_file.areas.get_type(4)
        for area in type_4_areas:
            if area.enemypoint == del_point:
                area.find_closest_enemypoint()

    def remove_group(self, del_group, merge = True):
        super().remove_group(del_group, merge = True)

        type_4_areas = __class__.level_file.areas.get_type(4)
        for area in type_4_areas:
            if area.enemypoint in del_group.points:
                area.enemypoint = None

    @classmethod
    def from_file(cls, f):
        enemypointgroups = cls()

        assert f.read(4) == b"ENPT"
        count = read_uint16(f)
        f.read(2)


        all_points = []
        #read the enemy points
        for i in range(count):
            enemypoint = EnemyPoint.from_file(f)
            all_points.append(enemypoint)

        assert f.read(4) == b"ENPH"
        count = read_uint16(f)
        f.read(2)


        for i in range(count):
            enemypath = EnemyPointGroup.from_file(f, i, all_points)
            enemypointgroups.groups.append(enemypath)

        return enemypointgroups

    def write(self, f):


        f.write(b"ENPT")
        count_offset = f.tell()
        f.write(pack(">H", 0) ) # will be overridden later
        f.write(pack(">H", 0) )

        sum_points = 0
        point_indices = []

        for group in self.groups:
            point_indices.append(sum_points)
            sum_points += group.write_points_enpt(f)
        enph_offset = f.tell()

        if sum_points > 0xFF:
            raise Exception("too many enemy points")
        else:
            f.seek(count_offset)
            f.write(pack(">H", sum_points) )

        f.seek(enph_offset)
        f.write(b"ENPH")
        f.write(pack(">H", len(self.groups) ) )
        f.write(pack(">H", 0) )

        for idx, group in enumerate( self.groups ):
            group.write_enph(f, point_indices[idx], self)

        return enph_offset

class ItemPoint(KMPPoint):
    def __init__(self, position, scale, setting1, setting2) :
        super().__init__(position)
        self.scale = scale
        self.setting1 = setting1

        self.unknown = setting2 & 0x4
        self.lowpriority = setting2 & 0x2
        self.dontdrop = setting2 & 0x1

    @classmethod
    def new(cls):
        return cls( Vector3(0.0, 0.0, 0.0), 1, 1, 0)

    def set_setting2(self, setting2):
        self.unknown = setting2 & 0x4
        self.lowpriority = setting2 & 0x2
        self.dontdrop = setting2 & 0x1

    @classmethod
    def from_file(cls, f):

        point = cls.new()

        point.position = Vector3.from_file(f)
        point.scale = read_float(f)
        point.setting1 = read_uint16(f)
        point.set_setting2(read_uint16(f))

        return point


    def write(self, f):

        self.position.write(f)

        setting2 = self.unknown << 0x2
        setting2 = setting2 | (self.lowpriority << 0x1)
        setting2 = setting2 | self.dontdrop
        f.write(pack(">fHH", self.scale, self.setting1, setting2))
    
    def copy(self):
        return deepcopy(self)

    def __iadd__(self, other):
        self.position += other.position
        self.scale += other.scale
        self.setting1 += other.setting1
        self.unknown = self.unknown if self.unknown == other.unknown else 0
        self.lowpriority = self.lowpriority if self.lowpriority == other.lowpriority else 0
        self.dontdrop = self.dontdrop if self.dontdrop == other.dontdrop else 0

        return self

    def __itruediv__(self, scale):
        self.position /= scale
        self.scale /= scale
        self.setting1 /= self.setting1

        return self

class ItemPointGroup(PointGroup):
    def __init__(self):
        super().__init__()

    @classmethod
    def new(cls):
        return cls()

    @classmethod
    def from_file(cls, f, idx, points):
        group = cls()
        group.id = idx
        start_idx = read_uint8(f)
        len = read_uint8(f)


        group.prevgroup = list( unpack(">bbbbbb", f.read(6)) )
        group.nextgroup = list(unpack(">bbbbbb", f.read(6)) )
        f.read( 2)

        for i in range(start_idx, start_idx + len):
            group.points.append(points[i])

        return group

    def copy_group(self):
        group = ItemPointGroup()
        return super().copy_group(group)

    def copy_group_after(self, point, group):
        group = ItemPointGroup()
        return super().copy_group_after( point, group)

    def write_itpt(self, f):
        for point in self.points:
            point.write(f)
        return len(self.points)

    def write_itph(self, f, index, groups):


        f.write(pack(">B", index ) )
        f.write(pack(">B", len(self.points) ) )

        for grp in self.prevgroup:
           f.write(pack(">B", groups.get_idx(grp)))
        for i in range( 6 - len(self.prevgroup) ):
           f.write(pack(">b", -1))
        for grp in self.nextgroup:
           f.write(pack(">B", groups.get_idx(grp)))
        for i in range( 6 - len(self.nextgroup) ):
           f.write(pack(">b", -1))

        f.write(pack(">H",  0) )

class ItemPointGroups(PointGroups):
    def __init__(self):
        super().__init__()

    def get_new_point(self):
        return ItemPoint.new()

    def get_new_group(self):
        return ItemPointGroup.new()


    @classmethod
    def from_file(cls, f):
        itempointgroups = cls()

        assert f.read(4) == b"ITPT"
        count = read_uint16(f)
        f.read(2)


        all_points = []
        #read the item points
        for i in range(count):
            itempoint = ItemPoint.from_file(f)
            all_points.append(itempoint)


        assert f.read(4) == b"ITPH"
        count = read_uint16(f)
        f.read(2)


        for i in range(count):
            itempath = ItemPointGroup.from_file(f, i, all_points)
            itempointgroups.groups.append(itempath)
        return itempointgroups

    def write(self, f):

        f.write(b"ITPT")

        count_offset = f.tell()
        f.write(pack(">H", 0) ) #overwritten
        f.write(pack(">H", 0) )

        sum_points = 0
        point_indices = []

        for group in self.groups:
            point_indices.append(sum_points)
            sum_points += group.write_itpt(f)

        itph_offset = f.tell()

        if sum_points > 0xFF:
            raise Exception("too many enemy points")
        else:
            f.seek(count_offset)
            f.write(pack(">H", sum_points) )

        f.seek(itph_offset)

        f.write(b"ITPH")
        f.write(pack(">H", len(self.groups) ) )
        f.write(pack(">H", 0) )

        for idx, group in enumerate( self.groups ):
            group.write_itph(f, point_indices[idx], self)


        return  itph_offset

class Checkpoint(KMPPoint):
    def __init__(self, start, end, respawn=0, type=0):
        super().__init__( (start+end)/2.0 )
        self.start = start
        self.end = end

        self.respawnid = respawn
        self.respawn_obj = None
        self.type = type
        self.lapcounter = 0


        self.prev = -1
        self.next = -1

        self.widget = None

    @classmethod
    def new(cls):
        return cls(Vector3(0.0, 0.0, 0.0),
                   Vector3(0.0, 0.0, 0.0))

    def assign_to_closest(self, respawns):
        mid = (self.start + self.end) / 2
        distances = [ respawn.position.distance_2d( mid  ) for respawn in respawns ]
        if len(distances) > 0:
            smallest = [ i for i, x in enumerate(distances) if x == min(distances)]
            self.respawn_obj = respawns[smallest[0]]

    def get_mid(self):
        return (self.start+self.end)/2.0

    @classmethod
    def from_file(cls, f):
        checkpoint = cls.new()

        checkpoint.start = Vector3(*unpack(">f", f.read(4) ), 0, *unpack(">f", f.read(4) ) )
        checkpoint.end = Vector3(*unpack(">f", f.read(4) ), 0, *unpack(">f", f.read(4) ) )

        checkpoint.respawnid = read_uint8(f) #respawn

        checkpoint_type = read_uint8(f)
        if checkpoint_type == 0:
            checkpoint.lapcounter = 1
        elif checkpoint_type != 0xFF:
            checkpoint.type = 1

        checkpoint.prev = read_uint8(f)
        checkpoint.next = read_uint8(f)

        return checkpoint


    def write(self, f, prev, next, key, lap_counter = False ):
        f.write(pack(">ff", self.start.x, self.start.z))
        f.write(pack(">ff", self.end.x, self.end.z))
        f.write(pack(">b", self.respawnid))

        if self.lapcounter == 1:
            f.write(pack(">b", 0))
            key = 1
        elif self.type == 1:
            f.write(pack(">b", key))
            key += 1
        else:
            f.write(pack(">B", 0xFF))
        f.write(pack(">BB", prev & 0xFF, next & 0xFF) )
        return key

    def copy(self):
        return deepcopy(self)
    def __iadd__(self, other):
        self.start += other.start
        self.end += other.end
        self.respawn_obj = self.respawn_obj if self.respawn_obj == other.respawn_obj else None
        self.type = self.type if self.type == other.type else -1
        self.lapcounter = self.lapcounter if self.lapcounter == other.lapcounter else 0

        return self

    def __itruediv__(self, scale):
        self.start /= scale
        self.end /= scale

        return self

class CheckpointGroup(PointGroup):
    def __init__(self):
        super().__init__()

    @classmethod
    def new(cls):
        return cls()

    def copy_group(self):
        group = CheckpointGroup()
        return super().copy_group( group)


    def copy_group_after(self, point, group):
        group = CheckpointGroup()
        return super().copy_group_after( point, group)

    def get_used_respawns(self):
        return set( [checkpoint.respawn_obj for checkpoint in self.points]  )

    def num_key_cps(self):
        return sum( [1 for ckpt in self.points if ckpt.type > 0]  )

    @classmethod
    def from_file(cls, f, all_points, id):

        checkpointgroup = cls.new()
        checkpointgroup.id = id

        start_point = read_uint8(f)
        length = read_uint8(f)

        if len(all_points) > 0:
            assert( all_points[start_point].prev == 0xFF )
            if length > 1:
                assert( all_points[start_point + length - 1].next == 0xFF)
        checkpointgroup.points = all_points[start_point: start_point + length]

        checkpointgroup.prevgroup = list(unpack(">bbbbbb", f.read(6)))
        checkpointgroup.nextgroup = list(unpack(">bbbbbb", f.read(6)))
        f.read(2)

        return checkpointgroup

    def set_rspid(self, rsps):
        for point in self.points:
            if point.respawn_obj is not None:
                point.respawnid = rsps.index(point.respawn_obj)
            else:
                point.respawnid = 0

    def write_ckpt(self, f, key, prev):

        if len(self.points) > 0:
            key = self.points[0].write(f, -1, 1 + prev, key)

            for i in range(1, len( self.points) -1 ):
                key = self.points[i].write(f, i-1 + prev, i + 1 + prev, key)
            if len(self.points) > 1:
                key = self.points[-1].write(f, len(self.points) - 2 + prev, -1, key)
        return key

    def write_ckph(self, f, index, groups):
        f.write(pack(">B", index ) )
        f.write(pack(">B", len(self.points) ) )

        for grp in self.prevgroup:
           f.write(pack(">B", groups.get_idx(grp)))
        for i in range( 6 - len(self.prevgroup) ):
           f.write(pack(">b", -1))
        for grp in self.nextgroup:
           f.write(pack(">B", groups.get_idx(grp)))
        for i in range( 6 - len(self.nextgroup) ):
           f.write(pack(">b", -1))

        f.write(pack(">H",  0) )

class CheckpointGroups(PointGroups):
    def __init__(self):
        super().__init__()

    def get_new_point(self):
        return Checkpoint.new()

    def get_new_group(self):
        return CheckpointGroup.new()

    @classmethod
    def from_file(cls, f, ckph_offset):
        checkpointgroups = cls()
        assert f.read(4) == b"CKPT"
        count = read_uint16(f)
        f.read(2)

        all_points = []
        #read the enemy points
        for i in range(count):
            checkpoint = Checkpoint.from_file(f)
            all_points.append(checkpoint)

        assert f.read(4) == b"CKPH"
        count = read_uint16(f)
        f.read(2)

        for i in range(count):
            checkpointpath = CheckpointGroup.from_file(f, all_points, i)
            checkpointgroups.groups.append(checkpointpath)

        return checkpointgroups

    def write(self, f):
        f.write(b"CKPT")
        tot_points = self.num_total_points()
        if tot_points > 255:
            raise Exception("too many checkpoints")
        f.write(pack(">H", tot_points ) )
        f.write(pack(">H", 0) )

        sum_points = 0
        indices_offset = []
        num_key = 0
        starting_key_cp = [0] * len(self.groups)

        if len(self.groups) > 0:
            starting_key_cp[0] = 0

        for i, group in enumerate(self.groups):
            indices_offset.append(sum_points)
            num_key = group.write_ckpt(f, starting_key_cp[i], sum_points)

            for grp in group.nextgroup:
                id = self.get_idx(grp)
                starting_key_cp[ id ] = max( starting_key_cp[id], num_key)

            sum_points += len(group.points)
        ckph_offset = f.tell()

        f.write(b"CKPH")
        f.write(pack(">H", len(self.groups) ) )
        f.write(pack(">H", 0) )

        for idx, group in enumerate( self.groups ):
            group.write_ckph(f, indices_offset[idx], self)
        return ckph_offset

    def set_key_cps(self):
        #assume that checkpoint 0 is always the first one
        to_visit = [0]
        splits = [0]
        visited = []

        while len(to_visit) > 0:
            i = to_visit.pop(0)

            if i in visited:
                continue
            visited.append(i)
            checkgroup = self.groups[i]

            if len(splits) == 1:
                checkgroup.points[0].type = 1

                for i in range(10, len(checkgroup.points), 10):
                    checkgroup.points[i].type = 1

                checkgroup.points[-1].type = 1

            actual_next = [x for x in checkgroup.nextgroup if x != -1]

            splits.extend(actual_next)
            splits = [*set(splits)]
            splits = [x for x in splits if x != i]

            to_visit.extend(actual_next)
            to_visit = [*set(to_visit)]

    def get_used_respawns(self):
        used_respawns = []
        for group in self.groups:
            used_respawns.extend( group.get_used_respawns() )

        return set(used_respawns)

    def set_rspid(self, rsps):
        for group in self.groups:
            group.set_rspid(rsps)


# Section 3
# Routes/Paths for cameras, objects and other things
class Route(object):
    def __init__(self):
        self.points = []
        self._pointcount = 0
        self._pointstart = 0
        self.smooth = 0
        self.cyclic = 0
        self.pointclass = RoutePoint
        self.offset_vect = Vector3(500, 0, 0)

    @classmethod
    def new(cls):
        route = cls()
        return route

    def copy(self):
        this_class = self.__class__
        obj = this_class.new()
        return self.copy_params_to_child(obj)

    def to_childclass(self, childclass):
        new_route = childclass()
        self.copy_params_to_child(new_route)
        return new_route

    def copy_params_to_child(self, new_route):
        new_route.points = [point.copy(new_route.pointclass) for point in self.points]
        new_route.smooth = self.smooth
        new_route.cyclic = self.cyclic
        return new_route

    def total_distance(self):
        distance = 0
        for i, point in enumerate(self.points[:-1]):
            distance += point.position.distance( self.points[i + 1].position  )
        return distance

    @classmethod
    def from_file(cls, f):
        route = cls()
        route._pointcount = read_uint16(f)
        route.smooth = read_uint8(f)
        route.cyclic = read_uint8(f)

        for i in range(route._pointcount):
            point: RoutePoint = RoutePoint.from_file(f)
            route.points.append( point  )

        return route

    def add_routepoints(self, points):
        for i in range(self._pointcount):
            self.points.append(points[self._pointstart+i])

    def diff_points(self, pos:Vector3):
        new_route = self.copy()
        for point in new_route.points:
            point.position -= pos
        return new_route

    def write(self, f):
        f.write(pack(">H", len(self.points) ) )
        f.write(pack(">B", self.smooth ) )
        f.write(pack(">B", self.cyclic) )

        for point in self.points:
            point.write(f)
        return len(self.points)

    def add_points(self, position=None, absolute_pos=False, ref_points=None):
        #if absolute: then add the route points
        if ref_points:
            if absolute_pos:
                self.points = [self.pointclass(point.position + position) for point in ref_points]
            else:
                self.points = [self.pointclass(point.position - position) for point in ref_points]
        else:
            for i in range(2):
                point = self.pointclass.new()
                self.points.append(point)

            if absolute_pos:
                for point in self.points:
                    point.position += position

    def __eq__(self, other):
        return id(self) == id(other)

    def __hash__(self):
        return hash(id(self))

#here for type checking - they function in the same way
class ObjectRoute(Route):
    def __init__(self):
        super().__init__()
        self.pointclass = ObjectRoutePoint
        self.offset_vect = Vector3(500, 0, 0)

    def add_points(self, position=None, absolute_pos=False, points_to_diff=None):
        super().add_points(position, absolute_pos, points_to_diff)
        if not points_to_diff:
            self.points[0].position += Vector3(500, 0, 0)
            self.points[1].position += Vector3(-500, 0, 0)

class CameraRoute(Route):
    def __init__(self):
        super().__init__()
        self.pointclass = CameraRoutePoint
        self.offset_vect = Vector3(2000, 0, 0)

    def add_points(self, position=None, absolute_pos=False, points_to_diff=None):
        super().add_points(position, absolute_pos, points_to_diff)
        for point in self.points[:-1]:
            point.unk1 = 30
        if not points_to_diff:
            self.points[1].position += Vector3(2000, 0, 0)

class AreaRoute(Route):
    def __init__(self):
        super().__init__()
        self.pointclass = AreaRoutePoint
        self.offset_vect = Vector3(1500, 0, 0)

    @classmethod
    def new(cls):
        return cls()

    def add_points(self, position=None, absolute_pos=False, points_to_diff=None):
        super().add_points(position, absolute_pos, points_to_diff)
        for point in self.points:
            point.unk1 = 30
        if not points_to_diff:
            self.points[0].position += Vector3(2000, 0, 0)
            self.points[1].position += Vector3(4000, 0, 0)


class ReplayCameraRoute(Route):
    def __init__(self):
        super().__init__()
        self.pointclass = ReplayCameraRoutePoint

    def add_points(self, position=None, absolute_pos=False, points_to_diff=None):
        super().add_points(position, absolute_pos, points_to_diff)
        for point in self.points[:-1]:
            point.unk1 = 30
        if not points_to_diff:
            self.points[1].position += Vector3(2000, 0, 0)

# Section 4
# Route point for use with routes from section 3
class RoutePoint(PositionedObject):
    def __init__(self, position):
        super().__init__(position)
        self.unk1 = 0
        self.unk2 = 0

    @classmethod
    def new(cls):
        return cls(Vector3(0.0, 0.0, 0.0))

    @classmethod
    def from_file(cls, f):
        position = Vector3.from_file(f)
        point = cls(position)

        point.unk1 = read_uint16(f)
        point.unk2 = read_uint16(f)
        return point

    def copy(self, RPClass=None):
        if RPClass is None:
            obj = self.__class__(self.position.copy())
        else:
            obj = RPClass(self.position.copy())
        obj.unk1 = self.unk1
        obj.unk2 = self.unk2
        return obj

    def write(self, f):
        self.position.write(f)
        f.write(pack(">HH", self.unk1, self.unk2) )

    def __iadd__(self, other):
        self.position += other.position
        self.unk1 += other.unk1
        self.unk2 += other.unk2

        return self

    def __itruediv__(self, scale):
        self.position /= scale
        self.unk1 //= scale
        self.unk2 //= scale
        return self

class ObjectRoutePoint(RoutePoint):
    def __init__(self, position):
        super().__init__(position)
class CameraRoutePoint(RoutePoint):
    def __init__(self, position):
        super().__init__(position)
class ReplayCameraRoutePoint(RoutePoint):
    def __init__(self, position):
        super().__init__(position)
class AreaRoutePoint(RoutePoint):
    def __init__(self, position):
        super().__init__(position)


# Section 5
# Objects
class MapObject(RoutedObject, RotatedObject):
    def __init__(self, position, objectid, rotation):
        RoutedObject.__init__(self, position)
        RotatedObject.__init__(self, position, rotation)
        self.objectid = objectid
        self.scale = Vector3(1.0, 1.0, 1.0)

        self.route = -1
        self.route_obj = None
        self.userdata = [0 for i in range(8)]

        self.single = 1
        self.double = 1
        self.triple = 1

        self.widget = None

        self.routepoint = None
        self.routeclass = ObjectRoute

    @classmethod
    def get_empty(cls):
        null_obj = cls.new()
        null_obj.objectid = None
        null_obj.position = None
        null_obj.rotation = None
        null_obj.scale = None
        null_obj.route_obj = None
        null_obj.userdata = [None] * 8
        null_obj.single = 0
        null_obj.double = 0
        null_obj.triple = 0

    @classmethod
    def new(cls, obj_id = 101):
        new_object = cls(Vector3(0.0, 0.0, 0.0), obj_id, Rotation.default())
        defaults = new_object.get_single_json_val("Default Values")
        if defaults is not None:
            new_object.userdata = [0 if x is None else x for x in defaults]
        return new_object

    def copy(self, copyroute=True):
        route_obj = self.route_obj
        widget = self.widget
        routepoint = self.routepoint

        self.route_obj = None
        self.widget = None
        self.routepoint = None
        self.routeclass = None
        new_camera = deepcopy(self)

        self.route_obj = route_obj
        self.widget = widget
        self.routepoint = routepoint
        self.routeclass = ObjectRoute

        if copyroute and route_obj is not None:
            new_camera.route_obj = route_obj.copy()
        else:
            new_camera.route_obj = route_obj

        new_camera.route = routepoint
        new_camera.routeclass = ObjectRoute

        return new_camera

    @classmethod
    def default_item_box(cls):
        item_box = cls(Vector3(0.0, 0.0, 0.0), 101)
        return item_box

    def split_prescence(self, prescence):
        self.single = prescence & 0x1
        self.double = prescence & 0x2 >> 1
        self.triple = prescence & 0x4 >> 2

    @classmethod
    def all_of_same_id(cls, objs):
        return all([obj.objectid == objs[0].objectid for obj in objs])

    @classmethod
    def common_obj(cls, objs):
        cmn = objs[0].copy()
        members = [attr for attr in dir(cmn) if not callable(getattr(cmn, attr)) and not attr.startswith("__")]
        return cmn


    @classmethod
    def from_file(cls, f):
        object = cls(Vector3(0.0, 0.0, 0.0), 0, Rotation.default())

        object.objectid = read_uint16(f)

        f.read(2)
        object.position = Vector3.from_file(f)
        object.rotation = Rotation.from_file(f)

        object.scale = Vector3.from_file(f)
        object.route = read_uint16(f)
        if object.route == 65535:
            object.route = -1
        object.userdata = list(unpack(">hhhhhhhh", f.read(2 * 8)))
        object.split_prescence( read_uint16(f) )

        return object

    def write(self, f, routes):

        f.write(pack(">H", self.objectid  ))


        f.write(pack(">H", 0) )
        self.position.write(f)
        self.rotation.write(f)
        self.scale.write(f)
        route = self.set_route(routes)
        route = (2 ** 16 - 1) if route == -1 else route
        f.write(pack(">H", route) )

        special_setting = self.get_routepoint_idx()
        if special_setting is not None and self.route_obj is not None and self.routepoint in self.route_obj.points:
            self.userdata[special_setting] = self.route_obj.points.index(self.routepoint)

        for i in range(8):
            f.write(pack(">h", self.userdata[i]))

        presence = self.single | (self.double << 1) | (self.triple << 2)

        f.write( pack(">H", presence) )
        return 1
    def copy(self):

        route_obj = self.route_obj
        widget = self.widget
        routepoint = self.routepoint
        self.route_obj = None
        self.widget = None
        self.routepoint = None

        new_object = deepcopy(self)

        self.route_obj = route_obj
        self.widget = widget
        self.routepoint = routepoint

        new_object.route_obj = route_obj
        new_object.routepoint = routepoint


        return new_object

    def has_route(self):
        json_data = self.load_param_file()
        if (json_data is not None) and "Route Info" in json_data:
            return json_data["Route Info"]
        return None

    def set_route(self, routes):
        for i, route in enumerate(routes):
            if route == self.route_obj:
                return i
        return -1

    def load_param_file(self):
        if (self.objectid is None) or (not self.objectid in OBJECTNAMES):
            return None
        name = OBJECTNAMES[self.objectid]
        with open(os.path.join("object_parameters", name+".json"), "r") as f:
            data = json.load(f)
        return data

    def get_single_json_val(self, text):
        json_data = self.load_param_file()
        if (json_data is not None) and text in json_data:
            return json_data[text]
        return None

    def get_route_text(self):
        return self.get_single_json_val("Route Point Settings")

    def get_description(self):
        return self.get_single_json_val("Description")

    def get_routepoint_idx(self):
        return self.get_single_json_val("Route Start Point")

    def get_default_values(self):
        return self.get_single_json_val("Default Values")

    def route_info(self):
        route_info = self.get_single_json_val("Route Info")
        if route_info is not None:
            return route_info
        return 0

    def reassign_routepoint(self):
        if self.route_obj is None or self.get_routepoint_idx() is None:
            return
        closest_point_idx = argmin(array([x.position.distance(self.position) for x in self.route_obj.points]))
        self.routepoint = self.route_obj.points[closest_point_idx]

    def get_kcl_name(self):
        kcl_file = self.get_single_json_val("KCL File")
        if not kcl_file:
            return None
        kcl_index = self.get_single_json_val("KCL Index")
        if kcl_index is None:
            return kcl_file + ".kcl"
        return kcl_file + str(self.userdata[kcl_index]) + ".kcl"

    def __iadd__(self, other):
        self = RoutedObject.__iadd__(self, other)
        self.rotation += other.rotation
        self.scale += other.scale
        self.single = self.single if self.single == other.single else 1
        self.double = self.double if self.double == other.double else 1
        self.triple = self.triple if self.triple == other.triple else 1

        if self.objectid != other.objectid:
            self.object_id = None
            self.user_data = [0] * 8
            return self

        for i in range(8):
            self.user_data[i] += other.user_data[i]
        return self

    def __itruediv__(self, count):
        self.position /= count
        self.rotation /= count
        self.scale /= count

        if self.object_id is None:
            return self

        for i in range(8):
            self.user_data[i] //= count
        return self


class MapObjects(ObjectContainer):
    def __init__(self):
        super().__init__()

    @classmethod
    def from_file(cls, f, objectcount):
        mapobjs = cls()

        for i in range(objectcount):
            obj = MapObject.from_file(f)
            if obj is not None:
                mapobjs.append(obj)

        return mapobjs

    def write(self, f, routes):

        f.write(b"GOBJ")
        f.write(pack(">H", len(self)))
        f.write(pack(">H", 0) )

        for object in self:
            object.write(f, routes)

    def get_routes(self):
        return list(set([obj.route_obj for obj in self if obj.route_obj is not None and obj.route_info()]))

# Section 6
# Kart/Starting positions

class KartStartPoint(RotatedObject):
    def __init__(self, position, rotation):
        super().__init__(position, rotation)
        self.playerid = 0xFF

    @classmethod
    def new(cls):
        return cls(Vector3.default(), Rotation.default())

    @classmethod
    def from_file(cls, f):
        position = Vector3.from_file(f)
        rotation = Rotation.from_file(f)
        kstart = cls(position, rotation)
        kstart.playerid = read_uint8(f)
        return kstart

    def write(self,f):
        self.position.write(f)
        self.rotation.write(f)

        if self.playerid == 0xFF:
            f.write(pack(">H", self.playerid + 0xFF00 ) )
        else:
            f.write(pack(">H", self.playerid ) )
        f.write(pack(">H",  0) )

    def copy(self):
        return deepcopy(self)

    def __iadd__(self, other):
        self.position += other.position
        self.rotation += other.rotation
        return self

    def __itruediv__(self, count):
        self.position /= count
        self.rotation /= count
        return self

class KartStartPoints(object):
    def __init__(self):
        self.positions = []

        self.pole_position = 0
        self.start_squeeze = 0

        self.widget = None


    @classmethod
    def from_file(cls, f, count):
        kspoints = cls()
        for i in range(count):
            kstart = KartStartPoint.from_file(f)
            kspoints.positions.append(kstart)

        return kspoints

    def write(self, f):
        f.write(b"KTPT")
        f.write(pack(">H", len(self.positions)))
        f.write(pack(">H", 0) )
        for position in self.positions:
            position.write(f)

# Section 7
# Areas
class Area(RoutedObject, RotatedObject):
    level_file = None
    can_copy = True
    def __init__(self, position, rotation):
        RoutedObject.__init__(self, position)
        RotatedObject.__init__(self, position, rotation)
        self.shape = 0
        self.type = 0
        self.cameraid = -1
        self.camera = None
        self.priority = 0

        self.scale = Vector3(1.0, 1.0, 1.0)

        self.setting1 = 0
        self.setting2 = 0

        self.route = -1
        self.route_obj = None

        self.enemypointid = -1
        self.enemypoint = None

        self.widget = None
        self.routeclass = AreaRoute

    @classmethod
    def new(cls):
        return cls(Vector3.default(), Rotation.default())

    @classmethod
    def default(cls, type = 0):
        area = cls.new()
        area.scale = Vector3(1, .5, 1)
        area.type = type
        return area

    @classmethod
    def from_file(cls, f):

        shape = read_uint8(f) #shape
        type = read_uint8(f)
        camera = read_int8(f)
        priority = read_uint8(f)    #priority

        position = Vector3.from_file(f)
        area = cls(position, Rotation.default())

        area.shape = shape
        area.type = type

        area.cameraid = camera
        if type != 0:
            area.cameraid = -1
        area.priority = priority
        area.rotation = Rotation.from_file(f)

        area.scale = Vector3.from_file(f)

        area.setting1 = read_int16(f) #unk1
        area.setting2 = read_int16(f) #unk2
        area.route = read_uint8(f) #route
        if area.type != 3:
            area.route = -1
        area.enemypointid = read_uint8(f) #enemy
        if area.type != 4:
            area.enemypointid = -1

        f.read(2)

        return area

    def write(self, f, cameras, routes, enemypoints):
        f.write(pack(">B", self.shape) ) #shape
        f.write(pack(">B", self.type ) )
        cameraid = self.set_camera(cameras)
        cameraid = 255 if cameraid < 0 else cameraid
        f.write(pack(">B", cameraid) )
        f.write(pack(">B", self.priority) ) #priority

        self.position.write(f)
        self.rotation.write(f)
        self.scale.write(f)

        enemypointid = self.set_enemypointid(enemypoints)
        enemypointid = 255 if enemypointid < 0 else enemypointid
        route = self.set_route(routes)
        route = 255 if route < 0 else route
        f.write(pack(">HHBBH", self.setting1, self.setting2, route, enemypointid, 0 ) )
        return 1

    def copy(self, copy_cam = False):
        enemypoint = self.enemypoint
        camera = self.camera
        route_obj = self.route_obj
        widget = self.widget

        self.enemypoint = None
        self.camera = None
        self.route_obj = None
        self.widget = None

        new_area = deepcopy(self)

        self.enemypoint = enemypoint
        self.camera = camera
        self.route_obj = route_obj
        self.widget = widget

        new_area.enemypoint = enemypoint
        if copy_cam and camera is not None:
            new_area.camera = camera.copy()
        else:
            new_area.camera = camera
        new_area.route_obj = route_obj

        return new_area

    #type 0 - camera
    def set_camera(self, cameras):
        if self.type == 0:
            for i, camera in enumerate(cameras):
                if camera == self.camera:
                    return i
        return -1

    #type 3 - moving road
    def set_route(self, routes):
        if self.type == 3:
            for i, route in enumerate(routes):
                if route == self.route_obj:
                    return i
        return -1

    #type 4 - force recalc
    def set_enemypointid(self, enemies):
        if self.type == 4:
            point_idx = enemies.get_index_from_point(self.enemypoint)
            return point_idx
        return -1

    def find_closest_enemypoint(self):
        enemygroups = __class__.level_file.enemypointgroups.groups
        min_distance = 9999999999999
        self.enemypoint = None
        for group in enemygroups:
            for point in group.points:
                distance = self.position.distance( point.position)
                if distance < min_distance:
                    self.enemypoint = point
                    min_distance = distance

    def get_route_text(self):
        return ["Speed", "Rotation (Var 2)"]

    def check(self, pos:Vector3):
        forward, up, left = self.rotation.get_vectors()
        diff = pos - self.position
        dotVec = Vector3( left.dot(diff), up.dot(diff), forward.dot(diff) )
        scale = self.scale.scale_by( Vector3(5000, 10000, 5000))
        if scale.y < dotVec.y or dotVec.y < 0:
            return False
        if self.shape == 1: #cylinder
            if (scale.x ** 2 < (dotVec.x ** 2 + dotVec.z ** 2)):
                return False
        else: #box
            if (scale.x < dotVec.x) or (dotVec.x < -scale.x):
                return False
            if (scale.z < dotVec.z) or (dotVec.z < -scale.z):
                return False
        return True

    def route_info(self):
        if self.type == 3:
            return 2
        return 0

    def change_type(self, new_type):
        self.type = new_type
        self.widget.update_name()
        if new_type not in (3, 4, 7):
            return
        if self.type == 3:
            self.create_route(True)
        elif self.type == 4:
            self.find_closest_enemypoint
        elif self.type == 7:
            if __class__.level_file.areas.boo_obj is None:
                __class__.level_file.areas.boo_obj = MapObject.new(396)

    def __iadd__(self, other):
        self = RoutedObject.__iadd__(self, other)
        self.rotation += other.rotation
        self.scale += other.scale

        self.shape = self.shape if self.shape == other.shape else 0
        self.camera = self.camera if self.camera == other.camera else None

        if self.type != other.type:
            self.type = None
            return self
        self.setting1 += other.setting1
        self.setting2 += other.setting2

        return self

    def __itruediv__(self, count):
        self.position /= count
        self.rotation /= count
        self.scale /= count

        self.setting1 //= count
        self.setting2 //= count

        return self

class Areas(ObjectContainer):
    def __init__(self):
        super().__init__()
        self.boo_obj = None

    @classmethod
    def from_file(cls, f, count):
        areas = cls()
        for i in range(count):
            new_area = Area.from_file(f)
            if new_area is not None:
                areas.append(new_area)

        return areas

    def write(self, f, cameras, routes, enemypoints):
        f.write(b"AREA")
        area_count_off = f.tell()
        f.write(pack(">H", 0xFFFF) )
        f.write(pack(">H", 0) )

        num_written = 0
        for area in self:
            num_written += area.write(f, cameras, routes, enemypoints)

        end_sec = f.tell()
        f.seek(area_count_off)
        f.write(pack(">H", num_written) )
        f.seek(end_sec)

    def get_type(self, area_type):
        return [area for area in self if area.type == area_type]



    def remove_invalid(self):
        invalid_areas = [area for area in self if area.type < 0 or area.type > 10]
        for area in invalid_areas:
            self.remove_area( area )

    def get_routes(self):
        return list(set([area.route_obj for area in self if area.type == 3]))


class ReplayAreas(Areas):
    def __init__(self):
        super().__init__()

    def get_cameras(self):
        return list(set([area.camera for area in self if area.camera is not None]))

    def get_routes(self):
        cameras = self.get_cameras()
        routes = [cam.route_obj for cam in cameras if cam.route_obj is not None and cam.route_info()]
        return list(set([x for x in routes if len(x.points) > 1]))
# Section 8
# Cameras
class FOV:
    def __ini__(self):
        self.start = 0
        self.end = 0
class Cameras(ObjectContainer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.startcamid = -1
        self.startcam = None
        self.goalcam = GoalCamera.new()

    @classmethod
    def from_file(cls, f, count):
        cameras = cls()
        for i in range(count):

            cameras.append( Camera.from_file(f) )

        return cameras

    def to_opening(self):
        for camera in self:
            camera.__class__ = OpeningCamera

    def to_replay(self):
       for camera in self:
            camera.__class__ = ReplayCamera

    def get_type(self, type):
        return [cam for cam in self if cam.type == type]

    def get_routes(self):
        routes = [cam.route_obj for cam in self if cam.route_obj is not None and cam.route_info()]
        return list(set([x for x in routes if len(x.points) > 1]))

    def trim_unused(self, set_goal=False):
        if set_goal:
            goal_cams = self.get_type(0)
            self.goalcam = GoalCamera.from_generic(goal_cams[0]) if goal_cams else GoalCamera.new()
        used_cams = self.get_opening_cams()
        unused_cams = [cam for cam in self if not cam in used_cams]
        for cam in unused_cams:
            self.remove(cam)

    def get_opening_cams(self):
        opening_cams = []
        next_cam : Camera = self.startcam
        while next_cam is not None and next_cam not in opening_cams:
            opening_cams.append(next_cam)
            next_cam = next_cam.nextcam_obj
        return opening_cams

class Camera(RoutedObject):
    level_file = None
    can_copy = True
    def __init__(self, position):
        super().__init__(position)
        self.type = 1
        self.nextcam = -1
        self.nextcam_obj = None
        self.shake = 0
        self.route = -1
        self.route_obj = None
        self.routespeed = 0
        self.zoomspeed = 5
        self.viewspeed = 0
        self.startflag = 0
        self.movieflag = 0

        self.rot = Rotation.default()

        self.fov = FOV()
        self.fov.start = 30
        self.fov.end = 20

        self.position2 = Vector3(0.0, 0.0, 0.0)
        self.position3 = Vector3(0.0, 0.0, 0.0)
        self.follow_player = 0

        self.camduration = 0

        self.widget = None
        self.routeclass = CameraRoute
        self.position2_simple = self.position2
        self.position3_simple = self.position3
        self.position2_player = Vector3Relative(Vector3(200, 100, -500), self.position)
        self.position3_player = Vector3Relative(Vector3(0.0, 0.0, 0.0), self.position)


    @classmethod
    def new(cls):
        return cls(Vector3(0.0, 0.0, 0.0))
    
    @classmethod
    def default(cls, type = 1):
        camera = cls(Vector3(0.0, 0.0, 0.0))
        camera.type = type
        return camera

    @classmethod
    def from_file(cls, f):

        type = read_uint8(f)
        next_cam = read_int8(f)
        shake = read_uint8(f)
        route = read_int8(f)

        move_velocity = read_uint16(f)
        zoom_velocity = read_uint16(f)
        view_velocity = read_uint16(f)

        start_flag = read_uint8(f)
        movie_flag = read_uint8(f)

        position = Vector3.from_file(f)
        cam = cls(position)

        cam.type = type
        cam.nextcam = next_cam
        cam.shake = shake
        cam.route = route
        cam.routespeed = move_velocity
        cam.zoomspeed = zoom_velocity
        cam.viewspeed = view_velocity

        cam.startflag = start_flag
        cam.movieflag = movie_flag

        cam.rot = Rotation.from_file(f)

        cam.fov.start = read_float(f)
        cam.fov.end = read_float(f)
        cam.position2 = Vector3.from_file(f)
        cam.position3 = Vector3.from_file(f)
        if cam.type in (0, 1,2, 4, 5):
            cam.position2_simple = cam.position2.copy()
            cam.position3_simple = cam.position3.copy()
        else:
            cam.position2_player = Vector3Relative(cam.position2, cam.position)
            cam.position3_player = Vector3Relative(cam.position3, cam.position)
        cam.camduration = read_float(f)

        return cam

    def copy(self, copyroute=True):
        nextcam_obj = self.nextcam_obj
        route_obj = self.route_obj
        widget = self.widget

        self.nextcam_obj = None
        self.route_obj = None
        self.widget = None
        new_camera = deepcopy(self)

        self.nextcam_obj = nextcam_obj
        self.route_obj = route_obj
        self.widget = widget

        new_camera.nextcam_obj = None
        if copyroute and route_obj is not None:
            new_camera.route_obj = route_obj.copy()
        else:
            new_camera.route_obj = route_obj


        return new_camera

    def write(self, f, cameras, routes):
        type = self.to_kmp_type()
        f.write(pack(">B", type ) )
        nextcam = self.set_nextcam(cameras)
        nextcam = 255 if nextcam < 0 else nextcam
        route = self.set_route(routes)
        route = 255 if route < 0 else route
        f.write(pack(">BBB", nextcam, 0, route) )

        f.write(pack(">H", self.routespeed ) )
        f.write(pack(">H", self.zoomspeed ) )
        f.write(pack(">H", self.viewspeed ) )

        f.write(pack(">B", self.startflag ) )
        f.write(pack(">B", self.movieflag ) )

        self.position.write(f)
        self.rot.write(f)

        f.write(pack(">ff", self.fov.start, self.fov.end))

        position2 = self.position2_player if self.type == 3 else self.position2_simple
        position3 = self.position3_player if self.type == 3 else self.position3_simple
        f.write(pack(">fff", position2.x, position2.y, position2.z))
        f.write(pack(">fff", position3.x, position3.y, position3.z))

        f.write(pack(">f", self.camduration) )

        return 1

    def set_route(self, routes):
        if self.route_info():
            for i,route in enumerate(routes):
                if route == self.route_obj:
                    return i
        return -1

    def set_nextcam(self, cameras):
        if self.nextcam_obj is None:
            return -1
        for i, camera in enumerate(cameras):
            if self.nextcam_obj == camera:
                return i
        return -1

    def get_route_text(self):
        return ["Speed", None]

    def route_info(self):
        if self.type == 0:
            return 0
        return 1

    def to_kmp_type(self):
        if self.type == 0 or self.type > 6:
            return self.type
        has_route = self.route_info() and self.route_obj is not None and len(self.route_obj.points) > 1
        cam_type = 4
        if self.type in (3, 6):
            cam_type = 6 if has_route else 3
        elif self.follow_player:
            cam_type = 2 if has_route else 1
        elif has_route:
            cam_type = 5
        return cam_type

    def from_kmp_type(self):
        if self.type == 0:
            self.type = 0
        elif self.type in (1, 2):
            self.follow_player = 1
            self.type = 1
        elif self.type in (4,5):
            self.follow_player = 0
            self.type = 1
        elif self.type == 6:
            self.type = 3

    def handle_type_change(self):
        if self.route_obj is None or not self.route_obj.points:
            return
        #has a route
        if self.type == 1:
            self.create_route(True, None, True, True)
            self.position = self.route_obj.points[0].position
        else:
            self.create_route(True, None, False, True)
            for point in self.route_obj.points:
                point.position = Vector3Relative(point.position, self.position)
    def setup_route(self, override=True):
        if not (self.route_obj is None and override):
            return
        self.route_obj = self.routeclass()
        new_point = self.route_obj.pointclass(self.position)
        self.route_obj.points.append(new_point)

    def __iadd__(self, other):
        RoutedObject.__iadd__(self, other)

        self.routespeed += other.routespeed
        self.zoomspeed += other.zoomspeed
        self.viewspeed += other.viewspeed

        return self

    def __itruediv__(self, count):
        self.position /= count
        self.routespeed //= count
        self.viewspeed //= count
        self.zoomspeed //= count

        return self

class ReplayCamera(Camera):
    def __init__(self, position):
        super().__init__(position)
        self.routeclass = ReplayCameraRoute

    @classmethod
    def from_generic(cls, generic):
        generic.__class__ = cls
        generic.routeclass = ReplayCameraRoute
        generic.follow_player = 1
        return generic

    @classmethod
    def default(cls, type):
        camera = cls(Vector3(0.0, 0.0, 0.0))
        camera.type = type
        camera.follow_player = True
        return camera

class OpeningCamera(Camera):
    def __init__(self, position):
        super().__init__(position)
        self.type = 1
        self.follow_player = False

    @classmethod
    def from_generic(cls, generic):
        generic.__class__ = cls
        generic.type = 1
        generic.follow_player = False
        return generic

class GoalCamera(Camera):
    @classmethod
    def from_generic(cls, generic):
        generic.__class__ = cls
        generic.follow_player = False
        return generic

    @classmethod
    def new(cls):
        cam =  cls(Vector3(-860.444, 6545.688, 3131.74))
        cam.position2_simple = Vector3(-30, -1.0, 550)
        cam.position3_simple = Vector3(-5, 1.0, 0)
        cam.position2 = Vector3(-30, -1.0, 550)
        cam.position3 = Vector3(-5, 1.0, 0)
        cam.zoomspeed = 30
        cam.fov.start = 85
        cam.fov.end = 40
        cam.type = 0

        return cam

    @classmethod
    def from_generic(cls, generic):
        generic.__class__ = cls
        generic.follow_player = False
        return generic

# Section 9
# Jugem Points
class JugemPoint(RotatedObject):
    def __init__(self, position, rotation):
        super().__init__(position, rotation)
        self.range = 0

    @classmethod
    def new(cls):
        return cls(Vector3.default(), Rotation.default())


    @classmethod
    def from_file(cls, f):
        position = Vector3.from_file(f)
        rotation = Rotation.from_file(f)
        jugem = cls(position, rotation)


        read_uint16(f)

        jugem.range = read_int16(f)

        return jugem


    def write(self, f, count):
        self.position.write(f)
        self.rotation.write(f)
        f.write(pack(">H", count) )
        f.write(pack(">h", self.range ) )

    def copy(self):
        return deepcopy(self)

    def __iadd__(self, other):
        self.position += other.position
        self.rotation += other.rotation
        self.range = self.range if self.range == other.range else 0
        return self

    def __itruediv__(self, count):
        self.position /= count
        self.rotation /= count

        return self

class CannonPoint(RotatedObject):
    def __init__(self, position, rotation):
        super().__init__(position, rotation)
        self.id = 0
        self.shoot_effect = 0


    @classmethod
    def new(cls):
        return cls(Vector3.default(), Rotation.default())

    @classmethod
    def from_file(cls, f):
        position = Vector3.from_file(f)
        rotation = Rotation.from_file(f)

        cannon = cls(position, rotation)
        cannon.id = read_uint16(f)
        cannon.shoot_effect = read_int16(f)

        return cannon


    def write(self, f):
        self.position.write(f)
        self.rotation.write(f)
        f.write(pack(">Hh", self.id, self.shoot_effect) )


    def copy(self):
        return deepcopy(self)

    def __iadd__(self, other):
        self.position += other.position
        self.rotation += other.rotation
        self.shoot_effect = self.shoot_effect if self.shoot_effect == other.shoot_effect else 0
        return self

    def __itruediv__(self, count):
        self.position /= count
        self.rotation /= count

        return self

class MissionPoint(object):
    def __init__(self, position):
        self.position = position
        self.rotation = Rotation.default()
        self.mission_id = 0
        self.unk = 0


    @classmethod
    def new(cls):
        return cls(Vector3(0.0, 0.0, 0.0))

    @classmethod
    def from_file(cls, f):
        position = Vector3.from_file(f)
        jugem = cls(position)

        jugem.rotation = Rotation.from_file(f)
        jugem.mission_id = read_uint16(f)
        jugem.unk = read_uint16(f)

        return jugem


    def write(self, f, count):
        self.position.write(f)
        self.rotation.write(f)
        f.write(pack(">HH", count, self.unk) )

class KMP(object):
    def __init__(self):
        self.lap_count = 3
        self.pole_position = 0
        self.start_squeeze = 0
        self.lens_flare = 1
        self.flare_color = ColorRGB(255, 255, 255)
        self.flare_alpha = 0x32
        self.speed_modifier = 0

        self.kartpoints = KartStartPoints()
        self.enemypointgroups = EnemyPointGroups()
        self.itempointgroups = ItemPointGroups()

        self.checkpoints = CheckpointGroups()
        self.routes = ObjectContainer()

        self.objects = MapObjects()

        self.areas = Areas()

        self.replayareas = ReplayAreas()

        self.cameras = Cameras()

        self.respawnpoints = ObjectContainer()
        self.cannonpoints = ObjectContainer()

        self.missionpoints = ObjectContainer()

        Area.level_file = self
        Camera.level_file = self
        MapObject.level_file = self
        EnemyPointGroups.level_file = self

        self.set_assoc()

    def set_assoc(self):
        self.routes.assoc = ObjectRoute
        self.respawnpoints.assoc = JugemPoint
        self.cannonpoints.assoc = CannonPoint
        self.missionpoints.assoc = MissionPoint
        self.objects.assoc = MapObject

    @classmethod
    def make_useful(cls):
        kmp = cls()

        first_enemy = EnemyPointGroup.new()
        kmp.enemypointgroups.groups.append(first_enemy)
        first_enemy.add_new_prev(first_enemy)
        first_enemy.add_new_next(first_enemy)

        first_item = ItemPointGroup.new()
        kmp.itempointgroups.groups.append(first_item)
        first_item.add_new_prev(first_item)
        first_item.add_new_next(first_item)

        first_checkgroup = CheckpointGroup.new()
        kmp.checkpoints.groups.append(first_checkgroup)
        first_checkgroup.add_new_prev(first_checkgroup)
        first_checkgroup.add_new_next(first_checkgroup)
        kmp.kartpoints.positions.append( KartStartPoint.new() )

        kmp.respawnpoints.append(JugemPoint.new())

        return kmp

    def objects_with_position(self):
        for group in self.enemypointgroups.groups.values():
            for point in group.points:
                yield point

        for route in self.routes:
            for point in route.points:
                yield point
        for route in self.cameraroutes():
            for point in route.points:
                yield point
        for route in self.arearoutes():
            for point in route.points:
                yield point

    def objects_with_2positions(self):
        for group in self.checkpoints.groups:
            for point in group.points:
                yield point

    def objects_with_rotations(self):
        for object in self.objects:
            assert object is not None
            yield object

        for kartpoint in self.kartpoints.positions:
            assert kartpoint is not None
            yield kartpoint

        for area in self.areas:
            assert area is not None
            yield area

        for area in self.replayareas:
            assert area is not None
            yield area

        for camera in self.cameras:
            assert camera is not None
            yield camera

        for camera in self.cameras:
            assert camera is not None
            yield camera

        for respawn in self.respawnpoints:
            assert respawn is not None
            yield respawn

        for cannon in self.cannonpoints:
            assert cannon is not None
            yield cannon

        for mission in self.missionpoints:
            assert mission is not None
            yield mission

    def get_all_objects(self):
        objects = []

        for group in self.enemypointgroups.groups:
            objects.append(group)
            objects.extend(group.points)

        for group in self.itempointgroups.groups:
            objects.append(group)
            objects.extend(group.points)

        for group in self.checkpoints.groups:
            objects.append(group)
            objects.extend(group.points)

        for route in self.routes:
            objects.append(route)
            objects.extend(route.points)

        objects.extend(self.objects)
        objects.extend(self.kartpoints.positions)
        objects.extend(self.areas)
        objects.extend(self.replayareas)
        objects.extend(self.cameras)
        objects.extend(self.replayareas.get_cameras())
        objects.extend(self.cameras.get_routes())
        objects.extend(self.respawnpoints)
        objects.extend(self.cannonpoints)
        objects.extend(self.missionpoints)

        return objects

    @classmethod
    def from_file(cls, f):
        kmp = cls()
        magic = f.read(4)
        assert magic == b"RKMD"


        f.read(0xC)       #header stuff
        ktpt_offset = read_uint32(f)
        enpt_offset = read_uint32(f)
        enph_offset = read_uint32(f)
        itpt_offset = read_uint32(f)
        itph_offset = read_uint32(f)
        ckpt_offset = read_uint32(f)
        ckph_offset = read_uint32(f)
        gobj_offset = read_uint32(f)
        poti_offset = read_uint32(f)
        area_offset = read_uint32(f)
        came_offset = read_uint32(f)
        jgpt_offset = read_uint32(f)
        cnpt_offset = read_uint32(f)
        mspt_offset = read_uint32(f)
        stgi_offset = read_uint32(f)

        header_len = f.tell()
        f.seek(ktpt_offset + header_len)
        assert f.read(4) == b"KTPT"
        count = read_uint16(f)
        f.read(2)
        kmp.kartpoints = KartStartPoints.from_file(f, count)

        f.seek(enpt_offset + header_len)
        kmp.enemypointgroups = EnemyPointGroups.from_file(f)

        f.seek(itpt_offset + header_len)
        kmp.itempointgroups = ItemPointGroups.from_file(f)

        #skip itpt
        f.seek(ckpt_offset + header_len)
        kmp.checkpoints = CheckpointGroups.from_file(f, ckph_offset)

        #bol.checkpoints = CheckpointGroups.from_file(f, sectioncounts[CHECKPOINT])

        f.seek(gobj_offset + header_len)
        assert f.read(4) == b"GOBJ"
        count = read_uint16(f)
        f.read(2)
        kmp.objects = MapObjects.from_file(f, count)

        f.seek(poti_offset + header_len)
        assert f.read(4) == b"POTI"
        count = read_uint16(f)
        total = read_uint16(f)

        # will handle the routes
        kmp.routes = ObjectContainer.from_file(f, count, Route)


        f.seek(area_offset + header_len)
        assert f.read(4) == b"AREA"
        count = read_uint16(f)
        f.read(2)
        kmp.areas = Areas.from_file(f, count)

        f.seek(came_offset + header_len)
        assert f.read(4) == b"CAME"
        count = read_uint16(f)
        start = read_uint8(f)
        f.read(1)
        kmp.cameras = Cameras.from_file(f, count)
        kmp.cameras.startcamid = start

        f.seek(jgpt_offset + header_len)
        assert f.read(4) == b"JGPT"
        count = read_uint16(f)
        f.read(2)
        kmp.respawnpoints = ObjectContainer.from_file(f, count, JugemPoint)

        f.seek(cnpt_offset + header_len)
        assert f.read(4) == b"CNPT"
        count = read_uint16(f)
        f.read(2)

        for i in range(count):
            kmp.cannonpoints.append( CannonPoint.from_file(f)  )

        f.seek(mspt_offset + header_len)
        assert f.read(4) == b"MSPT"
        count = read_uint16(f)
        f.read(2)
        for i in range(count):
            kmp.missionpoints.append( MissionPoint.from_file(f)  )

        f.seek(stgi_offset + header_len)
        assert f.read(4) == b"STGI"
        f.read(2)
        f.read(2)
        kmp.lap_count = read_uint8(f)
        kmp.kartpoints.pole_position = read_uint8(f)
        kmp.kartpoints.start_squeeze = read_uint8(f)
        kmp.lens_flare = read_uint8(f)
        read_uint8(f)
        kmp.flare_color = ColorRGB.from_file(f)
        kmp.flare_alpha = read_uint8(f)

        read_uint8(f)

        b0 = read_uint8(f)
        b1 = read_uint8(f)

        kmp.speed_modifier = unpack('>f', bytearray([b0, b1, 0, 0])  )[0]

        kmp.set_assoc()

        Area.level_file = kmp
        EnemyPointGroups.level_file = kmp

        return kmp

    def fix_file(self):
        return_string = ""
        #change to be a map or something
        """take care of routes for objects/camera/areas"""
        #set all the used by stuff for routes

        routes_used_by = {}

        def add_to_map(dict, key, value):
            curr_val = dict.get(key, [])
            curr_val.append(value)
            dict[key] = curr_val

        #fix route headers before everything is split up
        for route in self.routes:
            if route.smooth == 1 and len(route.points) < 3:
                return_string += "A route had fewer than 3 points and was smooth. It is now not smooth."
                route.smooth = 0

        #remove invalid objects
        to_remove = []
        for object in self.objects:
            if object.objectid not in OBJECTNAMES:
                return_string += "An invalid object of id {0} was found and will be removed.".format(object.objectid)
                to_remove.append(object)
        [self.objects.remove(obj) for obj in to_remove]

        for object in self.objects:
            if object.route_info() > 0:
                if object.route > -1 and object.route < len(self.routes):
                    route = self.routes[object.route]
                    add_to_map(routes_used_by, route, object)
                elif object.route >= len(self.routes):
                    return_string += "Object {0} references route {1}, which does not exist. The reference will be removed.\n".format(get_kmp_name(object.objectid), object.route)

        for i, camera in enumerate(self.cameras):
            camera.from_kmp_type()
            if camera.route != -1 and camera.route < len(self.routes):
                route = self.routes[camera.route]
                add_to_map(routes_used_by, route, camera)
            elif camera.route >= len(self.routes):
                return_string += "Camera {0} references route {1}, which does not exist. The reference will be removed.\n".format(i, camera.route)

        cameras_used_by = {}
        for i, area in enumerate(self.areas):
            if area.type == 0:
                if area.cameraid != -1 and area.cameraid < len(self.cameras):
                    camera = self.cameras[area.cameraid]
                    add_to_map(cameras_used_by, camera, area)
                elif area.cameraid >= len(self.cameras):
                    return_string += "Area {0} references camera {1}, which does not exist. The reference will be removed.\n".format(i, area.cameraid)
                    area.cameraid = -1
            elif area.type == 3:
                if area.route != -1 and area.route < len(self.routes):
                    route = self.routes[area.route]
                    add_to_map(routes_used_by, route, area)
                elif area.route >= len(self.routes):
                    return_string += "Area {0} references route {1}, which does not exist. The reference will be removed.\n".format(i, area.route)

        #copy routes as necessary
        for i, (route, value) in enumerate(routes_used_by.items()):
            has_object = [obj for obj in value if isinstance(obj, MapObject) ]
            has_camera = [obj for obj in value if isinstance(obj, Camera) ]
            has_area = [obj for obj in value if isinstance(obj, Area) ]
            if len( [ x for x in (has_object, has_area, has_camera) if x ]  ) < 2:
                continue
            for objs in [objs for objs in (has_object, has_camera, has_area) if objs]:
                new_route = route.copy()
                self.routes.append(new_route)
                new_route_idx = len(self.routes)
                for obj in objs:
                    obj.route = new_route_idx

        #set route_obj
        for i, (route, value) in enumerate(routes_used_by.items()):
            for obj in value:
                obj.route_obj = route

        #remove self-linked routes
        for grouped_things in (self.enemypointgroups.groups, self.itempointgroups.groups, self.checkpoints.groups):
            #set the proper prevnext
            for i, group in enumerate(grouped_things):
                group.prevgroup = [grouped_things[i] for i in group.prevgroup if i != -1 and i < len(grouped_things)]
                group.nextgroup = [grouped_things[i] for i in group.nextgroup if i != -1 and i < len(grouped_things)]

            if len(grouped_things) < 2:
                continue
            for i,group in enumerate(grouped_things):
                if group in group.prevgroup and len(group.points) == 1:
                    return_string += "Group {0} was self-linked as a previous group. The link has been removed.\n".format(i)
                    group.remove_prev(group)
                if group in group.nextgroup  and len(group.points) == 1:
                    return_string += "Group {0} was self-linked as a next group. The link has been removed.\n".format(i)
                    group.remove_next(group)

        """sort cannonpoints by id"""
        self.cannonpoints.sort( key = lambda h: h.id)

        """remove invalid areas"""
        invalid_areas = []
        for i, area in enumerate(self.areas):
            if area.type < 0 or area.type > 10:
                invalid_areas.append(area)
                "Area {0} has type {1}, which is invalid. It will be removed.\n".format(i, area.type)
        for area in invalid_areas:
            self.areas.remove(area)

        """set cameras and enemypoints for areas"""
        num_cams = len(self.cameras)
        for area in self.areas.get_type(0):
            if area.cameraid > -1 and area.cameraid < num_cams:
                area.camera = self.cameras[area.cameraid]
        for area in self.areas.get_type(4):
            if area.enemypointid == -1:
                return_string += "A area of type 4 was found that referenced an enemypoint that does not exist.\
                    It will be assigned to the closest enemypoint instead.\n"
                area.find_closest_enemypoint()
            area.enemypoint = self.enemypointgroups.get_point_from_index(area.enemypointid)
            if area.enemypoint is None:
                return_string += "A area of type 4 was found that referenced an enemypoint that does not exist.\
                    It will be assigned to the closest enemypoint instead.\n"
                area.find_closest_enemypoint()

        """separate areas into replay and not"""
        self.replayareas.extend( self.areas.get_type(0) )
        for area in self.replayareas:
            self.areas.remove(area)
        self.areas.sort( key = lambda h: h.type)

        """separate cameras into replay and not"""

        #assign nextcams
        if self.cameras.startcamid < len(self.cameras):
            self.cameras.startcam = self.cameras[self.cameras.startcamid]
        opening_cameras = []

        if self.cameras.startcam: opening_cameras.append(self.cameras.startcam)

        for camera in self.cameras:
            if camera.nextcam != -1 and camera.nextcam < len(self.cameras):
                nextcam = self.cameras[camera.nextcam]
                camera.nextcam_obj = nextcam if nextcam not in opening_cameras else None

        #goalcam handling
        goalcams = self.cameras.get_type(0)
        if len(goalcams) > 1:
            return_string += "Multiple cameras of type 0 have been found. Only the first will be kept\n"
            self.cameras.goalcam = GoalCamera.from_generic(goalcams[0])
        elif len(goalcams) == 0:
            return_string += "No camera of type 0 has been found. One will be added\n"
        else:
            self.cameras.goalcam = GoalCamera.from_generic(goalcams[0])
        for camera in goalcams:
            self.cameras.remove(camera)



        #sep replay cameras
        replaycams = self.replayareas.get_cameras()
        for camera in replaycams:
            self.cameras.remove(camera)
            camera = ReplayCamera.from_generic(camera)

        """remove invalid cameras"""
        self.remove_invalid_cameras()

        """give all areas cameras"""
        repl_area_without_cams = [area for area in self.replayareas if area.camera is None]
        for area in repl_area_without_cams:
            return_string += "An area of type Camera did not reference a camera. It will be given a camera.\n"
            new_camera = ReplayCamera.new()
            new_camera.position = area.position + Vector3(2000, 0, 0)
            area.camera = new_camera

        self.cameras.trim_unused(set_goal=True)
        self.cameras.to_opening()

        """set respawn_obj for checkpoints"""
        for group in self.checkpoints.groups:
            for point in group.points:
                if point.respawnid > -1 and point.respawnid < len(self.respawnpoints):
                    point.respawn_obj = self.respawnpoints[point.respawnid]
                else:
                    return_string += "A checkpoint was found to have an invalid respawn reference\
                        it has been reassigned to the closest resapwn point.\n"
                    point.assign_to_closest(self.respawnpoints)

        """Convert and assign new routes"""
        new_types = ( (ObjectRoute, self.objects.get_routes()), (AreaRoute, self.areas.get_routes()),
                      (CameraRoute, self.cameras.get_routes()), (ReplayCameraRoute, self.replayareas.get_routes())  )

        for childclass, routecollec in new_types:
            for route in routecollec:
                new_route = route.to_childclass(childclass)
                for thing in self.route_used_by(route):
                    thing.route_obj = new_route

        for obj in self.objects:
            special_usersetting = obj.get_routepoint_idx()
            if (special_usersetting is not None) and obj.userdata[special_usersetting] < len(obj.route_obj.points):
                obj.routepoint = obj.route_obj.points[obj.userdata[special_usersetting]]

        """snap cameras to routes"""
        for camera in self.cameras:
            if camera.route_obj is not None and camera.route_obj.points:
                camera.position = camera.route_obj.points[0].position

        #set position2 and position3
        for camera in self.replayareas.get_cameras():
            has_route = camera.route_obj is not None and camera.route_obj.points
            if not has_route:
                continue
            if camera.type == 1:
                camera.position = camera.route_obj.points[0].position
                continue
            elif camera.type == 3:
                for point in camera.route_obj.points:
                    point.position = Vector3Relative(point.position, camera.position)
                camera.position2_player = camera.route_obj.points[0].position

        #type 7 area and boo
        boo_objs = [obj for obj in self.objects if obj.objectid == 396]
        [self.objects.remove(boo_obj) for boo_obj in boo_objs]
        boo_areas = [area for area in self.areas if area.type == 7]
        if not boo_objs and boo_areas:
            return_string += "Boo Areas are in the .kmp, but no boo objects exist. A boo object will be added.\n"
            self.areas.boo_obj = MapObject.new(396)
        elif boo_objs and not boo_areas:
            return_string += "Boo objects are in the .kmp, but no boo areas exist. The boo objects will be removed.\n"
        elif boo_objs and boo_areas:
            self.areas.boo_obj = boo_objs[0]
            if len(boo_objs) > 1:
                return_string += "Multiple boo objects are in the .kmp. Only one of them will be preserved.\n"


        return return_string

    @classmethod
    def from_bytes(cls, data: bytes) -> 'KMP':
        KMP = cls.from_file(BytesIO(data))
        KMP.fix_file()
        return KMP

    def write(self, f):
        f.write(b"RKMD") #file magic
        size_off = f.tell()
        f.write(b"FFFF") #will be the length of the file
        f.write(pack(">H", 0xF)) #number of sections
        f.write(pack(">H", 0x4c)) #length of header
        f.write(pack(">I", 0x9d8)) #length of header
        sec_offs = f.tell()
        f.write(b"FFFF" * 15) #placeholder for offsets

        offsets = [ f.tell()]  #offset 1 for ktpt
        self.kartpoints.write(f)

        offsets.append( f.tell() ) #offset 2 for entp
        enph_off = self.enemypointgroups.write(f)
        offsets.append(enph_off) #offset 3 for enph

        offsets.append( f.tell() ) #offset 4 for itpt
        itph_off = self.itempointgroups.write(f)
        offsets.append(itph_off) #offset 5 for itph

        offsets.append(f.tell()) #offset 6 for ckpt
        self.checkpoints.set_rspid(self.respawnpoints)
        ktph_offset = self.checkpoints.write(f)
        offsets.append(ktph_offset) #offset 7 for ktph

        cameraroutes = self.cameras.get_routes()
        replaycameraroutes = self.replayareas.get_routes()
        arearoutes = self.areas.get_routes()
        objectroutes = self.objects.get_routes()

        routes = ObjectContainer()
        routes.extend(replaycameraroutes)
        routes.extend(cameraroutes)
        routes.extend(arearoutes)
        routes.extend(objectroutes)

        all_objects = MapObjects()
        all_objects.extend(self.objects)
        if self.areas.boo_obj is not None and self.areas.get_type(7):
            all_objects.append(self.areas.boo_obj)

        offsets.append(f.tell() ) #offset 8 for gobj
        all_objects.write(f, routes)

        offsets.append(f.tell() ) #offset 9 for poti
        f.write(b"POTI")
        f.write(pack(">H", len(routes) ) )
        count_off = f.tell()
        f.write(pack(">H", 0xFFFF ) )  # will be overridden later

        count = 0
        for route in routes:
            count += route.write(f)

        offset = f.tell()
        offsets.append(offset) #offset 10 for AREA

        f.seek(count_off)
        f.write(pack(">H", count) ) #fill in count of points for poti
        f.seek(offset)

        cameras = Cameras()
        replaycameras = self.replayareas.get_cameras()
        cameras.append( self.cameras.goalcam)
        cameras.extend( replaycameras )
        cameras.extend( self.cameras )

        areas = Areas()
        areas.extend( self.areas  )
        areas.extend( self.replayareas )
        areas.write(f, cameras, routes, self.enemypointgroups )

        startcam = self.cameras.startcam
        startcamid = cameras.index(startcam) if startcam in cameras else 255
        offsets.append(f.tell() ) # offset 11 for CAME
        f.write(b"CAME")
        f.write(pack(">H", len(cameras) ) )
        f.write(pack(">BB", startcamid, 0) )

        for camera in cameras:
            camera.write(f, cameras, routes)

        offset = f.tell()  #offset 12 for JPGT
        offsets.append(offset)

        f.write(b"JGPT")
        f.write(pack(">H", len(self.respawnpoints) ) )
        f.write(pack(">H", 0 ) )

        count = 0
        for point in self.respawnpoints:
            point.write(f, count)
        count += 1


        offset = f.tell()
        offsets.append(offset) #offset 13 for CNPT

        f.write(b"CNPT")
        count_off = f.tell()
        f.write(pack(">H", len(self.cannonpoints) ) )  # will be overridden later
        f.write(pack(">H", 0 ) )

        for point in self.cannonpoints:
            point.write(f)
        offset = f.tell()
        offsets.append(offset) #offset 14 for MSPT

        f.write(b"MSPT")
        count_off = f.tell()
        f.write(pack(">H", len(self.missionpoints) ) )  # will be overridden later
        f.write(pack(">H", 0 ) )


        count = 0
        for point in self.missionpoints:
            point.write(f, count)
        count += 1
        offset = f.tell()

        offsets.append(offset) #offset 15 for STGI
        f.write(b"STGI")
        f.write(pack(">HH", 1, 0 ) )
        f.write(pack(">B", self.lap_count))
        f.write(pack(">BB", self.kartpoints.pole_position, self.kartpoints.start_squeeze) )
        f.write(pack(">B", self.lens_flare))
        f.write(pack(">BBBBB", 0, self.flare_color.r, self.flare_color.b, self.flare_color.b, self.flare_alpha ) )
        f.write(pack(">b", 0 ) )

        byte_array = pack(">f", self.speed_modifier)
        f.write( byte_array[0:2])

        assert( len(offsets) == 15 )
        size = f.tell()
        f.seek(size_off)
        f.write(pack(">I", size ) )
        f.seek(sec_offs)
        for i in range(15):
            f.write(pack(">I", offsets[i]  - 0x4C ) )

    def to_bytes(self) -> bytes:
        f = BytesIO()
        self.write(f)
        return f.getvalue()

    def auto_generation(self):
        """
            - add opening cams
            - add replay cams"""
        self.copy_enemy_to_item()
        self.create_checkpoints_from_enemy()
        self.checkpoints.set_key_cps()
        self.create_respawns()

    #respawnid code
    def create_respawns(self):

        #remove all respwans
        self.respawnpoints.clear()
        for checkgroup in self.checkpoints.groups:
            num_checks = len(checkgroup.points)
            for i in range(1, num_checks, 3):
                checkpoint_mid1 = (checkgroup.points[i].start + checkgroup.points[i].end) /2
                checkpoint_mid2 = (checkgroup.points[i-1].start + checkgroup.points[i-1].end)/2
                mid_position = (checkpoint_mid1 * .25) + (checkpoint_mid2 * .75)

                respawn_new = JugemPoint( mid_position )

                self.rotate_one_respawn(respawn_new, edity=True, editpos = True)
                self.respawnpoints.append(respawn_new)
        self.reassign_respawns()
        self.remove_unused_respawns()

    def reassign_respawns(self):
        if len(self.checkpoints.groups) == 0:
            return

        for checkgroup in self.checkpoints.groups:
            for checkpoint in checkgroup.points:
                checkpoint.assign_to_closest(self.respawnpoints)

    def reassign_one_respawn(self, respawn : JugemPoint):
        if len(self.checkpoints.groups) == 0:
            return

        for checkgroup in self.checkpoints.groups:
            for checkpoint in checkgroup.points:
                old_assign = checkpoint.respawn_obj
                checkpoint.assign_to_closest(self.respawnpoints)
                checkpoint.respawn_obj = old_assign if checkpoint.respawn_obj != respawn else checkpoint.respawn_obj

    def remove_respawn(self, rsp: JugemPoint):
        if len(self.respawnpoints) <= 1:
            return
        self.respawnpoints.remove(rsp)
        for checkgroup in self.checkpoints.groups:
            for checkpoint in checkgroup.points:
                if checkpoint.respawn_obj == rsp:
                    checkpoint.assign_to_closest(self.respawnpoints)

    def get_index_of_respawn(self, rsp: JugemPoint):
        for i, respawn in enumerate( self.respawnpoints) :
            if rsp == respawn:
                return i
        return -1

    def remove_unused_respawns(self):
        unused_respawns = [rsp for rsp in self.respawnpoints if rsp not in self.checkpoints.get_used_respawns()]
        unused_respawns.sort()
        unused_respawns.reverse()
        for rsp_idx in unused_respawns:
            self.remove_respawn( self.respawnpoints[rsp_idx]   )

    def find_closest_enemy_to_rsp(self, rsp: JugemPoint):
        enemy_groups = self.enemypointgroups.groups
        closest = None
        distance = 999999999
        group_idx = -1
        point_idx = -1
        master_point_idx = -1
        idx = 0
        for i, group in enumerate(enemy_groups):
            for j, point in enumerate(group.points):
                curr_distance = point.position.distance(rsp.position)
                if curr_distance < distance:
                    closest = point
                    distance = curr_distance
                    group_idx = i
                    point_idx = j
                    master_point_idx = idx
                idx += 1
        return closest, group_idx, point_idx, master_point_idx

    def rotate_one_respawn(self, rsp :JugemPoint, edity = False, editpos = False):
        point, group_idx, pos_idx, point_idx = self.find_closest_enemy_to_rsp(rsp)
        enemy_groups = self.enemypointgroups.groups

        if point_idx == -1:
            return

        point_behind_dis =  999999999999
        point_ahead_dis =   999999999999

        if pos_idx != 0:
            point_behind = enemy_groups[group_idx].points[pos_idx - 1].position
            point_behind_dis = point_behind.distance(rsp.position)
        if pos_idx < len(enemy_groups[group_idx].points) - 1:
            point_ahead = enemy_groups[group_idx].points[pos_idx + 1].position
            point_ahead_dis = point_ahead.distance(rsp.position)

        #no other points in group, i am not bothering with finding the linking points
        if point_behind_dis == point_ahead_dis and point_behind_dis == 999999999999:
            return

        if point_behind_dis < point_ahead_dis:
            pos_ray = point.position - point_behind
            midpoint = (point.position + point_behind) / 2
            pos_y = point_behind.y
        else:
            pos_ray = point_ahead - point.position
            midpoint = (point.position + point_ahead) / 2
            pos_y = point_ahead.y

        if editpos:
            rsp.position = midpoint.copy()
        if edity:
            rsp.position.y = pos_y

        if pos_ray.x == 0:
            pos_ray.x = 1

        theta = arctan( -pos_ray.z / pos_ray.x ) * 180 / 3.14
        if pos_ray.x > 0:
            theta += 180
        theta += 270
        rsp.rotation = Rotation(0, theta, 0)

    #enemy/item/checkpoint code
    def get_to_deal_with(self, obj):
        if isinstance(obj, (EnemyPointGroup, EnemyPoint, EnemyPointGroups) ):
            return self.enemypointgroups
        elif isinstance(obj, (ItemPointGroup, ItemPoint, ItemPointGroups) ):
            return self.itempointgroups
        else:
            return self.checkpoints

    def remove_group(self, del_group):
        to_deal_with = self.get_to_deal_with(del_group)

        to_deal_with.remove_group(del_group)

    def remove_point(self, del_point):
        to_deal_with = self.get_to_deal_with(del_point)

        to_deal_with.remove_point(del_point)

    def create_checkpoints_from_enemy(self):
        for checkgroup in self.checkpoints.groups:
            checkgroup.points.clear()
        self.checkpoints.groups.clear()

        #enemy_to_check = {-1 : -1}

        #create checkpoints from enemy points
        for i, group in enumerate( self.enemypointgroups.groups ):

            new_cp_group = CheckpointGroup()
            #new_cp_group.prevgroup = group.prevgroup
            #new_cp_group.nextgroup = group.nextgroup

            self.checkpoints.groups.append( new_cp_group )

            for j, point in enumerate( group.points ):
                draw_cp = False
                if i == 0 and j == 0:
                    draw_cp = True
                    #should both be vector3
                    central_point = self.kartpoints.positions[0].position
                    left_vector = self.kartpoints.positions[0].rotation.get_vectors()[2]
                    left_vector = Vector3( -1 * left_vector.x, left_vector.y,-1 * left_vector.z  )

                elif (i == 0 and j % 2 == 0 and len(group.points) > j + 1) or (i > 0 and j % 2 == 1 and len(group.points) > j + 1):
                #elif (i == 0  and len(group.points) > j + 1) or (i > 0 and len(group.points) > j + 1):
                    draw_cp = True
                    central_point = point.position

                    deltaX = group.points[j+1].position.x - group.points[j-1].position.x
                    deltaZ = group.points[j+1].position.z - group.points[j-1].position.z

                    left_vector = Vector3( -1 * deltaZ, 0, deltaX   ) * -1

                    left_vector.normalize()


                if draw_cp:

                    first_point = [central_point.x + 3500 * left_vector.x, 0, central_point.z + 3500 * left_vector.z]
                    second_point = [central_point.x - 3500 * left_vector.x, 0, central_point.z - 3500 * left_vector.z]

                    new_checkpoint = Checkpoint.new()
                    new_checkpoint.start = Vector3( *first_point)
                    new_checkpoint.end = Vector3(*second_point)
                    new_cp_group.points.append( new_checkpoint)
        #post processing:
        while i < len(self.checkpoints.groups) and len(self.checkpoints.groups) > 1:
            group = self.checkpoints.groups[i]
            if len(group.points) == 0:
                self.checkpoints.remove_group(group)
            else:
                i += 1

    def copy_enemy_to_item(self):
        self.itempointgroups = ItemPointGroups()

        for group in self.enemypointgroups.groups:
            new_group = ItemPointGroup()
            new_group.prevgroup = [self.enemypointgroups.get_idx(prev) for prev in group.prevgroup]
            new_group.nextgroup = [self.enemypointgroups.get_idx(next) for next in group.nextgroup]

            for point in group.points:
                new_point = ItemPoint.new()
                new_point.position = point.position.copy()

                new_group.points.append(new_point)

            self.itempointgroups.groups.append(new_group)

        for group in self.itempointgroups.groups:
            group.prevgroup = [self.itempointgroups.groups[prev] for prev in group.prevgroup]
            group.nextgroup = [self.itempointgroups.groups[next] for next in group.nextgroup]

    #routes
    def get_route_for_obj(self, obj):
        if isinstance(obj, (ReplayCameraRoute, ReplayCamera)):
            return ReplayCameraRoute()
        if isinstance(obj, (CameraRoute, Camera) ):
            return CameraRoute()
        elif isinstance(obj, (AreaRoute, Area)):
            return AreaRoute()
        else:
            return ObjectRoute()

    def create_route_for_obj(self, obj, add_points=False, ref_points=None, absolute_pos=False):
        if obj.route_info() < 1 or obj.route_obj is not None:
            return
        obj.route_obj = self.get_route_for_obj(obj)
        if add_points:
            obj.route_obj.add_points(obj.position, absolute_pos, ref_points)

    #cameras
    def remove_unused_cameras(self):
        self.cameras.trim_unused()

    def remove_camera(self, cam : Camera):
        if isinstance(cam, OpeningCamera):

            for camera in self.cameras:
                if camera.nextcam_obj == cam:
                    camera.nextcam_obj = None

            if self.cameras.startcam is cam:
                self.cameras.startcam = cam.nextcam_obj

            self.cameras.remove(cam)
        elif isinstance(cam, ReplayCamera):
            for area in self.camera_used_by(cam):
                area.camera = None

    def remove_invalid_cameras(self):
        invalid_cams = [camera for camera in self.cameras if camera.type < 0 or camera.type > 9]
        for cam in invalid_cams:
            self.remove_camera(cam)

    #objects
    def remove_object(self, obj: MapObject):
        self.objects.remove(obj)

    def remove_invalid_objects(self):
        invalid_objs = [obj for obj in self.objects if obj.objectid not in OBJECTNAMES]
        for obj in invalid_objs:
            self.remove_object(obj)

    #grabbing functions
    def get_route_collec_for(self, obj):
        if isinstance(obj, (Area, AreaRoute, AreaRoutePoint)):
            return self.areas.get_routes()
        elif isinstance(obj, (MapObject, ObjectRoute, ObjectRoutePoint)):
            return self.objects.get_routes()
        elif isinstance(obj, (ReplayCamera, ReplayCameraRoute, ReplayCameraRoutePoint)):
            return self.replayareas.get_routes()
        elif isinstance(obj, (Camera, CameraRoute, CameraRoutePoint)):
            return self.cameras.get_routes()
        else:
            all_routes = []
            all_routes.extend(self.areas.get_routes())
            all_routes.extend(self.objects.get_routes())
            all_routes.extend(self.replayareas.get_routes())
            all_routes.extend(self.cameras.get_routes())
            return all_routes

    def route_used_by(self, route: Route, mandatory=False):
        collec = []
        if isinstance(route, AreaRoute):
            collec = self.areas
        elif isinstance(route, ReplayCameraRoute):
            collec = self.replayareas.get_cameras()
        elif isinstance(route, CameraRoute):
            collec = self.cameras
        elif isinstance(route, ObjectRoute):
            collec = self.objects
        else:
            collec.extend(self.areas)
            collec.extend(self.replayareas.get_cameras())
            collec.extend(self.cameras)
            collec.extend(self.objects)
        if mandatory:
            return [x for x in collec if x.route_info() > 1 and x.route_obj == route]
        else:
            return [x for x in collec if x.route_info() and x.route_obj == route]

    def camera_used_by(self, camera: ReplayCamera):
        return [x for x in self.replayareas if x.camera == camera]

    def remove_area(self, area: Area):
        if area.type == 0:
            self.replayareas.remove(area)
            if area.camera is not None and not self.camera_used_by(area.camera):
                self.remove_camera(area.camera)
        else:
            self.areas.remove(area)

    def get_route_of_point(self, point:RoutePoint):
        collect = self.get_route_collec_for(point)
        for route in collect:
            if point in route.points:
                return route
        return None

    def get_linked(self, obj, lower=True, same=True, upper=True):
        upper_objs = []
        same_objs = []
        lower_objs = []
        #upper -----> lower
        #replay area <-> replay camera <-> replay camera route <-> replay camera route point
        #opening camera <-> openingcameraroute <-> opening camera route point
        #mapobject <-> mapobject route <-> mapobject camera route point
        #area -> enemypoint
        #area <-> area route <-> area route point

        if same:
            same_objs.append(obj)
        #if the point is a the ultimate lower - a routepoint
        if isinstance(obj, RoutePoint):
            route = self.get_route_of_point(obj)
            used_by = self.route_used_by(route)
            if same:
                same_objs.extend( route.points )
            if upper:
                upper_objs.extend( used_by )
                if isinstance(obj, ReplayCameraRoutePoint):
                    replay_cam = used_by[0]
                    upper_objs.extend( self.camera_used_by(replay_cam) )
        elif lower and isinstance(obj, Area):
            if obj.type == 4 and obj.enemypoint is not None:
                lower_objs.append(lower_objs)
            elif obj.type == 0:
                lower_objs.append(obj.camera)
                if obj.camera.route_obj is not None and len(obj.camera.route_obj.points) > 1:
                    lower_objs.extend(obj.camera.route_obj.points)
        elif upper and isinstance(obj, ReplayCamera):
            upper_objs.extend( self.camera_used_by(obj) )

        if lower and isinstance(obj, RoutedObject) and obj.route_info() and obj.route_obj:
            if isinstance(obj, Camera):
                if len(obj.route_obj.points) > 1:
                    lower_objs.extend( obj.route_obj.points )
            else:
                lower_objs.extend( obj.route_obj.points )

        selected = list(set(upper_objs + same_objs + lower_objs))
        selected_positions = [x.position for x in selected if hasattr(x, "position")]
        selected_rotations = [x.rotation for x in selected if hasattr(x, "rotation")]


        return selected, selected_positions, selected_rotations

    def get_next_points(self, points):
        next_points = []
        next_positions = []
        next_rotations = []
        for point in points:
            next_point = None
            if isinstance(point, KMPPoint):
                to_deal_with = self.get_to_deal_with(point)
                group_idx, group, point_idx = to_deal_with.find_group_of_point(point)
                if len(group.points) > point_idx + 1:
                    next_point = group.points[point_idx + 1]
            elif isinstance(point, RoutePoint):
                route = self.get_route_of_point(point)
                index = route.points.index(point)
                if len(route.points) > index + 1:
                    next_point = route.points[index + 1]
            elif isinstance(point, Camera) and point.has_route():
                route = point.route_obj
                if len(route.points) > 1:
                    next_point = route.points[1]

            if next_point and next_point not in points:
                next_points.append(next_point )
                if isinstance(next_point, Checkpoint):
                    next_positions.append(next_point.start)
                    next_positions.append(next_point.end)
                else:
                    next_positions.append(next_point.position)
        return next_points, next_positions, next_rotations

    def get_prev_points(self, points):
        prev_points = []
        prev_positions = []
        prev_rotations = []
        for point in points:
            prev_point = None
            if isinstance(point, KMPPoint):
                to_deal_with = self.get_to_deal_with(point)
                group_idx, group, point_idx = to_deal_with.find_group_of_point(point)
                if point_idx > 0:
                    prev_point = group.points[point_idx - 1]
            elif isinstance(point, RoutePoint):
                route = self.get_route_of_point(point)
                index = route.points.index(point)
                if index > 0:
                    prev_point = route.points[index - 1]
            if prev_point and prev_point not in points:
                prev_points.append(prev_point )
                if isinstance(prev_point, Checkpoint):
                    prev_positions.append(prev_point.start)
                    prev_positions.append(prev_point.end)
                prev_positions.append(prev_point.position)
        return prev_points, prev_positions, prev_rotations

with open("lib/mkwiiobjects.json", "r") as f:
    tmp = json.load(f)
    OBJECTNAMES = {}
    for key, val in tmp.items():
        OBJECTNAMES[int(key)] = val
    del tmp

REVERSEOBJECTNAMES = OrderedDict()
valpairs = [(x, y) for x, y in OBJECTNAMES.items()]
valpairs.sort(key=lambda x: x[1])
for key, val in valpairs:
    REVERSEOBJECTNAMES[OBJECTNAMES[key]] = key


def get_kmp_name(id):
    if id not in OBJECTNAMES:
        OBJECTNAMES[id] = "Unknown {0}".format(id)
        REVERSEOBJECTNAMES[OBJECTNAMES[id]] = id
        return "unknown " + str(id)
        #return
    #else:
    return OBJECTNAMES[id]