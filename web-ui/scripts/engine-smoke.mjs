// Engine port smoke test — pure functions only (no DOM): tokenize + parseScript.
// Mirrors web/smoke.js expectations for the parser.
import { tokenize, parseScript } from '../src/engine/kinetype.js'

let pass = 0, fail = 0
const eq = (name, a, b) => {
  const ok = JSON.stringify(a) === JSON.stringify(b)
  ok ? pass++ : fail++
  if (!ok) console.log(`FAIL ${name}\n  got      ${JSON.stringify(a)}\n  expected ${JSON.stringify(b)}`)
}

/* tokenize: plain text */
let t = tokenize('喂您好')
eq('plain text', t.map(x => x.t), ['喂您好'])

/* highlight [词] */
t = tokenize('[倒]了的鸭子')
eq('hl flag', t.map(x => !!(x.st && x.st.hl)), [true, false])
eq('hl text', t.map(x => x.t), ['倒', '了的鸭子'])

/* bold **词** */
t = tokenize('a **bold** b')
eq('bold flag', t.map(x => !!(x.st && x.st.bold)), [false, true, false])

/* style directive {color:...} */
t = tokenize('{color:#FFD84D}黄{/}字')
eq('directive colors', [t[0].st.color, t[1].st.color], ['#FFD84D', undefined])

/* nested + single-prop close {/color} */
t = tokenize('{color:red size:2}A{/color}B{/}')
eq('nested keep size', [t[0].st.color, t[0].st.size, t[1].st.color, t[1].st.size],
  ['red', 2, undefined, 2])

/* {转} and {转:-90} */
t = tokenize('{转}字')
eq('rot token', [!!t[0].rot, t[0].deg, t[1].t], [true, null, '字'])
t = tokenize('{转:-90}字')
eq('rot deg', [!!t[0].rot, t[0].deg], [true, -90])

/* escape \{ */
t = tokenize('\\{x\\}')
eq('escape', t.map(x => x.t), ['{x}'])

/* line break | */
t = tokenize('a|b')
eq('br', t.some(x => x.br), true)
eq('br keeps text', t.filter(x => x.t).map(x => x.t).join('|'), 'a|b')

/* parseScript: beats from lines */
const beats = parseScript('第一句，第二句。\n\n第三句！', 6, 13)
eq('beats count', beats.length, 2)
eq('beat 0 plain', beats[0].plain.includes('第一句'), true)
eq('beat indices', beats.map(b => b.index), [0, 1])

/* rotReq beats */
const beats2 = parseScript('甲\n\n{转}乙\n\n丙', 6, 13)
eq('rotReq flag', [!!beats2[1].rotReq, !!beats2[2].rotReq], [true, false])

/* duration clamped */
const beats3 = parseScript('短', 6, 13)
eq('min duration', beats3[0].dur >= 0.32, true)

console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
