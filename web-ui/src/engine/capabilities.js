/**
 * Device capability probe for the export pipeline.
 *
 * Browsers differ widely in what they can encode, so we ask the encoder
 * directly instead of sniffing the user agent (unreliable and easy to spoof).
 * The first answer is cached for the session — capability does not change
 * while the page is open.
 *
 * Tiers, fastest first:
 *   webcodecs-hw   WebCodecs + hardware H.264 — frame-exact, GPU encode.
 *   webcodecs-sw   WebCodecs + software H.264 — frame-exact, CPU encode.
 *   mediarecorder  Real-time capture — last resort, timing follows the clock.
 *   none           No encoder; export is unavailable.
 */

const PROBE_WIDTH = 1080
const PROBE_HEIGHT = 1920
const PROBE_BITRATE = 8_000_000
const PROBE_FPS = 30

/* Same order as the encoder picker: High profile first, Baseline as fallback. */
const CODEC_CANDIDATES = [
  ['avc1.640033', 'prefer-hardware'],
  ['avc1.640033', 'no-preference'],
  ['avc1.4d4028', 'prefer-hardware'],
  ['avc1.42001E', 'no-preference'],
]

/** @typedef {'webcodecs-hw' | 'webcodecs-sw' | 'mediarecorder' | 'none'} RenderTier */
/** @typedef {{ tier: RenderTier, label: string }} RenderCapability */

/** @type {Promise<RenderCapability> | null} */
let cached = null

/**
 * Probes the export pipeline once and returns the best usable tier.
 * @returns {Promise<RenderCapability>}
 */
export function probeRenderCapability() {
  if (!cached) cached = detect()
  return cached
}

/** @returns {RenderCapability} */
function fallbackCapability() {
  return typeof MediaRecorder === 'undefined'
    ? { tier: 'none', label: '不支持视频编码' }
    : { tier: 'mediarecorder', label: '兼容模式 · MediaRecorder' }
}

/** @returns {Promise<RenderCapability>} */
async function detect() {
  if (typeof VideoEncoder === 'undefined') return fallbackCapability()

  for (const [codec, hardwareAcceleration] of CODEC_CANDIDATES) {
    const config = {
      codec,
      width: PROBE_WIDTH,
      height: PROBE_HEIGHT,
      bitrate: PROBE_BITRATE,
      framerate: PROBE_FPS,
      latencyMode: 'quality',
      hardwareAcceleration,
    }
    try {
      const support = await VideoEncoder.isConfigSupported(config)
      if (!support.supported) continue
      const granted = support.config?.hardwareAcceleration ?? hardwareAcceleration
      return granted === 'prefer-hardware'
        ? { tier: 'webcodecs-hw', label: '硬件编码 · WebCodecs H.264' }
        : { tier: 'webcodecs-sw', label: '软件编码 · WebCodecs H.264' }
    } catch (_) {
      /* Unsupported config: try the next one. */
    }
  }
  return fallbackCapability()
}
