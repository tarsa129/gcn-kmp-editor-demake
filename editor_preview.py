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
    def __init__(self) -> None:
        self.curr_cam = 0
        self.duration = 1

        self.view_prog = 0
        self.zoom_prog = 0
        self.path_prog = 0
        self.path_point = 0
        self.path_speed = 0

        self.done = False


    def next_cam(self):
        self.view_prog = 0
        self.zoom_prog = 0
        self.path_prog = 0
        self.path_point = 0
        self.path_speed = 0

    def setup_cam(self, cam:Camera):
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
        super().__init__()
        self.cameras = cameras
        self.setup_cam(self.cameras[0])

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
            self.setup_cam(self.cameras[self.curr_cam])

    def get_lookat(self, delta, cam:Camera):
        self.view_prog += delta * cam.viewspeed * 100 / MKW_FRAMERATE
        ratio = self.view_prog / cam.position3.distance(cam.position2)
        self.view_pos = lerp(cam.position2, cam.position3, ratio)

class ReplayPreview(PreviewParams):
    def __init__(self, areas:Areas, enemies:EnemyPointGroups) -> None:

        super().__init__()
        self.areas = areas
        self.area : Area = None

        self.enemies = enemies
        self.enemypoint = enemies.groups[0].points[0]
        self.enemyspeed = 450

        self.lap = 0

    def advance_frame(self, delta):
        #advance player
        self.get_lookat(delta, self.enemypoint)
        if self.done:
            return

        #get area for camera
        player_pos = self.view_pos - Vector3(0, 200, 0)
        if self.area is None or not self.area.check(player_pos):
            new_area = self.find_area(player_pos)
            self.area = new_area if new_area is not None else self.area
            if self.area is not None:
                super().next_cam()
                self.setup_cam(self.area.camera)

        if self.area is None:
            return

        cam:Camera = self.area.camera
        self.advance_zoom(delta, cam)

        if cam.route_obj is not None:
            if cam.route_obj.smooth == 1:
                self.position = self.next_pos_smooth(delta, cam)
            else:
                self.position = self.next_pos_verbatim(delta, cam)

    def get_lookat(self, delta, enemy1:EnemyPoint) -> Vector3:
        enemy2 = self.get_next_enemy(enemy1)
        if enemy2 is None:
            self.done = True
            return None

        self.view_prog += delta * self.enemyspeed * 100 / MKW_FRAMERATE
        ratio = self.view_prog / enemy2.position.distance(enemy1.position)
        if ratio > 1:
            self.enemypoint = enemy2
            self.view_prog = 0
        self.view_pos = lerp(enemy1.position, enemy2.position, ratio)
        self.view_pos += Vector3(0, 200, 0)

    def get_next_enemy(self, enemy1:EnemyPoint) -> EnemyPoint:
        group_idx, group, point_idx = self.enemies.find_group_of_point(enemy1)
        if point_idx < len(group.points) - 1:
            return group.points[point_idx + 1]
        group_idx = self.lap % group.num_next()
        if group.nextgroup[group_idx] in self.enemies.groups:
            return group.nextgroup[group_idx].points[0]
        return None

    def find_area(self, position) -> Area:
        found_areas = [area for area in self.areas if area.check(position)]
        print(found_areas, position)
        if found_areas:
        #get area with highest priority
            found_areas.sort(key = lambda area: area.priority)
            return found_areas[0]
        return None