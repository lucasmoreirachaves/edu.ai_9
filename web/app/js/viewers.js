/* EDU.AI – visualização dos materiais (compartilhada entre editor do professor e área do aluno) */
import { esc, html, raw } from './core.js';

/* ---------------------------------------------------------------- resumo / roteiro */
export const resumoView = (c) => html`<article class="documento">
  ${(c.sections || []).map((s) => html`<h3>${s.title}</h3>${String(s.body || '').split(/\n{2,}/).map((p) => html`<p>${p}</p>`)}`)}
  ${c.keywords?.length ? html`<div><p class="rotulo-pequeno" style="color:var(--texto-fraco);margin-bottom:6px">Palavras-chave</p><div class="palavras">${c.keywords.map((k) => html`<span class="tag tag--azul">${k}</span>`)}</div></div>` : ''}
</article>`;

/* ---------------------------------------------------------------- mapa mental (SVG) */
function wrap(text, max) {
  const words = String(text || '').split(/\s+/);
  const lines = [];
  let cur = '';
  for (const w of words) {
    if ((cur + ' ' + w).trim().length > max && cur) { lines.push(cur); cur = w; } else cur = (cur + ' ' + w).trim();
  }
  if (cur) lines.push(cur);
  return lines.slice(0, 4);
}

function node(x, y, w, text, { fill, stroke, color, bold, cls, data, max = 22 }) {
  const lines = wrap(text, max);
  const h = 19 * lines.length + 20;
  const t = lines.map((l, i) => `<tspan x="${x}" dy="${i ? 19 : 0}">${esc(l)}</tspan>`).join('');
  return { h, svg: `<g class="mn ${cls || ''}" ${data || ''} tabindex="0" role="button" aria-label="${esc(text)}"><rect x="${x - w / 2}" y="${y - h / 2}" width="${w}" height="${h}" rx="12" fill="${fill}" stroke="${stroke}" stroke-width="1.8"/><text x="${x}" y="${y - (lines.length - 1) * 9.5 + 6}" text-anchor="middle" font-size="16" font-weight="${bold ? 700 : 500}" fill="${color}">${t}</text></g>` };
}

/** sel = {b, c} (c = -1 para o ramo; b = -1 para o centro) */
export function mapaSvg(c, sel = null) {
  const brs = c.branches || [];
  const sides = [brs.map((b, i) => [b, i]).filter((_, i) => i % 2 === 0), brs.map((b, i) => [b, i]).filter((_, i) => i % 2 === 1)];
  const CH = 64, GAP = 26;
  const block = (b) => Math.max(1, b.children.length) * CH;
  const sideH = (s) => s.reduce((a, [b]) => a + block(b) + GAP, -GAP);
  const H = Math.max(380, Math.max(sideH(sides[0]), sideH(sides[1])) + 60);
  const W = 1240, cx = W / 2, cy = H / 2;
  const links = [], nodes = [];
  sides.forEach((side, k) => {
    const dir = k === 0 ? 1 : -1;
    let y = cy - sideH(side) / 2;
    for (const [b, bi] of side) {
      const bh = block(b);
      const by = y + bh / 2, bx = cx + dir * 255;
      const isSel = sel && sel.b === bi && sel.c === -1;
      const color = b.color || '#2563EB';
      links.push(`<path d="M${cx + dir * 105},${cy} C${cx + dir * 170},${cy} ${bx - dir * 160},${by} ${bx - dir * 95},${by}" fill="none" stroke="${color}" stroke-width="2.5" opacity=".7"/>`);
      b.children.forEach((ch, ci) => {
        const chy = y + ci * CH + CH / 2, chx = cx + dir * 490;
        links.push(`<path d="M${bx + dir * 95},${by} C${bx + dir * 135},${by} ${chx - dir * 150},${chy} ${chx - dir * 115},${chy}" fill="none" stroke="${color}" stroke-width="1.6" opacity=".55"/>`);
        nodes.push(node(chx, chy, 230, ch, { fill: '#FFFFFF', stroke: color, color: '#172033', cls: sel && sel.b === bi && sel.c === ci ? 'sel' : '', data: `data-b="${bi}" data-c="${ci}"`, max: 24 }).svg);
      });
      nodes.push(node(bx, by, 190, b.label, { fill: color, stroke: color, color: '#FFFFFF', bold: true, cls: isSel ? 'sel' : '', data: `data-b="${bi}" data-c="-1"`, max: 20 }).svg);
      y += bh + GAP;
    }
  });
  nodes.push(node(cx, cy, 210, c.center, { fill: '#172033', stroke: '#172033', color: '#FFFFFF', bold: true, cls: sel && sel.b === -1 ? 'sel' : '', data: 'data-b="-1" data-c="-1"', max: 22 }).svg);
  return raw(`<div style="overflow-x:auto"><svg class="mapa-svg" viewBox="0 0 ${W} ${H}" style="min-width:720px" role="group" aria-label="Mapa mental: ${esc(c.center)}">${links.join('')}${nodes.join('')}</svg></div>`);
}

export const mapaArvore = (c) => html`<ul class="mapa-arvore"><li><strong>${c.center}</strong><ul>${(c.branches || []).map((b) => html`<li><span style="color:${b.color}">●</span> <strong>${b.label}</strong>${b.children.length ? html`<ul>${b.children.map((x) => html`<li>${x}</li>`)}</ul>` : ''}</li>`)}</ul></li></ul>`;

/* ---------------------------------------------------------------- flashcards */
export const flashcard = (card, i, total) => html`<button type="button" class="flashcard" data-flip aria-label="Virar cartão">
  <div class="flashcard__interno"><div class="flashcard__face"><small>Cartão ${i + 1} de ${total} · clique para virar</small>${card.front}</div>
  <div class="flashcard__face flashcard__face--verso"><small>Resposta</small>${card.back}</div></div></button>`;

export function bindFlip(root) {
  root.querySelectorAll('[data-flip]').forEach((c) => c.addEventListener('click', () => c.classList.toggle('virado')));
}

/* ---------------------------------------------------------------- glossário */
export const glossarioView = (c) => html`<dl class="glossario">${(c.terms || []).map((t, i) => html`<div class="glossario__item" data-termo="${t.term.toLowerCase()}">
  <dt>${t.term}</dt><dd data-def="${i}"><span>${t.definition}</span>${t.example ? html`<small><strong>Exemplo:</strong> ${t.example}</small>` : ''}</dd></div>`)}</dl>`;

/* ---------------------------------------------------------------- questões (prévia do professor, com gabarito) */
export const questoesPreview = (c) => html`<div class="pilha">${(c.questions || []).map((q, i) => html`<div class="questao">
  <div class="linha linha--entre"><span class="tag tag--cinza">Questão ${i + 1} · ${q.kind === 'discursiva' ? 'Discursiva' : 'Objetiva'}</span><span class="texto-fraco">${{ facil: 'Fácil', media: 'Média', dificil: 'Difícil' }[q.difficulty] || ''}</span></div>
  <p class="questao__enunciado">${q.statement}</p>
  ${q.kind === 'discursiva' ? html`<div class="resposta-aluno"><strong>Resposta esperada:</strong> ${q.expected}</div>`
    : html`<div class="alternativas">${q.options.map((o, j) => html`<div class="alternativa ${j === q.answer ? 'alternativa--correta' : ''}"><strong>${'ABCDE'[j]})</strong> ${o}</div>`)}</div>`}
  ${q.explanation ? html`<p class="texto-fraco"><strong>Explicação:</strong> ${q.explanation}</p>` : ''}</div>`)}</div>`;
