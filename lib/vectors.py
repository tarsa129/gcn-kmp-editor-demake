from math import sqrt
from io import StringIO
from numpy import arctan2, ndarray, matmul, deg2rad, cos, sin
from math import atan2
from copy import deepcopy
from struct import unpack, pack
from scipy.spatial.transform import Rotation as R

class Vector3(object):
    def __init__(self, x, y, z):
        self.x = x
        self.y = y
        self.z = z

    def copy(self):
        return Vector3(self.x, self.y, self.z)

    def norm(self):
        return sqrt(self.x**2 + self.y**2 + self.z**2)
    
    def absolute(self):
        return self

    def normalize(self):
        norm = self.norm()
        self.x /= norm
        self.y /= norm
        self.z /= norm

    def unit(self):
        return self/self.norm()

    def cross(self, other_vec):
        return Vector3(self.y*other_vec.z - self.z*other_vec.y,
                       self.z*other_vec.x - self.x*other_vec.z,
                       self.x*other_vec.y - self.y*other_vec.x)

    def dot(self, other_vec):
        return self.x*other_vec.x + self.y*other_vec.y + self.z*other_vec.z

    def __truediv__(self, other):
        return Vector3(self.x/other, self.y/other, self.z/other)

    def __add__(self, other_vec):
        return Vector3(self.x+other_vec.x, self.y+other_vec.y, self.z+other_vec.z)

    def __mul__(self, other):
        return Vector3(self.x*other, self.y*other, self.z*other)

    def __sub__(self, other_vec):
        return Vector3(self.x-other_vec.x, self.y-other_vec.y, self.z-other_vec.z)

    def cos_angle(self, other_vec):
        return self.dot(other_vec)/(self.norm()*other_vec.norm())

    def __iadd__(self, other_vec):
        self.x += other_vec.x
        self.y += other_vec.y
        self.z += other_vec.z
        return self

    def __isub__(self, other_vec):
        self.x -= other_vec.x
        self.y -= other_vec.y
        self.z -= other_vec.z
        return self

    def __imul__(self, other):
        self.x *= other
        self.y *= other
        self.z *= other
        return self

    def __itruediv__(self, other):
        self.x /= other
        self.y /= other
        self.z /= other
        return self

    def is_zero(self):
        return self.x == self.y == self.z == 0

    def __eq__(self, other_vec):
        return self.x == other_vec.x and self.y == other_vec.y and self.z == other_vec.z

    def __hash__(self):
        return hash((self.x, self.y, self.z))

    def __str__(self):
        return str((self.x, self.y, self.z))

    def distance(self, other):
        #this is not true distance - changes in y are punished so that overlapping stuff doesn't affect calculations.
        return sqrt( (self.x - other.x) ** 2 + (self.y - other.y) ** 2 + (self.z - other.z) ** 2  )

    def distance_2d(self, other):
        return sqrt( (self.x - other.x) ** 2 + (self.z - other.z) ** 2  )

    def flip_render(self):
        return Vector3(self.x, self.y, -self.z)

    def to_euler(self):
        #flipping the first one flips the thing
        horiz = arctan2(self.z, self.x)
        verti = arctan2(self.y, self.z)
        return horiz, verti

    def scale_by(self, other_vec):
        self.x = self.x * other_vec.x
        self.y = self.y * other_vec.y
        self.z = self.z * other_vec.z

    def rotate_y(self, deg):
        x = self.x * cos(deg2rad(deg)) - self.z * sin(deg2rad(deg))
        z = self.z * cos(deg2rad(deg)) + self.x * sin(deg2rad(deg))
        self.x = x
        self.z = z

    def rotate_around_point(self, point, axis, delta):
        diff = self - point
        setattr(diff, axis, 0)
        length = diff.norm()
        if length > 0:
            diff.normalize()
            if axis == "y":
                angle = atan2(diff.x, diff.z) + delta
                self.x = point.x + length * sin(angle)
                self.z = point.z + length * cos(angle)
            elif axis == "x":
                angle = atan2(diff.y, diff.z) - delta
                self.y = point.y + length * sin(angle)
                self.z = point.z + length * cos(angle)
            elif axis == "z":
                angle = atan2(diff.x, diff.y) - delta
                self.x = point.x + length * sin(angle)
                self.y = point.y + length * cos(angle)

    def get_base(self):
        return self

    def render(self):
        return self

class Vector3Mat(Vector3):
    def __init__(self, x, y, z, mat):
        super().__init__(x, y, z)
        self.mat = mat

class Vector4(Vector3):
    def __init__(self, x, y, z, w):
        Vector3.__init__(self, x, y, z)
        self.w = w

    def copy(self):
        return Vector4(self.x, self.y, self.z, self.w)

    def norm(self):
        return sqrt(self.x**2 + self.y**2 + self.z**2 + self.w**2)

    def normalize(self):
        norm = self.norm()
        self.x /= norm
        self.y /= norm
        self.z /= norm
        self.w /= norm


class Vector2(Vector3):
    def __init__(self, x, y):
        super().__init__(x, y, 0)

    def copy(self):
        return Vector2(self.x, self.y)

    def __truediv__(self, other):
        return Vector2(self.x/other, self.y/other)

    def __add__(self, other_vec):
        return Vector2(self.x+other_vec.x, self.y+other_vec.y)

    def __mul__(self, other):
        return Vector2(self.x*other, self.y*other)

    def __sub__(self, other_vec):
        return Vector2(self.x-other_vec.x, self.y-other_vec.y)


class Plane(object):
    def __init__(self, origin, vec1, vec2): # a point and two vectors defining the plane
        self.origin = origin
        self._vec1 = vec1
        self._vec2 = vec2
        self.normal = vec1.cross(vec2)

    @classmethod
    def from_implicit(cls, origin, normal):
        dummyvec = Vector3(0.0, 0.0, 0.0)
        plane = cls(origin, dummyvec, dummyvec)
        plane.normal = normal
        return plane

    def point_is_on_plane(self, vec):
        return (vec-self.origin).dot(self.normal) == 0

    def is_parallel(self, vec):
        return self.normal.dot(vec) == 0

    @classmethod
    def xy_aligned(cls, origin):
        return cls(origin, Vector3(1, 0, 0), Vector3(0, 1, 0))

    @classmethod
    def xz_aligned(cls, origin):
        return cls(origin, Vector3(1, 0, 0), Vector3(0, 0, 1))

    @classmethod
    def yz_aligned(cls, origin):
        return cls(origin, Vector3(0, 1, 0), Vector3(0, 0, 1))


class Triangle(object):
    def __init__(self, p1, p2, p3, material = None):
        self.origin = p1
        self.p2 = p2
        self.p3 = p3
        self.p1_to_p2 = p2 - p1
        self.p1_to_p3 = p3 - p1
        self.p2_to_p3 = p3 - p2
        self.p3_to_p1 = p1 - p3

        self.normal = self.p1_to_p2.cross(self.p1_to_p3)

        self.material = material

        if not self.normal.is_zero():
            self.normal.normalize()

    def is_parallel(self, vec):
        return self.normal.dot(vec) == 0


class Line(object):
    def __init__(self, origin, direction):
        self.origin = origin
        self.direction = direction
        self.direction.normalize()

    def collide(self, tri: Triangle):
        normal = tri.normal

        dot = normal.dot(self.direction)

        if dot == 0.0:
            return False

        d = (tri.origin - self.origin).dot(normal) / dot

        if d < 0:
            return False

        intersection_point = self.origin + self.direction * d

        # return intersection_point
        C0 = intersection_point - tri.origin

        if normal.dot(tri.p1_to_p2.cross(C0)) > 0:
            C1 = intersection_point - tri.p2
            if normal.dot(tri.p2_to_p3.cross(C1)) > 0:
                C2 = intersection_point - tri.p3
                if normal.dot(tri.p3_to_p1.cross(C2)) > 0:
                    return intersection_point, d
        return False

    def collide_py(self, tri: Triangle):
        hit = False

        edge1 = tri.p1_to_p2
        edge2 = tri.p1_to_p3

        normal = tri.normal
        if normal.is_zero():
            return False

        #d = -normal.dot(self.origin)

        if tri.normal.dot(self.direction) == 0:
            return False

        d = ((tri.origin - self.origin).dot(tri.normal)) / tri.normal.dot(self.direction)

        #if d == 0:
        #    return False

        #t = (normal.dot(self.origin) + d) / normal.dot(self.direction)

        if d < 0:
            return False

        intersection_point = self.origin + self.direction * d

        #return intersection_point
        C0 = intersection_point - tri.origin

        if tri.normal.dot(tri.p1_to_p2.cross(C0)) > 0:
            p2_to_p3 = tri.p3 - tri.p2
            C1 = intersection_point - tri.p2

            if tri.normal.dot(p2_to_p3.cross(C1)) > 0:
                p3_to_p1 = tri.origin - tri.p3
                C2 = intersection_point - tri.p3
                if tri.normal.dot(p3_to_p1.cross(C2)) > 0:
                    return intersection_point, d
                else:
                    return False
            else:
                return False
        else:
            return False

    def collide_plane(self, plane: Plane):
        pos = self.origin
        dir = self.direction

        if not plane.is_parallel(dir):
            d = ((plane.origin - pos).dot(plane.normal)) / plane.normal.dot(dir)
            if d >= 0:
                point = pos + (dir * d)
                return point, d
        return False

class Matrix4x4(object):
    def __init__(self,
                 val1A, val1B, val1C, val1D,
                 val2A, val2B, val2C, val2D,
                 val3A, val3B, val3C, val3D,
                 val4A, val4B, val4C, val4D):

        self.a1 = val1A
        self.b1 = val1B
        self.c1 = val1C
        self.d1 = val1D

        self.a2 = val2A
        self.b2 = val2B
        self.c2 = val2C
        self.d2 = val2D

        self.a3 = val3A
        self.b3 = val3B
        self.c3 = val3C
        self.d3 = val3D

        self.a4 = val4A
        self.b4 = val4B
        self.c4 = val4C
        self.d4 = val4D

    @classmethod
    def from_opengl_matrix(cls, row1, row2, row3, row4):
        return cls(row1[0], row1[1], row1[2], row1[3],
                   row2[0], row2[1], row2[2], row2[3],
                   row3[0], row3[1], row3[2], row3[3],
                   row4[0], row4[1], row4[2], row4[3])

    def transpose(self):
        self.__init__(self.a1, self.a2, self.a3, self.a4,
                      self.b1, self.b2, self.b3, self.b4,
                      self.c1, self.c2, self.c3, self.c4,
                      self.d1, self.d2, self.d3, self.d4)

    def multiply_vec4(self, x, y, z, w):
        newx = self.a1 * x + self.b1 * y + self.c1 * z + self.d1 * w
        newy = self.a2 * x + self.b2 * y + self.c2 * z + self.d2 * w
        newz = self.a3 * x + self.b3 * y + self.c3 * z + self.d3 * w
        neww = self.a4 * x + self.b4 * y + self.c4 * z + self.d4 * w
        return newx, newy, newz, neww

    def __str__(self):
        out = StringIO()
        out.write("{\n")
        out.write(str(self.a1))
        out.write(", ")
        out.write(str(self.b1))
        out.write(", ")
        out.write(str(self.c1))
        out.write(", ")
        out.write(str(self.d1))
        out.write(",\n")

        out.write(str(self.a2))
        out.write(", ")
        out.write(str(self.b2))
        out.write(", ")
        out.write(str(self.c2))
        out.write(", ")
        out.write(str(self.d2))
        out.write(",\n")

        out.write(str(self.a3))
        out.write(", ")
        out.write(str(self.b3))
        out.write(", ")
        out.write(str(self.c3))
        out.write(", ")
        out.write(str(self.d3))
        out.write(",\n")

        out.write(str(self.a4))
        out.write(", ")
        out.write(str(self.b4))
        out.write(", ")
        out.write(str(self.c4))
        out.write(", ")
        out.write(str(self.d4))
        out.write("\n}")

        return out.getvalue()


rotation_constant = 100
class Rotation(Vector3):
    def __init__(self, x, y, z):
        super().__init__(x, y, z)

    def rotate_around_x(self, degrees):
        self.x += degrees * rotation_constant

    def rotate_around_y(self, degrees):
        self.y += degrees * rotation_constant

    def rotate_around_z(self, degrees):
        self.z += degrees  * rotation_constant

    def get_rotation_matrix( self ):

        iden = [
			[1, 0, 0, 0],
			[0, 1, 0, 0],
			[0, 0, 1, 0],
			[0, 0, 0, 1]
		]
        iden = matmul(iden, self.get_rotation_from_vector( Vector3(0.0, 0.0, 0.1), 90))
        iden = matmul(iden, self.get_rotation_from_vector( Vector3(1.0, 0.0, 0.0), -self.x   ))
        iden = matmul(iden, self.get_rotation_from_vector( Vector3(0.0, 0.0, 1.0), -self.y   ))
        iden = matmul(iden, self.get_rotation_from_vector( Vector3(0.0, 1.0, 0.0), self.z   ))

        return iden

    def get_rotation_from_vector(self, vec, degrees):
        x = vec.x
        y = vec.y
        z = vec.z
        c = cos( deg2rad(degrees) )
        s = sin( deg2rad(degrees) )
        t = 1 - c

        return [
			[t*x*x + c,    t*x*y - z*s,  t*x*z + y*s, 0],
			[t*x*y + z*s,  t*y*y + c,    t*y*z - x*s, 0],
			[t*x*z - y*s,  t*y*z + x*s,  t*z*z + c,   0],
			[          0,            0,          0,   1]
		]

    @classmethod
    def default(cls):
        return cls(0, 0, 0)
    @classmethod
    def from_file(cls, f, printe = False):
        euler_angles = list(unpack(">fff", f.read(12)))

        return cls(*euler_angles)

    def get_vectors(self):

        y = self.y - 90
        y, z = self.z * -1, self.y

        r = R.from_euler('xyz', [self.x, y, z], degrees=True)
        vecs = r.as_matrix()
        vecs = vecs.transpose()

        mtx = ndarray(shape=(4,4), dtype=float, order="F")
        mtx[0][0:3] = vecs[0]
        mtx[1][0:3] = vecs[1]
        mtx[2][0:3] = vecs[2]
        mtx[3][0] = mtx[3][1] = mtx[3][2] = 0.0
        mtx[3][3] = 1.0

        left = Vector3(-mtx[0][0], mtx[0][2], mtx[0][1])
        left.normalize()
        #up = Vector3(-mtx[2][0], mtx[2][2], mtx[2][1])
        forward = Vector3(-mtx[1][0], mtx[1][2], mtx[1][1])
        forward.normalize()
        up = forward.cross(left) * -1

        return forward, up, left

    def write(self, f):
        f.write(pack(">fff", self.x, self.y, self.z) )

    def get_render(self):

        return self.get_rotation_matrix()

    def get_euler(self):

        vec = [self.x % 360, self.y % 360 , self.z % 360]

        return vec

    @classmethod
    def from_euler(cls, degs):
        rotation = cls(degs.x, degs.y, degs.z )


        return rotation


    def copy(self):
        return deepcopy(self)


class Vector3Relative(Vector3):
    def __init__(self, orig: Vector3, base: Vector3):
        super().__init__(orig.x, orig.y, orig.z)
        self.base = base

    def render(self):
        absol = self.absolute()
        vec = self.__class__(absol, self)
        return vec

    def absolute(self):
        return self.base.absolute() + self

    def to_absolute(self):
        self.x = self.base.x + self.x
        self.y = self.base.y + self.y
        self.z = self.base.z + self.z
        self.base = Vector3(0, 0, 0)

    def __eq__(self, other_vec):
        comps_same = self.x == other_vec.x and self.y == other_vec.y and self.z == other_vec.z
        bases_same = self.base == other_vec.get_base()
        return comps_same and bases_same

    def get_base(self):
        return self.base