// Complexity scoring constants (ported from architekton/classifier.py)
const BASE_SCORE = 0.5
const SIGNAL_WEIGHT = 0.12
const LONG_PROMPT_TOKENS = 400
const SHORT_PROMPT_TOKENS = 80
const LENGTH_WEIGHT = 0.15
const MAX_LENGTH_BONUS = 0.30
const SCAN_CHARS = 800
const THRESHOLDS = { light: 0.30, heavy: 0.65 }

const HEAVY = [
  /\barchitect\w*/i, /\bdesign\w*/i, /\brefactor\w*/i, /\brestructur\w*/i,
  /\breview\w*/i, /\baudit\w*/i, /\bdebug\w*/i, /\binvestigat\w*/i,
  /\broot cause\b/i, /\ball files\b/i, /\bacross the codebase\b/i,
  /\bmulti-file\b/i, /\bsecurity\b/i, /\bexploit\w*/i,
]
const LIGHT = [
  /\brename\w*/i, /\btypo\w*/i, /\bfix spelling\b/i, /\badd comment\w*/i,
  /\bformat(?:ting|ted)?\b/i, /\bwhat is\b/i, /\bshow me\b/i, /\blist\b/i,
  /\bgit status\b/i, /\brun tests\b/i, /\bsingle file\b/i, /\bone line\b/i,
  /\bcommit message\b/i,
]

function scorePrompt(text) {
  const tokens = Math.ceil(text.length / 4)
  let total = BASE_SCORE
  if (tokens > LONG_PROMPT_TOKENS) {
    total += Math.min(LENGTH_WEIGHT * Math.log2(tokens / LONG_PROMPT_TOKENS), MAX_LENGTH_BONUS)
  } else if (tokens < SHORT_PROMPT_TOKENS) {
    total -= LENGTH_WEIGHT
  }
  const head = text.slice(0, SCAN_CHARS)
  total += SIGNAL_WEIGHT * HEAVY.filter(re => re.test(head)).length
  total -= SIGNAL_WEIGHT * LIGHT.filter(re => re.test(head)).length
  return Math.round(Math.min(Math.max(total, 0), 1) * 100) / 100
}

function tierForScore(value) {
  if (value >= THRESHOLDS.heavy) return 'opus'
  if (value <= THRESHOLDS.light) return 'haiku'
  return 'sonnet'
}

function tierOfModel(model) {
  const m = (model || '').toLowerCase()
  for (const tier of ['opus', 'sonnet', 'haiku']) {
    if (m.includes(tier)) return tier
  }
  return null
}

export function register(on) {
  on('prompt.submit', async ($, e, next) => {
    try {
      const model = $.session.model()
      const currentTier = tierOfModel(model)
      if (currentTier === null) return next(e)

      const value = scorePrompt(e.text || '')
      const recommended = tierForScore(value)
      if (recommended === currentTier) return next(e)

      const context = `[architekton] Prompt complexity suggests ${recommended} (score ${value}). You are on ${model}. Switch: /model ${recommended}`
      return next({ ...e, context })
    } catch {
      return next(e)
    }
  })
}
