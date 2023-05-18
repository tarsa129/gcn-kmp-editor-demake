MKW_FRAMERATE = 59.94
from lib.libkmp import Camera, Area, EnemyPoint, EnemyPointGroup, EnemyPointGroups, Areas
from lib.vectors import Vector3
def lerp(start, end, ratio):
    ratio = min(ratio, 1)
    return (end-start) * ratio + start

def make_spline(path, i, c0, c1, c2, c3):
    x = c0 * path.points[i].position.x + c1 * path.points[i + 1].position.x + \
          c2 * path.points[i + 2].position.x + c3 * path.points[i + 3].position.x
    y = c0 * path.points[i + 0].position.y + c1 * path.points[i + 1].position.y + \
          c2 * path.points[i + 2].position.y + c3 * path.points[i + 3].position.y
    z = c0 * path.points[i + 0].position.z + c1 * path.points[i + 1].position.z + \
          c2 * path.points[i + 2].position.z + c3 * path.points[i + 3].position.z
    return Vector3(x, y, z)

class PreviewParams(object):
    def __init__(self, cameras) -> None:
        self.cameras = cameras
        self.curr_cam = 0
        self.duration = 1

        self.view_prog = 0
        self.zoom_prog = 0
        self.path_prog = 0
        self.path_point = 0
        self.path_speed = 0

        self.done = False

        self.setup_cam(0)

    def next_cam(self):
        self.view_prog = 0
        self.zoom_prog = 0
        self.path_prog = 0
        self.path_point = 0
        self.path_speed = 0

    def setup_cam(self, idx):
        cam:Camera = self.cameras[idx]
        self.zoom = cam.fov.start
        self.duration = cam.camduration

        self.view_start = cam.position2.copy()
        self.view_pos = cam.position2.copy()
        self.view_dist = cam.position3.distance(cam.position2)

        if cam.route_obj is not None:
            self.path_speed = cam.route_obj.points[0].unk1

        self.position = cam.position.copy()

    def advance_zoom(self, delta, cam:Camera):
        self.zoom_prog += delta * cam.zoomspeed * 100 / MKW_FRAMERATE
        ratio = self.zoom_prog / abs(cam.fov.end - cam.fov.start)
        ratio = min(ratio, 1)
        self.zoom = lerp(cam.fov.start, cam.fov.end, ratio)

    def next_pos_verbatim(self, delta, cam:Camera):

        path = cam.route_obj
        i = self.path_point
        if i == len(path.points) - 1:
            return path.points[-1].position.copy()
        self.path_prog += delta * self.path_speed * MKW_FRAMERATE
        ratio = self.path_prog / (path.points[i].position.distance(path.points[i+1].position))
        self.path_speed = lerp(path.points[i].unk1, path.points[i+1].unk1, ratio)

        if ratio > 1:
            self.path_point += 1
            self.path_prog = 0
        return lerp(path.points[i].position, path.points[i+1].position, ratio)

    def next_pos_smooth(self, delta, cam:Camera):
        path = cam.route_obj
        i = self.path_point
        if i + 4 > len(path.points):
            return self.next_pos_verbatim(delta, cam)
        self.path_prog += delta * self.path_speed * MKW_FRAMERATE
        ratio = self.path_prog / (path.points[i].position.distance(path.points[i+1].position))
        self.path_speed = lerp(path.points[i].unk1, path.points[i+1].unk1, ratio)

        if ratio <= 1:
            c0 = (1 - ratio)**3 / 6
            c1 = (3 * ratio**3 - 6 * ratio**2 + 4) / 6
            c2 = (1 - 3 * (ratio**3 - ratio**2 - ratio)) / 6
            c3 = ratio**3 / 6
            return make_spline(path, i, c0, c1, c2, c3)
        else:
            self.path_point += 1
            self.path_prog = 0
            return path.points[i+1].position.copy()

class OpeningPreview(PreviewParams):
    def __init__(self, cameras) -> None:
        super().__init__(cameras)

    def advance_frame(self, delta):
        if self.duration <= 0:
            self.next_cam()
        else:
            cam:Camera = self.cameras[self.curr_cam]
            self.advance_zoom(delta, cam)
            self.get_lookat(delta, cam)

            if cam.route_obj is not None:
                if cam.route_obj.smooth == 1:
                    self.position = self.next_pos_smooth(delta, cam)
                else:
                    self.position = self.next_pos_verbatim(delta, cam)

        self.duration -= delta * MKW_FRAMERATE

    def next_cam(self):
        super().next_cam()
        self.curr_cam += 1
        if self.curr_cam == len(self.cameras):
            self.done = True
        else:
            self.setup_cam(self.curr_cam)

    def get_lookat(self, delta, cam:Camera):
        self.view_prog += delta * cam.viewspeed * 100 / MKW_FRAMERATE
        ratio = self.view_prog / cam.position3.distance(cam.position2)
        self.view_pos = lerp(cam.position2, cam.position3, ratio)

class ReplayPreview(PreviewParams):
    def __init__(self, cameras, areas:Areas, enemies:EnemyPointGroups) -> None:
        super().__init__(cameras)
        self.areas = areas
        self.enemies = enemies
        self.enemypoint = enemies[0].points[0]
        self.enemyspeed = 45
