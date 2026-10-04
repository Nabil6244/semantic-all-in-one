// pakMap look: colours and geometry measured from the two reference videos
// (docs/pakmap/pakmap-editing-spec.md sections 16-17, docs/pakmap/phase0/pakmap.draft.json).
// All sizes are for a 1920x1080 frame and scale with the frame height.

export const REF_HEIGHT = 1080;

export const COLORS = {
  white: '#FFFFFF',
  panel: '#081320',
  subtitle: '#111111',
  yellow: '#FBE040',
  red: '#DF2721',
  blue: '#2978D8',
  cyan: '#3FC8E0',
  orange: '#F09030',
  text_dark: '#0A0A0A',
};

/** Chip colour roles (marker / zone / caption chips). */
export const ROLES = {
  dark: { bg: 'rgba(8,19,32,0.80)', fg: COLORS.white }, // default marker label (Reference 2: GARISSA · 163,000)
  neutral: { bg: COLORS.white, fg: COLORS.text_dark },
  featured: { bg: COLORS.yellow, fg: COLORS.text_dark },
  subject: { bg: COLORS.red, fg: COLORS.white },
  compare: { bg: COLORS.blue, fg: COLORS.white },
  stat: { bg: COLORS.panel, fg: COLORS.yellow },
};

/** Translucent region fills: role -> colour (Reference 1/2 sampled). Drawn at about 45 % over the satellite. */
export const FILL_ROLES = {
  primary: '#8A2A20', subject: '#DF2721', orange: '#D2641E', compare: '#4A7FB5', accent: '#7B4FC4',
  water: '#3FC8E0', featured: '#E6B83A', green: '#3E9E5B',
};

export const LINE_KINDS = {
  flow: { color: COLORS.orange, dash: null, arrow: true, width: 6 },
  river: { color: COLORS.cyan, dash: null, arrow: false, width: 5 },
  rail: { color: COLORS.white, dash: null, arrow: false, width: 4 },
  border_trace: { color: COLORS.yellow, dash: null, arrow: false, width: 5 },
  divide: { color: COLORS.yellow, dash: null, arrow: false, width: 5 },
  reference: { color: COLORS.yellow, dash: [22, 16], arrow: false, width: 3 },
  connector: { color: COLORS.yellow, dash: [18, 14], arrow: false, width: 4 },
};

export const FONT = { family: 'PakMapSans', weight: 800 };

/** Geometry in reference pixels (1080 p). */
export const GEOM = {
  margin: { left: 44, right: 63, top: 37, bottom: 66 },
  title: { x: 45, y: 37, h: 67, radius: 10, padX: 19, fontPx: 46 },
  subtitle: { x: 44, gap: 8, h: 39, radius: 8, padX: 15, fontPx: 21 },
  stat: { radius: 26, padX: 31, padTop: 28, gap: 24, padBottom: 26, numberPx: 86, subPx: 26, minW: 220 },
  caption: { radius: 16, padX: 30, padY: 32, fontPx: 63, lineGap: 16, subPx: 13, subGap: 12 },
  marker: { dot: 13, ring: 4, chipH: 52, chipPx: 34, padX: 14, radius: 8, offset: 27 },
  card: { border: 5, radius: 16, shadowBlur: 18, landscape: [420, 303], square: [300, 300], portrait: [260, 360], labelH: 42, labelPx: 28, labelGap: 6, labelPadX: 16, labelRadius: 8, margin: { left: 44, right: 63, top: 190, bottom: 66 } },
  strip: { maxWidth: 1520, gap: 16, gapWide: 31, maxCardW: 420, aspect: 1.4286, bottom: 94, minCards: 3, maxCards: 7 },
  sticker: { heightFrac: 0.42 },
  zone: { chipH: 52, chipPx: 34, padX: 18, radius: 8 },
  watermark: { fontPx: 22, right: 36, left: 36, bottom: 36, icon: 30 },
};

export const TIMING = {
  titlePop: 0.07,
  subtitleGrow: 0.27,
  wordSeconds: 0.067,
  chipIn: 0.28,
  chipOut: 0.3,
  statRamp: 0.6,
  lineDraw: 0.9,
  dotsReveal: 3.1,
  dotPx: 6,
  pointStagger: 0.045,
  markerPop: 0.22,
  cardIn: 0.17,
  cardOut: 0.45,
  cardStagger: 0.25,
  cardCrossfade: 0.5,
  stickerIn: 0.2,
  stickerOut: 0.5,
  dissolve: 0.5,
  clearBeat: 0.5,
};
