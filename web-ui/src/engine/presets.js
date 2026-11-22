/**
 * Caption style presets.
 *
 * Each preset describes palette, motion and background treatment consumed by
 * the renderer (engine/kinetype.js). `sug` is the suggested [bg1, bg2, accent]
 * triple applied when the preset is selected in the UI.
 *
 * The "guofeng" preset uses the traditional Chinese palette.
 */

export const PRESETS = {
  "meme-punch": {
    pal: ["#FFFFFF", "#FFFFFF", "#FFFFFF", "#FFFFFF", "#FFD84D", "#FF4D5E", "#4DA3FF", "#4CD964", "#FF6FB5"],
    acc: "#FFD84D", rot: 3.5, shake: 0.16, enter: "rand", flash: ["#FF2E63", "#00E5FF", "#7C4DFF", "#FFD400"],
    bg: "radial", dots: 0, noise: 0, glow: 0,
    sug: ["#20222e", "#0a0a0f", "#FFD84D"],
  },
  "beat-flash": {
    pal: ["#FFFFFF"], acc: "#FF2E63", rot: 5, shake: 0.22, enter: "rand",
    flash: ["#FF2E63", "#00E5FF", "#7C4DFF", "#FFD400"], bg: "radial", dots: 0, noise: 0, glow: 0,
    sug: ["#20222e", "#0a0a0f", "#FF2E63"],
  },
  "neon-terminal": {
    pal: ["#C8FFD4", "#7CFFB2", "#4CE0C8"], acc: "#E9FF70", rot: 1.2, shake: 0.05,
    enter: "type", flash: [], bg: "dots", dots: "#4CE0C8", noise: 0.08, glow: 16,
    sug: ["#04140c", "#010604", "#E9FF70"],
  },
  "sakura-pop": {
    pal: ["#3A3A46", "#FF6FA5", "#6FB3FF", "#63C9A8"], acc: "#FF4D8D", rot: 4.5, shake: 0.04,
    enter: "rise", flash: [], bg: "dots", dots: "#FF9EC4", noise: 0, glow: 0,
    sug: ["#fff5f7", "#ffe3ec", "#FF4D8D"],
  },
  "broadcast": {
    pal: ["#111111"], acc: "#E4002B", rot: 0, shake: 0, enter: "rise", flash: [],
    bg: "flat", dots: 0, noise: 0, glow: 0,
    sug: ["#ffffff", "#f2f2f2", "#E4002B"],
  },
  "retro-print": {
    pal: ["#1A1A1A", "#1A1A1A", "#1A1A1A", "#C0392B", "#1F4E79"], acc: "#C0392B", rot: 2, shake: 0.06,
    enter: "swing", flash: [], bg: "noise", dots: 0, noise: 0.16, glow: 0,
    sug: ["#f0e7d8", "#e3d5bd", "#C0392B"],
  },
  /* Traditional palette — silk-scroll green background, moon-white / reed-yellow text. */
  "guofeng": {
    pal: ["#eef7f2", "#eef7f2", "#eef7f2", "#dfc243", "#c04851", "#2bae85", "#1661ab", "#f0d695"],
    acc: "#dfc243", rot: 2.2, shake: 0.05, enter: "swing", flash: [],
    bg: "linear", dots: 0, noise: 0.05, glow: 0,
    sug: ["#223e36", "#141e1b", "#dfc243"],
  },
};
