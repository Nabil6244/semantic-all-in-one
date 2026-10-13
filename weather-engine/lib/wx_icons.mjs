// Weather icons drawn in code (no downloaded icon set): sun, moon, cloud, partly, partly_night, rain, storm, snow, sleet,
// fog, wind. Each is drawn centred on (cx, cy) in a box `size` pixels wide; the shapes are laid out on a 100-unit grid.
export const ICONS = ['sun', 'moon', 'cloud', 'partly', 'partly_night', 'rain', 'storm', 'snow', 'sleet', 'fog', 'wind'];

const C = { sun: '#FFC93C', ray: '#FFB627', moon: '#EDE6C8', cloud: '#F3F6F9', cloudEdge: 'rgba(0,0,0,0.18)', dark: '#A8B3BF', rain: '#5AB0FF', bolt: '#FFD43B', snow: '#FFFFFF', fog: '#CBD4DC' };

function sun(ctx, k = 1) {
  ctx.save(); ctx.scale(k, k);
  ctx.strokeStyle = C.ray; ctx.lineWidth = 6; ctx.lineCap = 'round';
  for (let i = 0; i < 8; i++) {
    const a = (i * Math.PI) / 4;
    ctx.beginPath(); ctx.moveTo(Math.cos(a) * 31, Math.sin(a) * 31); ctx.lineTo(Math.cos(a) * 42, Math.sin(a) * 42); ctx.stroke();
  }
  ctx.fillStyle = C.sun; ctx.beginPath(); ctx.arc(0, 0, 23, 0, Math.PI * 2); ctx.fill();
  ctx.restore();
}

function moon(ctx, k = 1) {
  ctx.save(); ctx.scale(k, k);
  ctx.beginPath(); ctx.rect(-60, -60, 120, 120); ctx.arc(13, -9, 22, 0, Math.PI * 2, true); ctx.clip('evenodd');
  ctx.fillStyle = C.moon; ctx.beginPath(); ctx.arc(0, 0, 27, 0, Math.PI * 2); ctx.fill();
  ctx.restore();
}

function cloud(ctx, color = C.cloud, dx = 0, dy = 0, k = 1) {
  ctx.save(); ctx.translate(dx, dy); ctx.scale(k, k);
  ctx.shadowColor = C.cloudEdge; ctx.shadowBlur = 6; ctx.shadowOffsetY = 2;
  ctx.fillStyle = color; ctx.beginPath();
  ctx.arc(-20, 8, 17, 0, Math.PI * 2); ctx.arc(0, -5, 24, 0, Math.PI * 2); ctx.arc(21, 7, 18, 0, Math.PI * 2);
  ctx.rect(-20, 7, 41, 18); ctx.fill();
  ctx.restore();
}

const SHAPES = {
  sun: (ctx) => sun(ctx),
  moon: (ctx) => moon(ctx),
  cloud: (ctx) => cloud(ctx),
  partly: (ctx) => { ctx.save(); ctx.translate(-14, -14); sun(ctx, 0.78); ctx.restore(); cloud(ctx, C.cloud, 8, 10, 0.86); },
  partly_night: (ctx) => { ctx.save(); ctx.translate(-14, -14); moon(ctx, 0.8); ctx.restore(); cloud(ctx, C.cloud, 8, 10, 0.86); },
  rain: (ctx) => {
    cloud(ctx, C.cloud, 0, -10);
    ctx.strokeStyle = C.rain; ctx.lineWidth = 6; ctx.lineCap = 'round';
    for (const x of [-18, 0, 18]) { ctx.beginPath(); ctx.moveTo(x + 4, 22); ctx.lineTo(x - 4, 40); ctx.stroke(); }
  },
  storm: (ctx) => {
    cloud(ctx, C.dark, 0, -12);
    ctx.fillStyle = C.bolt; ctx.beginPath();
    ctx.moveTo(4, 10); ctx.lineTo(-12, 32); ctx.lineTo(0, 32); ctx.lineTo(-6, 48); ctx.lineTo(14, 24); ctx.lineTo(2, 24); ctx.lineTo(8, 10); ctx.closePath(); ctx.fill();
  },
  snow: (ctx) => {
    cloud(ctx, C.cloud, 0, -10);
    ctx.strokeStyle = C.snow; ctx.lineWidth = 3.5; ctx.lineCap = 'round';
    for (const [x, y] of [[-18, 32], [0, 40], [18, 32]]) {
      for (let i = 0; i < 3; i++) { const a = (i * Math.PI) / 3; ctx.beginPath(); ctx.moveTo(x - Math.cos(a) * 7, y - Math.sin(a) * 7); ctx.lineTo(x + Math.cos(a) * 7, y + Math.sin(a) * 7); ctx.stroke(); }
    }
  },
  sleet: (ctx) => {
    cloud(ctx, C.cloud, 0, -10);
    ctx.strokeStyle = C.rain; ctx.lineWidth = 6; ctx.lineCap = 'round';
    ctx.beginPath(); ctx.moveTo(-10, 22); ctx.lineTo(-16, 38); ctx.stroke();
    ctx.fillStyle = C.snow; for (const [x, y] of [[8, 28], [20, 40]]) { ctx.beginPath(); ctx.arc(x, y, 5, 0, Math.PI * 2); ctx.fill(); }
  },
  fog: (ctx) => {
    cloud(ctx, C.cloud, 0, -16, 0.85);
    ctx.strokeStyle = C.fog; ctx.lineWidth = 6; ctx.lineCap = 'round';
    for (const [y, a, b] of [[16, -34, 30], [28, -26, 36], [40, -36, 22]]) { ctx.beginPath(); ctx.moveTo(a, y); ctx.lineTo(b, y); ctx.stroke(); }
  },
  wind: (ctx) => {
    ctx.strokeStyle = C.cloud; ctx.lineWidth = 6; ctx.lineCap = 'round';
    for (const [y, len, curl] of [[-16, 50, 10], [2, 62, 12], [20, 40, 9]]) {
      ctx.beginPath(); ctx.moveTo(-36, y); ctx.lineTo(-36 + len - curl, y); ctx.arc(-36 + len - curl, y - curl, curl, Math.PI / 2, -Math.PI * 0.9, true); ctx.stroke();
    }
  },
};

/** Draw icon `kind` centred on (cx, cy), `size` pixels across. An unknown kind draws a cloud (never nothing). */
export function drawIcon(ctx, kind, cx, cy, size) {
  ctx.save();
  ctx.translate(cx, cy); ctx.scale(size / 100, size / 100);
  (SHAPES[kind] || SHAPES.cloud)(ctx);
  ctx.restore();
}
