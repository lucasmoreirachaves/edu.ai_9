/* EDU.AI – Estúdio de IA (P09), Editor de materiais (P10–P13) e Publicação (P14) */
import {
  TYPE_LABEL, api, aviso, bindSeg, busy, confirmar, empty, fmtDate, fmtDateTime, go, header, html, icon,
  loading, modal, onLeave, page, route, segmented, tabs, tag, toast, typeIcon,
} from './core.js';
import { bindFlip, flashcard, glossarioView, mapaArvore, mapaSvg, questoesPreview, resumoView } from './viewers.js';

const R = { role: 'professor' };

const OPCOES = [
  { id: 'resumo-s', kind: 'resumo', variant: 'simplificado', t: 'Resumo simplificado', d: 'Versão curta para estudo rápido', on: true },
  { id: 'resumo-a', kind: 'resumo', variant: 'aprofundado', t: 'Resumo aprofundado', d: 'Texto completo com exemplos' },
  { id: 'mapa', kind: 'mapa', t: 'Mapa mental', d: 'Conceitos conectados visualmente', on: true },
  { id: 'flash', kind: 'flashcards', t: 'Flashcards', d: 'Cartões para memorizar', on: true, count: 8 },
  { id: 'lista', kind: 'exercicios', variant: 'lista', t: 'Lista de exercícios', d: 'Questões para praticar', count: 5, open: 1 },
  { id: 'simulado', kind: 'exercicios', variant: 'simulado', t: 'Simulado ou avaliação', d: 'Prova com correção automática', count: 10 },
  { id: 'jogo', kind: 'exercicios', variant: 'jogo', t: 'Questionário para jogo', d: 'Perguntas curtas para jogos ao vivo', count: 8 },
  { id: 'roteiro', kind: 'roteiro', t: 'Roteiro de revisão', d: 'Plano de estudo antes da prova' },
  { id: 'glossario', kind: 'glossario', t: 'Glossário', d: 'Termos-chave com definição e exemplo', count: 10 },
];

/* ================================================================ P09 Estúdio de IA */
route('p/estudio', async (_, q) => {
  page(loading());
  const [docs, ia] = await Promise.all([api('/prof/documents'), api('/ia/status')]);
  const prontos = docs.filter((d) => d.status === 'concluido');
  const docSel = Number(q.doc) || prontos.find((d) => String(d.subject_id) === q.disciplina)?.id || prontos[0]?.id;
  const el = page(html`${header('Estúdio de IA', 'Transforme o conteúdo em diferentes recursos de aprendizagem. Gere vários formatos do mesmo documento sem reenviar o arquivo.')}
    ${ia.provider !== 'simulada' ? '' : aviso(ia.online
    ? html`O Ollama está ativo, mas o modelo <strong>${ia.model}</strong> não está instalado. Rode <code>ollama pull ${ia.model}</code>. Enquanto isso, a geração usa o modo local simplificado.`
    : html`Ollama não encontrado em <code>${ia.url}</code>. A geração usa o modo local simplificado (resultado mais básico). Instale o Ollama e rode <code>ollama pull ${ia.model}</code> para a IA completa.`, 'amarelo')}
    ${prontos.length ? html`<form class="grade grade-lateral-e" style="grid-template-columns:360px minmax(0,1fr)" id="f">
      <div class="pilha">
        <section class="cartao"><div class="cartao__topo"><h2 class="cartao__titulo">1. Origem e público</h2></div>
          <label class="campo"><span>Material de origem</span><select class="entrada" name="document_id">${prontos.map((d) => html`<option value="${d.id}" ${d.id === docSel ? 'selected' : ''}>${d.title} · ${d.subject_name}</option>`)}</select></label>
          <label class="campo"><span>Assunto dos materiais gerados</span><select class="entrada" name="topic_id"></select></label>
          <label class="campo"><span>Nível de ensino</span><select class="entrada" name="level">${['Ensino Fundamental I', 'Ensino Fundamental II', 'Ensino Médio', 'Pré-vestibular', 'Ensino Técnico', 'Ensino Superior'].map((n) => html`<option ${n === 'Ensino Fundamental II' ? 'selected' : ''}>${n}</option>`)}</select></label>
          <div class="campo"><span>Nível de dificuldade</span>${segmented('dif', [['facil', 'Fácil'], ['media', 'Médio'], ['dificil', 'Difícil']], 'media')}</div>
          <div data-paginas hidden><div class="campos-2"><label class="campo"><span>Da página</span><input class="entrada" type="number" min="1" name="page_from" placeholder="1"></label>
            <label class="campo"><span>Até a página</span><input class="entrada" type="number" min="1" name="page_to" placeholder="última"></label></div>
            <p class="texto-fraco" data-paginas-info style="margin-top:6px"></p></div>
          <label class="campo"><span>Instruções extras (opcional)</span><textarea class="entrada" name="notes" placeholder="Ex.: usar exemplos do cotidiano"></textarea></label>
          <button type="submit" class="btn btn--primario btn--bloco">${icon('ia', 16)} Gerar materiais selecionados</button>
        </section>
        ${aviso('A IA cria um rascunho. Você revisa e edita antes de publicar — nada vai para os alunos automaticamente.')}
      </div>
      <section class="pilha">
        <h2 class="cartao__titulo">2. Escolha o que gerar</h2>
        <div class="grade grade-4">${OPCOES.map((o) => html`<label class="opcao"><input type="checkbox" name="op-${o.id}" ${o.on ? 'checked' : ''}>${typeIcon(o.kind)}<strong>${o.t}</strong><small>${o.d}</small>
          ${o.count ? html`<span class="opcao__extra">Qtd. <input class="entrada" type="number" min="1" max="30" name="n-${o.id}" value="${o.count}">${o.open != null ? html` discursivas <input class="entrada" type="number" min="0" max="10" name="o-${o.id}" value="${o.open}">` : ''}</span>` : ''}</label>`)}</div>
        <div class="cartao texto-suave"><span data-contador></span> · o resultado abre no editor para revisão</div>
        <section class="cartao" id="jobs" hidden><div class="cartao__topo"><h2 class="cartao__titulo">Gerações em andamento</h2></div><div id="jobs-lista"></div></section>
        <section class="cartao"><div class="cartao__topo"><h2 class="cartao__titulo">Gerações recentes</h2></div><div id="recentes">${loading()}</div></section>
      </section>
    </form>` : empty('Nenhum documento pronto', 'Envie um PDF, DOCX ou texto na Biblioteca. Quando o processamento terminar, ele aparece aqui.', html`<a class="btn btn--primario" href="#/p/biblioteca">Ir para a biblioteca</a>`)}`);
  if (!prontos.length) return;
  const f = el.querySelector('#f');
  const dif = bindSeg(el, 'dif');
  const contar = () => {
    const n = OPCOES.filter((o) => f['op-' + o.id].checked).length;
    el.querySelector('[data-contador]').textContent = `${n} ${n === 1 ? 'recurso selecionado' : 'recursos selecionados'}`;
  };
  f.addEventListener('change', contar);
  contar();
  const loadTopics = async () => {
    const d = prontos.find((x) => x.id === Number(f.document_id.value));
    const s = await api('/prof/subjects/' + d.subject_id);
    f.topic_id.innerHTML = html`<option value="">${d.topic_name ? 'Mesmo do documento' : 'Sem assunto'}</option>${s.topics.map((t) => html`<option value="${t.id}">${t.name}</option>`)}`.s;
  };
  const paginas = () => {
    const d = prontos.find((x) => x.id === Number(f.document_id.value));
    const box = el.querySelector('[data-paginas]');
    box.hidden = !(d && d.pages > 1);
    f.page_from.value = ''; f.page_to.value = '';
    if (box.hidden) return;
    f.page_from.max = f.page_to.max = d.pages;
    el.querySelector('[data-paginas-info]').textContent = d.chars > ia.max_chars
      ? `Documento com ${d.pages} páginas. A IA lê o documento inteiro em partes e condensa em notas antes de gerar (a primeira geração demora mais). Para focar num capítulo, escolha o intervalo.`
      : `Documento com ${d.pages} páginas — cabe inteiro numa geração. Deixe vazio para usar todas.`;
  };
  f.document_id.onchange = () => { loadTopics(); paginas(); };
  paginas();
  loadTopics();

  const renderJobs = (box, js) => {
    box.innerHTML = js.length ? html`${js.map((j) => {
      const o = JSON.parse(j.options || '{}');
      const label = TYPE_LABEL[j.kind] + (o.variant ? ` (${o.variant})` : '');
      return html`<div class="job"><div class="linha">${typeIcon(j.kind)}<div><strong>${j.material_title || label}</strong><div class="texto-fraco">${j.document_title} · ${fmtDateTime(j.created_at)}${j.ai_source ? ' · ' + j.ai_source : ''}</div>${j.error ? html`<div class="texto-vermelho texto-fraco">${j.error}</div>` : ''}</div></div>
        ${j.status === 'concluido' ? html`<a class="btn btn--escuro btn--p" href="#/p/material/${j.material_id}">Revisar</a>` : j.status === 'erro' ? tag('erro') : html`<span class="linha texto-fraco"><span class="spinner"></span> ${j.status === 'pendente' ? 'Na fila' : 'Gerando…'}</span>`}</div>`;
    })}`.s : '<p class="texto-fraco">Nenhuma geração ainda.</p>';
  };
  const recentes = async () => renderJobs(el.querySelector('#recentes'), await api('/prof/studio/jobs'));
  recentes();

  let timer;
  onLeave(() => clearTimeout(timer));
  const acompanhar = async (ids) => {
    const box = el.querySelector('#jobs');
    box.hidden = false;
    const js = await api('/prof/studio/jobs?ids=' + ids.join(','));
    renderJobs(el.querySelector('#jobs-lista'), js);
    if (js.some((j) => ['pendente', 'processando'].includes(j.status))) timer = setTimeout(() => acompanhar(ids), 2000);
    else { toast('Materiais gerados! Revise antes de publicar.'); recentes(); }
  };

  f.addEventListener('submit', async (e) => {
    e.preventDefault();
    const items = OPCOES.filter((o) => f['op-' + o.id].checked).map((o) => ({
      kind: o.kind, variant: o.variant || '', count: o.count ? Number(f['n-' + o.id].value) : null,
      open_count: o.open != null ? Number(f['o-' + o.id].value) : null,
    }));
    if (!items.length) return toast('Escolha pelo menos um formato', 'erro');
    await busy(f.querySelector('[type=submit]'), async () => {
      const r = await api('/prof/studio/generate', { method: 'POST', body: {
        document_id: Number(f.document_id.value), items, level: f.level.value, difficulty: dif(), notes: f.notes.value,
        topic_id: f.topic_id.value ? Number(f.topic_id.value) : null,
        page_from: f.page_from.value ? Number(f.page_from.value) : null, page_to: f.page_to.value ? Number(f.page_to.value) : null,
      } });
      toast(`${items.length} geração(ões) iniciada(s)`);
      acompanhar(r.jobs);
      el.querySelector('#jobs').scrollIntoView({ behavior: 'smooth', block: 'center' });
    });
  });
}, R);

/* ================================================================ lista de materiais (Editor de materiais) */
route('p/materiais', async (_, q) => {
  page(loading());
  const status = q.status || '';
  const mats = await api('/prof/materials' + (status ? '?status=' + status : ''));
  const el = page(html`${header('Editor de materiais', 'Revise, edite e publique o que a IA gerou.', html`<a class="btn btn--primario" href="#/p/estudio">${icon('ia', 16)} Gerar novos</a>`)}
    ${tabs([['', 'Todos'], ['rascunho', 'Rascunhos'], ['revisao', 'Em revisão'], ['publicado', 'Publicados'], ['arquivado', 'Arquivados']], status)}
    <div class="filtros"><input class="entrada entrada--busca" id="q" placeholder="Buscar…"><select class="entrada" id="tipo"><option value="">Todos os tipos</option>${Object.entries(TYPE_LABEL).map(([k, v]) => html`<option value="${k}">${v}</option>`)}</select></div>
    ${mats.length ? html`<div class="tabela-caixa"><table class="tabela"><thead><tr><th>Material</th><th>Disciplina / assunto</th><th>Fonte</th><th>Status</th><th>Turmas</th><th>Atualizado</th><th></th></tr></thead><tbody id="lista">
    ${mats.map((m) => html`<tr data-busca="${m.title.toLowerCase()}" data-tipo="${m.type}"><td><div class="linha">${typeIcon(m.type)}<a href="#/p/material/${m.id}">${m.title}</a></div></td>
      <td>${m.subject_name}<div class="texto-fraco">${m.topic_name || 'Sem assunto'}</div></td><td class="texto-fraco">${m.document_title || '—'}</td><td>${tag(m.status)}</td><td>${m.classes || '—'}</td><td>${fmtDate(m.updated_at)}</td><td><button class="btn btn--link texto-vermelho" data-excluir="${m.id}" data-titulo="${m.title}">Excluir</button></td></tr>`)}
    </tbody></table></div>` : empty('Nada por aqui', 'Use o Estúdio de IA para gerar materiais a partir dos seus documentos.')}`);
  bindSegTabs(el, (s) => go('#/p/materiais' + (s ? '?status=' + s : '')));
  const filtrar = () => {
    const t = el.querySelector('#q').value.toLowerCase(), tp = el.querySelector('#tipo').value;
    el.querySelectorAll('#lista tr').forEach((tr) => { tr.hidden = (t && !tr.dataset.busca.includes(t)) || (tp && tr.dataset.tipo !== tp); });
  };
  el.querySelector('#q').oninput = filtrar;
  el.querySelector('#tipo').onchange = filtrar;
  el.querySelectorAll('[data-excluir]').forEach((b) => { b.onclick = () => excluirMaterial(b.dataset.excluir, b.dataset.titulo, location.hash); });
}, R);

function bindSegTabs(el, fn) {
  el.querySelectorAll('[data-aba]').forEach((b) => b.addEventListener('click', () => fn(b.dataset.aba)));
}

async function excluirMaterial(id, titulo, destino) {
  if (!(await confirmar(`Excluir “${titulo}” definitivamente? Some também para os alunos, junto com o histórico de versões e o progresso deles neste material. Questões já enviadas ao banco continuam no banco.`, { ok: 'Excluir', perigo: true }))) return;
  try {
    await api('/prof/materials/' + id, { method: 'DELETE' });
    toast('Material excluído');
    go(destino);
  } catch (e) { toast(e.message, 'erro'); }
}

/* ================================================================ P10–P13 editor */
const KEY = { resumo: 'sections', roteiro: 'sections', flashcards: 'cards', exercicios: 'questions', mapa: 'branches', glossario: 'terms' };

route('p/material/:id', async ({ id }) => {
  page(loading());
  const m = await api('/prof/materials/' + id);
  const st = { content: m.content, title: m.title, topic_id: m.topic_id, dirty: false, modo: 'editar', sel: { b: -1, c: -1 }, sugestoes: {} };
  const aviso_ = st.content._aviso;
  delete st.content._aviso;

  const el = page(html`<a href="#/p/materiais" class="link-sutil">← Editor de materiais</a>
    <div class="cabecalho"><div style="flex:1;min-width:280px"><input class="entrada" id="titulo" value="${m.title}" style="font-size:26px;font-weight:800;border-color:transparent;background:transparent;padding-left:0" aria-label="Título">
      <p>${TYPE_LABEL[m.type]} · ${m.subject.name}${m.document ? html` · gerado a partir de <a href="#/p/documento/${m.document.id}">${m.document.title}</a>` : ''}${m.ai_source ? ` · ${m.ai_source}` : ''}</p></div></div>
    ${aviso_ ? aviso(aviso_, 'amarelo') : ''}
    <div class="editor-barra nao-imprimir">
      <div class="linha">${segmented('modo', [['editar', 'Editar'], ['visualizar', 'Visualizar como aluno']], 'editar')}<span id="status">${tag(m.status)}</span><span class="texto-fraco" id="sujo"></span></div>
      <div class="linha">
        <button type="button" class="btn btn--contorno" data-regen>Regenerar tudo</button>
        <button type="button" class="btn btn--contorno" data-print>Exportar PDF</button>
        <button type="button" class="btn btn--escuro" data-salvar>Salvar rascunho</button>
        ${m.status === 'rascunho' ? html`<button type="button" class="btn btn--contorno" data-revisado>Marcar como revisado</button>` : ''}
        <button type="button" class="btn btn--primario" data-publicar>${m.status === 'publicado' ? 'Alterar publicação' : 'Publicar'}</button>
      </div>
    </div>
    <div class="grade grade-editor-2">
      <section id="editor"></section>
      <aside class="pilha nao-imprimir">
        ${m.type === 'mapa' ? html`<section class="cartao" id="painel-no"></section>` : ''}
        <section class="cartao"><h2 class="cartao__titulo">Detalhes</h2>
          <label class="campo"><span>Assunto</span><select class="entrada" id="topico"><option value="">Sem assunto</option>${m.topics.map((t) => html`<option value="${t.id}" ${t.id === m.topic_id ? 'selected' : ''}>${t.name}</option>`)}</select></label>
          <p class="texto-fraco">Publicado para: ${m.classes.length ? m.classes.map((c) => c.name).join(', ') : 'ninguém (privado)'}</p>
          ${m.type === 'exercicios' ? html`<button class="btn btn--contorno btn--bloco" data-banco>Enviar questões ao banco${m.in_bank ? ` (${m.in_bank} já enviadas)` : ''}</button>` : ''}
          <button class="btn btn--contorno btn--bloco" data-duplicar>Duplicar</button>
          <button class="btn btn--perigo btn--bloco" data-excluir>Excluir material</button>
          ${m.status === 'publicado' ? html`<button class="btn btn--perigo btn--bloco" data-despublicar>Despublicar</button>` : html`<button class="btn btn--perigo btn--bloco" data-arquivar>Arquivar</button>`}
        </section>
        <section class="cartao"><h2 class="cartao__titulo">Versões</h2>
          <ul class="lista-simples">${m.versions.map((v, i) => html`<li><span><strong style="font-weight:600">${v.note || 'Versão'}</strong><br><span class="texto-fraco">${fmtDateTime(v.created_at)}</span></span>
            ${i ? html`<span class="linha" style="flex-wrap:nowrap"><button class="btn btn--link" data-ver="${v.id}">Ver</button><button class="btn btn--link" data-restaurar="${v.id}">Restaurar</button></span>` : html`<span class="tag tag--cinza">atual</span>`}</li>`)}</ul></section>
      </aside>
    </div>`);

  const editor = el.querySelector('#editor');
  const marcarSujo = () => { st.dirty = true; el.querySelector('#sujo').textContent = '• alterações não salvas'; };
  el.querySelector('#titulo').oninput = (e) => { st.title = e.target.value; marcarSujo(); };
  el.querySelector('#topico').onchange = (e) => { st.topic_id = e.target.value ? Number(e.target.value) : null; marcarSujo(); };
  bindSeg(el, 'modo', (v) => { st.modo = v; render(); });

  const salvar = async (note = 'Edição manual') => {
    const r = await api('/prof/materials/' + id, { method: 'PUT', body: { title: st.title, content: st.content, topic_id: st.topic_id, note } });
    st.content = r.content;
    st.dirty = false;
    el.querySelector('#sujo').textContent = '';
  };
  window.onbeforeunload = () => (st.dirty ? true : undefined);
  onLeave(() => { window.onbeforeunload = null; });

  el.querySelector('[data-salvar]').onclick = (e) => busy(e.currentTarget, async () => { await salvar(); toast('Rascunho salvo'); go(location.hash); });
  el.querySelector('[data-print]').onclick = () => { st.modo = 'visualizar'; render(); setTimeout(() => window.print(), 100); };
  el.querySelector('[data-revisado]')?.addEventListener('click', (e) => busy(e.currentTarget, async () => {
    if (st.dirty) await salvar();
    await api(`/prof/materials/${id}/status`, { method: 'POST', body: { status: 'revisao' } });
    toast('Marcado como revisado'); go(location.hash);
  }));
  el.querySelector('[data-publicar]').onclick = async () => { if (st.dirty) await salvar(); publicarModal(m); };
  el.querySelector('[data-despublicar]')?.addEventListener('click', async () => {
    if (!(await confirmar('Despublicar? Os alunos deixam de ver este material.', { ok: 'Despublicar', perigo: true }))) return;
    await api(`/prof/materials/${id}/unpublish`, { method: 'POST' }); toast('Material despublicado'); go(location.hash);
  });
  el.querySelector('[data-arquivar]')?.addEventListener('click', async () => {
    if (!(await confirmar('Arquivar este material?', { ok: 'Arquivar', perigo: true }))) return;
    await api(`/prof/materials/${id}/status`, { method: 'POST', body: { status: 'arquivado' } }); toast('Arquivado'); go('#/p/materiais');
  });
  el.querySelector('[data-excluir]').onclick = () => { st.dirty = false; excluirMaterial(id, m.title, '#/p/materiais'); };
  el.querySelector('[data-duplicar]').onclick = async () => { const r = await api(`/prof/materials/${id}/duplicate`, { method: 'POST' }); toast('Cópia criada'); go('#/p/material/' + r.id); };
  el.querySelector('[data-banco]')?.addEventListener('click', (e) => busy(e.currentTarget, async () => {
    if (st.dirty) await salvar();
    const r = await api(`/prof/materials/${id}/to-bank`, { method: 'POST' });
    toast(r.added ? `${r.added} questão(ões) enviadas ao banco` : 'Todas as questões já estão no banco');
  }));
  el.querySelector('[data-regen]').onclick = () => modal('Regenerar com IA', html`<form id="f">
    <p class="texto-suave">A IA cria uma nova versão completa a partir do documento de origem. A versão atual fica no histórico.</p>
    ${m.type === 'mapa' ? html`<div class="campo"><span>Nível de detalhe</span>${segmented('det', [['básico', 'Básico'], ['médio', 'Médio'], ['detalhado', 'Detalhado']], 'médio')}</div>` : ''}
    <label class="campo"><span>O que mudar? (opcional)</span><textarea class="entrada" name="instructions" placeholder="Ex.: linguagem mais simples, mais exemplos do cotidiano"></textarea></label>
    <div class="linha linha--fim"><button type="button" class="btn btn--contorno" data-fechar>Cancelar</button><button class="btn btn--primario">${icon('ia', 16)} Regenerar</button></div></form>`, {
    onMount: (mm, close) => {
      const det = bindSeg(mm, 'det');
      mm.querySelector('#f').addEventListener('submit', (e) => {
        e.preventDefault();
        busy(mm.querySelector('.btn--primario'), async () => {
          const r = await api(`/prof/materials/${id}/regenerate`, { method: 'POST', body: { instructions: e.target.instructions.value, detail: det() || '' } });
          close();
          toast(r.error ? 'Regenerado no modo local (Ollama indisponível)' : 'Nova versão gerada pela IA', r.error ? 'erro' : 'ok');
          go(location.hash);
        });
      });
    },
  });
  el.querySelectorAll('[data-ver]').forEach((b) => b.addEventListener('click', async () => {
    const v = await api(`/prof/materials/${id}/versions/${b.dataset.ver}`);
    modal(`Versão de ${fmtDateTime(v.created_at)}`, html`<p class="texto-fraco">${v.note}</p>${preview(m.type, v.content)}`, { largo: true, onMount: (mm) => bindFlip(mm) });
  }));
  el.querySelectorAll('[data-restaurar]').forEach((b) => b.addEventListener('click', async () => {
    if (!(await confirmar('Restaurar esta versão? A atual continuará no histórico.'))) return;
    await api(`/prof/materials/${id}/versions/${b.dataset.restaurar}/restore`, { method: 'POST' });
    toast('Versão restaurada'); go(location.hash);
  }));

  /* ---- reescrever uma parte com IA ---- */
  const reescrever = (i) => modal('Reescrever com IA', html`<form id="f"><label class="campo"><span>Como a IA deve reescrever este item?</span>
    <input class="entrada" name="instructions" placeholder="Ex.: mais simples / outro exemplo / alternativa mais difícil"></label>
    <div class="linha linha--fim"><button class="btn btn--primario">${icon('ia', 16)} Sugerir</button></div></form>`, {
    onMount: (mm, close) => mm.querySelector('#f').addEventListener('submit', (e) => {
      e.preventDefault();
      busy(mm.querySelector('button'), async () => {
        const r = await api(`/prof/materials/${id}/regenerate`, { method: 'POST', body: { index: i, instructions: e.target.instructions.value } });
        st.sugestoes[i] = r.part;
        close();
        if (r.error) toast('Ollama indisponível: sugestão não gerada', 'erro');
        render();
      });
    }),
  });
  const sugestaoBox = (i, conteudo) => (st.sugestoes[i] ? html`<div class="sugestao"><strong>${icon('ia', 14)} Sugestão da IA</strong>${conteudo}
    <div class="linha"><button type="button" class="btn btn--verde btn--p" data-aplicar="${i}">Aplicar</button><button type="button" class="btn btn--contorno btn--p" data-descartar="${i}">Descartar</button></div></div>` : '');

  const lista = () => st.content[KEY[m.type]];
  const mover = (i, d) => { const l = lista(); const j = i + d; if (j < 0 || j >= l.length) return; [l[i], l[j]] = [l[j], l[i]]; marcarSujo(); render(); };
  const barraItem = (i, label) => html`<div class="secao-editor__barra"><strong class="texto-fraco">${label}</strong><div class="ferramentas">
    <button type="button" data-mover="${i}" data-d="-1" title="Subir">↑</button><button type="button" data-mover="${i}" data-d="1" title="Descer">↓</button>
    ${m.document ? html`<button type="button" data-reescrever="${i}">${icon('ia', 12)} Reescrever</button>` : ''}<button type="button" data-remover="${i}" style="color:var(--vermelho)">Excluir</button></div></div>`;

  function render() {
    if (st.modo === 'visualizar') {
      editor.innerHTML = html`<div class="cartao">${preview(m.type, st.content)}</div>`.s;
      bindFlip(editor);
      bindMapa();
      return;
    }
    if (m.type === 'resumo' || m.type === 'roteiro') editor.innerHTML = editorTexto().s;
    if (m.type === 'flashcards') editor.innerHTML = editorCartoes().s;
    if (m.type === 'exercicios') editor.innerHTML = editorQuestoes().s;
    if (m.type === 'glossario') editor.innerHTML = editorGlossario().s;
    if (m.type === 'mapa') { editor.innerHTML = editorMapa().s; bindMapa(); }
    bindComum();
  }

  /* ---- glossário ---- */
  const editorGlossario = () => html`${st.content.terms.map((t, i) => html`<div class="secao-editor">${barraItem(i, `Termo ${i + 1}`)}
      <input class="entrada" data-campo="term" data-i="${i}" value="${t.term}" placeholder="Termo">
      <label class="campo" style="margin-top:8px"><span>Definição</span><textarea class="entrada" data-campo="definition" data-i="${i}" rows="2">${t.definition}</textarea></label>
      <label class="campo" style="margin-top:8px"><span>Exemplo (opcional)</span><textarea class="entrada" data-campo="example" data-i="${i}" rows="2">${t.example}</textarea></label>
      ${sugestaoBox(i, html`<p><strong>${st.sugestoes[i]?.term}</strong>: ${st.sugestoes[i]?.definition}</p>${st.sugestoes[i]?.example ? html`<p class="texto-fraco">Exemplo: ${st.sugestoes[i].example}</p>` : ''}`)}</div>`)}
    <button type="button" class="btn btn--contorno btn--bloco" data-add style="margin-top:12px">+ Adicionar termo</button>`;

  /* ---- resumo / roteiro ---- */
  const editorTexto = () => html`${st.content.sections.map((s, i) => html`<div class="secao-editor">${barraItem(i, `Seção ${i + 1}`)}
      <input class="entrada" data-campo="title" data-i="${i}" value="${s.title}" placeholder="Título da seção">
      <textarea class="entrada" data-campo="body" data-i="${i}" rows="5" style="margin-top:8px">${s.body}</textarea>
      ${sugestaoBox(i, html`<p><strong>${st.sugestoes[i]?.title}</strong></p><p>${st.sugestoes[i]?.body}</p>`)}</div>`)}
    <button type="button" class="btn btn--contorno btn--bloco" data-add style="margin-top:12px">+ Adicionar seção</button>
    <label class="campo" style="margin-top:16px"><span>Palavras-chave (separadas por vírgula)</span><input class="entrada" data-kw value="${(st.content.keywords || []).join(', ')}"></label>`;

  /* ---- flashcards ---- */
  const editorCartoes = () => html`<div class="grade grade-2" style="margin-bottom:12px"><div class="cartao">${st.content.cards.length ? flashcard(st.content.cards[0], 0, st.content.cards.length) : ''}<p class="texto-fraco centro">Prévia do primeiro cartão</p></div>
      <div class="cartao"><strong>${st.content.cards.length} cartões</strong><p class="texto-suave">Frente: pergunta ou termo curto. Verso: resposta objetiva. Os alunos revisam com repetição espaçada.</p></div></div>
    ${st.content.cards.map((c, i) => html`<div class="secao-editor">${barraItem(i, `Cartão ${i + 1}`)}
      <div class="campos-2"><label class="campo"><span>Frente</span><textarea class="entrada" data-campo="front" data-i="${i}" rows="2">${c.front}</textarea></label>
      <label class="campo"><span>Verso</span><textarea class="entrada" data-campo="back" data-i="${i}" rows="2">${c.back}</textarea></label></div>
      ${sugestaoBox(i, html`<p><strong>Frente:</strong> ${st.sugestoes[i]?.front}</p><p><strong>Verso:</strong> ${st.sugestoes[i]?.back}</p>`)}</div>`)}
    <button type="button" class="btn btn--contorno btn--bloco" data-add style="margin-top:12px">+ Adicionar cartão</button>`;

  /* ---- exercícios ---- */
  const editorQuestoes = () => html`${st.content.questions.map((q, i) => html`<div class="secao-editor">${barraItem(i, `Questão ${i + 1}`)}
      <div class="campos-2"><label class="campo"><span>Tipo</span><select class="entrada" data-tipo="${i}"><option value="objetiva" ${q.kind !== 'discursiva' ? 'selected' : ''}>Objetiva</option><option value="discursiva" ${q.kind === 'discursiva' ? 'selected' : ''}>Discursiva</option></select></label>
      <label class="campo"><span>Dificuldade</span><select class="entrada" data-campo="difficulty" data-i="${i}">${[['facil', 'Fácil'], ['media', 'Média'], ['dificil', 'Difícil']].map(([v, l]) => html`<option value="${v}" ${q.difficulty === v ? 'selected' : ''}>${l}</option>`)}</select></label></div>
      <label class="campo" style="margin-top:8px"><span>Enunciado</span><textarea class="entrada" data-campo="statement" data-i="${i}" rows="2">${q.statement}</textarea></label>
      ${q.kind === 'discursiva' ? html`<label class="campo" style="margin-top:8px"><span>Resposta esperada (usada na correção)</span><textarea class="entrada" data-campo="expected" data-i="${i}" rows="2">${q.expected}</textarea></label>`
    : html`<div class="campo" style="margin-top:8px"><span>Alternativas (marque a correta)</span>${q.options.map((o, j) => html`<div class="opcao-edicao"><input type="radio" name="gab-${i}" data-gab="${i}" value="${j}" ${j === q.answer ? 'checked' : ''} aria-label="Correta"><input class="entrada" data-opt="${i}" data-j="${j}" value="${o}"><button type="button" class="icone-botao" data-rmopt="${i}" data-j="${j}" aria-label="Remover alternativa">${icon('x', 14)}</button></div>`)}
        ${q.options.length < 5 ? html`<button type="button" class="btn btn--link" data-addopt="${i}">+ alternativa</button>` : ''}</div>`}
      <label class="campo" style="margin-top:8px"><span>Explicação / feedback</span><textarea class="entrada" data-campo="explanation" data-i="${i}" rows="2">${q.explanation}</textarea></label>
      ${sugestaoBox(i, html`<p><strong>${st.sugestoes[i]?.statement}</strong></p>${(st.sugestoes[i]?.options || []).map((o, j) => html`<p>${j === st.sugestoes[i].answer ? '✓' : '·'} ${o}</p>`)}`)}</div>`)}
    <button type="button" class="btn btn--contorno btn--bloco" data-add style="margin-top:12px">+ Adicionar questão</button>`;

  /* ---- mapa mental ---- */
  const editorMapa = () => html`<div class="cartao"><div class="ferramentas" style="margin-bottom:10px"><button type="button" data-addramo>+ Ramo</button><button type="button" data-addfilho>+ Nó filho no ramo selecionado</button></div>
    ${mapaSvg(st.content, st.sel)}<p class="texto-fraco" style="margin-top:8px">Clique em um nó para editar. ${st.content.branches.length} ramos.</p></div>
    ${st.content.branches.map((b, i) => sugestaoBox(i, html`<p><strong>${st.sugestoes[i]?.label}</strong>: ${(st.sugestoes[i]?.children || []).join(' · ')}</p>`))}`;

  const CORES = ['#2563EB', '#16A34A', '#DC2626', '#9333EA', '#EA580C', '#0891B2', '#CA8A04', '#172033'];
  function painelNo() {
    const p = el.querySelector('#painel-no');
    if (!p) return;
    const { b, c } = st.sel;
    const br = st.content.branches[b];
    const texto = b === -1 ? st.content.center : c === -1 ? br.label : br.children[c];
    p.innerHTML = html`<div class="cartao__topo"><h2 class="cartao__titulo">Nó selecionado</h2><span class="tag tag--cinza">${b === -1 ? 'Centro' : c === -1 ? 'Ramo' : 'Nó filho'}</span></div>
      <label class="campo"><span>Texto do nó</span><input class="entrada" id="no-texto" value="${texto}"></label>
      ${b >= 0 ? html`<div class="campo"><span>Cor do ramo</span><div class="linha">${CORES.map((cor) => html`<button type="button" class="cor-opcao ${br.color === cor ? 'ativo' : ''}" data-cor="${cor}" style="background:${cor}" aria-label="Cor ${cor}"></button>`)}</div></div>` : ''}
      ${b >= 0 && c === -1 ? html`<button type="button" class="btn btn--contorno btn--bloco" data-filho>+ Adicionar nó filho</button>${m.document ? html`<button type="button" class="btn btn--contorno btn--bloco" data-reescrever="${b}">${icon('ia', 14)} Reescrever ramo com IA</button>` : ''}` : ''}
      ${b >= 0 && c === -1 ? html`<div class="linha"><button type="button" class="btn btn--contorno btn--p" data-mover="${b}" data-d="-1">↑ Subir</button><button type="button" class="btn btn--contorno btn--p" data-mover="${b}" data-d="1">↓ Descer</button></div>` : ''}
      ${b >= 0 ? html`<button type="button" class="btn btn--perigo btn--bloco" data-excluir-no>Excluir nó${c === -1 ? ' (e filhos)' : ''}</button>` : ''}
      <details><summary class="link-sutil" style="cursor:pointer">Ver estrutura em lista</summary>${mapaArvore(st.content)}</details>`.s;
    p.querySelector('#no-texto').oninput = (e) => {
      if (b === -1) st.content.center = e.target.value; else if (c === -1) br.label = e.target.value; else br.children[c] = e.target.value;
      marcarSujo();
      const svg = el.querySelector('#editor .mapa-svg')?.parentElement;
      if (svg) { svg.outerHTML = mapaSvg(st.content, st.sel).s; bindMapa(false); }
    };
    p.querySelectorAll('[data-cor]').forEach((x) => { x.onclick = () => { br.color = x.dataset.cor; marcarSujo(); render(); }; });
    p.querySelector('[data-filho]')?.addEventListener('click', () => { br.children.push('Novo tópico'); st.sel = { b, c: br.children.length - 1 }; marcarSujo(); render(); });
    p.querySelector('[data-excluir-no]')?.addEventListener('click', () => {
      if (c === -1) st.content.branches.splice(b, 1); else br.children.splice(c, 1);
      st.sel = { b: -1, c: -1 }; marcarSujo(); render();
    });
    p.querySelector('[data-reescrever]')?.addEventListener('click', () => reescrever(b));
    p.querySelectorAll('[data-mover]').forEach((x) => { x.onclick = () => { mover(b, Number(x.dataset.d)); st.sel = { b: Math.max(0, Math.min(st.content.branches.length - 1, b + Number(x.dataset.d))), c: -1 }; render(); }; });
  }

  function bindMapa(painel = true) {
    if (m.type !== 'mapa') return;
    el.querySelectorAll('#editor .mn').forEach((g) => {
      const pick = () => { if (st.modo !== 'editar') return; st.sel = { b: Number(g.dataset.b), c: Number(g.dataset.c) }; render(); };
      g.addEventListener('click', pick);
      g.addEventListener('keydown', (e) => { if (e.key === 'Enter') pick(); });
    });
    if (painel) painelNo();
  }

  function bindComum() {
    editor.querySelectorAll('[data-campo]').forEach((x) => x.addEventListener('input', () => {
      const item = lista()[Number(x.dataset.i)];
      item[x.dataset.campo] = x.value;
      marcarSujo();
    }));
    editor.querySelector('[data-kw]')?.addEventListener('input', (e) => { st.content.keywords = e.target.value.split(',').map((s) => s.trim()).filter(Boolean); marcarSujo(); });
    editor.querySelectorAll('[data-mover]').forEach((b) => { b.onclick = () => mover(Number(b.dataset.mover), Number(b.dataset.d)); });
    editor.querySelectorAll('[data-remover]').forEach((b) => { b.onclick = () => { lista().splice(Number(b.dataset.remover), 1); st.sugestoes = {}; marcarSujo(); render(); }; });
    editor.querySelectorAll('[data-reescrever]').forEach((b) => { b.onclick = () => reescrever(Number(b.dataset.reescrever)); });
    editor.querySelectorAll('[data-aplicar]').forEach((b) => { b.onclick = () => { const i = Number(b.dataset.aplicar); const cur = lista()[i]; lista()[i] = { ...st.sugestoes[i], ...(m.type === 'mapa' ? { color: cur.color } : {}) }; delete st.sugestoes[i]; marcarSujo(); render(); }; });
    editor.querySelectorAll('[data-descartar]').forEach((b) => { b.onclick = () => { delete st.sugestoes[Number(b.dataset.descartar)]; render(); }; });
    editor.querySelector('[data-add]')?.addEventListener('click', () => {
      const novo = { resumo: { title: 'Nova seção', body: '' }, roteiro: { title: 'Nova etapa', body: '' }, flashcards: { front: '', back: '' },
        glossario: { term: '', definition: '', example: '' },
        exercicios: { kind: 'objetiva', statement: '', options: ['', '', '', ''], answer: 0, expected: '', explanation: '', difficulty: 'media' } }[m.type];
      lista().push(novo); marcarSujo(); render();
      editor.querySelector('.secao-editor:last-of-type textarea, .secao-editor:last-of-type input')?.focus();
    });
    // exercícios
    editor.querySelectorAll('[data-tipo]').forEach((s) => s.addEventListener('change', () => {
      const q = lista()[Number(s.dataset.tipo)];
      q.kind = s.value;
      if (q.kind === 'objetiva' && q.options.length < 2) { q.options = ['', '', '', '']; q.answer = 0; }
      marcarSujo(); render();
    }));
    editor.querySelectorAll('[data-gab]').forEach((r) => r.addEventListener('change', () => { lista()[Number(r.dataset.gab)].answer = Number(r.value); marcarSujo(); }));
    editor.querySelectorAll('[data-opt]').forEach((x) => x.addEventListener('input', () => { lista()[Number(x.dataset.opt)].options[Number(x.dataset.j)] = x.value; marcarSujo(); }));
    editor.querySelectorAll('[data-addopt]').forEach((b) => { b.onclick = () => { lista()[Number(b.dataset.addopt)].options.push(''); marcarSujo(); render(); }; });
    editor.querySelectorAll('[data-rmopt]').forEach((b) => {
      b.onclick = () => {
        const q = lista()[Number(b.dataset.rmopt)], j = Number(b.dataset.j);
        if (q.options.length <= 2) return toast('Mínimo de 2 alternativas', 'erro');
        q.options.splice(j, 1);
        if (q.answer >= q.options.length || q.answer === j) q.answer = 0;
        marcarSujo(); render();
      };
    });
    // mapa
    editor.querySelector('[data-addramo]')?.addEventListener('click', () => { st.content.branches.push({ label: 'Novo ramo', color: CORES[st.content.branches.length % CORES.length], children: [] }); st.sel = { b: st.content.branches.length - 1, c: -1 }; marcarSujo(); render(); });
    editor.querySelector('[data-addfilho]')?.addEventListener('click', () => {
      const b = st.sel.b;
      if (b < 0) return toast('Selecione um ramo primeiro', 'erro');
      st.content.branches[b].children.push('Novo tópico'); st.sel = { b, c: st.content.branches[b].children.length - 1 }; marcarSujo(); render();
    });
    bindFlip(editor);
  }
  render();
}, R);

function preview(type, c) {
  if (type === 'resumo' || type === 'roteiro') return resumoView(c);
  if (type === 'mapa') return mapaSvg(c);
  if (type === 'flashcards') return html`<div class="grade grade-2">${c.cards.map((k, i) => flashcard(k, i, c.cards.length))}</div>`;
  if (type === 'glossario') return glossarioView(c);
  return questoesPreview(c);
}

/* ================================================================ P14 publicação */
async function publicarModal(m) {
  const classes = await api('/prof/classes');
  const atuais = new Set(m.classes.map((c) => c.id));
  modal('Publicar material', html`<form id="f">
    <p class="texto-suave"><strong>${m.title}</strong> ficará visível para os alunos das turmas selecionadas. Rascunhos e versões anteriores continuam privados.</p>
    <div class="lista-checagem">${classes.map((c) => html`<label class="check"><input type="checkbox" name="c${c.id}" value="${c.id}" ${atuais.has(c.id) || (!atuais.size && c.id === m.subject.class_id) ? 'checked' : ''}><span><strong>${c.name}</strong><br><span class="texto-fraco">${c.students} alunos · ${c.subjects.map((s) => s.name).join(', ')}</span></span></label>`)}</div>
    ${aviso('Os alunos recebem uma notificação. Você pode despublicar a qualquer momento.')}
    <div class="linha linha--fim"><button type="button" class="btn btn--contorno" data-fechar>Cancelar</button><button class="btn btn--primario">Publicar agora</button></div></form>`, {
    onMount: (el, close) => el.querySelector('#f').addEventListener('submit', (e) => {
      e.preventDefault();
      const ids = [...el.querySelectorAll('input:checked')].map((i) => Number(i.value));
      if (!ids.length) return toast('Escolha ao menos uma turma', 'erro');
      busy(el.querySelector('.btn--primario'), async () => {
        await api(`/prof/materials/${m.id}/publish`, { method: 'POST', body: { class_ids: ids } });
        close(); toast('Material publicado!'); go(location.hash);
      });
    }),
  });
}

