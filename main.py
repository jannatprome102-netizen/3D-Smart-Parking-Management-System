"""
3D SMART PARKING MANAGEMENT SYSTEM  (pygame + PyOpenGL)
=======================================================
Keep these (optional) images in the same folder as main.py:
    parking_ground.jpg, tree.png, sky.jpg, grass.jpg, building.jpg, signboard.jpg
If an image is missing the program still runs with plain colours.

CONTROLS
    ARROWS (hold)  move the red car
    SPACE          park / exit  (when your car has left: bring it back)
    A  auto-park in nearest free bay     T      time speed  x1 / x60 / x600
    N  day / night                       K      change car colour
    O  auto-orbit camera                 1 2 3  camera presets
    LEFT-DRAG rotate camera, WHEEL zoom, C reset camera, ESC quit

SLOT COLOURS
    GREEN  = free        ORANGE = a car is driving in (reserved)
    RED    = a car is really parked there
"""
import math
import os
import random
import time

import pygame
from pygame.locals import *

from OpenGL.GL import *
from OpenGL.GLU import *


# ============================================================
# 1. INITIALIZATION
# ============================================================
pygame.init()

WIDTH = 1100
HEIGHT = 720

pygame.display.gl_set_attribute(pygame.GL_DEPTH_SIZE, 24)   # fixes flickering / hidden lines
try:
    pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLEBUFFERS, 1)
    pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLESAMPLES, 4)
    pygame.display.set_mode((WIDTH, HEIGHT), DOUBLEBUF | OPENGL)
except pygame.error:
    pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLEBUFFERS, 0)
    pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLESAMPLES, 0)
    pygame.display.set_mode((WIDTH, HEIGHT), DOUBLEBUF | OPENGL)
pygame.display.set_caption("3D Smart Parking Management System")

clock = pygame.time.Clock()
font = pygame.font.SysFont("Arial", 20, bold=True)
small_font = pygame.font.SysFont("Arial", 16, bold=True)
tiny_font = pygame.font.SysFont("Arial", 15, bold=True)
label_font = pygame.font.SysFont("Arial", 64, bold=True)
mono_font = pygame.font.SysFont("Consolas,Courier New,DejaVu Sans Mono,monospace", 16, bold=True)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


# ============================================================
# 2. OPENGL SETUP
# ============================================================
glEnable(GL_DEPTH_TEST)
glEnable(GL_BLEND)
glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
try:
    glEnable(GL_MULTISAMPLE)
except Exception:
    pass

glEnable(GL_FOG)
glFogi(GL_FOG_MODE, GL_LINEAR)
glFogf(GL_FOG_START, 40.0)
glFogf(GL_FOG_END, 120.0)

glMatrixMode(GL_PROJECTION)
glLoadIdentity()
gluPerspective(45, WIDTH / HEIGHT, 0.5, 150.0)     # near plane 0.5 -> much better depth precision
glMatrixMode(GL_MODELVIEW)


def load_texture(filename, size=None, alpha=False, mipmap=False, clamp=False):
    """Load an image from the folder of main.py as an OpenGL texture."""
    path = os.path.join(BASE_DIR, filename)
    try:
        surf = pygame.image.load(path)
        surf = surf.convert_alpha() if alpha else surf.convert()
    except (pygame.error, FileNotFoundError):
        print(f"WARNING: '{filename}' not found - using plain colour instead.")
        return None

    if size:
        surf = pygame.transform.smoothscale(surf, size)

    mode = "RGBA" if alpha else "RGB"
    fmt = GL_RGBA if alpha else GL_RGB
    data = pygame.image.tostring(surf, mode, True)
    w, h = surf.get_size()

    tid = glGenTextures(1)
    glBindTexture(GL_TEXTURE_2D, tid)
    wrap = GL_CLAMP_TO_EDGE if clamp else GL_REPEAT
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, wrap)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, wrap)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)

    done = False
    if mipmap:
        try:
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR_MIPMAP_LINEAR)
            gluBuild2DMipmaps(GL_TEXTURE_2D, fmt, w, h, fmt, GL_UNSIGNED_BYTE, data)
            done = True
        except Exception:
            done = False
    if not done:
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexImage2D(GL_TEXTURE_2D, 0, fmt, w, h, 0, fmt, GL_UNSIGNED_BYTE, data)

    glBindTexture(GL_TEXTURE_2D, 0)
    print(f"Loaded texture: {filename}")
    return tid


GROUND_TEXTURE = load_texture("parking_ground.jpg", (1024, 1024), mipmap=True)
TREE_TEXTURE = load_texture("tree.png", (256, 512), alpha=True, clamp=True)
SKY_TEX = load_texture("sky.jpg", (1024, 512))
GRASS_TEX = load_texture("grass.jpg", (512, 512), mipmap=True)
BUILDING_TEX = load_texture("building.jpg", (512, 512), mipmap=True)
SIGN_TEX = load_texture("signboard.jpg", (512, 256), clamp=True)

WHEEL_QUADRIC = gluNewQuadric()


# ============================================================
# 3. SETTINGS AND CONSTANTS
# ============================================================
PARKING_RATE = 50                 # Tk per started hour
SLOT_COUNT = 6
SLOT_START_X = -6.0
SLOT_WIDTH = 2.0
BAY_Z1, BAY_Z2 = -1.9, 1.9        # depth of every parking bay
LANE_Z = 3.15                     # driving lane in front of the bays
GATE_Z = 5.45
ROAD_Z1, ROAD_Z2 = 9.0, 12.6      # big road in front of the parking lot
LANE_RIGHT_Z = 9.9                # traffic moving +X
LANE_LEFT_Z = 11.7                # traffic moving -X
WHEEL_RADIUS = 0.22
MOVE_SPEED = 4.0

GATE_OPEN_ANGLE = 75.0
GATE_SPEED = 100.0

# slot states
SLOT_FREE = 0                     # green
SLOT_OCCUPIED = 1                 # red    (a car is really parked there)
SLOT_RESERVED = 2                 # orange (a car is still driving in)

CAR_COLORS = [
    (0.80, 0.015, 0.025),   # red
    (0.02, 0.20, 0.85),     # blue
    (0.65, 0.68, 0.72),     # silver
    (0.95, 0.75, 0.05),     # yellow
    (0.05, 0.55, 0.25),     # green
    (0.55, 0.10, 0.70),     # purple
    (0.95, 0.45, 0.05),     # orange
    (0.10, 0.10, 0.12),     # black
]

TIME_SCALES = [1, 60, 600]
TIME_SCALE_NAMES = ["real time", "1 sec = 1 min", "1 sec = 10 min"]

FACE_SHADES = (0.90, 0.62, 0.70, 0.78, 1.00, 0.45)   # front, back, left, right, top, bottom


def slot_center_x(i):
    return SLOT_START_X + SLOT_WIDTH * (i + 0.5)


def fmt_hms(seconds):
    s = int(max(0, seconds))
    return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def calc_fee(seconds):
    hours = max(1, math.ceil(seconds / 3600.0))
    return hours * PARKING_RATE, hours


# ============================================================
# 4. VEHICLE CLASS (smooth path following, turning, wheel spin)
# ============================================================
class Vehicle:
    def __init__(self, x, z, color, heading=0.0):
        self.x = x
        self.z = z
        self.color = color
        self.heading = heading
        self.h_target = heading
        self.wheel = 0.0
        self.path = []
        self.idx = 0
        self.speed = 4.0
        self.travel = 0.0
        self.total = 0.0
        self.on_first = None
        self.on_done = None

    def follow(self, waypoints, speed=4.0, on_first=None, on_done=None):
        """waypoints = [(x, z, heading_while_driving_there), ...]"""
        pts = []
        px, pz = self.x, self.z
        total = 0.0
        for wx, wz, wh in waypoints:
            d = math.hypot(wx - px, wz - pz)
            if d > 1e-4:
                pts.append((wx, wz, wh))
                total += d
                px, pz = wx, wz
        self.path = pts
        self.idx = 0
        self.travel = 0.0
        self.total = total
        self.speed = speed
        self.on_first = on_first
        self.on_done = on_done
        if not pts:
            if on_first:
                on_first()
            if on_done:
                on_done()

    def set_motion(self, dx, dz, dt, hdg=None, lat_angle=90.0):
        """Updates wheel spin + the wanted heading from the movement of this frame."""
        dist = math.hypot(dx, dz)
        if hdg is None:
            spd = dist / max(dt, 1e-4)
            if spd > 0.35:
                if abs(dx) > abs(dz):
                    self.h_target = lat_angle if dx > 0 else -lat_angle
                else:
                    self.h_target = 0.0
            elif spd < 0.06:
                self.h_target = 0.0
        else:
            self.h_target = hdg

        if dist > 1e-6:
            hr = math.radians(self.h_target)
            dot = (dx * math.sin(hr) + dz * math.cos(hr)) / dist
            sign = 1.0 if dot >= -0.01 else -1.0          # negative = reversing
            self.wheel = (self.wheel + sign * dist / WHEEL_RADIUS * 57.29578) % 360.0

    def _follow(self, dt):
        if not self.path:
            return
        ease_in = min(1.0, 0.25 + self.travel / 2.5)
        ease_out = min(1.0, 0.18 + (self.total - self.travel) / 2.5)
        step = self.speed * min(ease_in, ease_out) * dt
        hdg = self.path[min(self.idx, len(self.path) - 1)][2]
        mx = mz = 0.0

        while step > 1e-9 and self.idx < len(self.path):
            tx, tz, th = self.path[self.idx]
            hdg = th
            dx, dz = tx - self.x, tz - self.z
            d = math.hypot(dx, dz)
            if d <= step:
                self.x, self.z = tx, tz
                mx += dx
                mz += dz
                step -= d
                self.travel += d
                if self.idx == 0 and self.on_first:
                    cb = self.on_first
                    self.on_first = None
                    cb()
                self.idx += 1
            else:
                k = step / d
                self.x += dx * k
                self.z += dz * k
                mx += dx * k
                mz += dz * k
                self.travel += step
                step = 0.0

        self.set_motion(mx, mz, dt, hdg)

        if self.idx >= len(self.path):
            cb = self.on_done
            self.path = []
            self.on_done = None
            if cb:
                cb()

    def update(self, dt):
        self._follow(dt)
        d = ((self.h_target - self.heading + 180.0) % 360.0) - 180.0
        self.heading += d * min(1.0, 7.0 * dt)
        self.heading = ((self.heading + 180.0) % 360.0) - 180.0


# ============================================================
# 5. SIMULATION STATE
# ============================================================
sim_time = 0.0                    # simulated seconds (speeds up with the T key)
time_scale_index = 0
night_mode = False
NIGHT_T = 0.0                     # 0 = day ... 1 = night (smooth transition)
BRIGHT = 1.0

# --- parking slots -----------------------------------------------------
# 0 = free (green), 1 = occupied: a car is REALLY parked (red), 2 = reserved: a car is still driving in (orange)
slot_state = [SLOT_FREE] * SLOT_COUNT
slot_owner = [None] * SLOT_COUNT  # "npc" or "player"
slot_start = [None] * SLOT_COUNT  # sim_time when parking started (None = still driving in)
slot_car = [None] * SLOT_COUNT    # Vehicle object of the other (non-player) cars


def place_demo_car(i, color, minutes_ago):
    slot_state[i] = SLOT_OCCUPIED
    slot_owner[i] = "npc"
    slot_start[i] = -minutes_ago * 60.0
    slot_car[i] = Vehicle(slot_center_x(i), 0.0, color, 0.0)


place_demo_car(0, (0.02, 0.20, 0.85), 25)      # P1 - parked 25 min ago
place_demo_car(4, (0.65, 0.68, 0.72), 70)      # P5 - parked 70 min ago (2 billable hours)

leaving_cars = []

# --- player car --------------------------------------------------------
color_index = 0
P = Vehicle(-1.0, LANE_Z, CAR_COLORS[0], 0.0)
player_mode = "manual"            # manual / moving / parked / waiting_gate / gone
parked_slot = -1
target_x = P.x
target_z = P.z

# --- statistics / messages ----------------------------------------------
revenue_total = 0
cars_served = 0
last_fee = 0
message = "Drive into a green bay and press SPACE (or press A for auto-park)"
message_until = time.time() + 8
receipt_text = ""
receipt_until = 0.0

# --- gate ----------------------------------------------------------------
gate_angle = 0.0
gate_hold_until = 0.0

# --- other cars / traffic ----------------------------------------------------
npc_next_event = time.time() + 7.0
ambient = []


def new_ambient(direction, x):
    v = Vehicle(x, LANE_RIGHT_Z if direction > 0 else LANE_LEFT_Z,
                random.choice(CAR_COLORS), 90.0 * direction)
    v.dir = direction
    v.spd = random.uniform(3.5, 6.0)
    return v


ambient.extend([new_ambient(1, -20.0), new_ambient(1, 9.0),
                new_ambient(-1, 14.0), new_ambient(-1, -24.0)])

# --- camera ------------------------------------------------------------------
CAM_DEFAULT = (32.0, -12.0, 25.0)
camera_pitch, camera_yaw, camera_distance = CAM_DEFAULT
camera_dragging = False
camera_orbit = False
last_mouse_x = 0
last_mouse_y = 0

STARS = [(random.random(), random.uniform(0.35, 1.0), random.uniform(1.2, 2.8)) for _ in range(140)]


def set_message(text, seconds=3):
    global message, message_until
    message = text
    message_until = time.time() + seconds


# ============================================================
# 6. TEXT TEXTURE CACHE AND 2D HELPERS
# ============================================================
text_cache = {}


def get_text_tex(text, fnt, fg, bg, pad_x=8, pad_y=4):
    """Render (multi-line) text into a cached OpenGL texture -> (id, width, height)."""
    key = (text, id(fnt), fg, bg, pad_x, pad_y)
    hit = text_cache.get(key)
    if hit is not None:
        return hit

    if len(text_cache) > 300:
        glDeleteTextures([v[0] for v in text_cache.values()])
        text_cache.clear()

    renders = [fnt.render(line if line else " ", True, fg) for line in text.split("\n")]
    w = max(r.get_width() for r in renders)
    h = sum(r.get_height() for r in renders)
    W, H = w + pad_x * 2, h + pad_y * 2

    surf = pygame.Surface((W, H), pygame.SRCALPHA)
    if bg is not None:
        surf.fill(bg)
    yy = pad_y
    for r in renders:
        surf.blit(r, ((W - r.get_width()) // 2, yy))
        yy += r.get_height()

    data = pygame.image.tostring(surf, "RGBA", True)
    tid = glGenTextures(1)
    glBindTexture(GL_TEXTURE_2D, tid)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, W, H, 0, GL_RGBA, GL_UNSIGNED_BYTE, data)
    glBindTexture(GL_TEXTURE_2D, 0)

    entry = (tid, W, H)
    text_cache[key] = entry
    return entry


def begin_2d():
    glDisable(GL_DEPTH_TEST)
    glDisable(GL_FOG)
    glMatrixMode(GL_PROJECTION)
    glPushMatrix()
    glLoadIdentity()
    glOrtho(0, WIDTH, 0, HEIGHT, -1, 1)
    glMatrixMode(GL_MODELVIEW)
    glPushMatrix()
    glLoadIdentity()


def end_2d():
    glMatrixMode(GL_PROJECTION)
    glPopMatrix()
    glMatrixMode(GL_MODELVIEW)
    glPopMatrix()
    glEnable(GL_FOG)
    glEnable(GL_DEPTH_TEST)


def draw_text_overlay(text, x, y, fnt, fg=(255, 255, 255), bg=(20, 35, 65, 235), align="left"):
    """x, y measured from the top-left corner. y=None centres vertically."""
    tid, w, h = get_text_tex(text, fnt, fg, bg)
    if align == "right":
        x = WIDTH - w - x
    elif align == "center":
        x = (WIDTH - w) // 2
    if y is None:
        y = (HEIGHT - h) // 2

    begin_2d()
    glEnable(GL_TEXTURE_2D)
    glBindTexture(GL_TEXTURE_2D, tid)
    glColor4f(1, 1, 1, 1)
    bottom = HEIGHT - y - h
    glBegin(GL_QUADS)
    glTexCoord2f(0, 0); glVertex2f(x, bottom)
    glTexCoord2f(1, 0); glVertex2f(x + w, bottom)
    glTexCoord2f(1, 1); glVertex2f(x + w, bottom + h)
    glTexCoord2f(0, 1); glVertex2f(x, bottom + h)
    glEnd()
    glBindTexture(GL_TEXTURE_2D, 0)
    glDisable(GL_TEXTURE_2D)
    end_2d()


# ============================================================
# 7. BASIC 3D HELPERS
# ============================================================
def draw_cube(x, y, z, width, height, depth, color, emissive=False):
    """Box with simple per-face shading (gives depth) and day/night brightness."""
    x1, x2 = x - width / 2, x + width / 2
    y1, y2 = y - height / 2, y + height / 2
    z1, z2 = z - depth / 2, z + depth / 2
    r, g, b = color
    k = 1.0 if emissive else BRIGHT
    sf, sb, sl, sr, st, sbo = (1.0,) * 6 if emissive else FACE_SHADES

    glBegin(GL_QUADS)

    glColor3f(r * k * sf, g * k * sf, b * k * sf)          # front (+z)
    glVertex3f(x1, y1, z2); glVertex3f(x2, y1, z2); glVertex3f(x2, y2, z2); glVertex3f(x1, y2, z2)

    glColor3f(r * k * sb, g * k * sb, b * k * sb)          # back
    glVertex3f(x1, y1, z1); glVertex3f(x1, y2, z1); glVertex3f(x2, y2, z1); glVertex3f(x2, y1, z1)

    glColor3f(r * k * sl, g * k * sl, b * k * sl)          # left
    glVertex3f(x1, y1, z1); glVertex3f(x1, y1, z2); glVertex3f(x1, y2, z2); glVertex3f(x1, y2, z1)

    glColor3f(r * k * sr, g * k * sr, b * k * sr)          # right
    glVertex3f(x2, y1, z1); glVertex3f(x2, y1, z2); glVertex3f(x2, y2, z2); glVertex3f(x2, y2, z1)

    glColor3f(r * k * st, g * k * st, b * k * st)          # top
    glVertex3f(x1, y2, z2); glVertex3f(x2, y2, z2); glVertex3f(x2, y2, z1); glVertex3f(x1, y2, z1)

    glColor3f(r * k * sbo, g * k * sbo, b * k * sbo)       # bottom
    glVertex3f(x1, y1, z1); glVertex3f(x2, y1, z1); glVertex3f(x2, y1, z2); glVertex3f(x1, y1, z2)

    glEnd()


def draw_flat_rect(x1, z1, x2, z2, y, color, alpha=1.0, shaded=True):
    """A flat rectangle lying on the ground (used for lines, bays, roads)."""
    k = BRIGHT if shaded else 1.0
    glColor4f(color[0] * k, color[1] * k, color[2] * k, alpha)
    glBegin(GL_QUADS)
    glVertex3f(x1, y, z1)
    glVertex3f(x2, y, z1)
    glVertex3f(x2, y, z2)
    glVertex3f(x1, y, z2)
    glEnd()


def draw_tex_quad(p1, p2, p3, p4, tex, rx=1, ry=1, bright=None):
    if tex is None:
        return
    b = BRIGHT if bright is None else bright
    glEnable(GL_TEXTURE_2D)
    glBindTexture(GL_TEXTURE_2D, tex)
    glColor3f(b, b, b)
    glBegin(GL_QUADS)
    glTexCoord2f(0, 0);   glVertex3f(*p1)
    glTexCoord2f(rx, 0);  glVertex3f(*p2)
    glTexCoord2f(rx, ry); glVertex3f(*p3)
    glTexCoord2f(0, ry);  glVertex3f(*p4)
    glEnd()
    glBindTexture(GL_TEXTURE_2D, 0)
    glDisable(GL_TEXTURE_2D)


def draw_light_pool(x, z, radius, strength, color=(1.0, 0.85, 0.45), y=0.08):
    """Soft additive glow on the ground (street lights at night)."""
    if strength <= 0.02:
        return
    glDepthMask(GL_FALSE)
    glBlendFunc(GL_SRC_ALPHA, GL_ONE)
    glBegin(GL_TRIANGLE_FAN)
    glColor4f(color[0], color[1], color[2], 0.55 * strength)
    glVertex3f(x, y, z)
    glColor4f(color[0], color[1], color[2], 0.0)
    for k in range(25):
        a = k / 24.0 * 2.0 * math.pi
        glVertex3f(x + math.cos(a) * radius, y, z + math.sin(a) * radius)
    glEnd()
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
    glDepthMask(GL_TRUE)


def draw_ground_label(text, cx, cz, height=0.5, y=0.05):
    """Text painted flat on the ground, readable from the front camera."""
    tid, w, h = get_text_tex(text, label_font, (245, 245, 235), None, 0, 0)
    ww = height * w / h
    glEnable(GL_TEXTURE_2D)
    glBindTexture(GL_TEXTURE_2D, tid)
    glColor4f(BRIGHT, BRIGHT, BRIGHT, 1.0)
    glBegin(GL_QUADS)
    glTexCoord2f(0, 0); glVertex3f(cx - ww / 2, y, cz + height / 2)
    glTexCoord2f(1, 0); glVertex3f(cx + ww / 2, y, cz + height / 2)
    glTexCoord2f(1, 1); glVertex3f(cx + ww / 2, y, cz - height / 2)
    glTexCoord2f(0, 1); glVertex3f(cx - ww / 2, y, cz - height / 2)
    glEnd()
    glBindTexture(GL_TEXTURE_2D, 0)
    glDisable(GL_TEXTURE_2D)


def draw_billboard(text, fnt, fg, bg, x, y, z, scale=0.019):
    """Floating text panel that always faces the camera."""
    tid, w, h = get_text_tex(text, fnt, fg, bg, 8, 4)
    ww, hh = w * scale, h * scale
    glPushMatrix()
    glTranslatef(x, y, z)
    glRotatef(-camera_yaw, 0, 1, 0)
    glRotatef(-camera_pitch, 1, 0, 0)
    glEnable(GL_TEXTURE_2D)
    glBindTexture(GL_TEXTURE_2D, tid)
    glColor4f(1, 1, 1, 1)
    glBegin(GL_QUADS)
    glTexCoord2f(0, 0); glVertex3f(-ww / 2, -hh / 2, 0)
    glTexCoord2f(1, 0); glVertex3f(ww / 2, -hh / 2, 0)
    glTexCoord2f(1, 1); glVertex3f(ww / 2, hh / 2, 0)
    glTexCoord2f(0, 1); glVertex3f(-ww / 2, hh / 2, 0)
    glEnd()
    glBindTexture(GL_TEXTURE_2D, 0)
    glDisable(GL_TEXTURE_2D)
    glPopMatrix()


# ============================================================
# 8. SKY, GROUND, ROADS
# ============================================================
def draw_sky():
    begin_2d()
    if SKY_TEX is not None:
        n = NIGHT_T
        glEnable(GL_TEXTURE_2D)
        glBindTexture(GL_TEXTURE_2D, SKY_TEX)
        glColor3f(1.0 - 0.82 * n, 1.0 - 0.78 * n, 1.0 - 0.55 * n)
        # Map the entire sky.jpg image over the background.
        # The 3D scene is drawn over this image; camera controls still rotate
        # the scene, while this photo remains a clean sky backdrop.
        glBegin(GL_QUADS)
        glTexCoord2f(0, 0); glVertex2f(0, 0)
        glTexCoord2f(1, 0); glVertex2f(WIDTH, 0)
        glTexCoord2f(1, 1); glVertex2f(WIDTH, HEIGHT)
        glTexCoord2f(0, 1); glVertex2f(0, HEIGHT)
        glEnd()
        glBindTexture(GL_TEXTURE_2D, 0)
        glDisable(GL_TEXTURE_2D)

    if NIGHT_T > 0.25:                                      # stars
        t = time.time()
        for sx, sy, size in STARS:
            glPointSize(size)
            tw = 0.6 + 0.4 * math.sin(t * 2.0 + sx * 40.0)
            glColor4f(1, 1, 1, min(1.0, (NIGHT_T - 0.25) * 1.3) * tw)
            glBegin(GL_POINTS)
            glVertex2f(sx * WIDTH, HEIGHT * sy)
            glEnd()
        glPointSize(1.0)
    end_2d()


def draw_grass():
    if GRASS_TEX is None:
        draw_flat_rect(-60, -60, 60, 60, -0.15, (0.25, 0.55, 0.20))
        return
    draw_tex_quad((-60, -0.15, -60), (60, -0.15, -60),
                  (60, -0.15, 60), (-60, -0.15, 60), GRASS_TEX, 24, 24)


def draw_textured_ground():
    # asphalt slab: top surface exactly y = 0
    draw_cube(0, -0.08, 3.0, 30, 0.16, 30, (0.20, 0.21, 0.22))
    if GROUND_TEXTURE is None:
        return

    glEnable(GL_TEXTURE_2D)
    glBindTexture(GL_TEXTURE_2D, GROUND_TEXTURE)
    glColor3f(BRIGHT, BRIGHT, BRIGHT)
    y = 0.006
    glBegin(GL_QUADS)
    glTexCoord2f(0.0, 0.0); glVertex3f(-15.0, y, -12.0)
    glTexCoord2f(7.0, 0.0); glVertex3f(15.0, y, -12.0)
    glTexCoord2f(7.0, 7.0); glVertex3f(15.0, y, 18.0)
    glTexCoord2f(0.0, 7.0); glVertex3f(-15.0, y, 18.0)
    glEnd()
    glBindTexture(GL_TEXTURE_2D, 0)
    glDisable(GL_TEXTURE_2D)


def draw_roads():
    asphalt = (0.12, 0.12, 0.13)
    zc = (ROAD_Z1 + ROAD_Z2) / 2
    draw_cube(0, -0.07, zc, 140, 0.164, ROAD_Z2 - ROAD_Z1, asphalt)          # top surface y = 0.012
    draw_flat_rect(-2.1, GATE_Z - 0.4, 2.1, ROAD_Z1, 0.011, asphalt)         # exit road

    white = (0.92, 0.92, 0.90)
    yellow = (1.0, 0.78, 0.08)
    y = 0.02
    # edges of the big road + dashed centre line
    draw_flat_rect(-70, ROAD_Z1 + 0.10, 70, ROAD_Z1 + 0.17, y, white)
    draw_flat_rect(-70, ROAD_Z2 - 0.17, 70, ROAD_Z2 - 0.10, y, white)
    for x in range(-68, 68, 2):
        draw_flat_rect(x, zc - 0.04, x + 1.0, zc + 0.04, y, yellow)
    # exit road: yellow edges + zebra crossing
    draw_flat_rect(-2.0, GATE_Z + 0.1, -1.92, ROAD_Z1, y, yellow)
    draw_flat_rect(1.92, GATE_Z + 0.1, 2.0, ROAD_Z1, y, yellow)
    for k in range(6):
        x1 = -1.75 + k * 0.7
        draw_flat_rect(x1, 7.3, x1 + 0.35, 8.1, y, white)
    for z in (5.9, 6.5):
        draw_flat_rect(-0.05, z, 0.05, z + 0.4, y, white)


# ============================================================
# 9. PARKING BAYS, LINES, LABELS, LANE MARKINGS
# ============================================================
def find_nearest_slot(x, z, tol=0.9):
    if abs(z) > 1.5:
        return -1
    for i in range(SLOT_COUNT):
        if abs(x - slot_center_x(i)) < tol:
            return i
    return -1


def draw_parking_bays(highlight):
    t = time.time()
    line_col = (0.95, 0.95, 0.90)

    for i in range(SLOT_COUNT):
        cx = slot_center_x(i)
        st = slot_state[i]
        if st == SLOT_OCCUPIED:                      # a car is really parked -> RED
            col, a = (0.90, 0.10, 0.08), 0.34
        elif st == SLOT_RESERVED:                    # a car is driving in -> ORANGE (blinking)
            col, a = (1.0, 0.55, 0.05), 0.30 + 0.08 * math.sin(t * 5.0)
        else:                                        # free -> GREEN
            col, a = (0.12, 0.85, 0.32), 0.26 + 0.07 * math.sin(t * 3.0 + i)
        if i == highlight and st == SLOT_FREE:
            col, a = (0.95, 0.90, 0.15), 0.50 + 0.15 * math.sin(t * 6.0)
        a = min(0.75, a * (1.0 + 0.6 * NIGHT_T))
        draw_flat_rect(cx - 0.94, BAY_Z1 + 0.05, cx + 0.94, BAY_Z2, 0.03, col, a, shaded=False)

    # white bay lines (flat quads: always visible, no GL line-width problems)
    for px in range(-6, 7, 2):
        draw_flat_rect(px - 0.04, BAY_Z1 - 0.04, px + 0.04, BAY_Z2, 0.04, line_col)
    draw_flat_rect(-6.04, BAY_Z1 - 0.04, 6.04, BAY_Z1 + 0.04, 0.04, line_col)

    # P1..P6 painted on the ground
    for i in range(SLOT_COUNT):
        draw_ground_label(f"P{i + 1}", slot_center_x(i), 2.3, 0.5)

    # wheel stops + status sensor lamps at the back of each bay
    lamp_colors = {SLOT_FREE: (0.10, 0.95, 0.30),
                   SLOT_OCCUPIED: (0.95, 0.12, 0.08),
                   SLOT_RESERVED: (1.0, 0.55, 0.05)}
    for i in range(SLOT_COUNT):
        cx = slot_center_x(i)
        draw_cube(cx, 0.07, -1.62, 1.1, 0.14, 0.22, (0.62, 0.62, 0.60))
        draw_cube(cx, 0.55, -1.88, 0.07, 1.1, 0.07, (0.25, 0.26, 0.28))
        draw_cube(cx, 1.2, -1.88, 0.34, 0.2, 0.12, lamp_colors[slot_state[i]], emissive=True)


def draw_lane_markings():
    yellow = (1.0, 0.78, 0.08)
    draw_flat_rect(-6.5, 2.62, 6.5, 2.68, 0.035, yellow)
    draw_flat_rect(-6.5, 3.62, 6.5, 3.68, 0.035, yellow)
    x = -6.0
    while x < 6.0:
        draw_flat_rect(x, LANE_Z - 0.04, x + 0.8, LANE_Z + 0.04, 0.04, (0.95, 0.95, 0.95))
        x += 1.6


# ============================================================
# 10. CAR MODEL (with turning, rotating wheels, lights, shadow)
# ============================================================
def draw_wheel(cx, cy, cz, angle):
    q = WHEEL_QUADRIC
    tire = (0.035 * BRIGHT, 0.035 * BRIGHT, 0.04 * BRIGHT)
    hub = (0.72 * BRIGHT, 0.73 * BRIGHT, 0.76 * BRIGHT)
    bar = (0.12 * BRIGHT, 0.12 * BRIGHT, 0.14 * BRIGHT)

    glPushMatrix()
    glTranslatef(cx, cy, cz)
    glRotatef(angle, 1, 0, 0)          # spin around the axle
    glRotatef(90, 0, 1, 0)
    glTranslatef(0, 0, -0.14)

    glColor3f(*tire)
    gluCylinder(q, WHEEL_RADIUS, WHEEL_RADIUS, 0.28, 20, 1)

    for zpos, sgn in ((0.0, -1.0), (0.28, 1.0)):
        glPushMatrix()
        glTranslatef(0, 0, zpos)
        glColor3f(*tire)
        gluDisk(q, 0, WHEEL_RADIUS, 20, 1)
        glTranslatef(0, 0, 0.003 * sgn)
        glColor3f(*hub)
        gluDisk(q, 0, 0.13, 16, 1)
        glTranslatef(0, 0, 0.003 * sgn)
        glColor3f(*bar)                 # spokes -> you can SEE the wheel rotate
        glBegin(GL_QUADS)
        glVertex3f(-0.12, -0.022, 0); glVertex3f(0.12, -0.022, 0)
        glVertex3f(0.12, 0.022, 0);   glVertex3f(-0.12, 0.022, 0)
        glVertex3f(-0.022, -0.12, 0); glVertex3f(0.022, -0.12, 0)
        glVertex3f(0.022, 0.12, 0);   glVertex3f(-0.022, 0.12, 0)
        glEnd()
        glPopMatrix()

    glPopMatrix()


def draw_car(x, z, color, wheel_angle=0.0, heading=0.0, scale=1.0, lights=False):
    glPushMatrix()
    glTranslatef(x, 0.0, z)
    glRotatef(heading, 0, 1, 0)
    if scale != 1.0:
        glScalef(scale, scale, scale)

    # soft shadow on the asphalt
    draw_flat_rect(-0.92, -1.35, 0.92, 1.35, 0.065, (0.0, 0.0, 0.0), 0.35, shaded=False)

    cabin = (color[0] * 0.6, color[1] * 0.6, color[2] * 0.6)
    glass = (0.05, 0.55, 0.85)
    dark = (0.08, 0.08, 0.09)

    draw_cube(0, 0.42, 0, 1.50, 0.42, 2.40, color)
    draw_cube(0, 0.62, 0.72, 1.38, 0.12, 0.78, color)
    draw_cube(0, 0.59, -0.88, 1.35, 0.12, 0.40, color)
    draw_cube(0, 0.79, -0.05, 1.00, 0.38, 1.20, cabin)
    draw_cube(0, 0.99, -0.05, 0.94, 0.04, 1.08, color)

    draw_cube(0, 0.81, 0.555, 0.80, 0.25, 0.025, glass)
    draw_cube(0, 0.81, -0.655, 0.78, 0.23, 0.025, glass)
    for side in (-1, 1):
        draw_cube(side * 0.51, 0.81, -0.32, 0.025, 0.22, 0.42, glass)
        draw_cube(side * 0.51, 0.81, 0.20, 0.025, 0.22, 0.35, glass)

    for wx in (-0.72, 0.72):
        for wz in (-0.76, 0.76):
            draw_wheel(wx, 0.24, wz, wheel_angle)

    for lx in (-0.48, 0.48):
        draw_cube(lx, 0.48, 1.215, 0.24, 0.13, 0.035, (1.0, 0.92, 0.55), emissive=lights)
        draw_cube(lx, 0.47, -1.215, 0.23, 0.13, 0.035, (1.0, 0.015, 0.02), emissive=lights)

    draw_cube(0, 0.35, 1.22, 0.45, 0.12, 0.035, dark)
    for side in (-1, 1):
        draw_cube(side * 0.68, 0.69, 0.30, 0.15, 0.12, 0.16, dark)

    if lights:                                   # glowing headlight beams on the road
        glDepthMask(GL_FALSE)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE)
        glBegin(GL_QUADS)
        for lx in (-0.48, 0.48):
            glColor4f(1.0, 0.93, 0.60, 0.55 * NIGHT_T)
            glVertex3f(lx - 0.16, 0.085, 1.25)
            glVertex3f(lx + 0.16, 0.085, 1.25)
            glColor4f(1.0, 0.93, 0.60, 0.0)
            glVertex3f(lx + 1.0, 0.085, 5.2)
            glVertex3f(lx - 1.0, 0.085, 5.2)
        glEnd()
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glDepthMask(GL_TRUE)

    glPopMatrix()


def draw_vehicle(v):
    draw_car(v.x, v.z, v.color, v.wheel, v.heading, 1.0, NIGHT_T > 0.4)


# ============================================================
# 11. ENVIRONMENT
# ============================================================
def draw_tree(x, z, phase=0.0):
    if TREE_TEXTURE is None:
        draw_cube(x, 0.65, z, 0.22, 1.3, 0.22, (0.35, 0.18, 0.07))
        draw_cube(x, 1.55, z, 0.95, 0.85, 0.95, (0.08, 0.38, 0.13))
        draw_cube(x, 2.05, z, 0.68, 0.65, 0.68, (0.10, 0.48, 0.16))
        draw_cube(x, 2.43, z, 0.40, 0.42, 0.40, (0.14, 0.56, 0.20))
        return

    width, height = 1.5, 2.8
    sway = math.sin(time.time() * 1.4 + phase) * 0.06       # gentle wind animation
    b = 0.45 + 0.55 * BRIGHT

    glPushMatrix()
    glTranslatef(x, 0.0, z)
    glRotatef(-camera_yaw, 0, 1, 0)                          # tree always faces the camera
    glEnable(GL_TEXTURE_2D)
    glEnable(GL_ALPHA_TEST)
    glAlphaFunc(GL_GREATER, 0.35)
    glBindTexture(GL_TEXTURE_2D, TREE_TEXTURE)
    glColor4f(b, b, b, 1.0)
    glBegin(GL_QUADS)
    glTexCoord2f(0.0, 0.0); glVertex3f(-width / 2, 0.0, 0.0)
    glTexCoord2f(1.0, 0.0); glVertex3f(width / 2, 0.0, 0.0)
    glTexCoord2f(1.0, 1.0); glVertex3f(width / 2 + sway, height, 0.0)
    glTexCoord2f(0.0, 1.0); glVertex3f(-width / 2 + sway, height, 0.0)
    glEnd()
    glBindTexture(GL_TEXTURE_2D, 0)
    glDisable(GL_ALPHA_TEST)
    glDisable(GL_TEXTURE_2D)
    glPopMatrix()


def draw_street_light(x, z, d):
    pole = (0.16, 0.17, 0.19)
    draw_cube(x, 1.65, z, 0.10, 3.3, 0.10, pole)
    draw_cube(x + d * 0.28, 3.18, z, 0.62, 0.09, 0.10, pole)
    draw_cube(x + d * 0.52, 3.05, z, 0.28, 0.16, 0.30, (1.0, 0.88, 0.42), emissive=NIGHT_T > 0.35)


def draw_gate():
    post = (0.18, 0.19, 0.21)
    draw_cube(-2.2, 0.62, GATE_Z, 0.18, 1.24, 0.18, post)
    draw_cube(2.2, 0.62, GATE_Z, 0.18, 1.24, 0.18, post)
    lamp = (0.15, 0.95, 0.30) if gate_angle > 10 else (0.95, 0.12, 0.08)
    draw_cube(-2.2, 1.34, GATE_Z, 0.14, 0.14, 0.14, lamp, emissive=True)    # red / green gate light

    glPushMatrix()
    glTranslatef(-2.2, 1.12, GATE_Z)
    glRotatef(gate_angle, 0, 0, 1)
    draw_cube(2.175, 0, 0, 4.35, 0.14, 0.16, (0.88, 0.06, 0.06))
    for stripe_x in (0.7, 1.7, 2.7, 3.7):
        draw_cube(stripe_x, 0, -0.085, 0.25, 0.15, 0.025, (0.95, 0.95, 0.92))
    glPopMatrix()


def draw_signboard():
    draw_cube(-0.2, 1.85, -4.2, 3.3, 1.05, 0.16, (0.04, 0.20, 0.32))
    draw_cube(-0.2, 1.28, -4.2, 0.12, 1.0, 0.12, (0.25, 0.26, 0.28))
    draw_cube(-0.2, 1.28, -4.0, 0.12, 1.0, 0.12, (0.25, 0.26, 0.28))
    draw_cube(-0.2, 2.05, -4.105, 2.6, 0.08, 0.025, (1.0, 0.78, 0.12))
    draw_cube(-0.2, 1.65, -4.105, 2.1, 0.06, 0.025, (1.0, 0.78, 0.12))
    draw_tex_quad((-1.2, 1.35, -4.09), (0.8, 1.35, -4.09),
                  (0.8, 2.35, -4.09), (-1.2, 2.35, -4.09), SIGN_TEX, bright=0.55 + 0.45 * BRIGHT)


def draw_security_booth():
    bx, bz = 6.0, 5.0
    night = NIGHT_T > 0.4
    draw_cube(bx, 0.75, bz, 1.30, 1.5, 1.20, (0.82, 0.82, 0.76))
    draw_cube(bx, 1.55, bz, 1.43, 0.16, 1.33, (0.08, 0.22, 0.38))
    win = (1.0, 0.90, 0.50) if night else (0.10, 0.62, 0.82)
    draw_cube(bx, 0.92, bz - 0.61, 0.80, 0.48, 0.035, win, emissive=night)
    draw_cube(bx, 0.35, bz - 0.61, 0.34, 0.58, 0.035, (0.35, 0.22, 0.12))
    draw_cube(bx, 1.78, bz, 1.50, 0.08, 1.37, (0.85, 0.12, 0.08))


def draw_cctv(x, y, z):
    draw_cube(x, y, z, 0.12, 0.12, 0.12, (0.18, 0.18, 0.20))
    draw_cube(x, y - 0.12, z + 0.20, 0.22, 0.16, 0.42, (0.80, 0.82, 0.85))
    draw_cube(x, y - 0.12, z + 0.42, 0.10, 0.10, 0.08, (0.05, 0.05, 0.06))


def draw_building(x, z, width, depth, height, wall_color, window_color=(0.16, 0.42, 0.58)):
    draw_cube(x, height / 2, z, width, height, depth, wall_color)
    draw_cube(x, height + 0.08, z, width + 0.18, 0.16, depth + 0.18, (0.48, 0.50, 0.52))

    if BUILDING_TEX is not None:
        bb = 0.45 + 0.55 * BRIGHT                  # windows stay fairly bright at night
        e = 0.012
        x1, x2 = x - width / 2, x + width / 2
        z1, z2 = z - depth / 2, z + depth / 2
        rx = max(1, round(width / 2.0))
        rz = max(1, round(depth / 2.0))
        ry = max(1, round(height / 2.0))
        draw_tex_quad((x1, 0, z2 + e), (x2, 0, z2 + e), (x2, height, z2 + e), (x1, height, z2 + e), BUILDING_TEX, rx, ry, bb)
        draw_tex_quad((x2, 0, z1 - e), (x1, 0, z1 - e), (x1, height, z1 - e), (x2, height, z1 - e), BUILDING_TEX, rx, ry, bb)
        draw_tex_quad((x1 - e, 0, z1), (x1 - e, 0, z2), (x1 - e, height, z2), (x1 - e, height, z1), BUILDING_TEX, rz, ry, bb)
        draw_tex_quad((x2 + e, 0, z2), (x2 + e, 0, z1), (x2 + e, height, z1), (x2 + e, height, z2), BUILDING_TEX, rz, ry, bb)
        return

    cols = max(2, int(width / 0.75))
    rows = max(2, int(height / 0.75))
    spacing_x = width / (cols + 1)
    spacing_y = height / (rows + 1)
    lit = NIGHT_T > 0.4
    wcol = (1.0, 0.88, 0.45) if lit else window_color
    for zz in (z + depth / 2 + 0.012, z - depth / 2 - 0.012):
        for row in range(rows):
            wy = spacing_y * (row + 1)
            for col in range(cols):
                wx = x - width / 2 + spacing_x * (col + 1)
                draw_cube(wx, wy, zz, min(0.38, spacing_x * 0.55),
                          min(0.34, spacing_y * 0.48), 0.025, wcol, emissive=lit)


def draw_surrounding_buildings():
    draw_building(-11.0, -1.2, 3.2, 4.4, 4.8, (0.72, 0.70, 0.65))
    draw_building(-11.0, 5.2, 3.4, 3.4, 3.8, (0.78, 0.76, 0.70))
    draw_building(11.0, -1.0, 3.3, 4.8, 5.5, (0.70, 0.74, 0.76))
    draw_building(11.0, 5.3, 3.4, 3.6, 4.2, (0.78, 0.75, 0.69))
    draw_building(-5.8, -8.2, 4.8, 2.8, 3.6, (0.75, 0.73, 0.68))
    draw_building(0.0, -8.8, 4.2, 2.6, 4.4, (0.68, 0.72, 0.75))
    draw_building(5.8, -8.2, 4.8, 2.8, 3.6, (0.76, 0.74, 0.69))


LOT_LAMPS = [(-6.65, -2.7, 1), (-6.65, 2.7, 1), (6.65, -2.7, -1), (6.65, 2.7, -1)]
ROAD_LAMPS = [(-18.0, 8.4, 1), (-7.0, 8.4, 1), (7.0, 8.4, -1), (18.0, 8.4, -1)]
TREES = [(-7.45, -3.5), (-7.45, 0), (-7.45, 3.5), (7.45, -3.5), (7.45, 0), (7.45, 3.5),
         (-3.4, 7.0), (3.4, 7.0), (-9.0, 8.2), (9.0, 8.2)]


def draw_parking_environment():
    curb = (0.55, 0.57, 0.59)
    draw_cube(0, 0.10, -5.0, 14.2, 0.20, 0.22, curb)
    draw_cube(-4.15, 0.10, 5.0, 5.9, 0.20, 0.22, curb)       # opening in the curb for the gate road
    draw_cube(4.15, 0.10, 5.0, 5.9, 0.20, 0.22, curb)
    draw_cube(-7.0, 0.10, 0, 0.22, 0.20, 10.0, curb)
    draw_cube(7.0, 0.10, 0, 0.22, 0.20, 10.0, curb)
    draw_cube(0, 0.28, -4.65, 13.6, 0.56, 0.40, (0.10, 0.34, 0.14))   # hedge

    draw_gate()
    draw_signboard()
    draw_security_booth()

    for tx, tz in TREES:
        draw_tree(tx, tz, tx * 0.7 + tz)

    for lx, lz, d in LOT_LAMPS + ROAD_LAMPS:
        draw_street_light(lx, lz, d)

    for cx in (-6.4, 6.4):
        draw_cube(cx, 2.55, 0.0, 0.12, 3.0, 0.12, (0.18, 0.19, 0.21))
        draw_cctv(cx, 3.9, 0.0)

    draw_surrounding_buildings()


# ============================================================
# 12. PARKING LOGIC (billing, paths, other cars)
# ============================================================
def blocked(x, z):
    """
    Collision guard for the player's car.
    Uses a conservative distance check against parked and moving cars, so the
    player cannot drive through a parked car or a car currently entering/exiting.
    """
    # Cars physically parked in bays (including the NPC cars).
    for i in range(SLOT_COUNT):
        if slot_state[i] == SLOT_OCCUPIED:
            cx = slot_center_x(i)
            cz = 0.0
            if math.hypot(x - cx, z - cz) < 1.95:
                return True

    # Cars currently following a path in the parking lot / exit lane.
    other_cars = []
    other_cars.extend(c for c in slot_car if c is not None and c.path)
    other_cars.extend(leaving_cars)
    other_cars.extend(ambient)

    for car in other_cars:
        # Ignore traffic on the distant public road; it does not intersect
        # the player's driving area.
        if car in ambient and car.z > 8.5:
            continue
        if math.hypot(x - car.x, z - car.z) < 1.95:
            return True

    return False


def plan_park_path(fx, fz, sx):
    if abs(fz) <= 1.5 and abs(fx - sx) < 1.0:
        return [(sx, 0.0, 0.0)]
    path = []
    cx = fx
    if fz < LANE_Z - 0.2:
        path.append((fx, LANE_Z, 0.0))
    if abs(sx - cx) > 0.05:
        path.append((sx, LANE_Z, 90.0 if sx > cx else -90.0))
    path.append((sx, 0.0, 0.0))                 # reverse into the bay
    return path


def plan_exit_path(sx):
    return [
        (sx, LANE_Z, 0.0),                                      # forward out of the bay
        (0.0, LANE_Z, -90.0 if sx > 0 else 90.0),               # along the lane to the gate road
        (0.0, ROAD_Z1 + 0.6, 0.0),                              # through the gate
        (1.6, LANE_RIGHT_Z, 90.0),                              # turn right onto the main road
        (32.0, LANE_RIGHT_Z, 90.0),
    ]


def plan_arrival_path(end_x):
    return [
        (26.0, LANE_LEFT_Z, -90.0),
        (1.4, LANE_LEFT_Z, -90.0),
        (0.0, ROAD_Z1 + 0.4, 180.0),
        (0.0, 4.4, 180.0),
        (end_x, LANE_Z, 0.0),
    ]


def plan_npc_arrival(sx):
    return [
        (26.0, LANE_LEFT_Z, -90.0),
        (1.4, LANE_LEFT_Z, -90.0),
        (0.0, ROAD_Z1 + 0.4, 180.0),
        (0.0, 4.4, 180.0),
        (0.0, LANE_Z, 180.0),
        (sx, LANE_Z, 90.0 if sx > 0 else -90.0),
        (sx, 0.0, 0.0),
    ]


def finish_slot_billing(i, player=False):
    """The car leaves bay i: calculate the fee, add revenue, free the slot."""
    global revenue_total, cars_served, last_fee, receipt_text, receipt_until, parked_slot

    duration = (sim_time - slot_start[i]) if slot_start[i] is not None else 0.0
    fee, hours = calc_fee(duration)
    revenue_total += fee
    cars_served += 1

    if player:
        last_fee = fee
        print(f"Parking duration: {fmt_hms(duration)}")
        print(f"Billable hours: {hours}")
        print(f"Parking fee: Tk {fee}")
        receipt_text = (
            "PARKING RECEIPT\n"
            f"Slot: P{i + 1}\n"
            f"Parked time: {fmt_hms(duration)}\n"
            f"Rate: Tk {PARKING_RATE} per hour\n"
            f"Billable hours: {hours}\n"
            f"TOTAL FEE: Tk {fee}\n"
            "Thank you! Drive safe."
        )
        receipt_until = time.time() + 9.0
        set_message(f"Exited P{i + 1} | Duration {fmt_hms(duration)} | Fee Tk {fee}", 8)
        parked_slot = -1

    slot_state[i] = SLOT_FREE
    slot_owner[i] = None
    slot_start[i] = None
    slot_car[i] = None


def npc_busy():
    if any(v.path for v in leaving_cars):
        return True
    return any(c is not None and c.path for c in slot_car)


def start_player_park(slot):
    global player_mode, parked_slot
    sx = slot_center_x(slot)
    slot_state[slot] = SLOT_RESERVED          # orange: the car is still driving in
    slot_owner[slot] = "player"
    slot_start[slot] = None
    parked_slot = slot
    player_mode = "moving"

    def done():
        global player_mode
        player_mode = "parked"
        slot_state[slot] = SLOT_OCCUPIED      # now the car is really parked -> RED
        slot_start[slot] = sim_time
        set_message(f"Car parked successfully in P{slot + 1}!  Timer started.", 4)
        print(f"Car parked successfully in P{slot + 1}!")

    P.follow(plan_park_path(P.x, P.z, sx), 3.2, on_done=done)


def start_player_exit():
    global player_mode, gate_hold_until
    slot = parked_slot
    sx = slot_center_x(slot)
    player_mode = "moving"
    gate_hold_until = time.time() + 14.0

    def first():
        finish_slot_billing(slot, player=True)

    def done():
        global player_mode
        player_mode = "gone"
        set_message("Your car has left. Press SPACE to bring it back.", 6)

    P.follow(plan_exit_path(sx), 4.2, on_first=first, on_done=done)


def start_player_arrival():
    global player_mode, target_x, target_z
    P.x, P.z = 26.0, LANE_LEFT_Z
    P.heading = P.h_target = -90.0
    player_mode = "moving"
    set_message("Your car is arriving...", 4)

    def done():
        global player_mode, target_x, target_z
        player_mode = "manual"
        target_x, target_z = P.x, P.z
        set_message("Your turn! Drive into a green bay, then press SPACE.", 5)

    P.follow(plan_arrival_path(-1.0), 5.5, on_done=done)


def park_or_exit():
    global player_mode
    if player_mode == "manual":
        if npc_busy():
            set_message("Another car is moving - wait a moment.")
            return

        # SPACE can park in ANY free bay. If the car is already inside a bay,
        # prefer that bay; otherwise choose the nearest available bay.
        current_bay = find_nearest_slot(P.x, P.z, tol=1.05)
        if current_bay >= 0 and slot_state[current_bay] == SLOT_FREE:
            s = current_bay
        else:
            free_slots = [i for i in range(SLOT_COUNT)
                          if slot_state[i] == SLOT_FREE]
            if not free_slots:
                set_message("Parking is FULL! No free slot available.")
                return
            s = min(free_slots,
                    key=lambda i: abs(slot_center_x(i) - P.x))

        set_message(f"Parking in available slot P{s + 1}...", 3)
        start_player_park(s)
    elif player_mode == "parked":
        player_mode = "waiting_gate"
        set_message("Gate opening. Car will exit automatically.", 4)
    elif player_mode == "gone":
        if npc_busy():
            set_message("Another car is moving - wait a moment.")
        else:
            start_player_arrival()
    else:
        set_message("Please wait for the current animation.")


def auto_park():
    if player_mode != "manual":
        set_message("Auto-park works when you are driving in the lot.")
        return
    if npc_busy():
        set_message("Another car is moving - wait a moment.")
        return
    free = [i for i in range(SLOT_COUNT) if slot_state[i] == SLOT_FREE]
    if not free:
        set_message("Parking is FULL!")
        return
    s = min(free, key=lambda i: abs(slot_center_x(i) - P.x))
    set_message(f"Auto-parking in P{s + 1}...", 3)
    start_player_park(s)


def protected_slots():
    s = set()
    if parked_slot >= 0:
        s.add(parked_slot)
    if player_mode == "manual":
        n = find_nearest_slot(P.x, P.z, 1.3)
        if n >= 0:
            s.add(n)
    return s


def npc_event():
    """Other drivers arrive / leave by themselves, so the lot feels alive."""
    global npc_next_event
    npc_next_event = time.time() + random.uniform(9.0, 18.0)

    if npc_busy() or player_mode in ("moving", "waiting_gate"):
        return
    if player_mode == "manual" and P.z > 2.2:
        return

    prot = protected_slots()
    free = [i for i in range(SLOT_COUNT) if slot_state[i] == SLOT_FREE and i not in prot]
    leaving = [i for i in range(SLOT_COUNT)
               if slot_owner[i] == "npc" and slot_car[i] is not None
               and not slot_car[i].path and slot_start[i] is not None]

    if free and (len(leaving) <= 1 or random.random() < 0.5):
        i = random.choice(free)
        sx = slot_center_x(i)
        colors = [c for c in CAR_COLORS if c != P.color]
        v = Vehicle(26.0, LANE_LEFT_Z, random.choice(colors), -90.0)
        slot_state[i] = SLOT_RESERVED          # orange until the car really arrives
        slot_owner[i] = "npc"
        slot_start[i] = None
        slot_car[i] = v

        def arrived(idx=i):
            slot_state[idx] = SLOT_OCCUPIED    # parked -> RED
            slot_start[idx] = sim_time

        v.follow(plan_npc_arrival(sx), 5.5, on_done=arrived)
    elif leaving:
        i = random.choice(leaving)
        v = slot_car[i]
        slot_car[i] = None
        leaving_cars.append(v)

        def first(idx=i):
            finish_slot_billing(idx, player=False)

        def gone(car=v):
            if car in leaving_cars:
                leaving_cars.remove(car)

        v.follow(plan_exit_path(slot_center_x(i)), 4.2, on_first=first, on_done=gone)


def gate_needed():
    if player_mode == "waiting_gate" or time.time() < gate_hold_until:
        return True
    movers = list(leaving_cars)
    movers += [c for c in slot_car if c is not None and c.path]
    if player_mode in ("moving", "manual"):
        movers.append(P)
    for v in movers:
        if abs(v.x) < 2.8 and 3.9 < v.z < 9.6:
            return True
    return False


# ============================================================
# 13. WORLD UPDATE
# ============================================================
def update_world(dt, keys):
    global sim_time, NIGHT_T, BRIGHT, gate_angle, target_x, target_z

    sim_time += dt * TIME_SCALES[time_scale_index]

    # smooth day <-> night
    goal = 1.0 if night_mode else 0.0
    NIGHT_T += (goal - NIGHT_T) * min(1.0, 2.0 * dt)
    BRIGHT = 1.0 - 0.62 * NIGHT_T

    # ---- player car (fully controlled by YOU) -----------------------------
    if player_mode == "manual":
        mv_x = (1 if keys[K_RIGHT] else 0) - (1 if keys[K_LEFT] else 0)
        mv_z = (1 if keys[K_UP] else 0) - (1 if keys[K_DOWN] else 0)
        new_tx = max(-5.0, min(5.0, target_x + mv_x * 5.0 * dt))
        if not blocked(new_tx, target_z):
            target_x = new_tx
        new_tz = max(-1.5, min(3.2, target_z + mv_z * 5.0 * dt))
        if not blocked(target_x, new_tz):
            target_z = new_tz

        ox, oz = P.x, P.z
        f = min(1.0, MOVE_SPEED * dt)
        P.x += (target_x - P.x) * f
        P.z += (target_z - P.z) * f
        P.set_motion(P.x - ox, P.z - oz, dt, None, 30.0)

    elif player_mode == "waiting_gate":
        if gate_angle >= GATE_OPEN_ANGLE - 0.5:
            start_player_exit()

    # (player_mode == "gone": the car waits until YOU press SPACE - no automatic arrival)

    P.update(dt)

    # ---- other cars ---------------------------------------------------------
    for c in slot_car:
        if c is not None:
            c.update(dt)
    for v in list(leaving_cars):
        v.update(dt)

    for v in ambient:
        v.x += v.dir * v.spd * dt
        v.set_motion(v.dir * v.spd * dt, 0.0, dt, 90.0 * v.dir)
        v.update(dt)
        if v.x * v.dir > 34.0:
            v.x = -34.0 * v.dir
            v.color = random.choice(CAR_COLORS)
            v.spd = random.uniform(3.5, 6.0)

    if time.time() >= npc_next_event:
        npc_event()

    # ---- gate -------------------------------------------------------------------
    target = GATE_OPEN_ANGLE if gate_needed() else 0.0
    if gate_angle < target:
        gate_angle = min(gate_angle + GATE_SPEED * dt, target)
    elif gate_angle > target:
        gate_angle = max(gate_angle - GATE_SPEED * dt, target)


# ============================================================
# 14. HUD
# ============================================================
def draw_hud(highlight):
    total = SLOT_COUNT
    occupied = slot_state.count(SLOT_OCCUPIED)
    reserved = slot_state.count(SLOT_RESERVED)
    available = total - occupied - reserved

    draw_text_overlay("3D SMART PARKING SYSTEM", 12, 10, font)
    draw_text_overlay(f"Total: {total}   Available: {available}   Occupied: {occupied}   "
                      f"Rate: Tk {PARKING_RATE}/hr", 12, 40, small_font)
    draw_text_overlay(f"Revenue: Tk {revenue_total}   Cars served: {cars_served}   "
                      f"Last fee: Tk {last_fee}", 12, 64, small_font)
    clock_str = fmt_hms((8 * 3600 + sim_time) % 86400)
    mode_str = "NIGHT" if night_mode else "DAY"
    draw_text_overlay(f"Clock {clock_str}   Speed x{TIME_SCALES[time_scale_index]} "
                      f"({TIME_SCALE_NAMES[time_scale_index]})   {mode_str}", 12, 88, small_font)

    # slot status table (right side)
    draw_text_overlay("SLOT STATUS  |  TIME  |  FEE", 12, 10, small_font, align="right")
    for i in range(SLOT_COUNT):
        if slot_state[i] == SLOT_FREE:
            state, t, fee, rbg = "FREE", "--:--:--", "---", (20, 95, 50, 235)
        elif slot_start[i] is None:
            state = "ENTERING" if slot_owner[i] == "player" else "ARRIVING"
            t, fee, rbg = "--:--:--", "---", (130, 95, 20, 235)
        else:
            d = sim_time - slot_start[i]
            t, fee = fmt_hms(d), str(calc_fee(d)[0])
            if slot_owner[i] == "player":
                state, rbg = "YOU", (20, 75, 140, 235)
            else:
                state, rbg = "PARKED", (125, 35, 35, 235)
        draw_text_overlay(f"P{i + 1}  {state:<8}  {t}  Tk {fee:>3}", 12, 38 + i * 26,
                          mono_font, (255, 255, 255), rbg, align="right")

    if available == 0:
        draw_text_overlay("PARKING FULL", 0, 120, font, (255, 255, 255), (170, 30, 30, 240), align="center")

    if highlight >= 0 and slot_state[highlight] == SLOT_FREE:
        draw_text_overlay(f"Press SPACE to park in P{highlight + 1}", 0, HEIGHT - 128,
                          font, (30, 30, 30), (250, 235, 90, 240), align="center")

    if player_mode == "gone":
        draw_text_overlay("Your car is outside. Press SPACE to bring it back.", 0, HEIGHT - 128,
                          font, (30, 30, 30), (250, 235, 90, 240), align="center")

    if time.time() < message_until:
        draw_text_overlay(message, 14, HEIGHT - 92, small_font, (255, 240, 150), (35, 45, 60, 235))

    if time.time() < receipt_until:
        draw_text_overlay(receipt_text, 0, 160, font, (255, 255, 255), (10, 30, 60, 245), align="center")

    draw_text_overlay("ARROWS: move   SPACE: park / exit / call car   A: auto-park   T: time speed   "
                      "N: day/night   K: car colour", 14, HEIGHT - 60, tiny_font, (255, 255, 255), (25, 55, 85, 235))
    draw_text_overlay("O: orbit camera   1/2/3: views   LEFT-DRAG: rotate   WHEEL: zoom   "
                      "C: reset   ESC: quit", 14, HEIGHT - 34, tiny_font, (255, 255, 255), (25, 55, 85, 235))


def draw_billboards():
    """Floating timer + fee above every parked car."""
    for i in range(SLOT_COUNT):
        if slot_state[i] == SLOT_FREE or slot_start[i] is None:
            continue
        d = sim_time - slot_start[i]
        fee, hours = calc_fee(d)
        tag = "  YOU" if slot_owner[i] == "player" else ""
        text = f"P{i + 1}{tag}  {fmt_hms(d)}\nTk {fee}  ({hours} hr)"
        if slot_owner[i] == "player":
            bg = (15, 80, 150, 235)
        elif hours > 1:
            bg = (140, 70, 10, 235)
        else:
            bg = (20, 40, 75, 235)
        draw_billboard(text, tiny_font, (255, 255, 255), bg,
                       slot_center_x(i), 2.35 + (i % 2) * 0.8, 0.0)


# ============================================================
# 15. RENDER ONE FRAME
# ============================================================
def render():
    n = NIGHT_T
    sky = (0.65 * (1 - n) + 0.03 * n, 0.80 * (1 - n) + 0.05 * n, 0.90 * (1 - n) + 0.12 * n)
    glClearColor(sky[0], sky[1], sky[2], 1.0)
    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
    glFogfv(GL_FOG_COLOR, [sky[0], sky[1], sky[2], 1.0])

    draw_sky()

    glMatrixMode(GL_MODELVIEW)
    glLoadIdentity()
    glTranslatef(0.0, -2.2, -camera_distance)
    glRotatef(camera_pitch, 1, 0, 0)
    glRotatef(camera_yaw, 0, 1, 0)

    highlight = find_nearest_slot(P.x, P.z) if player_mode == "manual" else -1

    draw_grass()
    draw_textured_ground()
    draw_roads()
    draw_parking_bays(highlight)
    draw_lane_markings()
    draw_parking_environment()

    if NIGHT_T > 0.05:                                   # glow of street lights
        for lx, lz, d in LOT_LAMPS + ROAD_LAMPS:
            draw_light_pool(lx + d * 0.52, lz, 3.2, NIGHT_T)

    for c in slot_car:
        if c is not None:
            draw_vehicle(c)
    for v in leaving_cars:
        draw_vehicle(v)
    for v in ambient:
        draw_vehicle(v)
    if player_mode != "gone":
        draw_vehicle(P)

    draw_billboards()
    draw_hud(highlight)
    pygame.display.flip()


# ============================================================
# 16. MAIN LOOP
# ============================================================
running = True

try:
    while running:
        dt = min(clock.tick(60) / 1000.0, 0.05)

        for event in pygame.event.get():
            if event.type == QUIT:
                running = False

            elif event.type == MOUSEBUTTONDOWN:
                if event.button == 1:
                    camera_dragging = True
                    last_mouse_x, last_mouse_y = event.pos

            elif event.type == MOUSEBUTTONUP:
                if event.button == 1:
                    camera_dragging = False

            elif event.type == MOUSEMOTION and camera_dragging:
                mouse_x, mouse_y = event.pos
                camera_yaw += (mouse_x - last_mouse_x) * 0.45
                camera_pitch += (mouse_y - last_mouse_y) * 0.35
                camera_pitch = max(5.0, min(85.0, camera_pitch))
                last_mouse_x, last_mouse_y = mouse_x, mouse_y

            elif event.type == pygame.MOUSEWHEEL:
                camera_distance = max(10.0, min(50.0, camera_distance - event.y * 1.5))

            elif event.type == KEYDOWN:
                if event.key == K_ESCAPE:
                    running = False
                elif event.key == K_SPACE:
                    park_or_exit()
                elif event.key == K_a:
                    auto_park()
                elif event.key == K_c:
                    camera_pitch, camera_yaw, camera_distance = CAM_DEFAULT
                elif event.key == K_t:
                    time_scale_index = (time_scale_index + 1) % len(TIME_SCALES)
                    set_message(f"Time speed x{TIME_SCALES[time_scale_index]} "
                                f"({TIME_SCALE_NAMES[time_scale_index]})", 3)
                elif event.key == K_n:
                    night_mode = not night_mode
                    set_message("Night mode ON" if night_mode else "Day mode ON", 2)
                elif event.key == K_k:
                    color_index = (color_index + 1) % len(CAR_COLORS)
                    P.color = CAR_COLORS[color_index]
                elif event.key == K_o:
                    camera_orbit = not camera_orbit
                    set_message("Auto-orbit camera ON" if camera_orbit else "Auto-orbit camera OFF", 2)
                elif event.key == K_1:
                    camera_pitch, camera_yaw, camera_distance = CAM_DEFAULT
                elif event.key == K_2:
                    camera_pitch, camera_yaw, camera_distance = 72.0, 0.0, 30.0      # high overview
                elif event.key == K_3:
                    camera_pitch, camera_yaw, camera_distance = 18.0, -25.0, 16.0    # low cinematic view

        if camera_orbit:
            camera_yaw += 10.0 * dt

        update_world(dt, pygame.key.get_pressed())
        render()

finally:
    ids = [v[0] for v in text_cache.values()]
    for tex in (GROUND_TEXTURE, TREE_TEXTURE, SKY_TEX, GRASS_TEX, BUILDING_TEX, SIGN_TEX):
        if tex is not None:
            ids.append(tex)
    if ids:
        glDeleteTextures(ids)
    pygame.quit()
