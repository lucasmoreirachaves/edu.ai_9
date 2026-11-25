/* EDU.AI – Jogos ao vivo (G01–G16): criação, condução pelo professor e participação do aluno */
import {
  S, api, aviso, busy, confirmar, empty, fmtDateTime, go, header, homeOf, html, icon, loading, logoSvg, modal,
  onLeave, page, query, route, tag, toast,
} from './core.js';

const L = 'ABCD';
const COR = ['a', 'b', 'c', 'd'];
const EQUIPES = ['Equipe Azul', 'Equipe Amarela', 'Equipe Verde', 'Equipe Vermelha'];
const CONF = [[1, 'Chute'], [2, 'Acho que sei'], [3, 'Tenho certeza']];
const CONF_TXT = { 1: 'chute', 2: 'acho que sei', 3: 'tenho certeza' };
const PONTUACAO = {
  confianca: 'O aluno responde e diz o quanto tem certeza. Acertar com certeza vale mais; errar com certeza custa pontos. Ganha quem sabe o que sabe, não quem aperta mais rápido.',
  velocidade: 'Quem acerta mais rápido ganha mais pontos (estilo quiz clássico).',
};

/** Laço de consulta ao servidor, encerrado ao sair da rota. */
function poll(fn, ms = 1000) {
  let vivo = true, t;
  const loop = async () => {
    if (!vivo) return;
    try { await fn(); } catch (e) { console.warn(e); }
    if (vivo) t = setTimeout(loop, ms);
  };
  onLeave(() => { vivo = false; clearTimeout(t); });
  loop();
}

/** Atalho de teclado válido só enquanto a rota estiver aberta. */
function tecla(fn) {
  const h = (e) => { if (!e.target.closest('input, textarea, select') && !e.ctrlKey && !e.metaKey && !e.altKey) fn(e); };
  document.addEventListener('keydown', h);
  onLeave(() => document.removeEventListener('keydown', h));
}

const pref = (k, padrao) => { try { return localStorage.getItem(k) ?? padrao; } catch { return padrao; } };
const salvarPref = (k, v) => { try { localStorage.setItem(k, v); } catch { /* sem armazenamento */ } };

const topoJogo = (esq, dir = '') => html`<header class="jogo__topo"><div class="linha"><a class="logo" href="${homeOf(S.user.role)}"><span class="logo__marca">${logoSvg}</span><span class="logo__nome">EDU.AI</span></a>${esq}</div><div class="linha">${dir}</div></header>`;

/* ================================================================ G01 lista (professor) */
route('p/jogos', async (_, q) => {
  page(loading());
  const gs = await api('/jogos');
  const el = page(html`${header('Jogos ao vivo', 'Quizzes em sala para checar o entendimento: a turma vota, discute em duplas quando se divide e todos veem o porquê de cada resposta.', html`<button class="btn btn--primario" data-novo>+ Criar jogo</button>`)}
    ${gs.length ? html`<div class="tabela-caixa"><table class="tabela"><thead><tr><th>Jogo</th><th>Turma</th><th>Perguntas</th><th>Modo</th><th>Status</th><th>Participantes</th><th></th></tr></thead><tbody>
    ${gs.map((g) => html`<tr><td><a href="#/p/jogo/${g.id}">${g.title}</a><div class="texto-fraco">${g.subject_name} · ${fmtDateTime(g.created_at)}</div></td><td>${g.class_name || '—'}</td><td>${g.questions}</td>
      <td>${g.mode === 'equipes' ? 'Equipes' : 'Individual'}<div class="texto-fraco">${g.scoring === 'velocidade' ? 'por velocidade' : 'por confiança'}</div></td><td>${g.status === 'rascunho' ? tag('rascunho', 'Pronto para iniciar') : tag(g.status)}</td><td>${g.players}</td>
      <td><div class="acoes-icone">${g.status === 'finalizado' ? html`<a class="btn btn--contorno btn--p" href="#/p/jogo/${g.id}">Resultados</a>` : html`<a class="btn btn--escuro btn--p" href="#/p/jogo/${g.id}">${g.status === 'rascunho' ? 'Iniciar' : 'Continuar'}</a>`}
        <button class="btn btn--link texto-vermelho" data-del="${g.id}">Excluir</button></div></td></tr>`)}</tbody></table></div>`
    : empty('Nenhum jogo criado', 'Crie um quiz a partir do banco de questões, de uma lista de exercícios, de flashcards, de um glossário ou deixe a IA gerar a partir de um documento.')}`);
  el.querySelector('[data-novo]').onclick = () => criarModal(q);
  el.querySelectorAll('[data-del]').forEach((b) => {
    b.onclick = async () => {
      if (!(await confirmar('Excluir este jogo e seus resultados?', { ok: 'Excluir', perigo: true }))) return;
      await api('/jogos/' + b.dataset.del, { method: 'DELETE' }); go('#/p/jogos');
    };
  });
  if (q.novo) criarModal(q);
}, { role: 'professor' });

/* ================================================================ G02–G03 criar */
async function criarModal(q = {}) {
  const [subs, classes, docs, mats, qs] = await Promise.all([api('/prof/subjects'), api('/prof/classes'), api('/prof/documents'), api('/prof/materials'), api('/prof/questions?kind=objetiva')]);
  if (!subs.length) return toast('Crie uma disciplina primeiro', 'erro');
  const pre = new Set((q.q || '').split(',').filter(Boolean).map(Number));
  const sid0 = qs.find((x) => pre.has(x.id))?.subject_id || Number(q.disciplina) || subs[0].id;
  modal('Criar jogo ao vivo', html`<form id="f" class="pilha">
    <label class="campo"><span>Nome do jogo</span><input class="entrada" name="title" required placeholder="Ex.: Desafio de funções"></label>
    <div class="campos-2"><label class="campo"><span>Disciplina</span><select class="entrada" name="subject_id">${subs.map((s) => html`<option value="${s.id}" ${s.id === sid0 ? 'selected' : ''}>${s.name} · ${s.class_name}</option>`)}</select></label>
    <label class="campo"><span>Turma</span><select class="entrada" name="class_id">${classes.map((c) => html`<option value="${c.id}">${c.name}</option>`)}</select></label></div>
    <div class="campos-2"><label class="campo"><span>Modo</span><select class="entrada" name="mode"><option value="individual">Individual</option><option value="equipes">Colaborativo (equipes)</option></select></label>
    <label class="campo"><span>Tempo por pergunta (s)</span><input class="entrada" type="number" name="time_per_question" value="30" min="5" max="120"></label></div>
    <label class="campo"><span>Pontuação</span><select class="entrada" name="scoring"><option value="confianca">Por confiança (recomendado)</option><option value="velocidade">Por velocidade (clássico)</option></select></label>
    <p class="texto-fraco" data-explica>${PONTUACAO.confianca}</p>
    <label class="check"><input type="checkbox" name="peer" checked><span>Discussão em duplas quando a turma se dividir<br><span class="texto-fraco">Se entre 30% e 70% acertarem, a resposta não é revelada: os alunos discutem com um colega e votam de novo. Você também pode pedir a discussão a qualquer momento.</span></span></label>
    <label class="check"><input type="checkbox" name="show_ranking" checked> Mostrar ranking para os alunos durante o jogo</label>
    <div class="campo"><span>Conteúdo das perguntas</span>
      <div class="segmentado" data-fonte><button type="button" data-v="banco" class="ativo">Banco de questões</button><button type="button" data-v="material">Material existente</button><button type="button" data-v="ia">Gerar com IA</button></div></div>
    <div data-p="banco"><div class="lista-checagem" id="lista-q"></div></div>
    <div data-p="material" hidden><select class="entrada" name="material_id"></select><p class="texto-fraco">Listas de exercícios (objetivas), flashcards e glossários viram perguntas do quiz.</p></div>
    <div data-p="ia" hidden><div class="campos-2"><select class="entrada" name="document_id">${docs.filter((d) => d.status === 'concluido').map((d) => html`<option value="${d.id}" data-s="${d.subject_id}">${d.title}</option>`)}</select>
      <input class="entrada" type="number" name="ai_count" value="8" min="3" max="15" aria-label="Quantidade"></div><p class="texto-fraco">A IA cria perguntas curtas, próprias para quiz. Você revisa antes de abrir a sala.</p></div>
    <div class="linha linha--fim"><button type="button" class="btn btn--contorno" data-fechar>Cancelar</button><button class="btn btn--primario">Criar jogo</button></div></form>`, {
    largo: true,
    onMount: (el, close) => {
      const f = el.querySelector('#f');
      let fonte = 'banco';
      f.scoring.onchange = () => { el.querySelector('[data-explica]').textContent = PONTUACAO[f.scoring.value]; };
      el.querySelector('[data-fonte]').addEventListener('click', (e) => {
        const b = e.target.closest('button'); if (!b) return;
        fonte = b.dataset.v;
        el.querySelectorAll('[data-fonte] button').forEach((x) => x.classList.toggle('ativo', x === b));
        el.querySelectorAll('[data-p]').forEach((p) => { p.hidden = p.dataset.p !== fonte; });
      });
      const porDisciplina = () => {
        const sid = Number(f.subject_id.value);
        const s = subs.find((x) => x.id === sid);
        if (s) f.class_id.value = s.class_id;
        const lst = qs.filter((x) => x.subject_id === sid);
        el.querySelector('#lista-q').innerHTML = lst.length ? html`${lst.map((x) => html`<label class="check"><input type="checkbox" value="${x.id}" ${pre.has(x.id) || !pre.size ? 'checked' : ''}><span>${x.statement}<br><span class="texto-fraco">${x.topic_name || 'Sem assunto'}</span></span></label>`)}`.s
          : '<p class="texto-fraco">Nenhuma questão objetiva no banco desta disciplina.</p>';
        f.material_id.innerHTML = html`${mats.filter((m) => m.subject_id === sid && ['exercicios', 'flashcards', 'glossario'].includes(m.type)).map((m) => html`<option value="${m.id}">${m.title}</option>`)}`.s || '<option value="">Nenhum material compatível</option>';
      };
      f.subject_id.onchange = porDisciplina;
      porDisciplina();
      f.addEventListener('submit', (e) => {
        e.preventDefault();
        const body = {
          title: f.title.value, subject_id: Number(f.subject_id.value), class_id: Number(f.class_id.value), mode: f.mode.value,
          scoring: f.scoring.value, peer: f.peer.checked,
          time_per_question: Number(f.time_per_question.value), show_ranking: f.show_ranking.checked, question_ids: [],
        };
        if (fonte === 'banco') body.question_ids = [...el.querySelectorAll('#lista-q input:checked')].map((i) => Number(i.value));
        if (fonte === 'material') body.material_id = Number(f.material_id.value) || null;
        if (fonte === 'ia') { body.document_id = Number(f.document_id.value) || null; body.ai_count = Number(f.ai_count.value); }
        busy(f.querySelector('.btn--primario'), async () => {
          const r = await api('/jogos', { method: 'POST', body });
          close(); toast(`Jogo criado com ${r.questions} perguntas`); go('#/p/jogo/' + r.id);
        });
      });
    },
  });
}

/* ================================================================ G04–G08 condução (professor) */
route('p/jogo/:id', async ({ id }) => {
  const g = await api('/jogos/' + id);
  if (g.status === 'rascunho') return rascunho(g);
  if (g.status === 'finalizado') return resultado(id);
  conduzir(id);
}, { role: 'professor' });

/* painel do professor em outro aparelho (celular/notebook), enquanto o telão mostra o jogo */
route('p/jogo/:id/painel', ({ id }) => conduzir(id, { remoto: true }), { role: 'professor' });

function rascunho(g) {
  const st = { questions: g.questions };
  const salvar = () => api('/jogos/' + g.id, { method: 'PUT', body: { questions: st.questions, title: g.title, time_per_question: g.time_per_question, mode: g.mode, scoring: g.scoring, peer: !!g.peer, show_ranking: !!g.show_ranking } });
  const el = page(html`<a href="#/p/jogos" class="link-sutil">← Jogos ao vivo</a>
    ${header(g.title, `${st.questions.length} perguntas · ${g.time_per_question}s cada · ${g.mode === 'equipes' ? 'colaborativo em equipes' : 'individual'} · pontuação por ${g.scoring === 'velocidade' ? 'velocidade' : 'confiança'}${g.peer ? ' · com discussão em duplas' : ''}`, html`<button class="btn btn--primario btn--g" data-abrir>${icon('jogo', 18)} Abrir sala</button>`)}
    ${aviso('Revise as perguntas e as explicações: elas aparecem para você durante o jogo e para a turma na hora da revelação. Ao abrir a sala, um código de 6 dígitos aparece para os alunos entrarem.')}
    <div class="pilha" id="lista"></div>`);
  const lista = el.querySelector('#lista');
  const render = () => {
    lista.innerHTML = html`${st.questions.map((q, i) => html`<div class="questao"><div class="linha linha--entre"><span class="tag tag--cinza">Pergunta ${i + 1}</span><button class="btn btn--link texto-vermelho" data-rm="${i}">Remover</button></div>
      <p class="questao__enunciado">${q.statement}</p><div class="grade grade-2">${q.options.map((o, j) => html`<div class="alternativa ${j === q.answer ? 'alternativa--correta' : ''}" style="padding:8px 12px"><strong>${L[j] || j + 1})</strong> ${o}</div>`)}</div>
      <label class="campo"><span>Por que a resposta está certa (explicação)</span><textarea class="entrada" rows="2" data-exp="${i}" placeholder="Sem explicação: escreva uma frase para a turma entender o porquê">${q.explanation || ''}</textarea></label></div>`)}`.s;
    lista.querySelectorAll('[data-rm]').forEach((b) => {
      b.onclick = async () => { st.questions.splice(Number(b.dataset.rm), 1); await salvar(); render(); };
    });
    lista.querySelectorAll('[data-exp]').forEach((t) => {
      t.onchange = async () => { st.questions[Number(t.dataset.exp)].explanation = t.value.trim(); await salvar(); toast('Explicação salva'); };
    });
  };
  render();
  el.querySelector('[data-abrir]').onclick = (e) => busy(e.currentTarget, async () => {
    if (!st.questions.length) throw new Error('O jogo precisa de ao menos uma pergunta');
    await api(`/jogos/${g.id}/abrir`, { method: 'POST' });
    conduzir(g.id);
  });
}

/** Gabarito e votos — só para o professor. */
function painelProf(s) {
  const q = s.question;
  if (!q) return html`<section class="painel-prof" data-painel><p class="texto-fraco">O gabarito aparece aqui quando a primeira pergunta começar.</p></section>`;
  const porOpcao = q.options.map((_, j) => s.voters.filter((v) => v.choice === j));
  const certeza = s.scoring === 'confianca';
  return html`<section class="painel-prof" data-painel>
    <div class="painel-prof__topo"><strong>${icon('olho', 16)} Só para você · gabarito</strong>
      <span class="texto-fraco">${s.answered} de ${s.players.length} responderam${s.accuracy != null ? ` · ${s.accuracy}% de acerto` : ''}${s.round === 2 ? ' · 2ª votação' : ''}</span></div>
    <div class="painel-prof__certa"><span class="resposta__letra">${L[q.answer]}</span><div><small>Resposta certa</small><strong>${q.options[q.answer]}</strong></div></div>
    ${q.explanation ? html`<p><strong>Por que está certa:</strong> ${q.explanation}</p>` : html`<p class="texto-fraco">Esta pergunta não tem explicação cadastrada.</p>`}
    ${s.first_round ? html`<p class="texto-fraco">1ª votação, antes da discussão: ${s.first_round.accuracy ?? '—'}% de acerto (${s.first_round.answered} respostas).</p>` : ''}
    <div class="votos">${q.options.map((o, j) => html`<div class="votos__linha ${j === q.answer ? 'votos__linha--certa' : ''}">
      <span class="votos__letra" title="${o}">${L[j]}</span>
      <div class="votos__nomes">${porOpcao[j].length ? porOpcao[j].map((v) => html`<span class="voto ${certeza && v.confidence === 3 && !v.correct ? 'voto--alerta' : ''}" title="${CONF_TXT[v.confidence] || ''}">${v.name}${certeza ? html` <small>${CONF_TXT[v.confidence]}</small>` : ''}</span>`) : html`<span class="texto-fraco">ninguém</span>`}</div>
      <strong>${porOpcao[j].length}</strong></div>`)}</div>
    ${certeza && s.voters.some((v) => v.confidence === 3 && !v.correct) ? html`<p class="texto-fraco"><span class="voto voto--alerta">nome</span> errou tendo certeza: vale conversar sobre essa ideia.</p>` : ''}
    ${s.waiting.length && s.status === 'pergunta' ? html`<p class="texto-fraco"><strong>Ainda não responderam:</strong> ${s.waiting.join(', ')}</p>` : ''}
  </section>`;
}

/** Botões de controle de cada estado (telão e painel remoto). */
function controles(s, { primarioGrande = false } = {}) {
  const b = (a, txt, cls = 'btn--contorno btn--p', desligado = false) => html`<button class="btn ${cls}" data-a="${a}" ${desligado ? 'disabled' : ''}>${txt}</button>`;
  const grande = primarioGrande ? 'btn--primario btn--g' : 'btn--primario btn--p';
  if (s.status === 'sala') return b('proxima', 'Começar o jogo', grande, !s.players.length);
  if (s.status === 'pergunta') {
    return html`${b('pausar', s.paused ? 'Continuar' : 'Pausar')}
      ${s.round === 1 && s.players.length >= 2 ? b('discutir', html`${icon('duplas', 16)} Discutir em duplas`) : ''}
      ${b('revelar', 'Mostrar resposta')}`;
  }
  if (s.status === 'discussao') return html`${b('revelar', 'Revelar sem nova votação')}${b('revotar', 'Votar de novo', grande)}`;
  if (s.status === 'revelacao') return b('proxima', s.current + 1 >= s.total ? 'Ver resultado final' : 'Próxima pergunta →', grande);
  return '';
}

function conduzir(id, { remoto = false } = {}) {
  const root = remoto ? page(html`<div id="jogo" class="pilha"><div class="carregando">Conectando…</div></div>`) : page(html`<div class="jogo" id="jogo"><div class="carregando">Conectando…</div></div>`, { bare: true });
  const box = root.querySelector('#jogo');
  let chave = '', ultimo = null;
  let gabarito = remoto || pref('edu_gabarito', '1') === '1';
  const acao = (rota) => api(`/jogos/${id}/${rota}`, { method: 'POST' });

  poll(async () => {
    const s = await api(`/jogos/${id}/estado`);
    ultimo = s;
    const k = `${s.status}|${s.current}|${s.round}|${s.paused}`;
    if (k !== chave) { chave = k; render(s); } else atualizar(s);
    if (s.status === 'finalizado') go(remoto ? '#/p/jogos' : '#/p/jogo/' + id);
  }, 1000);

  if (!remoto) {
    tecla((e) => {
      if (e.key.toLowerCase() !== 'g') return;
      gabarito = !gabarito;
      salvarPref('edu_gabarito', gabarito ? '1' : '0');
      if (ultimo) render(ultimo);
    });
  }

  function atualizar(s) {
    box.querySelectorAll('[data-tempo]').forEach((t) => { t.textContent = Math.ceil(s.time_left); });
    const r = box.querySelector('[data-respostas]');
    if (r) r.textContent = `${s.answered || 0} de ${s.players.length} responderam`;
    const p = box.querySelector('[data-participantes]');
    if (p) { p.innerHTML = participantes(s).s; box.querySelector('[data-np]').textContent = s.players.length; }
    const painel = box.querySelector('[data-painel]');
    if (painel) painel.outerHTML = painelProf(s).s;
    if (s.status === 'sala') {
      const iniciar = box.querySelector('[data-a=proxima]');
      if (iniciar) iniciar.disabled = !s.players.length;
      const espera = box.querySelector('[data-espera]');
      if (espera) espera.hidden = !!s.players.length;
    }
  }
  const participantes = (s) => html`${s.players.map((p) => html`<span>${p.name}${s.mode === 'equipes' ? html` <small style="opacity:.7">· ${EQUIPES[p.team % 4].split(' ')[1]}</small>` : ''}</span>`)}`;
  const placar = (s, n = 5) => (s.mode === 'equipes'
    ? html`${s.teams.map((t, i) => html`<div class="placar-linha placar-linha--equipe-${t.team % 4}"><span class="placar-linha__pos">${i + 1}</span>${t.name} <small style="opacity:.7">(${t.members})</small><span class="placar-linha__pts">${t.score} pts</span></div>`)}`
    : html`${s.players.slice(0, n).map((p, i) => html`<div class="placar-linha"><span class="placar-linha__pos">${i + 1}</span>${p.name}<span class="placar-linha__pts">${p.score} pts</span></div>`)}`);
  const pct = (c, s) => (s.answered ? Math.round((100 * c) / s.answered) : 0);

  function renderRemoto(s) {
    const q = s.question;
    const titulo = { sala: 'Sala aberta', pergunta: `Pergunta ${s.current + 1} de ${s.total}`, discussao: 'Discussão em duplas', revelacao: `Resposta da pergunta ${s.current + 1}` }[s.status] || '';
    box.innerHTML = html`<a href="#/p/jogo/${id}" class="link-sutil">← Abrir o telão neste aparelho</a>
      ${header(`${s.title} · painel`, `${titulo}${s.status === 'sala' ? ` · código ${s.code} · ${s.players.length} participante(s)` : ''}`, html`<button class="btn btn--perigo btn--p" data-a="encerrar">Encerrar</button>`)}
      <div class="cartao pilha">${s.status === 'pergunta' ? html`<div class="linha linha--entre"><span class="tag tag--vermelho">Votação aberta${s.round === 2 ? ' · 2ª' : ''}</span><strong><span data-tempo>${Math.ceil(s.time_left)}</span>s</strong></div>` : ''}
        ${q ? html`<p class="questao__enunciado">${q.statement}</p>` : ''}
        <div class="linha">${controles(s)}</div></div>
      ${painelProf(s)}`.s;
  }

  function render(s) {
    if (remoto) { renderRemoto(s); bind(); return; }
    const q = s.question;
    const btnGab = html`<button class="btn btn--contorno btn--p" data-gab title="Tecla G">${icon('olho', 14)} Gabarito: ${gabarito ? 'visível' : 'oculto'}</button>`;
    const topo = (esq, extra = '') => topoJogo(esq, html`${extra}${s.status !== 'sala' ? btnGab : ''}<button class="btn btn--contorno btn--p" data-a="encerrar">Encerrar</button>`);
    const dicaTelao = html`<p class="texto-fraco jogo-centro">Projetando para a turma? Esconda o gabarito com a tecla <kbd>G</kbd> ou <a href="#/p/jogo/${id}/painel" target="_blank" rel="noopener">abra o painel no seu celular ou notebook</a>.</p>`;
    const painel = gabarito && s.status !== 'sala' ? html`<div class="painel-prof-caixa">${painelProf(s)}${dicaTelao}</div>` : html`${s.status !== 'sala' ? dicaTelao : ''}`;
    const tagPerg = html`<span class="tag tag--amarelo">Pergunta ${s.current + 1} de ${s.total}</span>${s.round === 2 ? html`<span class="tag tag--azul">2ª votação</span>` : ''}`;
    if (s.status === 'sala') {
      box.innerHTML = html`${topo(html`<span class="tag tag--amarelo">${s.title}</span>`)}
        <main class="jogo__corpo jogo-centro">
          <p class="texto-fraco" style="font-size:18px">Entre em <strong style="color:#fff">${location.host}/app</strong> → Jogos e desafios, e digite o código:</p>
          <div class="codigo-sala"><div class="codigo">${s.code}</div></div>
          <h2 style="font-size:22px"><span data-np>${s.players.length}</span> participante(s)</h2>
          <div class="participantes" data-participantes>${participantes(s)}</div>
          ${controles(s, { primarioGrande: true })}
          <p class="texto-fraco" data-espera ${s.players.length ? 'hidden' : ''}>Aguardando os alunos entrarem…</p>
          <p class="texto-fraco"><a href="#/p/jogo/${id}/painel" target="_blank" rel="noopener" style="color:#fff">Abrir painel do professor em outro aparelho</a> (gabarito e votos sem aparecer no telão)</p>
        </main>`.s;
    } else if (s.status === 'pergunta') {
      box.innerHTML = html`${topo(tagPerg, controles(s))}
        <main class="jogo__corpo">
          <div class="linha linha--entre" style="max-width:1100px;margin:0 auto"><div class="cronometro cronometro--pequeno" data-tempo>${Math.ceil(s.time_left)}</div><h2 class="jogo__pergunta" style="flex:1">${q.statement}</h2><div style="width:84px;text-align:center" class="texto-fraco"><span data-respostas>${s.answered} de ${s.players.length} responderam</span></div></div>
          ${s.round === 2 ? html`<p class="jogo-centro" style="font-size:18px">Depois da conversa: qual é a resposta agora?</p>` : ''}
          ${s.paused ? html`<p class="jogo-centro"><span class="tag tag--amarelo">Pausado</span></p>` : ''}
          <div class="jogo-grade">${q.options.map((o, j) => html`<div class="resposta resposta--${COR[j % 4]}"><span class="resposta__letra">${L[j]}</span>${o}</div>`)}</div>
          ${painel}
        </main>`.s;
    } else if (s.status === 'discussao') {
      box.innerHTML = html`${topo(tagPerg)}
        <main class="jogo__corpo">
          <h2 class="jogo__pergunta">${q.statement}</h2>
          <div class="discussao"><span class="discussao__icone">${icon('duplas', 40)}</span>
            <div><h3>A turma ficou dividida. Hora de discutir!</h3>
            <p>Encontre um colega que escolheu uma resposta diferente da sua. Cada um explica o próprio raciocínio. Depois, votem de novo.</p></div></div>
          <div class="jogo-grade">${q.options.map((o, j) => html`<div class="resposta resposta--${COR[j % 4]} resposta--neutra"><span class="resposta__letra">${L[j]}</span>${o}<span class="resposta__qtd">${pct(s.counts[j], s)}%</span></div>`)}</div>
          <div class="jogo-centro linha" style="justify-content:center">${controles(s, { primarioGrande: true })}</div>
          ${painel}
        </main>`.s;
    } else if (s.status === 'revelacao') {
      const max = Math.max(1, ...s.counts);
      box.innerHTML = html`${topo(tagPerg)}
        <main class="jogo__corpo">
          <h2 class="jogo__pergunta">${q.statement}</h2>
          <div class="jogo-grade">${q.options.map((o, j) => html`<div class="resposta resposta--${COR[j % 4]} ${j === q.answer ? 'resposta--certa' : 'resposta--apagada'}"><span class="resposta__letra">${j === q.answer ? '✓' : L[j]}</span>${o}<span class="resposta__qtd" title="respostas">${s.counts[j]}</span></div>`)}</div>
          ${q.explanation ? html`<div class="cartao porque"><strong>Por que ${L[q.answer]} está certa?</strong> ${q.explanation}</div>` : ''}
          ${s.first_round ? html`<p class="jogo-centro" style="font-size:18px">Antes da discussão: <strong>${s.first_round.accuracy ?? 0}%</strong> de acerto → depois: <strong>${s.accuracy ?? 0}%</strong></p>` : ''}
          <div class="barras" style="height:110px;max-width:520px;margin:0 auto">${s.counts.map((c, j) => html`<div class="barras__item"><span class="barras__valor" style="color:#fff">${c}</span><div class="barras__barra" style="height:${(100 * c) / max}%;background:var(--${['azul', 'amarelo', 'verde', 'vermelho'][j % 4]})"></div><span class="barras__rotulo">${L[j]}</span></div>`)}</div>
          <div class="grade grade-2" style="max-width:1100px;margin:24px auto 0;align-items:start"><div>${placar(s)}</div>
            <div class="jogo-centro">${controles(s, { primarioGrande: true })}</div></div>
          ${painel}
        </main>`.s;
    } else {
      box.innerHTML = '<div class="carregando">Finalizando…</div>';
    }
    bind();
  }

  function bind() {
    box.querySelector('[data-gab]')?.addEventListener('click', () => {
      gabarito = !gabarito;
      salvarPref('edu_gabarito', gabarito ? '1' : '0');
      if (ultimo) render(ultimo);
    });
    box.querySelectorAll('[data-a]').forEach((b) => {
      b.onclick = async () => {
        if (b.dataset.a === 'encerrar' && !(await confirmar('Encerrar o jogo agora?', { ok: 'Encerrar', perigo: true }))) return;
        b.disabled = true;
        try { await acao(b.dataset.a); } catch (e) { toast(e.message, 'erro'); b.disabled = false; }
        chave = '';
      };
    });
  }
}

async function resultado(id) {
  const r = await api(`/jogos/${id}/relatorio`);
  const top = r.players.slice(0, 3);
  const ordem = [top[1], top[0], top[2]];
  const corAcerto = (a) => (a == null ? '' : a < 50 ? 'vermelho' : a < 70 ? 'amarelo' : 'verde');
  const el = page(html`<a href="#/p/jogos" class="link-sutil">← Jogos ao vivo</a>
    ${header(`Resultado · ${r.game.title}`, `${r.players.length} participantes · ${r.total} perguntas · acerto médio ${r.accuracy ?? '—'}%`, html`<button class="btn btn--contorno" data-reabrir>Jogar novamente</button><a class="btn btn--primario" href="#/p/estudio">Gerar revisão</a>`)}
    ${r.discussion_gain == null ? '' : r.discussion_gain >= 0
    ? aviso(html`As discussões em duplas aumentaram o acerto em média <strong>${r.discussion_gain} pontos percentuais</strong> nas perguntas discutidas.`, 'verde')
    : aviso(html`As discussões em duplas não aumentaram o acerto (${r.discussion_gain} p.p.): vale retomar esses conceitos com a turma.`, 'amarelo')}
    <div class="grade grade-2">
      <section class="cartao"><h2 class="cartao__titulo">Pódio</h2>
        ${r.players.length ? html`<div class="podio">${ordem.map((p, i) => (p ? html`<div class="podio__col podio__col--${[2, 1, 3][i]}"><strong>${p.name}</strong><small>${p.score} pts · ${p.correct}/${r.total}</small><div class="podio__base">${[2, 1, 3][i]}º</div></div>` : ''))}</div>` : empty('Ninguém participou')}
        ${r.teams.length ? html`<h3 style="margin-top:12px">Equipes</h3><ul class="lista-simples">${r.teams.map((t) => html`<li><span>${t.name} (${t.members})</span><strong>${t.score} pts</strong></li>`)}</ul>` : ''}</section>
      <section class="cartao"><h2 class="cartao__titulo">Aprendizagem por pergunta</h2>
        <div class="barras-h">${r.questions.map((q) => html`<div class="barras-h__linha"><span title="${q.statement}">${q.index + 1}. ${q.statement.length > 40 ? q.statement.slice(0, 40) + '…' : q.statement}</span><div class="progresso progresso--${corAcerto(q.accuracy)}"><span style="width:${q.accuracy || 0}%"></span></div><strong>${q.accuracy == null ? '—' : q.accuracy + '%'}</strong></div>`)}</div>
        ${r.review.length ? aviso(`${r.review.length} pergunta(s) com menos de 60% de acerto — vale retomar esses conceitos em aula.`, 'amarelo') : ''}</section>
    </div>
    <section><div class="secao__topo"><h2>Pergunta a pergunta</h2><span class="texto-fraco">resposta certa, por quê, e onde a turma se confundiu</span></div>
      <div class="pilha">${r.questions.map((q) => html`<details class="questao revisao-q" ${q.accuracy != null && q.accuracy < 60 ? 'open' : ''}>
        <summary><span class="tag tag--${corAcerto(q.accuracy) || 'cinza'}">${q.accuracy == null ? 'sem respostas' : q.accuracy + '% de acerto'}</span> <strong>${q.index + 1}. ${q.statement}</strong></summary>
        <div class="alternativas">${q.options.map((o, j) => html`<div class="alternativa ${j === q.answer ? 'alternativa--correta' : ''}"><strong>${L[j]})</strong> ${o}<span class="alternativa__qtd">${q.counts[j]} ${q.counts[j] === 1 ? 'voto' : 'votos'}</span></div>`)}</div>
        ${q.explanation ? html`<p><strong>Por que ${L[q.answer]} está certa:</strong> ${q.explanation}</p>` : ''}
        <div class="chips">
          ${q.before != null ? html`<span class="chip">Antes da discussão ${q.before}% → depois ${q.accuracy ?? 0}%</span>` : ''}
          ${q.top_wrong && q.top_wrong.pct >= 20 ? html`<span class="chip">${q.top_wrong.pct}% escolheram ${q.top_wrong.letter} (errada): possível confusão comum</span>` : ''}
          ${q.overconfident ? html`<span class="chip chip--alerta">${q.overconfident} aluno(s) erraram tendo certeza</span>` : ''}
        </div></details>`)}</div></section>
    <section><div class="secao__topo"><h2>Classificação completa</h2></div><div class="tabela-caixa"><table class="tabela"><thead><tr><th>#</th><th>Aluno</th>${r.teams.length ? html`<th>Equipe</th>` : ''}<th>Acertos</th><th>Pontos</th></tr></thead><tbody>
      ${r.players.map((p, i) => html`<tr><td>${i + 1}</td><td>${p.name}</td>${r.teams.length ? html`<td>${EQUIPES[p.team % 4]}</td>` : ''}<td>${p.correct}/${r.total}</td><td><strong>${p.score}</strong></td></tr>`)}</tbody></table></div></section>`);
  el.querySelector('[data-reabrir]').onclick = (e) => busy(e.currentTarget, async () => { await api(`/jogos/${id}/abrir`, { method: 'POST' }); conduzir(id); });
}

/* ================================================================ G09–G16 aluno */
route('a/jogos', async () => {
  const p = await api('/aluno/progress');
  const el = page(html`${header('Jogos e desafios', 'Entre em um jogo ao vivo com o código mostrado pelo professor.')}
    <div class="grade grade-2">
      <form class="cartao jogo-centro" id="f"><h2 class="cartao__titulo">Entrar com código</h2>
        <input class="codigo-entrada" name="code" inputmode="numeric" maxlength="6" placeholder="000000" required autocomplete="off" aria-label="Código do jogo">
        <button class="btn btn--primario btn--g btn--bloco">Entrar no jogo</button></form>
      <section class="cartao"><h2 class="cartao__titulo">Meus últimos jogos</h2>${p.games.length ? html`<ul class="lista-simples">${p.games.map((g) => html`<li><span>${g.title}<br><span class="texto-fraco">${g.pos}º de ${g.players}</span></span><strong>${g.score} pts</strong></li>`)}</ul>` : html`<p class="texto-fraco">Você ainda não participou de jogos.</p>`}</section>
    </div>`);
  const f = el.querySelector('#f');
  const pre = query().codigo;
  if (pre) f.code.value = pre;
  f.addEventListener('submit', (e) => { e.preventDefault(); go('#/a/jogar/' + f.code.value.trim()); });
  f.code.focus();
}, { role: 'aluno' });

route('a/jogar/:code', async ({ code }) => {
  let gid;
  try { gid = (await api('/jogar/entrar', { method: 'POST', body: { code } })).game_id; } catch (e) {
    toast(e.message, 'erro');
    return go('#/a/jogos');
  }
  const root = page(html`<div class="jogo" id="jogo"><div class="carregando">Entrando…</div></div>`, { bare: true });
  const box = root.querySelector('#jogo');
  let chave = '';
  poll(async () => {
    const s = await api(`/jogar/${gid}/estado`);
    const k = `${s.status}|${s.current}|${s.round}|${s.my_answer ? 1 : 0}|${s.paused}`;
    if (k !== chave) { chave = k; render(s); } else {
      const t = box.querySelector('[data-tempo]');
      if (t) t.textContent = Math.ceil(s.time_left);
    }
    if (s.status === 'finalizado') { chave = 'fim'; }
  }, 1000);

  const enviar = async (s, choice, confidence = 2) => {
    box.querySelectorAll('[data-escolha], [data-conf]').forEach((x) => { x.disabled = true; });
    try { await api(`/jogar/${gid}/responder`, { method: 'POST', body: { choice, confidence, q_index: s.current } }); } catch (e) { toast(e.message, 'erro'); }
    chave = '';
  };

  function render(s) {
    const topo = topoJogo(html`<span class="tag tag--amarelo">${s.title}</span>`, html`<span class="tag tag--azul">${s.me.score} pts</span>${s.me.team ? html`<span class="tag tag--cinza">${s.me.team}</span>` : ''}`);
    const confianca = s.scoring === 'confianca';
    let corpo;
    if (s.status === 'sala') {
      corpo = html`<div class="jogo-centro"><div class="feedback__icone" style="background:var(--verde);margin:20px auto">✓</div><h1 style="font-size:28px">Você está dentro, ${s.me.name.split(' ')[0]}!</h1><p class="texto-fraco">Aguarde o professor iniciar o jogo. ${s.players} participante(s) na sala.</p>${s.me.team ? html`<p>Sua equipe: <strong>${s.me.team}</strong></p>` : ''}
        ${confianca ? html`<div class="cartao" style="text-align:left"><strong>Como funciona:</strong> em cada pergunta, escolha a resposta e diga o quanto tem certeza. Acertar com certeza vale mais; errar com certeza tira pontos. Seja honesto com você mesmo!</div>` : ''}
        <span class="spinner" style="border-color:#334155;border-top-color:#FACC15"></span></div>`;
    } else if (s.status === 'pergunta' && !s.my_answer) {
      corpo = html`<div class="linha linha--entre"><span class="tag tag--amarelo">Pergunta ${s.current + 1} de ${s.total}${s.round === 2 ? ' · 2ª votação' : ''}</span><div class="cronometro cronometro--pequeno" data-tempo>${Math.ceil(s.time_left)}</div></div>
        ${s.round === 2 ? html`<p class="jogo-centro"><strong>Depois da conversa, qual é a sua resposta?</strong></p>` : ''}
        <h2 class="jogo__pergunta" style="font-size:22px">${s.question.statement}</h2>
        ${s.paused ? html`<p class="jogo-centro"><span class="tag tag--amarelo">Pausado pelo professor</span></p>` : ''}
        <div class="jogo-grade">${s.question.options.map((o, j) => html`<button class="resposta resposta--${COR[j % 4]}" data-escolha="${j}" ${s.paused ? 'disabled' : ''}><span class="resposta__letra">${L[j]}</span>${o}</button>`)}</div>
        ${confianca ? html`<div class="confianca" data-confianca hidden><p><strong>Quanto você tem certeza?</strong></p><div class="confianca__botoes">${CONF.map(([v, l]) => html`<button type="button" class="btn ${v === 3 ? 'btn--primario' : 'btn--contorno'}" data-conf="${v}">${l}</button>`)}</div>
          <p class="texto-fraco">Certeza e acerto: +1000 · certeza e erro: −300 · chute: +400 ou 0</p></div>` : ''}`;
    } else if (s.status === 'pergunta') {
      const a = s.my_answer;
      corpo = html`<div class="jogo-centro"><span class="spinner" style="border-color:#334155;border-top-color:#FACC15"></span><h2 style="font-size:24px">Resposta enviada!</h2>
        <p>Você marcou <strong>${L[a.choice]}</strong>${confianca ? ` · ${CONF_TXT[a.confidence]}` : ''}</p>
        <p class="texto-fraco">Aguarde os colegas… <span data-tempo>${Math.ceil(s.time_left)}</span>s</p></div>`;
    } else if (s.status === 'discussao') {
      const a = s.my_answer;
      corpo = html`<div class="jogo-centro"><span class="discussao__icone" style="margin:12px auto">${icon('duplas', 40)}</span>
        <h2 style="font-size:26px">Hora de discutir!</h2>
        <p>A turma ficou dividida nesta pergunta. Procure um colega que escolheu uma resposta diferente e expliquem um para o outro por que escolheram.</p>
        ${a ? html`<div class="cartao" style="text-align:left">Você escolheu <strong>${L[a.choice]}) ${s.question.options[a.choice]}</strong>.<br><span class="texto-fraco">Por quê? Tente explicar em uma frase.</span></div>` : html`<p class="texto-fraco">Você não respondeu a tempo: participe da conversa mesmo assim!</p>`}
        <p class="texto-fraco">Daqui a pouco o professor abre uma nova votação.</p></div>`;
    } else if (s.status === 'revelacao') {
      const a = s.my_answer;
      const ok = a && a.correct;
      const pts = a ? a.points : 0;
      const dica = !a ? '' : confianca && !ok && a.confidence === 3 ? 'Você tinha certeza: vale rever esse conceito com calma.'
        : confianca && ok && a.confidence === 1 ? 'Acertou no chute! Revise para ter certeza da próxima vez.' : '';
      corpo = html`<div class="feedback-tela ${ok ? 'feedback--ok' : 'feedback--erro'}"><div class="feedback__icone" style="margin:0 auto">${ok ? '✓' : '✕'}</div>
          <h2>${ok ? 'Acertou!' : a ? 'Não foi dessa vez' : 'Tempo esgotado'}</h2><p style="font-size:20px;font-weight:700">${pts > 0 ? '+' : ''}${pts} pontos</p>
          ${dica ? html`<p>${dica}</p>` : ''}
          ${!ok ? html`<p>Resposta certa: <strong>${L[s.question.answer]}) ${s.question.options[s.question.answer]}</strong></p>` : ''}
          ${s.question.explanation ? html`<p style="opacity:.95"><strong>Por quê:</strong> ${s.question.explanation}</p>` : ''}</div>
        <p class="jogo-centro" style="font-size:18px">Você está em <strong>${s.me.position}º</strong> lugar · ${s.me.score} pts${s.me.streak > 1 ? ` · ${s.me.streak} acertos seguidos 🔥` : ''}</p>
        ${s.ranking ? html`<div>${s.ranking.slice(0, 5).map((r, i) => html`<div class="placar-linha ${r.me ? 'placar-linha--voce' : ''}"><span class="placar-linha__pos">${i + 1}</span>${r.name}<span class="placar-linha__pts">${r.score}</span></div>`)}</div>` : ''}`;
    } else {
      corpo = html`<div class="jogo-centro"><p class="rotulo-pequeno">Fim de jogo</p><h1 style="font-size:34px">${s.me.position}º lugar</h1>
          <div class="cronometro" style="font-size:34px">${s.me.score}</div><p>pontos · ${s.correct} de ${s.total} acertos</p>
          ${s.teams ? html`<p>Equipe vencedora: <strong>${s.teams[0]?.name}</strong></p>` : ''}</div>
        ${s.review?.length ? html`<section class="cartao pilha revisao-aluno"><h2 class="cartao__titulo">Para revisar (${s.review.length})</h2>
          ${s.review.map((q) => html`<div class="revisao-aluno__item"><p><strong>${q.statement}</strong></p>
            ${q.given ? html`<p class="texto-vermelho">Sua resposta: ${q.given}</p>` : html`<p class="texto-fraco">Você não respondeu.</p>`}
            <p class="texto-verde">Resposta certa: ${q.right}</p>${q.explanation ? html`<p class="texto-suave">${q.explanation}</p>` : ''}</div>`)}</section>`
          : html`<p class="jogo-centro">Você acertou todas! 🎉</p>`}
        ${s.ranking ? html`<div>${s.ranking.map((r, i) => html`<div class="placar-linha ${r.me ? 'placar-linha--voce' : ''}"><span class="placar-linha__pos">${i + 1}</span>${r.name}<span class="placar-linha__pts">${r.score}</span></div>`)}</div>` : ''}
        <a class="btn btn--primario btn--bloco" href="#/a/progresso">Ver meu progresso</a><a class="btn btn--contorno btn--bloco" style="color:#fff" href="#/a/inicio">Voltar ao início</a>`;
    }
    box.innerHTML = html`${topo}<main class="jogo-celular pilha">${corpo}</main>`.s;
    let escolha = null;
    box.querySelectorAll('[data-escolha]').forEach((b) => {
      b.onclick = () => {
        escolha = Number(b.dataset.escolha);
        if (!confianca) {
          box.querySelectorAll('[data-escolha]').forEach((x) => { if (x !== b) x.classList.add('resposta--apagada'); });
          enviar(s, escolha);
          return;
        }
        box.querySelectorAll('[data-escolha]').forEach((x) => { x.classList.toggle('resposta--apagada', x !== b); x.classList.toggle('resposta--escolhida', x === b); });
        const c = box.querySelector('[data-confianca]');
        c.hidden = false;
        c.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      };
    });
    box.querySelectorAll('[data-conf]').forEach((b) => {
      b.onclick = () => { if (escolha != null) enviar(s, escolha, Number(b.dataset.conf)); };
    });
  }
}, { role: 'aluno' });
