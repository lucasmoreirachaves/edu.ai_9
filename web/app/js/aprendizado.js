/* EDU.AI – Estúdio de aprendizado gamificado (aluno e professor)
   O aluno escolhe o que quer aprender e a IA monta jogos com o conteúdo; o professor cria jogos para
   as turmas e acompanha o aprendizado de cada aluno. Motores: memória, quiz relâmpago (estilo Kahoot),
   verdadeiro ou falso, completar frases, adivinhar o conceito e desafios de programação. */
import {
  S, ago, api, aviso, bindTabs, busy, confirmar, empty, esc, fmtDate, fmtDateTime, go, header, html, icon, kpi, loading, onLeave,
  page, pad2, progress, raw, route, tabs, tag, toast,
} from './core.js';

const R = { role: ['aluno', 'professor'] };
const TIPOS = {
  memoria: ['Jogo da memória', 'Encontre os pares de conceito e definição', 'cartas'],
  quiz: ['Quiz relâmpago', 'Perguntas com tempo, estilo Kahoot: quanto mais rápido, mais pontos', 'jogo'],
  verdadeiro_falso: ['Verdadeiro ou falso', 'Decida rápido se a afirmação está certa', 'check'],
  completar: ['Complete a frase', 'Escolha a palavra que falta', 'editar'],
  adivinhacao: ['Adivinhe o conceito', 'Descubra a resposta com o mínimo de dicas', 'questao'],
  programacao: ['Desafio de programação', 'Complete o código, preveja a saída ou ache o erro', 'conteudo'],
};
const cardTipo = (k) => html`<span class="tipo-icone jogo-tipo jogo-tipo--${k}">${icon(TIPOS[k]?.[2] || 'jogo')}</span>`;
const pct = (v) => (v == null ? '—' : `${Math.round(v)}%`);
const embaralhar = (a) => { const b = [...a]; for (let i = b.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [b[i], b[j]] = [b[j], b[i]]; } return b; };
const normal = (s) => String(s || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[^a-z0-9]+/g, ' ').trim();
function parecido(a, b) {
  a = normal(a); b = normal(b);
  if (!a || !b) return false;
  if (a === b) return true;
  if (Math.abs(a.length - b.length) > 1 || a.length < 5) return false;
  const d = Array.from({ length: a.length + 1 }, (_, i) => [i, ...Array(b.length).fill(0)]);
  for (let j = 1; j <= b.length; j++) d[0][j] = j;
  for (let i = 1; i <= a.length; i++) for (let j = 1; j <= b.length; j++) d[i][j] = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
  return d[a.length][b.length] <= 1;
}

/* ================================================================ estúdio */
route('aprender', async (_, q) => {
  page(loading());
  const prof = S.user.role === 'professor';
  const [op, jogos] = await Promise.all([api('/aprendizado/opcoes'), api('/aprendizado/jogos')]);
  const aba = q.aba || (prof ? 'alunos' : jogos.meus.length || jogos.turma.length ? 'meus' : 'criar');
  const abas = prof ? [['alunos', 'Aprendizado dos alunos'], ['criar', 'Criar jogos para a turma'], ['meus', `Meus jogos (${jogos.meus.length})`]]
    : [['criar', 'Criar jogos'], ['meus', `Meus jogos (${jogos.meus.length})`], ['turma', `Jogos da turma (${jogos.turma.length})`]];
  const el = page(html`${header('Estúdio de aprendizado gamificado', prof ? 'Crie jogos com IA para as suas turmas e acompanhe como cada aluno aprende jogando.'
    : 'Escolha o que você quer aprender e a IA transforma o conteúdo em jogos.')}
    ${prof ? '' : html`<div class="grade grade-4">${kpi('Pontos', jogos.pontos.toLocaleString('pt-BR'), 'somando todas as partidas')}${kpi('Partidas', pad2(jogos.partidas))}${kpi('Jogos criados', pad2(jogos.meus.length))}${kpi('Jogos da turma', pad2(jogos.turma.length))}</div>`}
    ${tabs(abas, aba)}<div id="aba"></div>`);
  const box = el.querySelector('#aba');
  const show = (t) => {
    history.replaceState(null, '', '#/aprender?aba=' + t);
    if (t === 'criar') return criar(box, op, prof);
    if (t === 'alunos') return alunosProf(box);
    const lista = t === 'turma' ? jogos.turma : jogos.meus;
    box.innerHTML = (lista.length ? html`<div class="grade grade-3">${lista.map((g) => html`<article class="cartao jogo-cartao">
      <div class="linha">${cardTipo(g.kind)}<div><strong>${g.title}</strong><div class="texto-fraco">${g.kind_label}${g.author ? ' · prof. ' + g.author : ''}${g.class_name ? ' · ' + g.class_name : ''}</div></div></div>
      ${prof ? html`<p class="texto-fraco">${g.total_plays} partida(s) de alunos · criado ${ago(g.created_at)}</p>` : html`${progress(g.best_pct || 0, (g.best_pct || 0) >= 70 ? 'verde' : 'amarelo')}<p class="texto-fraco">Melhor resultado: ${pct(g.best_pct)} · ${g.plays} partida(s)</p>`}
      <div class="linha linha--entre"><a class="btn btn--primario btn--p" href="#/aprender/jogo/${g.id}">${icon('jogo', 14)} ${prof ? 'Abrir' : 'Jogar'}</a>
        ${t === 'meus' ? html`<button class="btn btn--link texto-vermelho" data-apagar="${g.id}">Excluir</button>` : ''}</div></article>`)}</div>`
      : empty(t === 'turma' ? 'Nenhum jogo da turma ainda' : 'Nenhum jogo ainda', t === 'turma' ? 'Quando o professor publicar jogos, eles aparecem aqui.' : 'Crie jogos na aba ao lado.')).s;
    box.querySelectorAll('[data-apagar]').forEach((b) => {
      b.onclick = async () => {
        if (!(await confirmar('Excluir este jogo e as partidas dele?', { ok: 'Excluir', perigo: true }))) return;
        await api('/aprendizado/jogos/' + b.dataset.apagar, { method: 'DELETE' }); go('#/aprender?aba=meus');
      };
    });
  };
  bindTabs(el, show);
  show(aba);
}, R);

function criar(box, op, prof) {
  const fontes = prof ? [['documento', 'Documento da biblioteca'], ['material', 'Material'], ['texto', 'Texto colado'], ['tema', 'Só um tema']]
    : [['material', 'Material da escola'], ['texto', 'Colar um texto'], ['tema', 'Escrever um tema']];
  box.innerHTML = html`<form class="pilha" id="f" style="max-width:980px">
    <section class="cartao"><h2 class="cartao__titulo">1. O que ${prof ? 'os alunos vão' : 'você quer'} aprender?</h2>
      <div class="chips" role="radiogroup">${fontes.map(([k, l], i) => html`<label class="chip ${i === 0 ? 'ativo' : ''}"><input type="radio" name="fonte" value="${k}" ${i === 0 ? 'checked' : ''} hidden>${l}</label>`)}</div>
      <div data-fonte="documento" ${fontes[0][0] === 'documento' ? '' : 'hidden'}>${op.documents.length ? html`<select class="entrada" name="document_id">${op.documents.map((d) => html`<option value="${d.id}">${d.subject} · ${d.title}</option>`)}</select>` : aviso('Nenhum documento processado na biblioteca.', 'amarelo')}</div>
      <div data-fonte="material" ${fontes[0][0] === 'material' ? '' : 'hidden'}>${op.materials.length ? html`<select class="entrada" name="material_id">${op.materials.map((m) => html`<option value="${m.id}">${m.subject} · ${m.title}</option>`)}</select>` : aviso('Nenhum material disponível ainda.', 'amarelo')}</div>
      <div data-fonte="texto" hidden><textarea class="entrada" name="text" rows="6" maxlength="40000" placeholder="Cole aqui o texto, as anotações da aula ou o resumo que você quer estudar…"></textarea></div>
      <div data-fonte="tema" hidden><input class="entrada" name="topic" maxlength="200" placeholder="Ex.: Revolução Francesa, frações, fotossíntese, laços de repetição em Python"></div>
      <div class="campos-2"><label class="campo"><span>Título (opcional)</span><input class="entrada" name="title" maxlength="120"></label>
      <label class="campo"><span>Nível (opcional)</span><input class="entrada" name="level" maxlength="80" placeholder="${S.user.grade || 'Ex.: 9º ano, ensino médio'}"></label></div>
    </section>
    <section class="cartao"><h2 class="cartao__titulo">2. Escolha os jogos</h2>
      <div class="grade grade-3">${Object.entries(TIPOS).map(([k, [t, d]], i) => html`<label class="opcao"><input type="checkbox" name="kind" value="${k}" ${i < 3 ? 'checked' : ''}>${cardTipo(k)}<strong>${t}</strong><small>${d}</small></label>`)}</div>
      ${prof ? html`<label class="campo"><span>Publicar para a turma</span><select class="entrada" name="class_id"><option value="">Não publicar agora (só eu vejo)</option>${op.classes.map((c) => html`<option value="${c.id}">${c.name}</option>`)}</select></label>` : ''}
    </section>
    <div class="linha linha--fim"><button class="btn btn--primario btn--g" type="submit">${icon('ia', 16)} Criar jogos com IA</button></div>
    <div id="progresso"></div></form>`.s;
  const f = box.querySelector('#f');
  f.querySelectorAll('[name=fonte]').forEach((r) => r.addEventListener('change', () => {
    f.querySelectorAll('.chips .chip').forEach((c) => c.classList.toggle('ativo', c.contains(r) && r.checked));
    f.querySelectorAll('[data-fonte]').forEach((d) => { d.hidden = d.dataset.fonte !== r.value; });
  }));
  f.addEventListener('submit', (e) => {
    e.preventDefault();
    const fonte = f.querySelector('[name=fonte]:checked').value;
    const kinds = [...f.querySelectorAll('[name=kind]:checked')].map((c) => c.value);
    if (!kinds.length) return toast('Escolha pelo menos um jogo', 'erro');
    const base = { title: f.title.value, level: f.level.value, class_id: f.class_id?.value ? Number(f.class_id.value) : null };
    if (fonte === 'material') base.material_id = Number(f.material_id?.value) || null;
    if (fonte === 'documento') base.document_id = Number(f.document_id?.value) || null;
    if (fonte === 'texto') base.text = f.text.value;
    if (fonte === 'tema') base.topic = f.topic.value;
    if ((fonte === 'material' && !base.material_id) || (fonte === 'documento' && !base.document_id) || (fonte === 'texto' && base.text.trim().length < 20) || (fonte === 'tema' && base.topic.trim().length < 3)) {
      return toast(fonte === 'texto' ? 'Cole um texto um pouco maior' : 'Escolha o conteúdo', 'erro');
    }
    const prog = box.querySelector('#progresso');
    busy(f.querySelector('[type=submit]'), async () => {
      prog.innerHTML = html`<section class="cartao"><h2 class="cartao__titulo">Criando ${kinds.length} jogo(s)…</h2><ul class="lista-simples">${kinds.map((k) => html`<li data-k="${k}"><span>${TIPOS[k][0]}</span><span class="texto-fraco"><span class="spinner spinner--p"></span> na fila</span></li>`)}</ul><p class="texto-fraco">A IA lê o conteúdo e monta cada jogo: pode levar alguns segundos por jogo.</p></section>`.s;
      const criados = [];
      for (const k of kinds) {
        const li = prog.querySelector(`[data-k="${k}"] span:last-child`);
        li.innerHTML = '<span class="spinner spinner--p"></span> criando…';
        try {
          const g = await api('/aprendizado/gerar', { method: 'POST', body: { ...base, kind: k } });
          criados.push(g);
          li.innerHTML = html`<a class="btn btn--primario btn--p" href="#/aprender/jogo/${g.id}">${prof ? 'Abrir' : 'Jogar'}</a>${g.content._aviso ? html` <span class="tag tag--amarelo" title="${g.content._aviso}">modo simplificado</span>` : ''}`.s;
        } catch (err) { li.innerHTML = html`<span class="texto-vermelho">${err.message}</span>`.s; }
      }
      if (criados.length) toast(`${criados.length} jogo(s) pronto(s)!`);
    });
  });
}

/* ================================================================ professor: aprendizado dos alunos */
async function alunosProf(box, turma = '') {
  box.innerHTML = loading().s;
  const d = await api('/aprendizado/professor/alunos' + (turma ? '?class_id=' + turma : ''));
  const ativos = d.students.filter((s) => s.plays);
  box.innerHTML = html`<div class="grade grade-4">${kpi('Alunos', pad2(d.students.length))}${kpi('Jogando', pad2(ativos.length), 'com pelo menos 1 partida')}
      ${kpi('Partidas', pad2(d.students.reduce((s, a) => s + a.plays, 0)))}${kpi('Acerto médio', pct(ativos.length ? ativos.reduce((s, a) => s + (a.avg_pct || 0), 0) / ativos.length : null))}</div>
    <div class="filtros"><select class="entrada" id="ft" style="max-width:260px"><option value="">Todas as minhas turmas</option>${d.classes.map((c) => html`<option value="${c.id}" ${String(c.id) === String(turma) ? 'selected' : ''}>${c.name}</option>`)}</select></div>
    ${d.students.length ? html`<div class="tabela-caixa"><table class="tabela"><thead><tr><th>Aluno</th><th>Turma</th><th>Jogos criados</th><th>Partidas</th><th>Acerto médio</th><th>Última partida</th><th></th></tr></thead><tbody>
      ${d.students.map((s) => html`<tr><td><strong style="font-weight:600">${s.name}</strong></td><td>${s.classes}</td><td>${s.games_created}</td><td>${s.plays}</td>
        <td>${s.avg_pct == null ? '—' : html`<span class="tag tag--${s.avg_pct >= 70 ? 'verde' : s.avg_pct >= 50 ? 'amarelo' : 'vermelho'}">${pct(s.avg_pct)}</span>`}</td>
        <td>${s.last_play ? ago(s.last_play) : '—'}</td><td><a class="btn btn--contorno btn--p" href="#/aprender/aluno/${s.id}">Ver aprendizado</a></td></tr>`)}</tbody></table></div>`
    : empty('Nenhum aluno nas suas turmas')}
    <section class="cartao"><h2 class="cartao__titulo">Jogos que publiquei para as turmas</h2>
      ${d.class_games.length ? html`<ul class="lista-simples">${d.class_games.map((g) => html`<li><span><a href="#/aprender/jogo/${g.id}"><strong>${g.title}</strong></a><br><span class="texto-fraco">${g.kind_label} · ${g.class_name}</span></span><span>${g.players} aluno(s) · ${pct(g.avg_pct)}</span></li>`)}</ul>`
    : html`<p class="texto-fraco">Nenhum jogo publicado. Crie na aba “Criar jogos para a turma”.</p>`}</section>`.s;
  box.querySelector('#ft').onchange = (e) => alunosProf(box, e.target.value);
}

route('aprender/aluno/:id', async ({ id }) => {
  page(loading());
  const d = await api('/aprendizado/professor/alunos/' + id);
  const el = page(html`<a href="#/aprender?aba=alunos" class="link-sutil">← Aprendizado dos alunos</a>
    ${header(d.student.name, `Jogos de aprendizado: ${d.plays.length} partida(s) · ${d.games.length} jogo(s) criados pelo próprio aluno`)}
    <div class="grade grade-2" style="align-items:start">
      <section class="cartao"><h2 class="cartao__titulo">Desempenho por tipo de jogo</h2>
        ${d.by_kind.length ? html`<div class="barras-h">${d.by_kind.map((k) => html`<div class="barras-h__linha"><span>${k.kind} <small class="texto-fraco">(${k.plays})</small></span>${progress(k.avg_pct || 0, (k.avg_pct || 0) >= 70 ? 'verde' : (k.avg_pct || 0) >= 50 ? 'amarelo' : 'vermelho')}<strong>${pct(k.avg_pct)}</strong></div>`)}</div>` : empty('Nenhuma partida ainda')}</section>
      <section class="cartao"><h2 class="cartao__titulo">Onde mais errou</h2>
        ${d.top_errors.length ? html`<ul class="lista-simples">${d.top_errors.map((e) => html`<li><span>${e.q}</span><span class="tag tag--vermelho">${e.n}×</span></li>`)}</ul>` : html`<p class="texto-fraco">Sem erros registrados.</p>`}</section>
    </div>
    <section class="cartao"><h2 class="cartao__titulo">O que o aluno escolheu estudar</h2>
      ${d.games.length ? html`<ul class="lista-simples">${d.games.map((g) => html`<li><span><a href="#/aprender/jogo/${g.id}">${g.title}</a><br><span class="texto-fraco">${g.kind_label}${g.topic ? ' · tema: ' + g.topic : ''}</span></span><span class="texto-fraco">${fmtDate(g.created_at)}</span></li>`)}</ul>` : html`<p class="texto-fraco">O aluno ainda não criou jogos.</p>`}</section>
    <section class="cartao"><h2 class="cartao__titulo">Partidas</h2>
      ${d.plays.length ? html`<div class="tabela-caixa"><table class="tabela"><thead><tr><th>Jogo</th><th>Origem</th><th>Acertos</th><th>Pontos</th><th>Tempo</th><th>Quando</th><th></th></tr></thead><tbody>
        ${d.plays.map((p, i) => html`<tr><td><strong style="font-weight:600">${p.title}</strong><div class="texto-fraco">${p.kind_label}</div></td><td>${p.origin === 'aluno' ? 'Criado pelo aluno' : 'Jogo da turma'}</td>
          <td>${p.correct}/${p.total} ${p.pct != null ? html`<span class="tag tag--${p.pct >= 70 ? 'verde' : p.pct >= 50 ? 'amarelo' : 'vermelho'}">${p.pct}%</span>` : ''}</td><td>${p.score}/${p.max_score}</td>
          <td>${Math.round(p.duration_ms / 1000)} s</td><td>${fmtDateTime(p.created_at)}</td><td>${p.details.some((x) => !x.ok) ? html`<button class="btn btn--link" data-det="${i}">Ver erros</button>` : ''}</td></tr>`)}</tbody></table></div>`
    : empty('Nenhuma partida ainda')}</section>`);
  el.querySelectorAll('[data-det]').forEach((b) => {
    b.onclick = () => {
      const p = d.plays[Number(b.dataset.det)];
      const tr = b.closest('tr');
      if (tr.nextElementSibling?.classList.contains('detalhe-erros')) { tr.nextElementSibling.remove(); return; }
      tr.insertAdjacentHTML('afterend', html`<tr class="detalhe-erros"><td colspan="7"><ul class="lista-simples">${p.details.filter((x) => !x.ok).map((x) => html`<li><span>${x.q}</span><span><span class="texto-vermelho">${x.answer || '(sem resposta)'}</span> → <strong>${x.right}</strong></span></li>`)}</ul></td></tr>`.s);
    };
  });
}, { role: 'professor' });

/* ================================================================ partida */
route('aprender/jogo/:id', async ({ id }) => {
  page(loading());
  const g = await api('/aprendizado/jogos/' + id);
  const prof = S.user.role === 'professor';
  const dono = g.user_id === S.user.id;
  const el = page(html`<a href="#/aprender?aba=${prof ? (dono ? 'meus' : 'alunos') : g.class_id && !dono ? 'turma' : 'meus'}" class="link-sutil">← Estúdio</a>
    ${header(g.title, html`${g.kind_label}${g.ai_source?.startsWith('simulada') ? ' · modo simplificado (sem IA)' : ''}`,
    prof && dono ? html`<label class="linha" style="gap:8px"><span class="texto-fraco">Turma:</span><select class="entrada" data-publicar style="max-width:200px"><option value="">Não publicado</option></select></label>` : '')}
    <div class="grade grade-lateral" style="align-items:start"><div id="palco" class="palco-jogo"></div>
      <aside class="pilha"><section class="cartao"><h2 class="cartao__titulo">${cardTipo(g.kind)} ${TIPOS[g.kind][0]}</h2><p class="texto-suave">${TIPOS[g.kind][1]}.</p>
        ${g.content._aviso ? aviso(g.content._aviso, 'amarelo') : ''}</section>
        ${g.ranking.length ? html`<section class="cartao"><h2 class="cartao__titulo">${icon('trofeu', 16)} Ranking da turma</h2><ol class="ranking">${g.ranking.map((r) => html`<li><span>${r.name}</span><strong>${r.score}</strong></li>`)}</ol></section>` : ''}</aside></div>`);
  if (prof && dono) {
    const sel = el.querySelector('[data-publicar]');
    api('/aprendizado/opcoes').then((op) => {
      sel.innerHTML = html`<option value="">Não publicado</option>${op.classes.map((c) => html`<option value="${c.id}" ${c.id === g.class_id ? 'selected' : ''}>${c.name}</option>`)}`.s;
    });
    sel.onchange = async () => { await api(`/aprendizado/jogos/${id}/publicar`, { method: 'PUT', body: { class_id: sel.value ? Number(sel.value) : null } }); toast(sel.value ? 'Jogo publicado para a turma' : 'Jogo despublicado'); };
  }
  const palco = el.querySelector('#palco');
  const inicio = () => {
    palco.innerHTML = html`<div class="jogo-inicio">${cardTipo(g.kind)}<h2>${g.title}</h2><p class="texto-suave">${TIPOS[g.kind][1]}.</p>
      <button class="btn btn--primario btn--g" data-comecar>${icon('jogo', 18)} ${g.can_play ? 'Começar' : 'Pré-visualizar'}</button></div>`.s;
    palco.querySelector('[data-comecar]').onclick = () => {
      const t0 = Date.now();
      MOTORES[g.kind](palco, g.content, async (res) => {
        res.duration_ms = Date.now() - t0;
        let rec = null;
        if (g.can_play) { try { rec = await api(`/aprendizado/jogos/${id}/partidas`, { method: 'POST', body: res }); } catch (e) { toast(e.message, 'erro'); } }
        fim(palco, res, rec, inicio);
      });
    };
  };
  inicio();
}, R);

function fim(palco, r, rec, denovo) {
  const p = r.total ? Math.round((100 * r.correct) / r.total) : 0;
  const erros = r.details.filter((d) => !d.ok);
  palco.innerHTML = html`<div class="jogo-fim">
    <span class="jogo-fim__emoji">${p >= 90 ? '🏆' : p >= 70 ? '🎉' : p >= 50 ? '💪' : '📚'}</span>
    <h2>${p >= 90 ? 'Incrível!' : p >= 70 ? 'Muito bem!' : p >= 50 ? 'Bom trabalho!' : 'Continue praticando!'}</h2>
    <div class="grade grade-3">${kpi('Pontos', r.score.toLocaleString('pt-BR'), rec?.record ? 'novo recorde!' : rec ? `recorde: ${rec.best}` : '', rec?.record ? 'verde' : '')}${kpi('Acertos', `${r.correct}/${r.total}`, `${p}%`)}${kpi('Tempo', `${Math.round(r.duration_ms / 1000)} s`)}</div>
    ${erros.length ? html`<section class="cartao" style="text-align:left"><h3 class="cartao__titulo">Revise o que errou</h3><ul class="lista-simples">${erros.map((e) => html`<li><span>${e.q}</span><span>${e.answer ? html`<span class="texto-vermelho">${e.answer}</span> → ` : ''}<strong>${e.right}</strong></span></li>`)}</ul></section>` : ''}
    <div class="linha" style="justify-content:center"><button class="btn btn--primario" data-denovo>Jogar de novo</button><a class="btn btn--contorno" href="#/aprender">Voltar ao estúdio</a></div></div>`.s;
  palco.querySelector('[data-denovo]').onclick = denovo;
}

/* ---------------------------------------------------------------- utilitários dos motores */
function cronometro(palco, segundos, onFim) {
  const barra = palco.querySelector('.jogo-tempo span');
  const t0 = Date.now();
  let parado = false;
  const tick = () => {
    if (parado || !barra.isConnected) return;
    const resta = Math.max(0, segundos * 1000 - (Date.now() - t0));
    barra.style.width = `${(100 * resta) / (segundos * 1000)}%`;
    barra.parentElement.classList.toggle('jogo-tempo--fim', resta < segundos * 300);
    if (resta <= 0) { parado = true; onFim(); return; }
    requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
  onLeave(() => { parado = true; });
  return { parar: () => { parado = true; return Math.max(0, segundos * 1000 - (Date.now() - t0)) / (segundos * 1000); } };
}
const placar = (i, n, pts) => html`<div class="jogo-placar"><span>${i + 1} de ${n}</span><strong>${pts.toLocaleString('pt-BR')} pts</strong></div>`;

/** Motor genérico de perguntas: cada item tem enunciado, opções e a resposta certa. */
function rodadas(palco, itens, { segundos = 0, pontos = 100, bonusTempo = false, render, opcoes, certa, texto, explicacao }, onFim) {
  let i = 0, score = 0, correct = 0;
  const details = [];
  const max = itens.length * (bonusTempo ? pontos * 2 : pontos);
  const proxima = () => {
    if (i >= itens.length) return onFim({ score, max_score: max, correct, total: itens.length, details });
    const it = itens[i];
    const ops = opcoes(it);
    palco.innerHTML = html`${placar(i, itens.length, score)}${segundos ? raw('<div class="jogo-tempo"><span></span></div>') : ''}
      <div class="jogo-pergunta">${render(it)}</div>
      <div class="jogo-opcoes ${ops.length === 2 ? 'jogo-opcoes--2' : ''}">${ops.map((o, k) => html`<button class="resposta resposta--${'abcd'[k % 4]}" data-k="${k}"><span class="resposta__letra">${o.icone || 'ABCD'[k % 4]}</span><span>${o.label}</span></button>`)}</div>
      <div class="jogo-feedback" hidden></div>`.s;
    let resp = false;
    const timer = segundos ? cronometro(palco, segundos, () => responder(null)) : null;
    function responder(k) {
      if (resp) return;
      resp = true;
      const frac = timer ? timer.parar() : 0;
      const ok = k !== null && certa(it, k);
      const ganho = ok ? (bonusTempo ? pontos + Math.round(pontos * frac) : pontos) : 0;
      score += ganho;
      if (ok) correct++;
      details.push({ q: texto(it).slice(0, 280), ok, answer: k === null ? '(tempo esgotado)' : ops[k].label, right: ops.find((_, x) => certa(it, x))?.label || '' });
      palco.querySelectorAll('[data-k]').forEach((b) => {
        b.disabled = true;
        const x = Number(b.dataset.k);
        b.classList.toggle('resposta--certa', certa(it, x));
        b.classList.toggle('resposta--apagada', !certa(it, x) && x !== k);
      });
      const fb = palco.querySelector('.jogo-feedback');
      fb.hidden = false;
      fb.className = 'jogo-feedback ' + (ok ? 'jogo-feedback--ok' : 'jogo-feedback--erro');
      fb.innerHTML = html`<strong>${ok ? `Certo! +${ganho}` : k === null ? 'Tempo esgotado!' : 'Não foi dessa vez.'}</strong>${explicacao(it) ? html`<p>${explicacao(it)}</p>` : ''}
        <button class="btn btn--escuro" data-prox>${i + 1 < itens.length ? 'Próxima' : 'Ver resultado'}</button>`.s;
      const b = fb.querySelector('[data-prox]');
      b.focus();
      b.onclick = () => { i++; proxima(); };
    }
    palco.querySelectorAll('[data-k]').forEach((b) => { b.onclick = () => responder(Number(b.dataset.k)); });
  };
  proxima();
}

/* ---------------------------------------------------------------- motores */
const MOTORES = {
  quiz: (palco, c, onFim) => rodadas(palco, embaralhar(c.questions), {
    segundos: 20, pontos: 500, bonusTempo: true, render: (q) => html`<h2>${q.question}</h2>`,
    opcoes: (q) => q.options.map((o, k) => ({ label: o, icone: ['▲', '◆', '●', '■'][k % 4] })), certa: (q, k) => k === q.answer,
    texto: (q) => q.question, explicacao: (q) => q.explanation,
  }, onFim),

  verdadeiro_falso: (palco, c, onFim) => rodadas(palco, embaralhar(c.statements), {
    segundos: 15, pontos: 100, bonusTempo: true, render: (s) => html`<p class="jogo-afirmacao">${s.statement}</p>`,
    opcoes: () => [{ label: 'Verdadeiro', icone: '✔' }, { label: 'Falso', icone: '✘' }], certa: (s, k) => (k === 0) === s.answer,
    texto: (s) => s.statement, explicacao: (s) => s.explanation,
  }, onFim),

  completar: (palco, c, onFim) => rodadas(palco, embaralhar(c.sentences), {
    pontos: 100, render: (s) => html`<p class="jogo-afirmacao">${raw(esc(s.text).replace(/_{3,}/, '<span class="lacuna">?</span>'))}</p>`,
    opcoes: (s) => s.options.map((o) => ({ label: o })), certa: (s, k) => s.options[k] === s.answer,
    texto: (s) => s.text, explicacao: (s) => s.explanation,
  }, onFim),

  programacao: (palco, c, onFim) => rodadas(palco, c.challenges, {
    segundos: 0, pontos: 150,
    render: (ch) => html`<p class="texto-fraco">${c.language}</p><h2>${ch.prompt}</h2><pre class="jogo-codigo"><code>${raw(esc(ch.code).replace(/_{3,}/g, '<mark>___</mark>'))}</code></pre>`,
    opcoes: (ch) => ch.options.map((o) => ({ label: o })), certa: (ch, k) => k === ch.answer,
    texto: (ch) => `${ch.prompt} ${ch.code.split('\n')[0]}`, explicacao: (ch) => ch.explanation,
  }, onFim),

  memoria: (palco, c, onFim) => {
    const pares = c.pairs.slice(0, 8);
    const cartas = embaralhar(pares.flatMap((p, i) => [{ par: i, txt: p.term, tipo: 'termo' }, { par: i, txt: p.definition, tipo: 'def' }]));
    const erros = new Set();
    let abertas = [], achados = 0, jogadas = 0, travado = false;
    palco.innerHTML = html`<div class="jogo-placar"><span data-info>0 de ${pares.length} pares</span><strong data-jog>0 jogadas</strong></div>
      <div class="mem-grade">${cartas.map((x, k) => html`<button class="mem-carta" data-k="${k}" aria-label="Carta ${k + 1}"><span class="mem-carta__frente">${icon('cartas', 22)}</span><span class="mem-carta__verso mem-carta__verso--${x.tipo}">${x.txt}</span></button>`)}</div>`.s;
    palco.querySelectorAll('[data-k]').forEach((b) => {
      b.onclick = () => {
        const k = Number(b.dataset.k);
        if (travado || b.classList.contains('virada') || b.classList.contains('achada')) return;
        b.classList.add('virada');
        abertas.push(k);
        if (abertas.length < 2) return;
        jogadas++;
        palco.querySelector('[data-jog]').textContent = `${jogadas} jogadas`;
        const [a, bb] = abertas.map((x) => cartas[x]);
        const els = abertas.map((x) => palco.querySelector(`[data-k="${x}"]`));
        abertas = [];
        if (a.par === bb.par && a.tipo !== bb.tipo) {
          els.forEach((e) => e.classList.add('achada'));
          achados++;
          palco.querySelector('[data-info]').textContent = `${achados} de ${pares.length} pares`;
          if (achados === pares.length) {
            const score = Math.max(pares.length * 20, pares.length * 100 - (jogadas - pares.length) * 15);
            setTimeout(() => onFim({ score, max_score: pares.length * 100, correct: pares.length - erros.size, total: pares.length,
              details: pares.map((p, i) => ({ q: p.term, ok: !erros.has(i), answer: erros.has(i) ? 'precisou de mais tentativas' : '', right: p.definition })) }), 600);
          }
        } else {
          erros.add(a.par); erros.add(bb.par);
          travado = true;
          setTimeout(() => { els.forEach((e) => e.classList.remove('virada')); travado = false; }, 1100);
        }
      };
    });
  },

  adivinhacao: (palco, c, onFim) => {
    const itens = embaralhar(c.riddles);
    let i = 0, score = 0, correct = 0;
    const details = [];
    const proxima = () => {
      if (i >= itens.length) return onFim({ score, max_score: itens.length * 100, correct, total: itens.length, details });
      const r = itens[i];
      let dicas = 1, tentativas = 0;
      const render = () => {
        palco.innerHTML = html`${placar(i, itens.length, score)}
          <div class="jogo-pergunta"><span class="tag tag--azul">${r.category}</span><h2>O que é? <small class="texto-fraco">(${r.answer.length} letras)</small></h2>
          <ol class="jogo-dicas">${r.hints.slice(0, dicas).map((h) => html`<li>${h}</li>`)}</ol></div>
          <form class="linha" id="fg"><input class="entrada" name="g" autocomplete="off" placeholder="Sua resposta…" style="flex:1" required>
            <button class="btn btn--primario">Responder</button></form>
          <div class="linha" style="margin-top:12px">${dicas < r.hints.length ? html`<button class="btn btn--contorno" data-dica>Mais uma dica (−20 pts)</button>` : ''}<button class="btn btn--link" data-desisto>Desistir</button>
            <span class="texto-fraco">Vale ${Math.max(20, 100 - (dicas - 1) * 20)} pts${tentativas ? ` · ${tentativas} tentativa(s)` : ''}</span></div>
          <div class="jogo-feedback" hidden></div>`.s;
        const inp = palco.querySelector('[name=g]');
        inp.focus();
        palco.querySelector('[data-dica]')?.addEventListener('click', () => { dicas++; render(); });
        palco.querySelector('[data-desisto]').onclick = () => fimRodada(false, '');
        palco.querySelector('#fg').addEventListener('submit', (e) => {
          e.preventDefault();
          tentativas++;
          if (parecido(inp.value, r.answer)) return fimRodada(true, inp.value);
          if (tentativas >= 3) return fimRodada(false, inp.value);
          inp.value = ''; inp.classList.add('tremer'); setTimeout(() => inp.classList.remove('tremer'), 400);
          toast(`Ainda não… (${3 - tentativas} tentativa(s) restante(s))`, 'erro');
          if (dicas < r.hints.length) { dicas++; render(); }
        });
      };
      const fimRodada = (ok, resposta) => {
        const ganho = ok ? Math.max(20, 100 - (dicas - 1) * 20) : 0;
        score += ganho;
        if (ok) correct++;
        details.push({ q: `${r.category}: ${r.hints[0]}`.slice(0, 280), ok, answer: resposta, right: r.answer });
        const fb = palco.querySelector('.jogo-feedback');
        palco.querySelector('#fg').remove();
        fb.hidden = false;
        fb.className = 'jogo-feedback ' + (ok ? 'jogo-feedback--ok' : 'jogo-feedback--erro');
        fb.innerHTML = html`<strong>${ok ? `Acertou! +${ganho}` : 'A resposta era:'}</strong><p style="font-size:20px;font-weight:700">${r.answer}</p>
          <button class="btn btn--escuro" data-prox>${i + 1 < itens.length ? 'Próximo' : 'Ver resultado'}</button>`.s;
        fb.querySelector('[data-prox]').onclick = () => { i++; proxima(); };
        fb.querySelector('[data-prox]').focus();
      };
      render();
    };
    proxima();
  },
};
