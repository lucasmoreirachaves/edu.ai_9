/* EDU.AI – Banco de questões, Atividades e avaliações (P15) e Correção (P16) */
import {
  api, aviso, bindTabs, busy, confirmar, empty, fmtDateTime, formData, go, header, html, icon, kpi, loading, modal, nota,
  pad2, page, route, tabs, tag, toast,
} from './core.js';
import { excluirAtividade, tabelaAtividades } from './professor.js';

const R = { role: 'professor' };
const DIF = { facil: 'Fácil', media: 'Média', dificil: 'Difícil' };
const L = 'ABCDE';

/* ================================================================ banco de questões */
route('p/questoes', async (_, q) => {
  page(loading());
  const subs = await api('/prof/subjects');
  const f = { subject_id: q.disciplina || '', difficulty: q.dif || '', kind: q.tipo || '', q: q.q || '' };
  const qs = await api('/prof/questions?' + new URLSearchParams(Object.entries(f).filter(([, v]) => v)));
  const pend = qs.filter((x) => !x.reviewed).length;
  const el = page(html`${header('Banco de questões', 'Questões reutilizáveis para listas, provas e jogos.', html`
      <button class="btn btn--contorno" data-gerar>${icon('ia', 16)} Gerar com IA</button><button class="btn btn--primario" data-nova>+ Nova questão</button>`)}
    <form class="filtros" id="filtros">
      <input class="entrada entrada--busca" name="q" value="${f.q}" placeholder="Buscar no enunciado…">
      <select class="entrada" name="disciplina"><option value="">Todas as disciplinas</option>${subs.map((s) => html`<option value="${s.id}" ${String(s.id) === f.subject_id ? 'selected' : ''}>${s.name} · ${s.class_name}</option>`)}</select>
      <select class="entrada" name="dif"><option value="">Toda dificuldade</option>${Object.entries(DIF).map(([k, v]) => html`<option value="${k}" ${k === f.difficulty ? 'selected' : ''}>${v}</option>`)}</select>
      <select class="entrada" name="tipo"><option value="">Todos os tipos</option><option value="objetiva" ${f.kind === 'objetiva' ? 'selected' : ''}>Objetiva</option><option value="discursiva" ${f.kind === 'discursiva' ? 'selected' : ''}>Discursiva</option></select>
      <button class="btn btn--contorno">Filtrar</button></form>
    ${pend ? aviso(`${pend} questão(ões) geradas pela IA aguardam sua revisão antes de serem usadas.`, 'amarelo') : ''}
    <div class="linha linha--entre"><span class="texto-fraco">${qs.length} questão(ões) · <span data-sel>0 selecionada(s)</span></span>
      <div class="linha"><button class="btn btn--escuro btn--p" data-montar disabled>Montar atividade com as selecionadas</button><button class="btn btn--contorno btn--p" data-jogo disabled>Criar jogo com as selecionadas</button></div></div>
    ${qs.length ? html`<div class="pilha">${qs.map((x) => html`<div class="questao">
      <div class="linha linha--entre"><label class="check"><input type="checkbox" data-q="${x.id}"> <span class="tag tag--cinza">${x.subject_name}${x.topic_name ? ' · ' + x.topic_name : ''}</span>
        <span class="tag tag--azul">${x.kind === 'discursiva' ? 'Discursiva' : 'Objetiva'}</span><span class="tag tag--${x.difficulty === 'dificil' ? 'vermelho' : x.difficulty === 'facil' ? 'verde' : 'amarelo'}">${DIF[x.difficulty] || x.difficulty}</span>
        ${x.reviewed ? '' : html`<span class="tag tag--amarelo">Revisar</span>`}${x.uses ? html`<span class="texto-fraco">usada em ${x.uses} atividade(s)</span>` : ''}</label>
        <div class="linha">${x.reviewed ? '' : html`<button class="btn btn--verde btn--p" data-revisar="${x.id}">Aprovar</button>`}<button class="btn btn--contorno btn--p" data-editar="${x.id}">Editar</button><button class="btn btn--link texto-vermelho" data-excluir="${x.id}">Excluir</button></div></div>
      <p class="questao__enunciado">${x.statement}</p>
      ${x.kind === 'discursiva' ? html`<p class="texto-suave"><strong>Esperado:</strong> ${x.expected}</p>` : html`<div class="alternativas">${x.options.map((o, j) => html`<div class="alternativa ${j === x.answer ? 'alternativa--correta' : ''}" style="padding:8px 12px"><strong>${L[j]})</strong> ${o}</div>`)}</div>`}
      </div>`)}</div>` : empty('Nenhuma questão encontrada', 'Crie manualmente, gere com IA ou envie as questões de uma lista de exercícios para o banco.')}`);

  el.querySelector('#filtros').addEventListener('submit', (e) => {
    e.preventDefault();
    go('#/p/questoes?' + new URLSearchParams(Object.entries(formData(e.target)).filter(([, v]) => v)));
  });
  const selecionadas = () => [...el.querySelectorAll('[data-q]:checked')].map((c) => c.dataset.q);
  el.addEventListener('change', (e) => {
    if (!e.target.matches('[data-q]')) return;
    const n = selecionadas().length;
    el.querySelector('[data-sel]').textContent = `${n} selecionada(s)`;
    el.querySelector('[data-montar]').disabled = !n;
    el.querySelector('[data-jogo]').disabled = !n;
  });
  el.querySelector('[data-montar]').onclick = () => go('#/p/atividade/nova?q=' + selecionadas().join(','));
  el.querySelector('[data-jogo]').onclick = () => go('#/p/jogos?novo=1&q=' + selecionadas().join(','));
  el.querySelector('[data-nova]').onclick = () => questaoModal(null, subs, f.subject_id);
  el.querySelector('[data-gerar]').onclick = () => gerarModal();
  el.querySelectorAll('[data-editar]').forEach((b) => { b.onclick = () => questaoModal(qs.find((x) => String(x.id) === b.dataset.editar), subs); });
  el.querySelectorAll('[data-revisar]').forEach((b) => {
    b.onclick = async () => {
      const x = qs.find((y) => String(y.id) === b.dataset.revisar);
      await api('/prof/questions/' + x.id, { method: 'PUT', body: { ...x, reviewed: true } });
      toast('Questão aprovada'); go(location.hash);
    };
  });
  el.querySelectorAll('[data-excluir]').forEach((b) => {
    b.onclick = async () => {
      if (!(await confirmar('Excluir esta questão do banco?', { ok: 'Excluir', perigo: true }))) return;
      try { await api('/prof/questions/' + b.dataset.excluir, { method: 'DELETE' }); go(location.hash); } catch (e) { toast(e.message, 'erro'); }
    };
  });
}, R);

async function questaoModal(x, subs, defSubject) {
  const q = x || { subject_id: Number(defSubject) || subs[0]?.id, kind: 'objetiva', options: ['', '', '', ''], answer: 0, difficulty: 'media', statement: '', expected: '', explanation: '', topic_id: null };
  modal(x ? 'Editar questão' : 'Nova questão', html`<form id="f">
    <div class="campos-2"><label class="campo"><span>Disciplina</span><select class="entrada" name="subject_id">${subs.map((s) => html`<option value="${s.id}" ${s.id === q.subject_id ? 'selected' : ''}>${s.name} · ${s.class_name}</option>`)}</select></label>
    <label class="campo"><span>Assunto</span><select class="entrada" name="topic_id"></select></label></div>
    <div class="campos-2"><label class="campo"><span>Tipo</span><select class="entrada" name="kind"><option value="objetiva">Objetiva</option><option value="discursiva" ${q.kind === 'discursiva' ? 'selected' : ''}>Discursiva</option></select></label>
    <label class="campo"><span>Dificuldade</span><select class="entrada" name="difficulty">${Object.entries(DIF).map(([k, v]) => html`<option value="${k}" ${k === q.difficulty ? 'selected' : ''}>${v}</option>`)}</select></label></div>
    <label class="campo"><span>Enunciado</span><textarea class="entrada" name="statement" required>${q.statement}</textarea></label>
    <div data-obj class="campo"><span>Alternativas (marque a correta)</span>${[0, 1, 2, 3, 4].map((j) => html`<div class="opcao-edicao"><input type="radio" name="answer" value="${j}" ${j === q.answer ? 'checked' : ''}><input class="entrada" name="opt${j}" value="${q.options[j] || ''}" placeholder="${j < 2 ? 'Obrigatória' : 'Opcional'}"><span></span></div>`)}</div>
    <label data-disc class="campo"><span>Resposta esperada</span><textarea class="entrada" name="expected">${q.expected || ''}</textarea></label>
    <label class="campo"><span>Explicação (feedback ao aluno)</span><textarea class="entrada" name="explanation">${q.explanation || ''}</textarea></label>
    <div class="linha linha--fim"><button type="button" class="btn btn--contorno" data-fechar>Cancelar</button><button class="btn btn--primario">Salvar</button></div></form>`, {
    largo: true,
    onMount: (el, close) => {
      const f = el.querySelector('#f');
      const tipo = () => { el.querySelector('[data-obj]').hidden = f.kind.value === 'discursiva'; el.querySelector('[data-disc]').hidden = f.kind.value !== 'discursiva'; };
      f.kind.onchange = tipo; tipo();
      const topics = async () => {
        const d = await api('/prof/subjects/' + f.subject_id.value);
        f.topic_id.innerHTML = html`<option value="">Sem assunto</option>${d.topics.map((t) => html`<option value="${t.id}" ${t.id === q.topic_id ? 'selected' : ''}>${t.name}</option>`)}`.s;
      };
      f.subject_id.onchange = topics; topics();
      f.addEventListener('submit', (e) => {
        e.preventDefault();
        const opts = [0, 1, 2, 3, 4].map((j) => f['opt' + j].value);
        const ans = Number(f.querySelector('[name=answer]:checked')?.value ?? 0);
        const filled = opts.map((o, j) => [o.trim(), j]).filter(([o]) => o);
        const body = {
          subject_id: Number(f.subject_id.value), topic_id: f.topic_id.value ? Number(f.topic_id.value) : null, kind: f.kind.value,
          statement: f.statement.value, options: filled.map(([o]) => o), answer: Math.max(0, filled.findIndex(([, j]) => j === ans)),
          expected: f.expected.value, explanation: f.explanation.value, difficulty: f.difficulty.value, reviewed: true,
        };
        busy(f.querySelector('.btn--primario'), async () => {
          await api('/prof/questions' + (x ? '/' + x.id : ''), { method: x ? 'PUT' : 'POST', body });
          close(); toast('Questão salva'); go(location.hash);
        });
      });
    },
  });
}

async function gerarModal() {
  const docs = (await api('/prof/documents')).filter((d) => d.status === 'concluido');
  if (!docs.length) return toast('Envie e processe um documento primeiro', 'erro');
  modal('Gerar questões com IA', html`<form id="f">
    <label class="campo"><span>Documento de origem</span><select class="entrada" name="document_id">${docs.map((d) => html`<option value="${d.id}">${d.title} · ${d.subject_name}</option>`)}</select></label>
    <div class="campos-2"><label class="campo"><span>Quantidade</span><input class="entrada" type="number" name="count" value="5" min="1" max="20"></label>
    <label class="campo"><span>Delas, discursivas</span><input class="entrada" type="number" name="open_count" value="0" min="0" max="10"></label></div>
    <label class="campo"><span>Dificuldade</span><select class="entrada" name="difficulty">${Object.entries(DIF).map(([k, v]) => html`<option value="${k}" ${k === 'media' ? 'selected' : ''}>${v}</option>`)}</select></label>
    <label class="campo"><span>Instruções (opcional)</span><input class="entrada" name="notes" placeholder="Ex.: foco em interpretação de gráficos"></label>
    ${aviso('As questões entram no banco marcadas como “Revisar”. Aprove cada uma antes de usar.')}
    <div class="linha linha--fim"><button type="button" class="btn btn--contorno" data-fechar>Cancelar</button><button class="btn btn--primario">${icon('ia', 16)} Gerar</button></div></form>`, {
    onMount: (el, close) => el.querySelector('#f').addEventListener('submit', (e) => {
      e.preventDefault();
      const d = formData(e.target);
      busy(el.querySelector('.btn--primario'), async () => {
        const r = await api('/prof/questions/generate', { method: 'POST', body: { ...d, document_id: Number(d.document_id) } });
        close();
        toast(`${r.ids.length} questões geradas${r.provider === 'simulada' ? ' (modo local)' : ''}`);
        go('#/p/questoes');
      });
    }),
  });
}

/* ================================================================ atividades */
route('p/atividades', async () => {
  page(loading());
  const acts = await api('/prof/activities');
  const pend = acts.reduce((a, x) => a + x.to_grade, 0);
  page(html`${header('Atividades e avaliações', 'Listas, testes e provas com correção automática das objetivas.', html`<a class="btn btn--contorno" href="#/p/questoes">Banco de questões</a><a class="btn btn--primario" href="#/p/atividade/nova">+ Nova atividade</a>`)}
    <div class="grade grade-4">${kpi('Publicadas', pad2(acts.filter((a) => a.status === 'publicada').length))}${kpi('Rascunhos', pad2(acts.filter((a) => a.status === 'rascunho').length))}
      ${kpi('Aguardando correção', pad2(pend), 'respostas discursivas', pend ? 'vermelho' : '')}${kpi('Notas a publicar', pad2(acts.reduce((a, x) => a + x.unpublished, 0)))}</div>
    ${tabelaAtividades(acts)}`);
}, R);

route('p/atividade/:id', async ({ id }, q) => {
  page(loading());
  const nova = id === 'nova';
  const [subs, classes] = await Promise.all([api('/prof/subjects'), api('/prof/classes')]);
  if (!subs.length) return page(empty('Você ainda não tem disciplinas', 'A coordenação da escola vincula você às disciplinas e turmas.'));
  let a;
  if (nova) {
    const pre = q.q ? q.q.split(',').map(Number) : [];
    const all = pre.length ? await api('/prof/questions') : [];
    const qsel = all.filter((x) => pre.includes(x.id));
    const sid = qsel[0]?.subject_id || Number(q.disciplina) || subs[0].id;
    a = { title: '', subject_id: sid, class_id: subs.find((s) => s.id === sid)?.class_id, kind: 'atividade', instructions: '', due_date: '', points: 10, max_attempts: 1, auto_publish: 1, accept_late: 0, status: 'rascunho', questions: qsel };
  } else a = await api('/prof/activities/' + id);
  const st = { questions: a.questions };
  const locked = !nova && a.status !== 'rascunho';
  const el = page(html`<a href="#/p/atividades" class="link-sutil">← Atividades</a>
    ${header(nova ? 'Nova atividade' : a.title, nova ? 'Selecione questões do banco e configure as regras.' : `${a.subject_name} · ${a.class_name}`, nova ? '' : html`${tag(a.status)}
      ${a.status !== 'rascunho' ? html`<a class="btn btn--contorno" href="#/p/correcao/${a.id}">Ver entregas e correção</a>` : ''}<button class="btn btn--contorno" data-duplicar>Duplicar para outra turma</button>`)}
    <form class="grade grade-editor-2" id="f">
      <div class="pilha">
        <section class="cartao"><h2 class="cartao__titulo">Configuração</h2>
          <label class="campo"><span>Título</span><input class="entrada" name="title" required value="${a.title}" placeholder="Ex.: Lista – Funções do 1º grau"></label>
          <div class="campos-2"><label class="campo"><span>Disciplina</span><select class="entrada" name="subject_id">${subs.map((s) => html`<option value="${s.id}" ${s.id === a.subject_id ? 'selected' : ''}>${s.name} · ${s.class_name}</option>`)}</select></label>
          <label class="campo"><span>Turma (da disciplina)</span><select class="entrada" name="class_id" disabled title="A turma é a da disciplina, definida pela coordenação">${classes.map((c) => html`<option value="${c.id}" ${c.id === a.class_id ? 'selected' : ''}>${c.name}</option>`)}</select></label></div>
          <div class="campos-2"><label class="campo"><span>Tipo</span><select class="entrada" name="kind">${[['atividade', 'Lista / atividade'], ['simulado', 'Simulado'], ['prova', 'Prova']].map(([v, l]) => html`<option value="${v}" ${v === a.kind ? 'selected' : ''}>${l}</option>`)}</select></label>
          <label class="campo"><span>Prazo</span><input class="entrada" type="date" name="due_date" value="${a.due_date || ''}"></label></div>
          <div class="campos-2"><label class="campo"><span>Pontuação total</span><input class="entrada" type="number" name="points" min="1" step="0.5" value="${a.points}"></label>
          <label class="campo"><span>Tentativas permitidas</span><input class="entrada" type="number" name="max_attempts" min="1" max="10" value="${a.max_attempts}"></label></div>
          <label class="campo"><span>Instruções para os alunos</span><textarea class="entrada" name="instructions">${a.instructions || ''}</textarea></label>
          <label class="check"><input type="checkbox" name="auto_publish" ${a.auto_publish ? 'checked' : ''}> Publicar a nota automaticamente quando todas as questões forem objetivas</label>
          <label class="check"><input type="checkbox" name="accept_late" ${a.accept_late ? 'checked' : ''}> Aceitar entregas depois do prazo (ficam marcadas como atrasadas)</label>
          <p class="texto-fraco">Sem essa opção, a atividade fecha no fim do dia do prazo. O gabarito só aparece para o aluno quando ele não puder mais entregar.</p>
        </section>
        <section class="cartao"><div class="cartao__topo"><h2 class="cartao__titulo">Questões (<span data-n>${st.questions.length}</span>)</h2>${locked ? tag('encerrada', 'Bloqueadas: já há entregas') : html`<button type="button" class="btn btn--contorno btn--p" data-banco>+ Adicionar do banco</button>`}</div>
          <div id="qs"></div></section>
      </div>
      <aside class="pilha">
        <section class="cartao"><h2 class="cartao__titulo">Ações</h2>
          <button class="btn btn--escuro btn--bloco" type="submit">Salvar ${a.status === 'rascunho' ? 'rascunho' : 'alterações'}</button>
          ${a.status === 'rascunho' ? html`<button type="button" class="btn btn--primario btn--bloco" data-publicar>Salvar e publicar para a turma</button>` : ''}
          ${a.status === 'publicada' ? html`<button type="button" class="btn btn--perigo btn--bloco" data-encerrar>Encerrar entregas</button>` : ''}
          ${nova ? '' : html`<button type="button" class="btn btn--perigo btn--bloco" data-excluir>Excluir atividade</button>`}</section>
        ${aviso('Objetivas são corrigidas na hora. Discursivas ficam aguardando sua correção (com sugestão da IA) e a nota só aparece para o aluno depois que você publicar.')}
      </aside>
    </form>`);
  const box = el.querySelector('#qs');
  const renderQs = () => {
    el.querySelector('[data-n]').textContent = st.questions.length;
    box.innerHTML = st.questions.length ? html`<ol class="pilha" style="list-style:none">${st.questions.map((x, i) => html`<li class="item"><div class="item__info" style="align-items:flex-start"><span class="tag tag--cinza">${i + 1}</span><div><strong>${x.statement}</strong><small>${x.kind === 'discursiva' ? 'Discursiva' : `Objetiva · ${x.options.length} alternativas`} · ${DIF[x.difficulty] || ''}</small></div></div>
      ${locked ? '' : html`<div class="item__acoes"><button type="button" class="btn btn--link" data-up="${i}">↑</button><button type="button" class="btn btn--link" data-down="${i}">↓</button><button type="button" class="btn btn--link texto-vermelho" data-rm="${i}">Remover</button></div>`}</li>`)}</ol>`.s
      : empty('Nenhuma questão', 'Adicione questões do banco.').s;
    box.querySelectorAll('[data-rm]').forEach((b) => { b.onclick = () => { st.questions.splice(Number(b.dataset.rm), 1); renderQs(); }; });
    box.querySelectorAll('[data-up],[data-down]').forEach((b) => {
      b.onclick = () => {
        const i = Number(b.dataset.up ?? b.dataset.down), j = i + (b.dataset.up != null ? -1 : 1);
        if (j < 0 || j >= st.questions.length) return;
        [st.questions[i], st.questions[j]] = [st.questions[j], st.questions[i]]; renderQs();
      };
    });
  };
  renderQs();
  const f = el.querySelector('#f');
  f.subject_id.onchange = () => { const s = subs.find((x) => x.id === Number(f.subject_id.value)); if (s) f.class_id.value = s.class_id; };
  const body = () => {
    const d = formData(f);
    return { ...d, subject_id: Number(d.subject_id), class_id: Number(d.class_id), due_date: d.due_date || null, question_ids: st.questions.map((x) => x.id) };
  };
  const salvar = async () => {
    if (nova) { const r = await api('/prof/activities', { method: 'POST', body: body() }); return r.id; }
    const r = await api('/prof/activities/' + id, { method: 'PUT', body: body() });
    if (r.questions_locked) toast('As questões não foram alteradas porque já há entregas.');
    return Number(id);
  };
  f.addEventListener('submit', (e) => { e.preventDefault(); busy(f.querySelector('[type=submit]'), async () => { const nid = await salvar(); toast('Atividade salva'); go('#/p/atividade/' + nid); }); });
  el.querySelector('[data-publicar]')?.addEventListener('click', (e) => {
    if (!f.reportValidity()) return;
    busy(e.currentTarget, async () => {
      const nid = await salvar();
      await api(`/prof/activities/${nid}/publish`, { method: 'POST' });
      toast('Atividade publicada! Os alunos foram notificados.'); go('#/p/atividade/' + nid);
    });
  });
  el.querySelector('[data-excluir]')?.addEventListener('click', async () => {
    const subs = await api(`/prof/activities/${id}/submissions`);
    excluirAtividade(id, a.title, subs.students.filter((s) => s.id).length, '#/p/atividades');
  });
  el.querySelector('[data-encerrar]')?.addEventListener('click', async () => {
    if (!(await confirmar('Encerrar as entregas? Os alunos não poderão mais responder.', { ok: 'Encerrar', perigo: true }))) return;
    await api(`/prof/activities/${id}/close`, { method: 'POST' }); go(location.hash);
  });
  el.querySelector('[data-duplicar]')?.addEventListener('click', () => modal('Duplicar para outra turma', html`<form id="d"><label class="campo"><span>Turma de destino</span><select class="entrada" name="class_id">${classes.map((c) => html`<option value="${c.id}">${c.name}</option>`)}</select></label>
    <p class="texto-fraco">A cópia é criada como rascunho, com as mesmas questões e regras.</p><div class="linha linha--fim"><button class="btn btn--primario">Duplicar</button></div></form>`, {
    onMount: (m, close) => m.querySelector('#d').addEventListener('submit', async (e) => {
      e.preventDefault();
      const r = await api(`/prof/activities/${id}/duplicate`, { method: 'POST', body: { class_id: Number(e.target.class_id.value) } });
      close(); toast('Cópia criada'); go('#/p/atividade/' + r.id);
    }),
  }));
  el.querySelector('[data-banco]')?.addEventListener('click', async () => {
    const all = await api('/prof/questions?subject_id=' + f.subject_id.value);
    const ja = new Set(st.questions.map((x) => x.id));
    modal('Adicionar questões do banco', html`<input class="entrada" id="busca" placeholder="Filtrar…" style="margin-bottom:10px">
      <div class="lista-checagem">${all.filter((x) => !ja.has(x.id)).map((x) => html`<label class="check" data-txt="${x.statement.toLowerCase()}"><input type="checkbox" value="${x.id}"><span><strong>${x.statement}</strong><br><span class="texto-fraco">${x.topic_name || 'Sem assunto'} · ${x.kind} · ${DIF[x.difficulty] || ''}${x.reviewed ? '' : ' · ⚠ não revisada'}</span></span></label>`)}</div>
      ${!all.length ? empty('Banco vazio para esta disciplina', 'Gere questões com IA no Banco de questões.') : ''}
      <div class="linha linha--fim"><button class="btn btn--primario" data-add>Adicionar selecionadas</button></div>`, {
      largo: true,
      onMount: (m, close) => {
        m.querySelector('#busca').oninput = (e) => m.querySelectorAll('[data-txt]').forEach((l) => { l.hidden = !l.dataset.txt.includes(e.target.value.toLowerCase()); });
        m.querySelector('[data-add]').onclick = () => {
          const ids = [...m.querySelectorAll('input:checked')].map((i) => Number(i.value));
          st.questions.push(...all.filter((x) => ids.includes(x.id)));
          close(); renderQs();
        };
      },
    });
  });
}, R);

/* ================================================================ P16 correção */
route('p/correcao/:id', async ({ id }, q) => {
  page(loading());
  const d = await api(`/prof/activities/${id}/submissions`);
  const a = d.activity;
  const entregues = d.students.filter((s) => s.id);
  const aguard = entregues.filter((s) => s.status === 'entregue').length;
  const naoPub = entregues.filter((s) => s.status === 'corrigida' && !s.published).length;
  const notas = entregues.filter((s) => s.score != null);
  const aba = q.aba || 'entregas';
  const el = page(html`<a href="#/p/atividade/${id}" class="link-sutil">← ${a.title}</a>
    ${header('Correção e respostas', a.title, html`${naoPub ? html`<button class="btn btn--primario" data-pubnotas>Publicar ${naoPub} nota(s) corrigida(s)</button>` : ''}`)}
    <div class="grade grade-4">${kpi('Entregas', `${entregues.length}/${d.students.length}`)}${kpi('Aguardando correção', pad2(aguard), 'discursivas', aguard ? 'vermelho' : '')}
      ${kpi('Média', nota(notas.length ? notas.reduce((x, s) => x + (10 * s.score) / a.points, 0) / notas.length : null), 'escala 0–10')}${kpi('Notas não publicadas', pad2(naoPub))}</div>
    ${tabs([['entregas', 'Entregas'], ['questoes', 'Análise por questão']], aba)}<div id="aba"></div>`);
  const box = el.querySelector('#aba');
  const show = (t) => {
    if (t === 'entregas') {
      box.innerHTML = html`<div class="tabela-caixa"><table class="tabela"><thead><tr><th>Aluno</th><th>Status</th><th>Nota</th><th>Visível ao aluno</th><th>Tentativas</th><th>Enviado</th><th></th></tr></thead><tbody>
        ${d.students.map((s) => html`<tr><td>${s.name}</td><td>${s.id ? tag(s.status) : tag('pendente', 'Não entregou')}${s.late ? html` <span class="tag tag--amarelo">Atrasada</span>` : ''}</td><td>${s.score == null ? '—' : `${nota(s.score)} / ${nota(a.points)}`}</td>
          <td>${s.id ? (s.published ? html`<span class="texto-verde">Sim</span>` : 'Não') : '—'}</td><td>${s.attempts || '—'}</td><td>${fmtDateTime(s.submitted_at)}</td>
          <td>${s.id ? html`<button class="btn ${s.status === 'entregue' ? 'btn--primario' : 'btn--contorno'} btn--p" data-corrigir="${s.id}">${s.status === 'entregue' ? 'Corrigir' : 'Ver / ajustar'}</button>` : ''}</td></tr>`)}</tbody></table></div>`.s;
      box.querySelectorAll('[data-corrigir]').forEach((b) => { b.onclick = () => corrigirModal(Number(b.dataset.corrigir), a); });
    } else {
      box.innerHTML = d.questions.length ? html`<div class="tabela-caixa"><table class="tabela"><thead><tr><th>Questão</th><th>Respostas</th><th>Índice de erro</th></tr></thead><tbody>
        ${d.questions.map((x) => html`<tr><td>${x.statement}</td><td>${x.total}</td><td><span class="tag tag--${x.error_rate >= 50 ? 'vermelho' : x.error_rate >= 30 ? 'amarelo' : 'verde'}">${x.error_rate}%</span></td></tr>`)}</tbody></table></div>`.s
        : empty('Sem respostas corrigidas ainda').s;
    }
    history.replaceState(null, '', `#/p/correcao/${id}?aba=${t}`);
  };
  bindTabs(el, show);
  show(aba);
  el.querySelector('[data-pubnotas]')?.addEventListener('click', (e) => busy(e.currentTarget, async () => {
    const r = await api(`/prof/activities/${id}/publish-grades`, { method: 'POST' });
    toast(`${r.published} nota(s) publicada(s)`); go(location.hash);
  }));
}, R);

async function corrigirModal(subId, a) {
  const d = await api('/prof/submissions/' + subId);
  const s = d.submission;
  const g = s.grading;
  const temDisc = d.questions.some((x) => x.kind === 'discursiva');
  modal(`Correção · ${s.student_name}`, html`<form id="f" class="pilha">
    ${temDisc ? html`<div class="linha linha--entre">${aviso('A IA sugere nota e comentário para as discursivas. Você decide a nota final.')}<button type="button" class="btn btn--contorno" data-ia>${icon('ia', 16)} Sugerir correção com IA</button></div>` : ''}
    ${d.questions.map((x, i) => {
      const gi = g[String(x.id)] || {};
      const resp = s.answers[String(x.id)];
      const cls = gi.score == null ? 'pendente' : gi.score >= 0.5 ? 'ok' : 'erro';
      return html`<div class="correcao-q correcao-q--${cls}"><p><strong>${i + 1}. ${x.statement}</strong></p>
        ${x.kind === 'objetiva' ? html`<p>Resposta: <strong>${resp == null ? 'em branco' : `${L[resp]}) ${x.options[resp] || ''}`}</strong> ${resp != null && Number(resp) === x.answer ? html`<span class="tag tag--verde">Correta</span>` : html`<span class="tag tag--vermelho">Incorreta · gabarito ${L[x.answer]}</span>`}</p>`
        : html`<div class="resposta-aluno">${resp || '(em branco)'}</div><p class="texto-fraco"><strong>Esperado:</strong> ${x.expected}</p>
          ${gi.ai_score != null ? html`<div class="ia-sugestao"><strong>Sugestão da IA: ${Math.round(gi.ai_score * 100)}%</strong> — ${gi.ai_feedback} <button type="button" class="btn btn--link" data-usar="${x.id}" data-s="${gi.ai_score}" data-fb="${gi.ai_feedback}">Usar sugestão</button></div>` : ''}`}
        <div class="campos-2" style="margin-top:8px"><label class="campo"><span>Nota da questão (%)</span><input class="entrada" type="number" min="0" max="100" step="5" name="s${x.id}" value="${gi.score == null ? '' : Math.round(gi.score * 100)}" ${x.kind === 'discursiva' ? 'required' : ''}></label>
        <label class="campo"><span>Comentário para o aluno</span><input class="entrada" name="f${x.id}" value="${gi.feedback || ''}"></label></div></div>`;
    })}
    <label class="campo"><span>Comentário geral</span><textarea class="entrada" name="feedback">${s.feedback || ''}</textarea></label>
    <div class="linha linha--fim"><button type="button" class="btn btn--contorno" data-salvar>Salvar sem publicar</button><button class="btn btn--primario" type="submit">Salvar e publicar nota</button></div>
  </form>`, {
    largo: true,
    onMount: (el, close) => {
      const f = el.querySelector('#f');
      el.querySelector('[data-ia]')?.addEventListener('click', (e) => busy(e.currentTarget, async () => {
        await api(`/prof/submissions/${subId}/ai-grade`, { method: 'POST' });
        close(); corrigirModal(subId, a);
      }));
      el.querySelectorAll('[data-usar]').forEach((b) => { b.onclick = () => { f['s' + b.dataset.usar].value = Math.round(Number(b.dataset.s) * 100); f['f' + b.dataset.usar].value = b.dataset.fb; }; });
      const enviar = (publish, btn) => {
        if (!f.reportValidity()) return;
        const grading = {};
        d.questions.forEach((x) => {
          const v = f['s' + x.id].value;
          grading[x.id] = { score: v === '' ? null : Number(v) / 100, feedback: f['f' + x.id].value };
        });
        busy(btn, async () => {
          const r = await api(`/prof/submissions/${subId}/grade`, { method: 'PUT', body: { grading, feedback: f.feedback.value, publish } });
          close(); toast(`Nota ${nota(r.score)} / ${nota(a.points)} ${publish ? 'publicada' : 'salva'}`); go(location.hash);
        });
      };
      f.addEventListener('submit', (e) => { e.preventDefault(); enviar(true, f.querySelector('[type=submit]')); });
      el.querySelector('[data-salvar]').onclick = (e) => enviar(false, e.currentTarget);
    },
  });
}
