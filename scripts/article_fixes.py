"""
The hand-written part of the Markdown conversion, applied by
scripts/html_to_markdown.py after it has proved that the mechanical part kept
every word. Images are keyed by the content hash in their file name.
"""

# The old numeric URL. The sentence reads "Newton also contributed a great deal
# to motion with his laws". The number can't confirm it, because the table
# assigned new ids at import.
LINK_FIXES = {
    'https://joaovitorwitt.com/articles/10': (
        '/articles/how-the-laws-of-newton-shape-our-reality'
    ),
}

CAPTIONS = {
    # kinematics-in-one-dimension
    'cb5b772bf4e5': 'A set of coordinate axes.',
    '58f6606a2041': 'Driving 10 km east, then 5 km west: the displacement is 5 km.',
    '0118c4d0c785': (
        "The dog's path, with its displacement of -20 m and total distance of 60 m."
    ),
    '8ef808c6001e': (
        'The path of the dotted line represents the total distance covered by the dog.'
    ),
    'fc369ee970a1': (
        'The displacement runs between the start at 25 m and the end at 5 m.'
    ),
    '2913270bb7db': (
        'A rock and a feather falling in a tube filled with air and in a tube '
        'without air.'
    ),
    'ea54e39edd9c': (
        'The ball leaves the hand at A with an initial velocity of 20 m/s, and its '
        'velocity reaches zero at B.'
    ),
    # how-the-measurement-of-units-changed-physics
    '492808f13223': 'The seven base quantities of the SI, with their units and symbols.',
    '89d4ba2e59f9': (
        'Some lengths in meters, from the distance to the Andromeda Galaxy to the '
        'radius of a proton.'
    ),
    'f915d19f3a82': 'Light travels exactly 299 792 458 meters in 1 second.',
    '9b1bc511f067': (
        'Some time intervals in seconds, from the age of the Sun to the Planck time.'
    ),
    'dcd7810d5cac': (
        'Microwaves at exactly 9192631770 cycles per second make the outermost '
        'electron of a cesium-133 atom invert its spin.'
    ),
    'e1ddf7df1640': 'The Kibble balance in force mode.',
    '8261d5deb0b8': 'The Kibble balance in velocity mode.',
}

# Pictures of formulas, written out. Any words the picture held become text.
FORMULAS = {
    # kinematics-in-one-dimension
    '0498b8821c6e': r"""$$ \Delta x = x_2 - x_1 $$

The symbol $\Delta x$ means the change in position of an object.""",
    'b7e4f9ab3ebe': r"""- $\Delta x$: displacement
- $x_1$: initial position
- $x_2$: final position

$$ \Delta x = x_2 - x_1 = 5 \, \text{km} - 0 \, \text{km} $$

$$ \Delta x = 5 \, \text{km} $$""",
    'e98cbf0f43eb': (
        r'$$ \text{Average velocity} = '
        r'\frac{\text{Displacement}}{\text{Time Elapsed}} $$'
    ),
    '096c5bf46b44': (
        r'$$ \text{Average speed} = '
        r'\frac{\text{Total Distance}}{\text{Time Elapsed}} $$'
    ),
    '2ea4a39cae9c': (
        r'$$ \text{average acceleration} = '
        r'\frac{\text{change in velocity}}{\text{time interval}} $$'
    ),
    'e3a430750ca7': r'$$ a = \frac{V_2 - V_1}{t_2 - t_1} = \frac{\Delta v}{\Delta t} $$',
    '68cbe1481300': r'$$ V = V_0 + at $$',
    'f0d3add053fe': r'$$ X = X_0 + V_0 t + \frac{1}{2} a t^2 $$',
    'a010820717cd': r'$$ V^2 = V_0^2 + 2a \Delta x $$',
    '007797850f4e': r"""Kinematics equations for constant acceleration:

$$ v = v_0 + at $$

$$ x = x_0 + v_0 t + \frac{1}{2} a t^2 $$

$$ v^2 = v_0^2 + 2a (x - x_0) $$

Where:

- $t$ = time
- $a$ = acceleration
- $V_0$ = initial velocity
- $V$ = velocity
- $X_0$ = initial position
- $X$ = position""",
    '8c7911b50ec5': r'$$ g = 9.8 \, \text{m/s}^2 $$',
    '825330234f5b': r"""$$ V^2 = V_0^2 + 2ay $$

Solving for y:

$$ y = \frac{V^2 - V_0^2}{2a} $$

Plugging the values in the equation:

$$ y = \frac{(0)^2 - (20)^2}{2 \cdot (-9.8)} $$

Final answer:

$$ y \cong 20.4 \, \text{meters} $$""",
    # how-the-measurement-of-units-changed-physics
    '0b8de63c0e22': r"""$$ \frac{1 \, \text{m}}{100 \, \text{cm}} = 1 \qquad \frac{100 \, \text{cm}}{1 \, \text{m}} = 1 $$

Now to convert 3 meters to centimeters, we do:

$$ 3 \, \text{m} = (3 \, \text{m}) (1) $$

$$ (3 \, \cancel{\text{m}}) \left( \frac{100 \, \text{cm}}{1 \, \cancel{\text{m}}} \right) = 300 \, \text{cm} $$""",
}
