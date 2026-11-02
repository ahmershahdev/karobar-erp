export const vertexShader = /* glsl */ `
  attribute vec3 aBars;
  attribute vec3 aRing;
  attribute float aSeed;

  uniform float uTime;
  uniform float uMorph;
  uniform float uSize;
  uniform vec2 uPointer;
  uniform float uPointerStrength;

  varying float vSeed;
  varying float vDepth;

  // Each point starts its move at a slightly different moment, so shapes dissolve and
  // re-form like a flock instead of sliding over each other in one block.
  float stagger(float t, float seed) {
    return smoothstep(0.0, 1.0, clamp(t * 1.6 - seed * 0.6, 0.0, 1.0));
  }

  void main() {
    float toBars = stagger(clamp(uMorph, 0.0, 1.0), aSeed);
    float toRing = stagger(clamp(uMorph - 1.0, 0.0, 1.0), aSeed);
    vec3 p = mix(position, aBars, toBars);
    p = mix(p, aRing, toRing);

    // Cheap layered sine flow: enough to feel alive without a noise texture.
    float t = uTime * 0.35 + aSeed * 6.2831;
    p += vec3(
      sin(t + p.y * 2.1) * 0.025,
      cos(t * 0.8 + p.x * 1.7) * 0.025,
      sin(t * 1.2 + p.z * 1.9) * 0.025
    );

    vec4 mv = modelViewMatrix * vec4(p, 1.0);
    vec4 clip = projectionMatrix * mv;

    // Push points away from the pointer in screen space.
    vec2 ndc = clip.xy / clip.w;
    vec2 away = ndc - uPointer;
    float pull = exp(-dot(away, away) * 18.0) * uPointerStrength;
    clip.xy += normalize(away + 1e-5) * pull * 0.12 * clip.w;

    gl_Position = clip;
    gl_PointSize = uSize * (0.6 + aSeed * 1.1) * (6.0 / -mv.z);
    vSeed = aSeed;
    vDepth = clamp((-mv.z - 3.0) / 4.0, 0.0, 1.0);
  }
`;

export const fragmentShader = /* glsl */ `
  precision highp float;
  uniform vec3 uGold;
  uniform vec3 uPeach;
  uniform vec3 uCoral;
  uniform vec3 uLavender;
  uniform vec3 uTurquoise;
  uniform float uOpacity;

  varying float vSeed;
  varying float vDepth;

  void main() {
    vec2 c = gl_PointCoord - 0.5;
    float d = length(c);
    if (d > 0.5) discard;
    float core = smoothstep(0.5, 0.0, d);
    float glow = pow(core, 1.7);

    // Mostly warm metals, with a few cool sparks for depth.
    vec3 color = mix(uGold, uPeach, smoothstep(0.0, 0.55, vSeed));
    color = mix(color, uCoral, smoothstep(0.55, 0.82, vSeed));
    color = mix(color, uLavender, step(0.9, vSeed) * 0.85);
    color = mix(color, uTurquoise, step(0.965, vSeed));

    float alpha = glow * uOpacity * mix(0.95, 0.4, vDepth);
    gl_FragColor = vec4(color * (0.9 + glow * 0.9), alpha);
  }
`;
