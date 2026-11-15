"""Sky Sim physics: every on-screen number is computed here, never typed into the CSV.

Units inside: metres, seconds, watts, kelvin, degrees for angles. A step names an object and a distance;
these functions give its size in the sky, brightness, light travel time, temperature and clocks, plus the
short readout text the sk_* layers show.
"""
from __future__ import annotations

import math
import re

# ---- constants -------------------------------------------------------------------------------------------
C = 299_792_458.0                    # m/s
G = 6.674_30e-11
AU = 1.495_978_707e11                # m
LY = 9.460_730_472_580_8e15          # m
PC = 3.085_677_581e16
KM = 1_000.0
R_SUN = 6.957e8                      # m
L_SUN = 3.828e26                     # W
M_SUN = 1.988_47e30                  # kg
T_SUN = 5772.0                       # K
YEAR = 365.25 * 86400.0              # Julian year, s
MOON_DIST = 384_400 * KM
MOON_RADIUS = 1737.4 * KM
MOON_ALBEDO = 0.12                   # geometric albedo
SIGMA = 5.670_374e-8

# ---- bodies ----------------------------------------------------------------------------------------------
# radius km, orbit (AU from the Sun), geometric albedo, mass kg
PLANETS = {
    'mercury': dict(radius=2439.7, orbit=0.387, albedo=0.142, mass=3.301e23),
    'venus':   dict(radius=6051.8, orbit=0.723, albedo=0.689, mass=4.867e24),
    'earth':   dict(radius=6371.0, orbit=1.000, albedo=0.434, mass=5.972e24, bond=0.306),
    'mars':    dict(radius=3389.5, orbit=1.524, albedo=0.170, mass=6.417e23),
    'jupiter': dict(radius=69911, orbit=5.203, albedo=0.538, mass=1.898e27),
    'saturn':  dict(radius=58232, orbit=9.537, albedo=0.499, mass=5.683e26),
    'uranus':  dict(radius=25362, orbit=19.19, albedo=0.488, mass=8.681e25),
    'neptune': dict(radius=24622, orbit=30.07, albedo=0.442, mass=1.024e26),
    'moon':    dict(radius=1737.4, orbit=1.000, albedo=0.12, mass=7.342e22),
}

# moon name -> (parent, orbit radius km from the parent's centre, moon radius km)
MOONS = {
    'moon': ('earth', 384_400, 1737.4),
    'phobos': ('mars', 9_376, 11.27), 'deimos': ('mars', 23_463, 6.2),
    'metis': ('jupiter', 128_000, 21.5), 'io': ('jupiter', 421_700, 1821.6),
    'callisto': ('jupiter', 1_882_700, 2410.3), 'valetudo': ('jupiter', 18_980_000, 0.5),
    'pan': ('saturn', 133_584, 14.1), 'titan': ('saturn', 1_221_870, 2574.7),
    'phoebe': ('saturn', 12_952_000, 106.5), 'fornjot': ('saturn', 25_146_000, 3.0),
    'cordelia': ('uranus', 49_770, 20.1), 'miranda': ('uranus', 129_390, 235.8),
    'ferdinand': ('uranus', 20_900_000, 10.0),
    'naiad': ('neptune', 48_224, 33.0), 'triton': ('neptune', 354_759, 1353.4),
    'neso': ('neptune', 49_285_000, 30.0),
}

# stars: radius in solar radii, surface temperature K (luminosity follows from both)
STARS = {
    'sun': dict(radius=1.0, temp=5772),
    'proxima_centauri': dict(radius=0.154, temp=3042),
    'trappist_1': dict(radius=0.119, temp=2566),
    '2mass_j0523': dict(radius=0.086, temp=2074),          # smallest known star (~)
    'sirius_a': dict(radius=1.711, temp=9940),
    'vega': dict(radius=2.36, temp=9602),
    'arcturus': dict(radius=25.4, temp=4286),
    'rigel': dict(radius=78.9, temp=12100),
    'betelgeuse': dict(radius=764, temp=3600),
    'antares': dict(radius=680, temp=3660),
    'uy_scuti': dict(radius=909, temp=3365),
    'stephenson_2_18': dict(radius=2150, temp=3200),       # largest known star (~)
}

# black holes: mass in solar masses, luminosity in solar luminosities (quasar glow; 0 = dark)
BLACK_HOLES = {
    'ton618': dict(mass=4.07e10, lum=1.4e14),
    'sagittarius_a': dict(mass=4.3e6, lum=0.0),
    'm87': dict(mass=6.5e9, lum=0.0),
    'gargantua': dict(mass=1.0e8, lum=0.0),
}

SUN_FROM_EARTH_DEG = 2 * math.degrees(math.asin(R_SUN / AU))          # ~0.533
MOON_FROM_EARTH_DEG = 2 * math.degrees(math.asin(MOON_RADIUS / MOON_DIST))  # ~0.518


def _key(name: str) -> str:
    return re.sub(r'[^a-z0-9]+', '_', str(name).strip().lower()).strip('_')


def _find(table: dict, name: str) -> dict:
    """Look a name up ignoring case, spaces and punctuation: 'TON 618', 'ton618', 'Sirius A'."""
    k = _key(name)
    if k in table:
        return table[k]
    squashed = {t.replace('_', ''): v for t, v in table.items()}
    if k.replace('_', '') in squashed:
        return squashed[k.replace('_', '')]
    raise KeyError(f'unknown object {name!r}')


# ---- distances -------------------------------------------------------------------------------------------
_UNITS = {'m': 1.0, 'km': KM, 'au': AU, 'ly': LY, 'light_year': LY, 'light_years': LY, 'lightyear': LY,
          'lightyears': LY, 'pc': PC, 'kpc': 1e3 * PC, 'mpc': 1e6 * PC, 'ls': C, 'light_second': C,
          'light_seconds': C, 'lm': 60 * C, 'light_minute': 60 * C, 'light_minutes': 60 * C}
_WORDS = {'thousand': 1e3, 'million': 1e6, 'billion': 1e9, 'trillion': 1e12}


def parse_distance(text) -> float:
    """'10.8 billion ly', '10.8e9 ly', '1,000 ly', '0.39 AU', '9380 km', '2.4 light-seconds' -> metres.
    A bare number is taken as km. Raises ValueError on anything else."""
    if isinstance(text, (int, float)):
        return float(text) * KM
    s = str(text).strip().lower().replace(',', '').replace('-', ' ')
    m = re.fullmatch(r'([0-9]*\.?[0-9]+(?:e[+-]?[0-9]+)?)\s*(thousand|million|billion|trillion)?\s*([a-z ]*)', s)
    if not m:
        raise ValueError(f'distance not understood: {text!r}')
    n = float(m.group(1)) * _WORDS.get(m.group(2) or '', 1.0)
    unit = _key(m.group(3) or 'km')
    if unit not in _UNITS:
        raise ValueError(f'unknown distance unit in {text!r}')
    return n * _UNITS[unit]


# ---- geometry and light ----------------------------------------------------------------------------------
def angular_size_deg(radius_m: float, distance_m: float) -> float:
    """Full angular diameter seen from `distance_m` (measured from the centre). 180 when inside."""
    if distance_m <= radius_m:
        return 180.0
    return 2 * math.degrees(math.asin(radius_m / distance_m))


def light_time_s(distance_m: float) -> float:
    return distance_m / C


def flux(lum_w: float, distance_m: float) -> float:
    return lum_w / (4 * math.pi * distance_m ** 2)


SOLAR_FLUX_EARTH = flux(L_SUN, AU)
# sunlight is ~398,000 full Moons (magnitudes -26.74 vs -12.74, 14 magnitudes apart)
FULL_MOON_PER_SUN = 10 ** (0.4 * 14.0)


def star_luminosity(radius_rsun: float, temp_k: float) -> float:
    """Watts, from radius and surface temperature (Stefan-Boltzmann)."""
    return radius_rsun ** 2 * (temp_k / T_SUN) ** 4 * L_SUN


def equilibrium_temp_k(lum_w: float, distance_m: float, bond_albedo: float = 0.306, greenhouse_k: float = 33.0) -> float:
    """Average surface temperature of an Earth-like planet; greenhouse_k is Earth's ~33 K warming."""
    t = (flux(lum_w, distance_m) * (1 - bond_albedo) / (4 * SIGMA)) ** 0.25
    return t + greenhouse_k


def schwarzschild_radius_m(mass_msun: float) -> float:
    return 2 * G * mass_msun * M_SUN / C ** 2


def dilation_factor(planet_time_s: float, far_time_s: float) -> float:
    """'1 hour = 7 years' -> dilation_factor(3600, 7*YEAR) = 61,362."""
    return far_time_s / planet_time_s


# ---- the step-level readouts -----------------------------------------------------------------------------
def sun_from_planet(planet: str) -> dict:
    """The Sun seen from a planet: distance, size and light against Earth's view, light travel time."""
    p = _find(PLANETS, planet)
    d = p['orbit'] * AU
    return dict(distance_m=d, distance_au=p['orbit'], size_x=AU / d, brightness_x=(AU / d) ** 2,
                angular_deg=angular_size_deg(R_SUN, d), light_s=light_time_s(d))


def planet_as_moon(planet: str) -> dict:
    """A planet at the Moon's distance, lit by sunlight like the Moon: size and brightness against the full Moon."""
    p = _find(PLANETS, planet)
    r = p['radius'] * KM
    size = r / MOON_RADIUS
    return dict(size_x=size, brightness_x=size ** 2 * p['albedo'] / MOON_ALBEDO,
                angular_deg=angular_size_deg(r, MOON_DIST))


def parent_from_moon(moon: str) -> dict:
    """The parent planet seen from one of its moons."""
    parent, orbit_km, _ = _find(MOONS, moon)
    r = PLANETS[parent]['radius'] * KM
    d = orbit_km * KM
    ang = angular_size_deg(r, d)
    return dict(parent=parent, distance_m=d, altitude_m=d - r, angular_deg=ang, moon_x=ang / MOON_FROM_EARTH_DEG)


def star_in_place_of_sun(star: str, distance_m: float = AU) -> dict:
    """Any star at `distance_m` (default: where the Sun is): size, brightness, Earth's temperature."""
    s = _find(STARS, star)
    lum = star_luminosity(s['radius'], s['temp'])
    r = s['radius'] * R_SUN
    ang = angular_size_deg(r, distance_m)
    return dict(lum_w=lum, angular_deg=ang, sun_x=ang / SUN_FROM_EARTH_DEG, moon_x=ang / MOON_FROM_EARTH_DEG,
                flux_x=flux(lum, distance_m) / SOLAR_FLUX_EARTH, full_moon_x=flux(lum, distance_m) / SOLAR_FLUX_EARTH * FULL_MOON_PER_SUN,
                earth_temp_c=equilibrium_temp_k(lum, distance_m) - 273.15, temp_k=s['temp'])



def black_hole_at(name: str, distance_m: float) -> dict:
    """A black hole at `distance_m`: horizon size in the sky and its glow against the Sun."""
    b = _find(BLACK_HOLES, name)
    rs = schwarzschild_radius_m(b['mass'])
    lum = b['lum'] * L_SUN
    fx = flux(lum, distance_m) / SOLAR_FLUX_EARTH if lum else 0.0
    return dict(horizon_m=rs, horizon_au=rs / AU, angular_deg=angular_size_deg(rs, distance_m),
                flux_x=fx, sun_match_ly=AU * math.sqrt(b['lum']) / LY if lum else None)


def heat_stage(flux_x: float) -> str:
    """Landscape look stage from light against sunlight at Earth: night, dot, day, glare, scorch, burn, melt."""
    if flux_x < 1e-6:
        return 'night'
    if flux_x < 0.02:
        return 'dot'
    if flux_x < 2:          # up to Venus-level light
        return 'day'
    if flux_x < 5:
        return 'glare'
    if flux_x < 10:         # Mercury-level: rock bakes
        return 'scorch'
    if flux_x < 100:        # wood ignites (~14x at 50 ly from TON 618 in the reference)
        return 'burn'
    return 'melt'           # rock turns to lava


# ---- readout text ----------------------------------------------------------------------------------------
def _num(x: float) -> str:
    """Readout number: under 1 -> 2 significant digits (0.39), under 100 -> 1 decimal (2.6, 19.2, 10.8),
    else a whole number with commas. Trailing zeros dropped."""
    if x >= 100:
        return f'{round(x):,}'
    s = f'{x:.1f}' if x >= 1 else f'{x:.{max(1 - math.floor(math.log10(x)), 1)}f}' if x > 0 else '0'
    return s.rstrip('0').rstrip('.') if '.' in s else s


def fmt_big(x: float) -> str:
    """1.2e9 -> '1.2 billion', 58e6 -> '58 million', 714370 -> '714,370'."""
    for word, v in (('trillion', 1e12), ('billion', 1e9), ('million', 1e6)):
        if x >= v:
            return f'{_num(x / v)} {word}'
    return f'{round(x):,}'


def fmt_distance(m: float, unit: str = 'auto') -> str:
    """km below ~0.1 ly (with million/billion), light-years beyond; unit forces 'km', 'au' or 'ly'."""
    if unit == 'au':
        return f'{_num(m / AU)} AU'
    if unit == 'ly' or (unit == 'auto' and m >= 0.05 * LY):
        ly = m / LY
        return f'{fmt_big(ly) if ly >= 1e6 else _num(ly)} ly'
    return f'{fmt_big(m / KM)} km'


def fmt_ratio(x: float, of: str = '') -> str:
    """2.58 -> '2.6×', 0.052 -> '5%', 1/369 -> '1/369', 0.27 -> 'a quarter'."""
    tail = f' {of}' if of else ''
    if x >= 1.05:
        return f'{round(x):,}×{tail}' if x >= 10 else f'{_num(x)}×{tail}'
    if x >= 0.95:
        return f'the same as{tail}' if of else 'the same'
    for frac, word in ((0.5, 'half'), (1 / 3, 'a third'), (0.25, 'a quarter')):
        if abs(x - frac) / frac < 0.12:
            return f'{word}{" of" + tail if of else ""}'
    if x >= 0.02:
        return f'{round(x * 100)}%{" of" + tail if of else ""}'
    return f'1/{round(1 / x):,}'


def fmt_duration(s: float) -> str:
    """Light travel time / sunset length: '2.4 light-seconds' is the caller's; here '3 min 13 s', '2.7 hours', '4.2 years'."""
    if s < 60:
        return f'{_num(s)} s'
    if s < 3600:
        mi, se = divmod(round(s), 60)
        return f'{mi} min {se} s' if se else f'{mi} min'
    if s < 2 * 86400:
        return f'{_num(s / 3600)} hours'
    if s < YEAR:
        return f'{_num(s / 86400)} days'
    return f'{_num(s / YEAR)} years'


def fmt_light_time(s: float) -> str:
    """Under a minute as light-seconds (the journey readout), otherwise as a duration."""
    return f'{_num(s)} light-seconds' if s < 60 else fmt_duration(s)


def fmt_clock(s: float) -> str:
    """Twin clock on the planet: '00:05:51'."""
    s = int(s)
    return f'{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}'


def fmt_far_clock(s: float) -> str:
    """Twin clock far away: '249 d 22 h', '3 y 41 d', '5 h 12 m'."""
    s = int(s)
    if s >= YEAR:
        y = int(s // YEAR)
        return f'{y} y {int((s - y * YEAR) // 86400)} d'
    if s >= 86400:
        return f'{s // 86400} d {s % 86400 // 3600} h'
    return f'{s // 3600} h {s % 3600 // 60} m'


def fmt_angle(deg: float) -> str:
    return f'{_num(deg)}°' if deg < 10 else f'{round(deg)}°'


def fmt_temp(c: float) -> str:
    return f'{round(c):+d} °C'.replace('+', '') if c >= 0 else f'−{abs(round(c))} °C'


# ---- rung-card facts ---------------------------------------------------------------------------------------------
SUN_MAG = -26.74
# bright things in our sky, brightest first: (magnitude, name)
SKY_MARKS = ((-12.74, 'the full Moon'), (-4.6, 'Venus'), (-2.9, 'Jupiter'), (-1.46, 'Sirius'), (0.0, 'Vega'))
NAKED_EYE = 6.5


def magnitude(flux_x: float) -> float:
    """Apparent magnitude from light against sunlight at Earth."""
    return SUN_MAG - 2.5 * math.log10(max(flux_x, 1e-40))


def earth_temp_c(flux_x: float) -> float:
    """Earth's average temperature under this much light (sunlight = 1 gives ~15 °C)."""
    return 255.0 * max(flux_x, 0.0) ** 0.25 + 33.0 - 273.15 if flux_x > 0 else -270.0


def light_fact(flux_x: float) -> str:
    """One short line about how bright it is, in our own words."""
    m = magnitude(flux_x)
    if m > NAKED_EYE:
        return f'Magnitude {m:.1f}: too faint for the eye'
    if flux_x < 0.5 / FULL_MOON_PER_SUN:
        brighter = [name for mag, name in SKY_MARKS if m < mag]
        return f'Brighter than {brighter[0]}' if brighter else f'Magnitude {m:.1f}: a faint star'
    if flux_x < 0.02:
        return f'{fmt_big(flux_x * FULL_MOON_PER_SUN)} times the full Moon'
    if flux_x < 0.95:
        return f'{round(flux_x * 100)}% of the Sun\'s light'
    if flux_x < 1.05:
        return 'As bright as our Sun'
    return f'{fmt_big(flux_x) if flux_x >= 100 else _num(flux_x)} times the Sun\'s light'


def heat_fact(flux_x: float) -> str:
    """Earth under that light, or '' while it changes nothing."""
    if flux_x < 0.3:
        return ''
    c = earth_temp_c(flux_x)
    if c > 5500:
        return "Earth: hotter than the Sun's surface"
    step = 10 if c < 300 else 50 if c < 2000 else 100
    return f'Earth: about {fmt_big(round(c / step) * step)} °C'
