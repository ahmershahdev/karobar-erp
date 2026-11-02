export const vertexShader = /* glsl */ `
  varying vec2 vUv;
  void main() {
    vUv = uv;
    gl_Position = vec4(position.xy, 0.0, 1.0);
  }
`;

// Domain-warped fractal noise (after Inigo Quilez's "warp" article) mapped onto the palette,
// with faint horizontal rules so it reads as ledger paper under silk.
export const fragmentShader = /* glsl */ `
  precision highp float;
  varying vec2 vUv;
  uniform float uTime;
  uniform vec2 uResolution;
  uniform vec2 uPointer;
  uniform float uScroll;
  uniform vec3 uNavy;
  uniform vec3 uIndigo;
  uniform vec3 uViolet;
  uniform vec3 uMagenta;
  uniform vec3 uGold;
  uniform vec3 uTeal;
  uniform vec3 uBlack;

  float hash(vec2 p) {
    p = fract(p * vec2(123.34, 456.21));
    p += dot(p, p + 45.32);
    return fract(p.x * p.y);
  }

  float noise(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    vec2 u = f * f * (3.0 - 2.0 * f);
    return mix(
      mix(hash(i), hash(i + vec2(1.0, 0.0)), u.x),
      mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), u.x),
      u.y
    );
  }

  float fbm(vec2 p) {
    float value = 0.0;
    float amplitude = 0.5;
    mat2 rotate = mat2(0.8, -0.6, 0.6, 0.8);
    for (int i = 0; i < 5; i++) {
      value += amplitude * noise(p);
      p = rotate * p * 2.02;
      amplitude *= 0.5;
    }
    return value;
  }

  void main() {
    vec2 uv = vUv;
    vec2 p = (gl_FragCoord.xy - 0.5 * uResolution) / uResolution.y;
    float t = uTime * 0.06;

    vec2 pointer = (uPointer - 0.5) * vec2(uResolution.x / uResolution.y, 1.0);
    float pull = exp(-3.0 * length(p - pointer));

    vec2 q = vec2(fbm(p * 1.4 + t), fbm(p * 1.4 - t + 5.2));
    vec2 r = vec2(
      fbm(p * 1.8 + 3.0 * q + vec2(1.7, 9.2) + 0.6 * t + pull * 0.6),
      fbm(p * 1.8 + 3.0 * q + vec2(8.3, 2.8) - 0.4 * t)
    );
    float f = fbm(p * 1.6 + 3.5 * r);

    vec3 color = mix(uNavy, uIndigo, smoothstep(0.1, 0.6, f));
    color = mix(color, uViolet, smoothstep(0.35, 0.85, length(q)));
    color = mix(color, uMagenta, 0.55 * smoothstep(0.6, 1.0, r.x));
    color = mix(color, uTeal, 0.35 * smoothstep(0.65, 1.0, r.y));

    float sheen = pow(smoothstep(0.55, 0.95, f), 3.0);
    color += uGold * sheen * (0.55 + 0.6 * pull);

    float rule = smoothstep(0.985, 1.0, abs(sin(uv.y * 68.0 + f * 1.6)));
    color += uGold * rule * 0.05;

    float vignette = smoothstep(1.25, 0.25, length(p * vec2(0.85, 1.1)));
    color = mix(uBlack, color, vignette * (1.0 - 0.75 * uScroll));
    color = mix(color, uBlack, smoothstep(0.35, 0.0, uv.y));

    gl_FragColor = vec4(color, 1.0);
  }
`;
