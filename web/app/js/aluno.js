/* EDU.AI – aluno (A01–A11): estudar, revisar, fazer atividades e acompanhar o próprio progresso */
import {
  S, TYPE_LABEL, api, aviso, bars, bindTabs, busy, confirmar, download, dueTag, empty, fmtDate, go, header, hbars, html, icon, kpi,
  lineChart, loading, nota, onLeave, pad2, page, progress, route, tabs, tag, toast, typeIcon,
} from './core.js';

/* arquivos originais enviados pelo professor (PDF, DOCX…), para ver e baixar */
const tamanho = (b) => (b >= 1048576 ? `${(b / 1048576).toFixed(1).replace('.', ',')} MB` : `${Math.max(1, Math.round(b / 1024))} KB`);
const extDe = (d) => (d.filename && d.filename.includes('.') ? d.filename.split('.').pop().toUpperCase() : 'TXT');
const nomeArquivo = (d) => d.filename || `${d.title}.txt`;
const arquivoLinha = (d) => html`<li><span class="linha">${icon('conteudo')}<span><strong>${d.title}</strong>
  <span class="texto-fraco" style="display:block">${extDe(d)} · ${tamanho(d.size || 0)}${d.pages ? ` · ${d.pages} páginas` : ''}${d.topic_name ? ` · ${d.topic_name}` : ''}</span></span></span>
  <button class="btn btn--contorno btn--p" data-baixar-doc="${d.id}" data-nome="${nomeArquivo(d)}" title="Baixar ${nomeArquivo(d)}">${icon('baixar', 14)} Baixar</button></li>`;
const ligarDownloads = (el) => el.querySelectorAll('[data-baixar-doc]').forEach((b) => {
  b.onclick = () => busy(b, () => download(`/aluno/documentos/${b.dataset.baixarDoc}/arquivo`, b.dataset.nome));
});
import { glossarioView, mapaArvore, mapaSvg, resumoView } from './viewers.js';

const R = { role: 'aluno' };
const L = 'ABCDE';
const linkCartao = 'color:inherit;text-decoration:none';

/* ---------------------------------------------------------------- cartão de revisão */
const NOTAS = ['errei', 'dificil', 'facil'];
const cartaoHtml = (frente, verso, topo) => html`${topo}
  <button type="button" class="flashcard" data-flip><div class="flashcard__interno"><div class="flashcard__face"><small>Pergunta · tente lembrar antes de virar</small>${frente}</div><div class="flashcard__face flashcard__face--verso"><small>Resposta</small>${verso}</div></div></button>
  <p class="texto-fraco centro" data-dica>Pense na resposta e depois vire o cartão <kbd>Espaço</kbd></p>
  <div data-notas hidden><p class="texto-fraco centro">Como foi lembrar?</p>
    <div class="avaliacao-cartao"><button class="btn btn--vermelho" data-r="errei">Errei <kbd>1</kbd></button><button class="btn btn--primario" data-r="dificil">Difícil <kbd>2</kbd></button><button class="btn btn--verde" data-r="facil">Fácil <kbd>3</kbd></button></div></div>`;

/** Liga o cartão: virar com clique ou Espaço; avaliar (1·2·3) só depois de virar — lembrar antes de ver
 *  a resposta é o que fixa o conteúdo. `teclas` acrescenta atalhos (ex.: setas). Devolve a função que desliga. */
function ligarCartao(box, avaliar, teclas = {}) {
  const card = box.querySelector('[data-flip]');
  const notas = box.querySelector('[data-notas]');
  const virar = () => { card.classList.toggle('virado'); notas.hidden = false; box.querySelector('[data-dica]').hidden = true; };
  card.onclick = virar;
  box.querySelectorAll('[data-r]').forEach((b) => { b.onclick = () => avaliar(b.dataset.r); });
  const onKey = (e) => {
    if (e.target.closest('input, textarea, select') || document.querySelector('.modal-fundo') || e.ctrlKey || e.metaKey || e.altKey) return;
    if (e.key === ' ' || e.key === 'Enter') {
      if (e.target.closest('button, a')) return; // o próprio botão já trata
      e.preventDefault(); virar();
    } else if (!notas.hidden && '123'.includes(e.key) && e.key.length === 1) avaliar(NOTAS[Number(e.key) - 1]);
    else if (teclas[e.key]) teclas[e.key]();
  };
  document.addEventListener('keydown', onKey);
  return () => document.removeEventListener('keydown', onKey);
}

/* ---------------------------------------------------------------- tutor (tire dúvidas com a IA) */
function tutor(box, mid) {
  const conversa = [];
  box.innerHTML = html`<h2 class="cartao__titulo">${icon('chat', 16)} Tire dúvidas com a IA</h2>
    <p class="texto-fraco">Pergunte sobre este material. A IA responde só com base no conteúdo do professor.</p>
    <div class="tutor__mensagens" aria-live="polite"></div>
    <form class="tutor__form"><input class="entrada" name="q" placeholder="Ex.: não entendi a parte sobre…" autocomplete="off" maxlength="600" aria-label="Sua dúvida"><button class="btn btn--escuro">Enviar</button></form>`.s;
  const lista = box.querySelector('.tutor__mensagens');
  const f = box.querySelector('form');
  const mostrar = () => {
    lista.innerHTML = html`${conversa.map((m) => html`<div class="tutor__msg tutor__msg--${m.role}">${m.text}${m.local ? html`<small>resposta automática (IA indisponível)</small>` : ''}</div>`)}`.s;
    lista.scrollTop = lista.scrollHeight;
  };
  f.addEventListener('submit', (e) => {
    e.preventDefault();
    const q = f.q.value.trim();
    if (q.length < 3) return;
    const history = conversa.slice(-6);
    conversa.push({ role: 'aluno', text: q });
    f.q.value = '';
    mostrar();
    busy(f.querySelector('button'), async () => {
      const r = await api(`/aluno/materials/${mid}/ask`, { method: 'POST', body: { question: q, history } });
      conversa.push({ role: 'tutor', text: r.answer, local: r.provider === 'simulada' });
      mostrar();
      f.q.focus();
    });
  });
}
const matItem = (m) => html`<a class="item" href="#/a/estudar/${m.id}" style="${linkCartao}"><div class="item__info">${typeIcon(m.type)}<div><strong>${m.title}</strong><small>${m.subject_name}${m.topic_name ? ' · ' + m.topic_name : ''} · ${TYPE_LABEL[m.type]}</small></div></div>
  <div style="width:120px">${m.pct >= 100 ? tag('concluida', 'Concluído') : progress(m.pct, 'verde')}</div></a>`;

/* ================================================================ A01 início */
route('a/inicio', async () => {
  page(loading());
  const d = await api('/aluno/home');
  const c = d.continue;
  const cal = await api('/calendario/proximos').catch(() => null);
  page(html`${header('Minha aprendizagem', 'Continue de onde você parou.', html`<a class="btn btn--contorno" href="#/calendario">${icon('calendario', 16)} Calendário</a>`)}
    ${cal ? html`<div class="aviso aviso--azul">${icon('calendario')}<p>${cal.class_today ? html`<strong>Hoje tem aula.</strong>` : cal.next_class_day ? html`Próximo dia de aula: <strong>${fmtDate(cal.next_class_day)}</strong>.` : 'O calendário de aulas ainda não foi publicado pela escola.'}
      ${cal.events.length ? html` Em breve: ${cal.events.slice(0, 2).map((e, i) => html`${i ? ' · ' : ''}<strong>${e.title}</strong> (${fmtDate(e.date)})`)}.` : ''} <a href="#/calendario">Ver calendário</a></p></div>` : ''}
    ${d.live_games.map((g) => html`<a class="aviso aviso--vermelho" href="#/a/jogar/${g.code}" style="${linkCartao}">${icon('jogo')}<p><strong>Jogo ao vivo agora: ${g.title}</strong> — toque para entrar (código ${g.code})</p></a>`)}
    <div class="grade grade-2">
      <section class="cartao cartao--escuro boas-vindas">
        <h2>Olá, ${S.user.name.split(' ')[0]}! Vamos aprender?</h2>
        <p class="rotulo-pequeno">Seu progresso nos materiais</p>
        <div class="linha" style="gap:18px"><span class="boas-vindas__pct">${d.progress}%</span><div style="flex:1;max-width:240px">${progress(d.progress, 'amarelo')}<small style="color:var(--texto-claro-2)">${d.materials_done} de ${d.materials_total} materiais concluídos</small></div></div>
        <div class="linha">${d.flashcards_due ? html`<a class="tag tag--amarelo" href="#/a/flashcards">${d.flashcards_due} cartões para revisar hoje</a>` : html`<span class="tag tag--verde">Revisões em dia</span>`}<span class="tag tag--azul">${d.activities.length} atividade(s) pendente(s)</span></div>
      </section>
      ${c ? html`<section class="cartao"><p class="texto-fraco">Continuar estudando</p><span class="tag tag--azul">${c.subject_name}</span>
        <h2 style="font-size:22px;font-weight:800">${c.title}</h2><p class="texto-fraco">${TYPE_LABEL[c.type]}</p>
        <div style="max-width:300px">${progress(c.pct)}</div><a class="btn btn--primario" href="#/a/estudar/${c.id}">${c.pct ? 'Continuar' : 'Começar'}</a></section>`
    : html`<section class="cartao">${empty('Nenhum material liberado ainda', 'Quando seu professor publicar materiais, eles aparecem aqui.')}</section>`}
    </div>
    <section><div class="secao__topo"><h2>Aprenda de outras formas</h2></div><div class="grade grade-4">
      ${[['mapa', 'Mapas mentais', 'Visualize os conceitos.', '#/a/materiais?tipo=mapa'], ['flashcards', 'Flashcards', 'Revise e memorize.', '#/a/flashcards'],
    ['exercicios', 'Exercícios', 'Pratique o conteúdo.', '#/a/materiais?tipo=exercicios'], ['roteiro', 'Desafios', 'Teste o que aprendeu.', '#/a/jogos']].map(([t, h, p, href]) => html`
        <a class="cartao" href="${href}" style="${linkCartao}">${typeIcon(t)}<h3 class="cartao__titulo">${h}</h3><p class="texto-fraco">${p}</p></a>`)}</div></section>
    <div class="grade grade-lateral" style="grid-template-columns:minmax(0,1fr) 420px">
      <section><div class="secao__topo"><h2>Suas próximas atividades</h2><a href="#/a/atividades">Ver todas</a></div>
        ${d.activities.length ? html`<div class="lista-itens">${d.activities.map((a) => html`<a class="item" href="#/a/atividade/${a.id}" style="${linkCartao}"><div class="item__info"><span class="tipo-icone tipo-icone--exercicios">${icon('tarefa')}</span><div><strong>${a.title}</strong><small>${a.subject_name} · ${a.questions} questões</small></div></div>${dueTag(a.due_date)}</a>`)}</div>` : empty('Tudo em dia!', 'Nenhuma atividade pendente.')}</section>
      <section><div class="secao__topo"><h2>Recomendado para você</h2></div>
        ${d.recommendations.length ? html`<div class="pilha">${d.recommendations.map((r) => html`<section class="cartao"><span class="tag tag--vermelho">Revisão sugerida</span>
          <h3 style="font-size:19px;font-weight:700">${r.topic}</h3><p class="texto-suave">Você acertou ${r.pct}% das questões deste assunto em ${r.subject}. Uma revisão rápida pode ajudar antes da próxima atividade.</p>
          ${r.material ? html`<a class="btn btn--escuro" href="#/a/estudar/${r.material.id}">Revisar com ${TYPE_LABEL[r.material.type].toLowerCase()}</a>` : ''}</section>`)}</div>`
    : html`<section class="cartao"><p class="texto-suave">Sem recomendações por enquanto. Continue praticando! As sugestões aparecem a partir dos resultados das atividades.</p><a class="btn btn--contorno" href="#/a/progresso">Ver meu plano de revisão</a></section>`}</section>
    </div>`);
}, R);

/* ================================================================ A02 matérias */
route('a/materias', async () => {
  page(loading());
  const subs = await api('/aluno/subjects');
  page(html`${header('Minhas matérias', 'Disciplinas e turmas em que você está matriculado.')}
    ${subs.length ? html`<div class="grade grade-3">${subs.map((s) => html`<a class="cartao disciplina" href="#/a/materia/${s.id}" style="${linkCartao}">
      <div class="capa" style="background:${s.color}">${s.class_name}</div><h3>${s.name}</h3><p class="texto-fraco">Prof. ${s.teacher} · ${s.materials} materiais</p>
      ${progress(s.progress, 'verde')}<div class="linha linha--entre"><span class="texto-fraco">${s.progress}% estudado</span>${s.pending ? html`<span class="tag tag--amarelo">${s.pending} atividade(s)</span>` : ''}</div></a>`)}</div>`
    : empty('Você ainda não está em nenhuma turma', 'Peça ao professor o código da turma.')}`);
}, R);

/* ================================================================ A03 matéria – assuntos */
route('a/materia/:id', async ({ id }) => {
  page(loading());
  const d = await api('/aluno/subjects/' + id);
  const docs = d.documents || [];
  const el = page(html`<a href="#/a/materias" class="link-sutil">← Minhas matérias</a>
    ${header(d.subject.name, `Prof. ${d.subject.teacher}${d.subject.description ? ' · ' + d.subject.description : ''}`)}
    <div class="grade grade-lateral">
      <div class="pilha">${d.topics.length ? d.topics.map((t) => html`<section class="assunto"><div class="assunto__topo"><h3>${t.name}</h3><span class="texto-fraco">${t.materials.filter((m) => m.pct >= 100).length}/${t.materials.length} concluídos</span></div>
        <div class="assunto__corpo">${t.materials.map((m) => html`<div class="material-linha"><div class="linha">${typeIcon(m.type)}<a href="#/a/estudar/${m.id}">${m.title}</a></div><div style="width:110px">${progress(m.pct, 'verde')}</div></div>`)}</div></section>`) : empty('Nenhum material liberado nesta matéria')}</div>
      <aside class="pilha">
        <section class="cartao"><h2 class="cartao__titulo">Arquivos do professor</h2>${docs.length ? html`<ul class="lista-simples">${docs.map(arquivoLinha)}</ul>` : html`<p class="texto-fraco">Nenhum arquivo disponível.</p>`}</section>
        <section class="cartao"><h2 class="cartao__titulo">Atividades</h2>${d.activities.length ? html`<ul class="lista-simples">${d.activities.map((a) => html`<li><a href="#/a/${a.sub_status ? 'resultado' : 'atividade'}/${a.id}">${a.title}</a>${a.sub_status ? tag(a.sub_status === 'corrigida' && a.published ? 'corrigida' : 'entregue', a.score != null ? nota((10 * a.score) / a.points) : 'Entregue') : dueTag(a.due_date)}</li>`)}</ul>` : html`<p class="texto-fraco">Nenhuma atividade.</p>`}</section>
      </aside>
    </div>`);
  ligarDownloads(el);
}, R);

/* ================================================================ materiais de estudo */
route('a/materiais', async (_, q) => {
  page(loading());
  const [mats, subs] = await Promise.all([api('/aluno/materials'), api('/aluno/subjects')]);
  const el = page(html`${header('Materiais de estudo', 'Resumos, mapas mentais, flashcards e exercícios liberados pelos professores.')}
    <div class="filtros"><input class="entrada entrada--busca" id="q" placeholder="Buscar…">
      <select class="entrada" id="disc"><option value="">Todas as matérias</option>${subs.map((s) => html`<option value="${s.id}">${s.name}</option>`)}</select>
      <select class="entrada" id="tipo"><option value="">Todos os tipos</option>${Object.entries(TYPE_LABEL).map(([k, v]) => html`<option value="${k}" ${k === q.tipo ? 'selected' : ''}>${v}</option>`)}</select></div>
    ${mats.length ? html`<div class="lista-itens" id="lista">${mats.map((m) => html`<div data-t="${m.title.toLowerCase()}" data-d="${m.subject_id}" data-tp="${m.type}">${matItem(m)}</div>`)}</div>` : empty('Nenhum material liberado ainda')}`);
  const filtrar = () => {
    const t = el.querySelector('#q').value.toLowerCase(), d = el.querySelector('#disc').value, tp = el.querySelector('#tipo').value;
    el.querySelectorAll('#lista > div').forEach((x) => { x.hidden = (t && !x.dataset.t.includes(t)) || (d && x.dataset.d !== d) || (tp && x.dataset.tp !== tp); });
  };
  ['#q', '#disc', '#tipo'].forEach((s) => el.querySelector(s).addEventListener('input', filtrar));
  filtrar();
}, R);

/* ================================================================ A04–A07 estudar */
const salvarProgresso = (id, pct) => api(`/aluno/materials/${id}/progress`, { method: 'POST', body: { pct } }).catch(() => {});

route('a/estudar/:id', async ({ id }) => {
  page(loading());
  const m = await api('/aluno/materials/' + id);
  const el = page(html`<a href="#/a/materia/${m.subject_id}" class="link-sutil">← ${m.subject_name}</a>
    ${header(m.title, `${TYPE_LABEL[m.type]}${m.topic_name ? ' · ' + m.topic_name : ''}`)}
    <div class="grade grade-lateral"><section id="estudo"></section>
      <aside class="pilha"><section class="cartao"><h2 class="cartao__titulo">Seu progresso</h2><div id="pct">${progress(m.pct, 'verde')}</div><p class="texto-fraco" id="pct-txt">${m.pct}% concluído</p></section>
        ${m.document ? html`<section class="cartao"><h2 class="cartao__titulo">Arquivo original</h2><p class="texto-fraco">Este material foi gerado a partir do arquivo do professor.</p><ul class="lista-simples">${arquivoLinha(m.document)}</ul></section>` : ''}
        <section class="cartao tutor" id="tutor"></section>
        ${m.siblings.length ? html`<section class="cartao"><h2 class="cartao__titulo">Estude de outras formas</h2><ul class="lista-simples">${m.siblings.map((s) => html`<li><span class="linha">${typeIcon(s.type)}<a href="#/a/estudar/${s.id}">${s.title}</a></span></li>`)}</ul></section>` : ''}</aside></div>`);
  const box = el.querySelector('#estudo');
  tutor(el.querySelector('#tutor'), id);
  ligarDownloads(el);
  let pct = m.pct;
  const marcar = (p) => {
    if (p <= pct) return;
    pct = p;
    salvarProgresso(id, p);
    const barra = el.querySelector('#pct');
    if (!barra) return; // o aluno já saiu da página
    barra.innerHTML = progress(p, 'verde').s;
    el.querySelector('#pct-txt').textContent = `${p}% concluído`;
  };

  if (m.type === 'resumo' || m.type === 'roteiro') {
    box.innerHTML = html`<div class="cartao">${resumoView(m.content)}</div><button class="btn btn--verde" data-ok style="margin-top:16px">${icon('check', 16)} Marcar como estudado</button>`.s;
    box.querySelector('[data-ok]').onclick = () => { marcar(100); toast('Ótimo! Material concluído.'); };
    const onScroll = () => {
      const r = box.getBoundingClientRect();
      const lido = Math.min(100, Math.round((100 * (window.innerHeight - r.top)) / r.height));
      if (lido > 0) marcar(Math.min(90, Math.floor(lido / 10) * 10));
    };
    window.addEventListener('scroll', onScroll);
    S.cleanup.push(() => window.removeEventListener('scroll', onScroll));
    onScroll();
  }

  if (m.type === 'mapa') {
    box.innerHTML = html`<div class="cartao">${mapaSvg(m.content)}<p class="texto-fraco">Leia do centro para fora. Clique em um ramo para destacá-lo.</p></div>
      <details class="cartao" style="margin-top:16px"><summary style="cursor:pointer;font-weight:700">Ver em formato de lista</summary>${mapaArvore(m.content)}</details>`.s;
    marcar(100);
    box.querySelectorAll('.mn').forEach((g) => g.addEventListener('click', () => {
      box.querySelectorAll('.mn').forEach((x) => x.classList.toggle('sel', x.dataset.b === g.dataset.b));
    }));
  }

  if (m.type === 'flashcards') {
    const cards = m.content.cards;
    let i = 0, soltar = () => {}, enviando = false;
    onLeave(() => soltar());
    const show = () => {
      soltar();
      box.innerHTML = html`<div class="cartao pilha">${cartaoHtml(cards[i].front, cards[i].back,
        html`<div class="linha linha--entre"><span class="texto-fraco">Cartão ${i + 1} de ${cards.length}</span>${progress(((i + 1) * 100) / cards.length)}</div>`)}
        <div class="linha linha--entre"><button class="btn btn--link" data-prev ${i ? '' : 'disabled'}>← Anterior</button><span class="texto-fraco atalhos">Atalhos: Espaço vira · 1 2 3 avaliam · ← → navegam</span><button class="btn btn--link" data-next>Pular →</button></div></div>`.s;
      const prev = () => { if (i) { i--; show(); } };
      const next = () => { i = (i + 1) % cards.length; show(); };
      box.querySelector('[data-prev]').onclick = prev;
      box.querySelector('[data-next]').onclick = next;
      soltar = ligarCartao(box, async (rating) => {
        if (enviando) return;
        enviando = true;
        try {
          await api('/aluno/flashcards/review', { method: 'POST', body: { material_id: Number(id), card: i, rating } });
          marcar(Math.round(((i + 1) * 100) / cards.length));
          if (i + 1 >= cards.length) { toast('Baralho concluído! Os cartões voltam na data de revisão.'); i = 0; } else i++;
          show();
        } catch (e) { toast(e.message, 'erro'); } finally { enviando = false; }
      }, { ArrowLeft: prev, ArrowRight: next });
    };
    show();
  }

  if (m.type === 'glossario') {
    box.innerHTML = html`<div class="cartao pilha">
      <div class="linha linha--entre"><input class="entrada entrada--busca" data-busca placeholder="Buscar termo…" style="max-width:320px" aria-label="Buscar termo">
        <label class="check"><input type="checkbox" data-teste> Modo teste: esconder as definições</label></div>
      <p class="texto-fraco" data-teste-dica hidden>Leia o termo, tente explicar com suas palavras e toque na definição para conferir.</p>
      ${glossarioView(m.content)}
      <div><button class="btn btn--verde" data-ok>${icon('check', 16)} Marcar como estudado</button></div></div>`.s;
    const lista = box.querySelector('.glossario');
    box.querySelector('[data-ok]').onclick = () => { marcar(100); toast('Ótimo! Glossário concluído.'); };
    const vistos = new Set();
    box.querySelector('[data-busca]').oninput = (e) => {
      const t = e.target.value.trim().toLowerCase();
      lista.querySelectorAll('[data-termo]').forEach((x) => { x.hidden = !!t && !x.dataset.termo.includes(t) && !x.textContent.toLowerCase().includes(t); });
    };
    box.querySelector('[data-teste]').onchange = (e) => {
      lista.classList.toggle('glossario--teste', e.target.checked);
      box.querySelector('[data-teste-dica]').hidden = !e.target.checked;
      lista.querySelectorAll('dd').forEach((d) => {
        d.classList.remove('revelado');
        if (e.target.checked) { d.tabIndex = 0; d.setAttribute('role', 'button'); d.setAttribute('aria-label', 'Mostrar definição'); } else { d.removeAttribute('tabindex'); d.removeAttribute('role'); d.removeAttribute('aria-label'); }
      });
    };
    const revelar = (dd) => {
      if (!dd || !lista.classList.contains('glossario--teste')) return;
      dd.classList.add('revelado');
      dd.removeAttribute('aria-label');
      vistos.add(dd.dataset.def);
      marcar(Math.round((100 * vistos.size) / m.content.terms.length));
    };
    lista.addEventListener('click', (e) => revelar(e.target.closest('dd')));
    lista.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); revelar(e.target.closest('dd')); } });
    marcar(50); // abriu e leu a lista; o modo teste completa o progresso
  }

  if (m.type === 'exercicios') {
    const qs = m.content.questions;
    const res = {};
    const show = () => {
      box.innerHTML = html`<div class="pilha">${qs.map((q, i) => html`<div class="questao" data-q="${i}"><span class="tag tag--cinza">Questão ${i + 1} de ${qs.length}</span>
        <p class="questao__enunciado">${q.statement}</p>
        ${q.kind === 'discursiva' ? html`<textarea class="entrada" data-txt="${i}" placeholder="Escreva sua resposta…">${res[i]?.texto || ''}</textarea>`
          : html`<div class="alternativas">${q.options.map((o, j) => {
            const r = res[i];
            const cls = r ? (j === r.answer ? 'alternativa--correta' : j === r.choice ? 'alternativa--errada' : '') : '';
            return html`<label class="alternativa ${cls} ${r ? 'desabilitada' : ''}"><input type="radio" name="q${i}" value="${j}" ${r ? 'disabled' : ''} ${r && r.choice === j ? 'checked' : ''}><strong>${L[j]})</strong> ${o}</label>`;
          })}</div>`}
        ${res[i]?.locked ? aviso(res[i].explanation, 'amarelo') : res[i] ? html`<div class="aviso aviso--${res[i].correct === false ? 'vermelho' : 'verde'}">${icon(res[i].correct === false ? 'alerta' : 'check')}<p><strong>${res[i].correct === true ? 'Correto!' : res[i].correct === false ? 'Não foi dessa vez.' : 'Compare com a resposta esperada:'}</strong> ${res[i].correct === null ? res[i].expected + ' — ' : ''}${res[i].explanation || ''}</p></div>`
          : html`<button class="btn btn--escuro btn--p" data-conferir="${i}">Conferir resposta</button>`}</div>`)}
        <div class="cartao"><strong>${Object.values(res).filter((r) => r.correct).length} acerto(s)</strong> de ${qs.filter((q) => q.kind !== 'discursiva').length} objetivas · ${Object.keys(res).length}/${qs.length} respondidas
          ${Object.keys(res).length === qs.length ? html` <button class="btn btn--link" data-refazer>Refazer</button>` : ''}</div></div>`.s;
      box.querySelectorAll('[data-conferir]').forEach((b) => {
        b.onclick = async () => {
          const i = Number(b.dataset.conferir);
          const q = qs[i];
          let answer;
          if (q.kind === 'discursiva') answer = box.querySelector(`[data-txt="${i}"]`).value;
          else {
            const sel = box.querySelector(`input[name=q${i}]:checked`);
            if (!sel) return toast('Escolha uma alternativa', 'erro');
            answer = Number(sel.value);
          }
          const r = await api(`/aluno/materials/${id}/check`, { method: 'POST', body: { index: i, answer } });
          res[i] = r.locked ? { ...r } : { ...r, choice: answer, texto: q.kind === 'discursiva' ? answer : '' };
          marcar(Math.round((Object.keys(res).length * 100) / qs.length));
          show();
          box.querySelector(`[data-q="${i}"]`).scrollIntoView({ block: 'nearest' });
        };
      });
      box.querySelector('[data-refazer]')?.addEventListener('click', () => { Object.keys(res).forEach((k) => delete res[k]); show(); });
    };
    show();
  }
}, R);

/* ================================================================ flashcards e revisão */
route('a/flashcards', async () => {
  page(loading());
  const decks = await api('/aluno/flashcards/due');
  const total = decks.reduce((a, d) => a + d.due, 0);
  const el = page(html`${header('Flashcards e revisão', 'Repetição espaçada: os cartões que você acha fáceis voltam com menos frequência.')}
    <div class="grade grade-3">${kpi('Para revisar hoje', pad2(total), '', total ? 'vermelho' : 'verde')}${kpi('Baralhos', pad2(decks.length))}${kpi('Cartões dominados', pad2(decks.reduce((a, d) => a + d.mastered, 0)), 'acertou várias vezes seguidas', 'verde')}</div>
    ${total ? html`<button class="btn btn--primario btn--g" data-sessao>Começar revisão de hoje (${total} cartões)</button>` : aviso('Revisões em dia! Volte amanhã ou estude um baralho livremente.', 'verde')}
    <div id="sessao"></div>
    ${decks.length ? html`<div class="lista-itens">${decks.map((d) => html`<a class="item" href="#/a/estudar/${d.id}" style="${linkCartao}"><div class="item__info">${typeIcon('flashcards')}<div><strong>${d.title}</strong><small>${d.subject_name} · ${d.total} cartões · ${d.mastered} dominados</small></div></div>
      ${d.due ? html`<span class="tag tag--amarelo">${d.due} para hoje</span>` : tag('concluida', 'Em dia')}</a>`)}</div>` : empty('Nenhum baralho liberado ainda')}`);
  el.querySelector('[data-sessao]')?.addEventListener('click', (ev) => {
    ev.currentTarget.hidden = true;
    const fila = decks.flatMap((d) => d.cards.map((c) => ({ ...c, material_id: d.id, deck: d.title })));
    const placar = { errei: 0, dificil: 0, facil: 0 };
    let i = 0, soltar = () => {}, enviando = false;
    onLeave(() => soltar());
    const box = el.querySelector('#sessao');
    const show = () => {
      soltar();
      if (i >= fila.length) {
        box.innerHTML = html`<section class="cartao centro" style="max-width:640px"><div class="feedback__icone" style="background:var(--verde);margin:0 auto">✓</div>
          <h2 class="cartao__titulo">Sessão concluída! Ótimo trabalho.</h2>
          <p class="texto-suave">${placar.facil} fácil · ${placar.dificil} difícil · ${placar.errei} para rever.${placar.errei ? ' Os cartões que você errou voltam daqui a alguns minutos.' : ''}</p></section>`.s;
        return;
      }
      const c = fila[i];
      box.innerHTML = html`<div class="cartao pilha" style="max-width:640px">${cartaoHtml(c.front, c.back,
        html`<div class="linha linha--entre"><span class="texto-fraco">${c.deck}</span><span class="texto-fraco">${i + 1}/${fila.length}</span></div>${progress((100 * i) / fila.length)}`)}</div>`.s;
      soltar = ligarCartao(box, async (rating) => {
        if (enviando) return;
        enviando = true;
        try {
          await api('/aluno/flashcards/review', { method: 'POST', body: { material_id: c.material_id, card: c.index, rating } });
          placar[rating]++;
          i++; show();
        } catch (e) { toast(e.message, 'erro'); } finally { enviando = false; }
      });
      box.scrollIntoView({ behavior: 'smooth', block: 'center' });
    };
    show();
  });
}, R);

/* ================================================================ A08 atividades */
route('a/atividades', async (_, q) => {
  page(loading());
  const acts = await api('/aluno/activities');
  const aba = q.aba || 'pendentes';
  const grupos = {
    pendentes: acts.filter((a) => !a.sub_status && a.open && a.kind === 'atividade'),
    simulados: acts.filter((a) => a.kind !== 'atividade' && !a.sub_status && a.open),
    concluidas: acts.filter((a) => a.sub_status || !a.open),
  };
  const el = page(html`${header('Atividades', 'Tarefas, simulados, prazos e resultados.')}
    ${tabs([['pendentes', `Pendentes (${grupos.pendentes.length})`], ['simulados', `Simulados e provas (${grupos.simulados.length})`], ['concluidas', `Concluídas (${grupos.concluidas.length})`]], aba)}
    <div id="lista"></div>`);
  const show = (t) => {
    history.replaceState(null, '', '#/a/atividades?aba=' + t);
    const l = grupos[t];
    el.querySelector('#lista').innerHTML = (l.length ? html`<div class="lista-itens">${l.map((a) => {
      const feita = !!a.sub_status;
      const href = feita ? `#/a/resultado/${a.id}` : !a.open ? '#/a/atividades?aba=concluidas' : `#/a/atividade/${a.id}`;
      return html`<a class="item" href="${href}" style="${linkCartao}"><div class="item__info"><span class="tipo-icone tipo-icone--exercicios">${icon('tarefa')}</span><div><strong>${a.title}</strong>
        <small>${a.subject_name} · ${a.questions} questões · ${a.max_attempts} tentativa(s)${feita ? ` · entregue em ${fmtDate(a.submitted_at)}` : ''}</small></div></div>
        ${feita ? (a.score != null ? html`<span class="tag tag--${(10 * a.score) / a.points < 6 ? 'vermelho' : 'verde'}">Nota ${nota((10 * a.score) / a.points)}</span>` : tag('entregue', a.sub_status === 'entregue' ? 'Aguardando correção' : 'Nota não publicada'))
          : !a.open ? tag('encerrada', 'Não entregue') : html`${a.past_due ? html`<span class="tag tag--amarelo">Aceita com atraso</span>` : ''}${dueTag(a.due_date)}`}</a>`;
    })}</div>` : empty(t === 'concluidas' ? 'Nenhuma atividade concluída' : 'Nada pendente por aqui 🎉')).s;
  };
  bindTabs(el, show);
  show(aba);
}, R);

route('a/atividade/:id', async ({ id }) => {
  page(loading());
  const d = await api('/aluno/activities/' + id);
  const a = d.activity, sub = d.submission;
  const restam = a.max_attempts - (sub?.attempts || 0);
  if (sub && restam <= 0) return go('#/a/resultado/' + id);
  if (a.status !== 'publicada' || (a.past_due && !a.accept_late)) {
    return page(html`<a href="#/a/atividades" class="link-sutil">← Atividades</a>${header(a.title, a.subject_name)}
      ${aviso('O prazo desta atividade terminou. Se precisar de uma nova chance, fale com o seu professor ou abra um chamado em Atendimento.', 'amarelo')}
      ${sub ? html`<a class="btn btn--contorno" href="#/a/resultado/${id}">Ver minha entrega</a>` : ''}`);
  }
  const el = page(html`<a href="#/a/atividades" class="link-sutil">← Atividades</a>
    ${header(a.title, `${a.subject_name} · ${d.questions.length} questões · ${a.points} pontos`, dueTag(a.due_date))}
    ${a.instructions ? aviso(a.instructions) : ''}
    ${sub ? aviso(`Você já entregou esta atividade. Ainda tem ${restam} tentativa(s); a nova entrega substitui a anterior.`, 'amarelo') : ''}
    ${a.past_due ? aviso('O prazo já passou: a entrega será registrada como atrasada.', 'amarelo') : ''}
    <form class="pilha" id="f">${d.questions.map((q, i) => html`<div class="questao"><span class="tag tag--cinza">Questão ${i + 1}</span><p class="questao__enunciado">${q.statement}</p>
      ${q.kind === 'discursiva' ? html`<textarea class="entrada" name="q${q.id}" rows="4" placeholder="Sua resposta…">${sub?.answers?.[q.id] || ''}</textarea>`
        : html`<div class="alternativas">${q.options.map((o, j) => html`<label class="alternativa"><input type="radio" name="q${q.id}" value="${j}"><strong>${L[j]})</strong> ${o}</label>`)}</div>`}</div>`)}
      <div class="cartao linha linha--entre"><span class="texto-suave" data-resp>0 de ${d.questions.length} respondidas</span><button class="btn btn--primario btn--g" type="submit">Enviar respostas</button></div></form>`);
  const f = el.querySelector('#f');
  const coletar = () => {
    const ans = {};
    d.questions.forEach((q) => {
      if (q.kind === 'discursiva') { const v = f['q' + q.id].value.trim(); if (v) ans[q.id] = v; } else {
        const s = f.querySelector(`[name=q${q.id}]:checked`);
        if (s) ans[q.id] = Number(s.value);
      }
    });
    return ans;
  };
  f.addEventListener('input', () => { el.querySelector('[data-resp]').textContent = `${Object.keys(coletar()).length} de ${d.questions.length} respondidas`; });
  f.addEventListener('submit', async (e) => {
    e.preventDefault();
    const ans = coletar();
    const faltam = d.questions.length - Object.keys(ans).length;
    if (faltam && !(await confirmar(`Ainda há ${faltam} questão(ões) em branco. Enviar mesmo assim?`, { ok: 'Enviar' }))) return;
    await busy(f.querySelector('[type=submit]'), async () => {
      const r = await api(`/aluno/activities/${id}/submit`, { method: 'POST', body: { answers: ans } });
      toast(r.pending_review ? 'Entregue! A nota sai depois da correção do professor.' : 'Entregue!');
      go('#/a/resultado/' + id);
    });
  });
}, R);

/* ================================================================ A09 resultado */
route('a/resultado/:id', async ({ id }) => {
  page(loading());
  const r = await api(`/aluno/activities/${id}/result`);
  const a = r.activity;
  if (!r.published) {
    return page(html`<a href="#/a/atividades" class="link-sutil">← Atividades</a>${header(a.title, a.subject_name)}
      <section class="cartao centro" style="max-width:560px"><div class="feedback__icone" style="background:var(--azul);margin:0 auto">✓</div><h2 class="cartao__titulo">Atividade entregue em ${fmtDate(r.submitted_at)}</h2>
      <p class="texto-suave">${r.status === 'entregue' ? 'Seu professor está corrigindo as questões discursivas.' : 'A correção foi feita, mas a nota ainda não foi publicada.'} Você será notificado quando o resultado sair.</p>
      <a class="btn btn--contorno" href="#/a/atividades">Voltar</a></section>`);
  }
  const n10 = (10 * r.score) / a.points;
  const cor = n10 >= 7 ? 'verde' : n10 >= 5 ? 'amarelo' : 'vermelho';
  const podeRefazer = r.can_retry;
  page(html`<a href="#/a/atividades" class="link-sutil">← Atividades</a>
    ${header('Resultado da atividade', `${a.title} · ${a.subject_name}`, podeRefazer ? html`<a class="btn btn--contorno" href="#/a/atividade/${id}">Tentar novamente (${a.max_attempts - r.attempts} restante)</a>` : '')}
    <div class="grade grade-lateral-e">
      <section class="cartao centro"><div class="nota-circulo" style="border-color:var(--${cor === 'amarelo' ? 'amarelo' : cor})"><div><strong>${nota(r.score)}</strong><br><small>DE ${nota(a.points)}</small></div></div>
        <p><strong>${r.correct}</strong> de ${r.items.length} questões corretas</p>${r.late ? html`<p><span class="tag tag--amarelo">Entregue com atraso</span></p>` : ''}
        ${r.answers_released ? '' : aviso('As respostas certas aparecem quando você não tiver mais tentativas ou quando o prazo terminar. Por enquanto, veja quais você acertou e tente de novo.', 'amarelo')}${r.feedback ? html`<div class="aviso aviso--azul"><p><strong>Comentário do professor:</strong> ${r.feedback}</p></div>` : ''}
        ${r.recommendations.length ? html`<div style="text-align:left"><p class="rotulo-pequeno" style="color:var(--texto-fraco)">Para revisar</p><ul class="lista-simples">${r.recommendations.map((m) => html`<li><a href="#/a/estudar/${m.id}">${m.title}</a>${typeIcon(m.type)}</li>`)}</ul></div>` : ''}</section>
      <div class="pilha">${r.items.map((q, i) => {
        const ok = (q.score ?? 0) >= 0.5;
        return html`<div class="questao"><div class="linha linha--entre"><span class="tag tag--cinza">Questão ${i + 1} · ${q.topic}</span><span class="tag tag--${ok ? 'verde' : 'vermelho'}">${q.kind === 'discursiva' ? `${Math.round((q.score || 0) * 100)}%` : ok ? 'Correta' : 'Incorreta'}</span></div>
          <p class="questao__enunciado">${q.statement}</p>
          ${q.kind === 'discursiva' ? html`<div class="resposta-aluno">${q.given || '(em branco)'}</div>${q.expected ? html`<p class="texto-fraco"><strong>Resposta esperada:</strong> ${q.expected}</p>` : ''}`
            : html`<div class="alternativas">${q.options.map((o, j) => {
              const minha = q.given != null && j === Number(q.given);
              const cls = q.answer != null ? (j === q.answer ? 'alternativa--correta' : minha ? 'alternativa--errada' : '') : (minha ? (ok ? 'alternativa--correta' : 'alternativa--errada') : '');
              return html`<div class="alternativa ${cls}"><strong>${L[j]})</strong> ${o}${minha ? html` <span class="texto-fraco">(sua resposta)</span>` : ''}</div>`;
            })}</div>`}
          ${q.feedback ? html`<p class="texto-suave"><strong>Feedback:</strong> ${q.feedback}</p>` : ''}</div>`;
      })}</div>
    </div>`);
}, R);

/* ================================================================ A11 meu progresso + plano de revisão */
route('a/progresso', async () => {
  page(loading());
  const p = await api('/aluno/progress');
  const el = page(html`${header('Meu progresso', 'Histórico, evolução das notas e tópicos que merecem mais atenção.')}
    <div class="grade grade-4">${kpi('Média geral', nota(p.avg), 'escala de 0 a 10')}${kpi('Atividades entregues', `${p.delivered}/${p.total}`)}
      ${kpi('Materiais concluídos', `${p.materials_done.length}/${p.materials_total}`)}${kpi('Assuntos para reforçar', pad2(p.attention.length), '', p.attention.length ? 'vermelho' : 'verde')}</div>
    <div class="grade grade-2">
      <section class="cartao"><h2 class="cartao__titulo">Evolução das notas</h2>${lineChart(p.evolution)}</section>
      <section class="cartao"><h2 class="cartao__titulo">Média por matéria</h2>${bars(p.subjects.map((s) => ({ label: s.name, value: s.avg })))}</section>
      <section class="cartao"><h2 class="cartao__titulo">Acerto por assunto</h2>${hbars(p.topics.map((t) => ({ label: `${t.topic} · ${t.subject}`, value: t.pct })))}</section>
      <section class="cartao cartao--destaque" id="plano"><h2 class="cartao__titulo">${icon('ia', 16)} Plano de revisão sugerido</h2>
        <p class="texto-suave">A IA monta um roteiro com base nos seus erros recentes e nos materiais liberados pelos professores. É uma recomendação de estudo — não uma avaliação sobre você.</p>
        <button class="btn btn--escuro" data-plano>Gerar meu plano de revisão</button></section>
    </div>
    <section><div class="secao__topo"><h2>Histórico de atividades</h2></div>${p.history.length ? html`<div class="tabela-caixa"><table class="tabela"><thead><tr><th>Atividade</th><th>Matéria</th><th>Entregue</th><th>Nota</th></tr></thead><tbody>
      ${p.history.map((a) => html`<tr><td><a href="#/a/resultado/${a.id}">${a.title}</a></td><td>${a.subject_name}</td><td>${fmtDate(a.submitted_at)}</td><td>${a.score == null ? tag('entregue', 'Aguardando') : nota((10 * a.score) / a.points)}</td></tr>`)}</tbody></table></div>` : empty('Nenhuma entrega ainda')}</section>
    ${p.games.length ? html`<section class="cartao"><h2 class="cartao__titulo">Jogos</h2><ul class="lista-simples">${p.games.map((g) => html`<li><span>${g.title}</span><span>${g.pos}º de ${g.players} · <strong>${g.score} pts</strong></span></li>`)}</ul></section>` : ''}`);
  el.querySelector('[data-plano]').onclick = (e) => busy(e.currentTarget, async () => {
    const plano = await api('/aluno/study-plan', { method: 'POST' });
    el.querySelector('#plano').innerHTML = html`<div class="cartao__topo"><h2 class="cartao__titulo">${icon('ia', 16)} Seu plano de revisão</h2><span class="tag tag--${plano.provider !== 'simulada' ? 'verde' : 'cinza'}">${plano.provider !== 'simulada' ? 'IA' : 'sugestão automática'}</span></div>
      <p class="texto-suave">${plano.intro}</p>
      <div>${plano.steps.map((s, i) => html`<div class="plano-passo"><span class="fluxo__n">${i + 1}</span><div><strong>${s.title}</strong><p class="texto-suave">${s.detail}</p></div></div>`)}</div>
      ${plano.materials.length ? html`<p class="rotulo-pequeno" style="color:var(--texto-fraco)">Materiais para usar</p><div class="chips">${plano.materials.map((m) => html`<a class="chip" href="#/a/estudar/${m.id}">${m.title}</a>`)}</div>` : ''}
      <p class="texto-fraco">Este plano é uma sugestão. Seu professor continua acompanhando sua aprendizagem.</p>`.s;
  });
}, R);
