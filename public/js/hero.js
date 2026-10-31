// Home page hero: the orbiting star field, the gravitational-lensing particle
// canvas, mouse parallax and the scroll-driven shrink of the black hole. The
// black hole itself is pure CSS (hero.modules.css); this only animates
// around it.
(function () {
  'use strict';

  var hero = document.querySelector('.hero');
  if (!hero) return;

  var reduceMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;

  function randomBetween(min, max) {
    return Math.random() * (max - min) + min;
  }

  // ---------------------------------------------------------------------
  // Star field
  // ---------------------------------------------------------------------

  // "far" stars are smaller, dimmer, and orbit much slower than "near" ones;
  // that size/brightness/speed difference is what reads as parallax depth,
  // not a difference in orbit radius. Sizes are ranges so stars within a
  // layer still vary instead of looking like two uniform dot sizes.
  var STAR_LAYERS = [
    { layer: 'near', count: 160, radiusRange: [22, 46], orbitDurationRange: [20, 90], sizeRange: [3, 5] },
    { layer: 'far', count: 110, radiusRange: [20, 48], orbitDurationRange: [90, 220], sizeRange: [1.5, 3] },
  ];

  function randomTint() {
    var roll = Math.random();
    if (roll < 0.14) return 'blue';
    if (roll < 0.28) return 'amber';
    return 'white';
  }

  function createStar(layer, config) {
    var orbitDuration = randomBetween(config.orbitDurationRange[0], config.orbitDurationRange[1]);
    // A negative delay starts the animation partway through its cycle, which
    // scatters each star's starting angle while sharing one keyframe.
    var orbitDelay = -(Math.random() * orbitDuration);
    var radius = randomBetween(config.radiusRange[0], config.radiusRange[1]);
    var size = randomBetween(config.sizeRange[0], config.sizeRange[1]);
    var tint = randomTint();

    var orbit = document.createElement('div');
    orbit.className = 'star-orbit';
    orbit.style.animationDuration = orbitDuration + 's';
    orbit.style.animationDelay = orbitDelay + 's';
    orbit.style.animationDirection = Math.random() < 0.5 ? 'normal' : 'reverse';

    var dot = document.createElement('div');
    dot.className = 'star-dot' + (layer === 'far' ? ' -far' : '') + (tint !== 'white' ? ' -' + tint : '');
    dot.style.width = size + 'px';
    dot.style.height = size + 'px';
    dot.style.top = -size / 2 + 'px';
    dot.style.left = -size / 2 + 'px';
    dot.style.transform = 'translateX(' + radius + 'vmin)';
    dot.style.animationDuration = randomBetween(4, 11) + 's';
    dot.style.animationDelay = randomBetween(1, 5) + 's';

    orbit.appendChild(dot);
    return orbit;
  }

  // Generated here rather than in the HTML: the orbits are random, and 270
  // inline-styled divs would add weight to every cached page for no gain.
  STAR_LAYERS.forEach(function (config) {
    var container = hero.querySelector('.stars-overflow.-' + config.layer);
    if (!container) return;
    var fragment = document.createDocumentFragment();
    for (var i = 0; i < config.count; i++) fragment.appendChild(createStar(config.layer, config));
    container.appendChild(fragment);
  });

  // ---------------------------------------------------------------------
  // Lensing canvas
  // ---------------------------------------------------------------------

  // A small particle system orbiting close to the black hole that stretches
  // into a tangential streak as it nears the "photon sphere", a decorative
  // approximation of gravitational lensing. Coordinates are in a fixed canvas
  // pixel space; LENS_INNER_RADIUS sits just outside where .shadow's edge
  // renders (the canvas's CSS size is kept proportional to .shadow's 20vw so
  // the alignment holds at any viewport width).
  var LENS_CANVAS_SIZE = 600;
  var LENS_OUTER_RADIUS = 280;
  var LENS_INNER_RADIUS = 185;
  var LENS_PARTICLE_COUNT = 40;
  // Proximity (0 at the outer edge, 1 at the photon sphere) thresholds for
  // fading a particle in after it spawns and out before it's consumed.
  var LENS_FADE_IN_END = 0.08;
  var LENS_FADE_OUT_START = 0.8;
  // How much faster a particle spins near the photon sphere, a stand-in for
  // real orbital speed-up at smaller radii.
  var LENS_SPIN_BOOST = 6;

  function randomAngularSpeed() {
    return (Math.random() < 0.5 ? -1 : 1) * randomBetween(0.15, 0.4);
  }

  function createLensParticle() {
    return {
      angle: randomBetween(0, Math.PI * 2),
      radius: randomBetween(LENS_INNER_RADIUS, LENS_OUTER_RADIUS),
      angularSpeed: randomAngularSpeed(),
      decayPerSecond: randomBetween(6, 14),
      size: randomBetween(1.5, 3),
    };
  }

  // Canvas strokeStyle can't take var(--x), so the theme color is resolved
  // to a real value. One shared color: the star tints read poorly against
  // the light theme's background.
  function lensParticleColor() {
    var value = getComputedStyle(document.documentElement).getPropertyValue('--default-text-color').trim();
    return value || '#ffffff';
  }

  function lensProximity(radius) {
    return Math.min(Math.max((LENS_OUTER_RADIUS - radius) / (LENS_OUTER_RADIUS - LENS_INNER_RADIUS), 0), 1);
  }

  function updateLensParticles(particles, dtSeconds) {
    particles.forEach(function (particle) {
      var proximity = lensProximity(particle.radius);
      // Negligible far out, dramatic right at the photon sphere.
      var spinMultiplier = 1 + proximity * proximity * LENS_SPIN_BOOST;
      particle.angle += particle.angularSpeed * spinMultiplier * dtSeconds;
      particle.radius -= particle.decayPerSecond * dtSeconds;

      if (particle.radius <= LENS_INNER_RADIUS) {
        // "Consumed": respawn at the outer edge. The fade-out has already
        // taken it to alpha 0, so the jump happens while invisible.
        particle.radius = LENS_OUTER_RADIUS;
        particle.angle = randomBetween(0, Math.PI * 2);
        particle.angularSpeed = randomAngularSpeed();
        particle.decayPerSecond = randomBetween(6, 14);
      }
    });
  }

  function drawLensParticles(ctx, particles, color) {
    ctx.clearRect(0, 0, LENS_CANVAS_SIZE, LENS_CANVAS_SIZE);
    ctx.strokeStyle = color;
    ctx.lineCap = 'round';
    var center = LENS_CANVAS_SIZE / 2;

    particles.forEach(function (particle) {
      var x = center + Math.cos(particle.angle) * particle.radius;
      var y = center + Math.sin(particle.angle) * particle.radius;

      var proximity = lensProximity(particle.radius);
      // Grows sharply only near the photon sphere, so far-out particles read
      // as dots and the streak is a late, dramatic effect.
      var halfStretch = (particle.size + proximity * proximity * 26) / 2;

      // Tangential to the radius (along the direction of travel), which is
      // what makes it read as motion smear.
      var tangentAngle = particle.angle + Math.PI / 2;
      var dx = Math.cos(tangentAngle) * halfStretch;
      var dy = Math.sin(tangentAngle) * halfStretch;

      var alpha = 1;
      if (proximity < LENS_FADE_IN_END) {
        alpha = proximity / LENS_FADE_IN_END;
      } else if (proximity > LENS_FADE_OUT_START) {
        alpha = 1 - (proximity - LENS_FADE_OUT_START) / (1 - LENS_FADE_OUT_START);
      }

      ctx.beginPath();
      ctx.moveTo(x - dx, y - dy);
      ctx.lineTo(x + dx, y + dy);
      ctx.lineWidth = particle.size;
      ctx.globalAlpha = alpha;
      ctx.stroke();
    });

    ctx.globalAlpha = 1;
  }

  var canvas = hero.querySelector('.lensing-canvas');
  var ctx = canvas && canvas.getContext('2d');
  if (ctx) {
    var dpr = window.devicePixelRatio || 1;
    canvas.width = LENS_CANVAS_SIZE * dpr;
    canvas.height = LENS_CANVAS_SIZE * dpr;
    ctx.scale(dpr, dpr);

    var particles = [];
    for (var i = 0; i < LENS_PARTICLE_COUNT; i++) particles.push(createLensParticle());

    if (reduceMotion) {
      // One static frame instead of an animation, matching how the rest of
      // the scene pauses in a varied state rather than disappearing. It is
      // redrawn on theme changes so the particles never vanish into the
      // background.
      var drawStatic = function () {
        drawLensParticles(ctx, particles, lensParticleColor());
      };
      drawStatic();
      new MutationObserver(drawStatic).observe(document.documentElement, {
        attributes: true,
        attributeFilter: ['data-theme'],
      });
    } else {
      var lastTime = null;
      var frame = function (time) {
        if (lastTime === null) lastTime = time;
        var dtSeconds = (time - lastTime) / 1000;
        lastTime = time;

        updateLensParticles(particles, dtSeconds);
        // Re-resolved every frame (cheap) so a theme toggle shows at once.
        drawLensParticles(ctx, particles, lensParticleColor());

        requestAnimationFrame(frame);
      };
      requestAnimationFrame(frame);
    }
  }

  // ---------------------------------------------------------------------
  // Mouse parallax and scroll progress
  // ---------------------------------------------------------------------

  if (reduceMotion) return;

  var mouseX = 0;
  var mouseY = 0;
  var mouseFrame = null;
  var scrollFrame = null;

  function applyParallax() {
    mouseFrame = null;
    var nx = (mouseX / window.innerWidth - 0.5) * 2;
    var ny = (mouseY / window.innerHeight - 0.5) * 2;
    hero.style.setProperty('--parallax-near-x', nx * 20 + 'px');
    hero.style.setProperty('--parallax-near-y', ny * 20 + 'px');
    hero.style.setProperty('--parallax-far-x', nx * 8 + 'px');
    hero.style.setProperty('--parallax-far-y', ny * 8 + 'px');
  }

  function applyScrollProgress() {
    scrollFrame = null;
    var rect = hero.getBoundingClientRect();
    var progress = Math.min(Math.max(-rect.top / rect.height, 0), 1);
    hero.style.setProperty('--scroll-progress', progress.toFixed(3));
  }

  window.addEventListener('mousemove', function (event) {
    mouseX = event.clientX;
    mouseY = event.clientY;
    if (mouseFrame === null) mouseFrame = requestAnimationFrame(applyParallax);
  });

  window.addEventListener(
    'scroll',
    function () {
      if (scrollFrame === null) scrollFrame = requestAnimationFrame(applyScrollProgress);
    },
    { passive: true }
  );
})();
