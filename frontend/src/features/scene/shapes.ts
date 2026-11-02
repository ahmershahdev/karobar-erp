// Target layouts for the particle field. Each returns xyz triples for `count` points; the vertex
// shader blends between them, so every shape must use the same count and the same point order.

function random(seed: number): () => number {
  // mulberry32: deterministic, so the field looks the same on every load and in every test.
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** A globe: an even Fibonacci shell with a thin cloud around it. */
export function globe(count: number, radius = 1.65): Float32Array {
  const rand = random(1);
  const out = new Float32Array(count * 3);
  const golden = Math.PI * (3 - Math.sqrt(5));
  for (let i = 0; i < count; i++) {
    const y = 1 - (i / (count - 1)) * 2;
    const ring = Math.sqrt(1 - y * y);
    const theta = golden * i;
    const r = radius * (rand() < 0.86 ? 1 + (rand() - 0.5) * 0.03 : 1 + rand() * 0.45);
    out[i * 3] = Math.cos(theta) * ring * r;
    out[i * 3 + 1] = y * r;
    out[i * 3 + 2] = Math.sin(theta) * ring * r;
  }
  return out;
}

/** A 3D bar chart: a 7 by 4 grid of columns whose heights rise like a good quarter. */
export function bars(count: number): Float32Array {
  const rand = random(2);
  const out = new Float32Array(count * 3);
  const cols = 7;
  const rows = 4;
  const gap = 0.52;
  const width = 0.3;
  for (let i = 0; i < count; i++) {
    const c = i % cols;
    const r = Math.floor(i / cols) % rows;
    const height = 0.35 + (c / (cols - 1)) * 1.9 + Math.sin(c * 1.7 + r) * 0.25 + r * 0.08;
    // Most points sit on the faces of each column so the edges read clearly.
    const onFace = rand() < 0.7;
    let x = (rand() - 0.5) * width;
    let z = (rand() - 0.5) * width;
    if (onFace) {
      if (rand() < 0.5) x = Math.sign(x || 1) * width * 0.5;
      else z = Math.sign(z || 1) * width * 0.5;
    }
    out[i * 3] = (c - (cols - 1) / 2) * gap + x;
    out[i * 3 + 1] = rand() * height - 1.15;
    out[i * 3 + 2] = (r - (rows - 1) / 2) * gap + z;
  }
  return out;
}

/** A coin: a torus seen at an angle, like a ring of light. */
export function ring(count: number, major = 1.55, minor = 0.32): Float32Array {
  const rand = random(3);
  const out = new Float32Array(count * 3);
  for (let i = 0; i < count; i++) {
    const u = rand() * Math.PI * 2;
    const v = rand() * Math.PI * 2;
    const spread = minor * (0.85 + rand() * 0.3);
    out[i * 3] = (major + spread * Math.cos(v)) * Math.cos(u);
    out[i * 3 + 1] = spread * Math.sin(v);
    out[i * 3 + 2] = (major + spread * Math.cos(v)) * Math.sin(u);
  }
  return out;
}

export function seeds(count: number): Float32Array {
  const rand = random(4);
  const out = new Float32Array(count);
  for (let i = 0; i < count; i++) out[i] = rand();
  return out;
}
