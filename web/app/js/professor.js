/* EDU.AI – professor (P01–P08, P17): visão geral, disciplinas, turmas, biblioteca, processamento e desempenho */
import {
  TYPE_LABEL, api, aviso, bars, bindTabs, busy, confirmar, download, dueTag, empty, fmtDate, formData, go, hbars, header,
  html, icon, initials, kpi, lineChart, loading, modal, nota, onLeave, pad2, page, progress, route, tabs, tag, toast,
  typeIcon,
} from './core.js';

const R = { role: 'professor' };
const linkCartao = 'color:inherit;text-decoration:none';

/* ================================================================ P01 visão geral */
route('p/inicio', async () => {
  page(loading());
  const d = await api('/prof/overview');
  const k = d.kpis;
  page(html`${header('Bom dia, professor!', 'Acompanhe suas turmas e continue criando materiais.', html`
      <button class="btn btn--contorno" data-upload>Adicionar conteúdo</button>
      <a class="btn btn--primario" href="#/p/estudio">Gerar materiais com IA</a>
      <a class="btn btn--escuro" href="#/p/jogos?novo=1">Criar jogo ao vivo</a>`)}
    <div class="grade grade-4">
      ${kpi('Turmas ativas', pad2(k.classes), 'suas turmas')}
      ${kpi('Materiais criados', pad2(k.materials), `+${k.materials_week} esta semana`, 'verde')}
      ${kpi('Entregas para corrigir', pad2(k.to_grade), k.due_today ? `${k.due_today} atividade(s) vencem hoje` : 'nenhuma vence hoje', k.to_grade ? 'vermelho' : '')}
      ${kpi('Jogos abertos', pad2(k.games), d.games[0] ? d.games[0].title : 'nenhum agendado')}
    </div>
    <div class="grade grade-lateral">
      <div class="pilha">
        <section><div class="secao__topo"><h2>Atividades em andamento</h2><a href="#/p/atividades">Ver todas</a></div>
          ${d.activities.length ? html`<div class="tabela-caixa"><table class="tabela"><thead><tr><th>Atividade</th><th>Turma</th><th>Entregas</th><th>Corrigir</th><th>Prazo</th></tr></thead><tbody>
            ${d.activities.map((a) => html`<tr><td><a href="#/p/correcao/${a.id}">${a.title}</a></td><td>${a.class_name}</td><td>${a.delivered}/${a.total}</td><td>${a.pending ? html`<span class="tag tag--vermelho">${a.pending}</span>` : '—'}</td><td>${dueTag(a.due_date)}</td></tr>`)}
          </tbody></table></div>` : empty('Nenhuma atividade publicada', 'Crie uma atividade a partir do banco de questões.', html`<a class="btn btn--contorno btn--p" href="#/p/atividades">Criar atividade</a>`)}</section>
        <section><div class="secao__topo"><h2>Últimos materiais</h2><a href="#/p/materiais">Ver todos</a></div>
          ${d.materials.length ? html`<div class="tabela-caixa"><table class="tabela"><thead><tr><th>Material</th><th>Tipo</th><th>Status</th><th>Atualizado</th></tr></thead><tbody>
            ${d.materials.map((m) => html`<tr><td><a href="#/p/material/${m.id}">${m.title}</a></td><td>${TYPE_LABEL[m.type]}</td><td>${tag(m.status)}</td><td>${fmtDate(m.updated_at)}</td></tr>`)}
          </tbody></table></div>` : empty('Nenhum material ainda', 'Envie um PDF e use o Estúdio de IA.')}</section>
      </div>
      <div class="pilha">
        <section class="cartao"><div class="cartao__topo"><h2 class="cartao__titulo">Média das turmas (0–10)</h2></div>
          ${bars(d.performance.map((p) => ({ label: p.name, value: p.avg })))}</section>
        <section class="cartao"><div class="cartao__topo"><h2 class="cartao__titulo">Documentos recentes</h2><a href="#/p/biblioteca">Biblioteca</a></div>
          ${d.documents.length ? html`<ul class="lista-simples">${d.documents.map((x) => html`<li><a href="#/p/documento/${x.id}">${x.title}</a>${tag(x.status)}</li>`)}</ul>` : html`<p class="texto-fraco">Nenhum documento enviado.</p>`}</section>
        <section class="cartao"><div class="cartao__topo"><h2 class="cartao__titulo">Ações rápidas</h2></div>
          <button class="btn btn--contorno btn--bloco" data-upload>Adicionar conteúdo</button>
          <a class="btn btn--primario btn--bloco" href="#/p/estudio">Gerar materiais com IA</a>
          <a class="btn btn--contorno btn--bloco" href="#/p/questoes">Banco de questões</a></section>
      </div>
    </div>`).querySelectorAll('[data-upload]').forEach((b) => { b.onclick = () => uploadModal(); });
}, R);

/* ================================================================ upload (P07) */
export async function uploadModal({ subjectId, topicId } = {}) {
  const subs = await api('/prof/subjects');
  if (!subs.length) return toast('Você ainda não tem disciplinas. A coordenação da escola precisa vincular você a uma turma.', 'erro');
  const sel = subjectId || subs[0].id;
  modal('Enviar conteúdo', html`<form id="f-up">
    <label class="upload" data-drop><input type="file" name="file" accept=".pdf,.docx,.txt,.md,.html">
      ${icon('upload', 28)}<strong>Arraste o arquivo ou clique para escolher</strong><span class="texto-fraco">PDF, DOCX, TXT ou MD · até 25 MB</span><span class="texto-fraco" data-nome></span></label>
    <details><summary class="link-sutil" style="cursor:pointer">Ou cole o texto do conteúdo</summary><textarea class="entrada" name="text" rows="6" placeholder="Cole aqui o texto da apostila ou resumo…" style="margin-top:8px"></textarea></details>
    <label class="campo"><span>Título</span><input class="entrada" name="title" placeholder="Ex.: Funções do 1º grau (opcional: usa o nome do arquivo)"></label>
    <div class="campos-2">
      <label class="campo"><span>Disciplina</span><select class="entrada" name="subject_id">${subs.map((s) => html`<option value="${s.id}" ${s.id === sel ? 'selected' : ''}>${s.name} · ${s.class_name}</option>`)}</select></label>
      <label class="campo"><span>Assunto</span><select class="entrada" name="topic_id"></select></label>
    </div>
    <label class="campo"><span>Pasta (opcional)</span><input class="entrada" name="folder" placeholder="Ex.: Matemática / Álgebra"></label>
    <label class="linha" style="gap:8px;cursor:pointer"><input type="checkbox" name="shared" checked> Disponibilizar o arquivo original para os alunos da turma (ver e baixar)</label>
    ${aviso('O arquivo original fica guardado no formato em que foi enviado e pode ser baixado depois. Em segundo plano, o sistema extrai o texto e a IA identifica os principais tópicos.')}
    <div class="linha linha--fim"><button type="button" class="btn btn--contorno" data-fechar>Cancelar</button><button class="btn btn--primario" type="submit">Enviar e processar</button></div>
  </form>`, {
    onMount: (el, close) => {
      const f = el.querySelector('#f-up');
      const fileInput = f.querySelector('input[type=file]');
      const drop = f.querySelector('[data-drop]');
      const loadTopics = async () => {
        const d = await api('/prof/subjects/' + f.subject_id.value);
        f.topic_id.innerHTML = html`<option value="">Sem assunto</option>${d.topics.map((t) => html`<option value="${t.id}" ${t.id === topicId ? 'selected' : ''}>${t.name}</option>`)}`.s;
      };
      f.subject_id.onchange = loadTopics;
      loadTopics();
      fileInput.onchange = () => { f.querySelector('[data-nome]').textContent = fileInput.files[0]?.name || ''; };
      ['dragenter', 'dragover'].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add('arrastando'); }));
      ['dragleave', 'drop'].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove('arrastando'); }));
      drop.addEventListener('drop', (e) => { fileInput.files = e.dataTransfer.files; fileInput.onchange(); });
      f.addEventListener('submit', async (e) => {
        e.preventDefault();
        await busy(f.querySelector('[type=submit]'), async () => {
          const fd = new FormData();
          ['subject_id', 'title', 'folder', 'text'].forEach((k) => fd.append(k, f[k].value));
          if (f.topic_id.value) fd.append('topic_id', f.topic_id.value);
          fd.append('shared', f.shared.checked ? 'true' : 'false');
          if (fileInput.files[0]) fd.append('file', fileInput.files[0]);
          const r = await api('/prof/documents', { method: 'POST', form: fd });
          close();
          toast('Documento enviado. Processando…');
          go('#/p/documento/' + r.id);
        });
      });
    },
  });
}

/* ================================================================ P02 disciplinas */
route('p/disciplinas', async () => {
  page(loading());
  const subs = await api('/prof/subjects');
  page(html`${header('Minhas disciplinas', 'As disciplinas e turmas são definidas pela coordenação. Aqui você organiza os conteúdos de cada uma.')}
    ${subs.length ? '' : empty('Nenhuma disciplina vinculada ainda', 'A coordenação da escola vincula você às disciplinas e turmas em que vai dar aula. Se algo estiver faltando, abra um chamado em Atendimento.', html`<a class="btn btn--contorno" href="#/atendimento/novo?categoria=secretaria">Falar com a coordenação</a>`)}
    <div class="grade grade-3">${subs.map((s) => html`<a class="cartao disciplina" href="#/p/disciplina/${s.id}" style="${linkCartao}">
      <div class="capa" style="background:${s.color}">${s.class_name} · ${s.students} alunos</div>
      <h3>${s.name}</h3>${s.active ? '' : tag('inativo', 'Inativa')}
      <p class="texto-fraco">${s.topics} assuntos · ${s.materials} materiais (${s.published} publicados) · ${s.activities} atividades</p>
      ${progress(s.materials ? (100 * s.published) / s.materials : 0, 'verde')}</a>`)}</div>`);
}, R);

function subjectModal(s) {
  modal('Configurações da disciplina', html`<form id="f">
    <p><strong>${s.name}</strong> · ${s.class_name}</p>
    <p class="texto-fraco">Nome, turma e professor responsável são definidos pela coordenação da escola.</p>
    <label class="campo"><span>Descrição (aparece para os alunos)</span><textarea class="entrada" name="description">${s.description || ''}</textarea></label>
    <label class="campo"><span>Cor</span><input class="entrada" type="color" name="color" value="${s.color || '#2563EB'}" style="height:42px;padding:4px;max-width:160px"></label>
    <div class="linha linha--fim"><button type="button" class="btn btn--contorno" data-fechar>Cancelar</button><button class="btn btn--primario">Salvar</button></div></form>`, {
    onMount: (el, close) => {
      const f = el.querySelector('#f');
      f.addEventListener('submit', async (e) => {
        e.preventDefault();
        await busy(f.querySelector('.btn--primario'), async () => {
          await api('/prof/subjects/' + s.id, { method: 'PUT', body: formData(f) });
          close(); toast('Disciplina salva'); go(location.hash);
        });
      });
    },
  });
}

/* ================================================================ P03 disciplina (abas) */
route('p/disciplina/:id', async ({ id }, q) => {
  page(loading());
  const d = await api('/prof/subjects/' + id);
  const s = d.subject;
  const aba = q.aba || 'conteudos';
  const el = page(html`
    <a href="#/p/disciplinas" class="link-sutil">← Minhas disciplinas</a>
    ${header(s.name, `${s.class_name} · ${s.students} alunos${s.description ? ' · ' + s.description : ''}`, html`
      <button class="btn btn--contorno" data-upload>Enviar conteúdo</button><a class="btn btn--primario" href="#/p/estudio?disciplina=${s.id}">Gerar com IA</a>`)}
    ${tabs([['conteudos', 'Conteúdos'], ['atividades', 'Atividades'], ['jogos', 'Jogos'], ['desempenho', 'Desempenho'], ['configuracoes', 'Configurações']], aba)}
    <div id="aba"></div>`);
  el.querySelector('[data-upload]').onclick = () => uploadModal({ subjectId: s.id });
  const box = el.querySelector('#aba');
  const show = async (a) => {
    history.replaceState(null, '', `#/p/disciplina/${id}?aba=${a}`);
    box.innerHTML = loading().s;
    if (a === 'conteudos') return abaConteudos(box, d);
    if (a === 'atividades') {
      const acts = await api('/prof/activities?subject_id=' + id);
      box.innerHTML = html`<div class="linha linha--fim" style="margin-bottom:12px"><a class="btn btn--primario" href="#/p/atividade/nova?disciplina=${id}">+ Nova atividade</a></div>${tabelaAtividades(acts)}`.s;
    }
    if (a === 'jogos') {
      const gs = (await api('/jogos')).filter((g) => g.subject_name === s.name);
      box.innerHTML = html`<div class="linha linha--fim" style="margin-bottom:12px"><a class="btn btn--primario" href="#/p/jogos?novo=1&disciplina=${id}">+ Criar jogo</a></div>
        ${gs.length ? html`<div class="lista-itens">${gs.map((g) => html`<a class="item" href="#/p/jogo/${g.id}" style="${linkCartao}"><div class="item__info"><span class="tipo-icone">${icon('jogo')}</span><div><strong>${g.title}</strong><small>${g.questions} perguntas · ${g.players} participantes</small></div></div>${tag(g.status === 'rascunho' ? 'rascunho' : g.status)}</a>`)}</div>` : empty('Nenhum jogo nesta disciplina')}`.s;
    }
    if (a === 'desempenho') box.innerHTML = (await painelDesempenho({ subject_id: id })).s;
    if (a === 'configuracoes') {
      box.innerHTML = html`<section class="cartao" style="max-width:640px"><h2 class="cartao__titulo">Configurações da disciplina</h2>
        <p class="texto-suave">Você pode ajustar a descrição e a cor. Nome, turma, professor e a situação da disciplina (ativa ou desativada) são definidos pela coordenação.</p>
        <button class="btn btn--escuro" data-editar>Editar configurações</button></section>`.s;
      box.querySelector('[data-editar]').onclick = () => subjectModal(s);
    }
  };
  bindTabs(el, show);
  show(aba);
}, R);

function abaConteudos(box, d) {
  const sid = d.subject.id;
  const docLinha = (x) => html`<div class="material-linha"><div class="linha">${icon('pasta')}<a href="#/p/documento/${x.id}">${x.title}</a>${tag(x.status)}</div>
    <a class="btn btn--contorno btn--p" href="#/p/estudio?doc=${x.id}">Gerar com IA</a></div>`;
  const matLinha = (m) => html`<div class="material-linha"><div class="linha">${typeIcon(m.type)}<a href="#/p/material/${m.id}">${m.title}</a></div>${tag(m.status)}</div>`;
  box.innerHTML = html`<div class="linha linha--entre" style="margin-bottom:14px"><p class="texto-suave">Organize por assunto. Rascunhos só aparecem para você.</p>
    <form class="linha" id="f-topico"><input class="entrada" name="name" placeholder="Novo assunto (ex.: Capítulo 3)" required style="width:260px"><button class="btn btn--escuro">+ Assunto</button></form></div>
    <div class="pilha">${d.topics.map((t) => html`<section class="assunto">
      <div class="assunto__topo"><h3>${t.name}</h3><div class="linha">
        <span class="texto-fraco">${t.documents.length} documento(s) · ${t.materials.length} material(is)</span>
        <button class="btn btn--contorno btn--p" data-up="${t.id}">Enviar</button><button class="btn btn--link" data-ren="${t.id}" data-nome="${t.name}">Renomear</button><button class="btn btn--link texto-vermelho" data-del="${t.id}">Excluir</button></div></div>
      <div class="assunto__corpo">${t.documents.map(docLinha)}${t.materials.map(matLinha)}${!t.documents.length && !t.materials.length ? html`<p class="texto-fraco">Nenhum conteúdo neste assunto.</p>` : ''}</div></section>`)}
      ${(() => {
        const soltosDocs = d.documents.filter((x) => !x.topic_id);
        return soltosDocs.length || d.loose_materials.length ? html`<section class="assunto"><div class="assunto__topo"><h3>Sem assunto</h3></div><div class="assunto__corpo">${soltosDocs.map(docLinha)}${d.loose_materials.map(matLinha)}</div></section>` : '';
      })()}
      ${!d.topics.length && !d.documents.length ? empty('Disciplina vazia', 'Crie assuntos e envie o primeiro material.') : ''}</div>`.s;
  const f = box.querySelector('#f-topico');
  f.addEventListener('submit', async (e) => {
    e.preventDefault();
    await api(`/prof/subjects/${sid}/topics`, { method: 'POST', body: formData(f) });
    go(`#/p/disciplina/${sid}?aba=conteudos`);
  });
  box.querySelectorAll('[data-up]').forEach((b) => { b.onclick = () => uploadModal({ subjectId: sid, topicId: Number(b.dataset.up) }); });
  box.querySelectorAll('[data-ren]').forEach((b) => {
    b.onclick = () => modal('Renomear assunto', html`<form id="f"><input class="entrada" name="name" value="${b.dataset.nome}" required><div class="linha linha--fim"><button class="btn btn--escuro">Salvar</button></div></form>`, {
      onMount: (el, close) => el.querySelector('#f').addEventListener('submit', async (e) => {
        e.preventDefault();
        await api('/prof/topics/' + b.dataset.ren, { method: 'PUT', body: formData(e.target) });
        close(); go(`#/p/disciplina/${sid}?aba=conteudos`);
      }),
    });
  });
  box.querySelectorAll('[data-del]').forEach((b) => {
    b.onclick = async () => {
      if (!(await confirmar('Excluir este assunto? Os materiais continuam na disciplina, sem assunto.', { ok: 'Excluir', perigo: true }))) return;
      await api('/prof/topics/' + b.dataset.del, { method: 'DELETE' });
      go(`#/p/disciplina/${sid}?aba=conteudos`);
    };
  });
}

export function tabelaAtividades(acts) {
  if (!acts.length) return empty('Nenhuma atividade', 'Monte uma lista com questões do banco.');
  return html`<div class="tabela-caixa"><table class="tabela"><thead><tr><th>Atividade</th><th>Turma</th><th>Tipo</th><th>Status</th><th>Entregas</th><th>Média</th><th>Prazo</th><th></th></tr></thead><tbody>
    ${acts.map((a) => html`<tr><td><a href="#/p/atividade/${a.id}">${a.title}</a><div class="texto-fraco">${a.subject_name} · ${a.questions} questões</div></td><td>${a.class_name}</td>
      <td>${a.kind === 'simulado' ? 'Simulado' : a.kind === 'prova' ? 'Prova' : 'Atividade'}</td><td>${tag(a.status)}</td>
      <td>${a.delivered}/${a.students}${a.to_grade ? html` <span class="tag tag--vermelho" title="aguardando correção">${a.to_grade}</span>` : ''}</td>
      <td>${nota(a.avg)}</td><td>${a.status === 'rascunho' ? '—' : dueTag(a.due_date)}</td>
      <td><div class="acoes-icone">${a.status !== 'rascunho' ? html`<a class="btn btn--contorno btn--p" href="#/p/correcao/${a.id}">Correção</a>` : ''}
        <button class="btn btn--link texto-vermelho" data-excluir-atividade="${a.id}" data-titulo="${a.title}" data-entregas="${a.delivered}">Excluir</button></div></td></tr>`)}</tbody></table></div>`;
}

export async function excluirAtividade(id, titulo, entregas, destino) {
  const aviso_ = Number(entregas) ? ` Ela já tem ${entregas} entrega(s): as respostas e notas dos alunos também serão apagadas.` : '';
  if (!(await confirmar(`Excluir a atividade “${titulo}” definitivamente?${aviso_} As questões continuam no banco de questões.`, { ok: 'Excluir', perigo: true }))) return;
  try {
    await api('/prof/activities/' + id, { method: 'DELETE' });
    toast('Atividade excluída');
    go(destino || location.hash);
  } catch (e) { toast(e.message, 'erro'); }
}

// A tabela de atividades aparece em várias telas: um único ouvinte cuida do botão Excluir.
document.addEventListener('click', (e) => {
  const b = e.target.closest('[data-excluir-atividade]');
  if (b) excluirAtividade(b.dataset.excluirAtividade, b.dataset.titulo, b.dataset.entregas);
});

/* ================================================================ P05 turmas e alunos */
route('p/turmas', async () => {
  page(loading());
  const cs = await api('/prof/classes');
  page(html`${header('Turmas e alunos', 'Turmas vinculadas às suas disciplinas.')}
    ${cs.length ? html`<div class="grade grade-3">${cs.map((c) => html`<a class="cartao" href="#/p/turma/${c.id}" style="${linkCartao}">
      <div class="linha linha--entre"><h3>${c.name}</h3><span class="tag tag--azul">${c.students} alunos</span></div>
      <p class="texto-fraco">${c.subjects.map((s) => s.name).join(', ')}</p>
      <div class="linha linha--entre"><span class="texto-suave">Média: <strong>${nota(c.avg)}</strong></span><span class="texto-fraco">Código: <code>${c.code}</code></span></div></a>`)}</div>`
    : empty('Nenhuma turma vinculada', 'O gestor da instituição vincula você às turmas.')}`);
}, R);

route('p/turma/:id', async ({ id }) => {
  page(loading());
  const d = await api('/prof/classes/' + id);
  const el = page(html`<a href="#/p/turmas" class="link-sutil">← Turmas</a>
    ${header(d.class.name, `${d.students.length} alunos · ${d.activities} atividades publicadas`)}
    ${aviso(html`Os alunos podem criar a conta com o código da turma <strong>${d.class.code}</strong> em “Criar conta com o código”.`)}
    <div class="filtros"><input class="entrada entrada--busca" id="q" placeholder="Buscar aluno…"></div>
    <div class="tabela-caixa"><table class="tabela"><thead><tr><th>Aluno</th><th>E-mail</th><th>Entregas</th><th>Conclusão</th><th>Média</th></tr></thead><tbody id="lista">
    ${d.students.map((s) => html`<tr data-nome="${s.name.toLowerCase()}"><td><div class="linha"><span class="avatar">${initials(s.name)}</span><a href="#/p/aluno/${s.id}">${s.name}</a></div></td><td>${s.email}</td>
      <td>${s.delivered}</td><td style="min-width:140px">${progress(s.completion, s.completion < 50 ? 'vermelho' : 'verde')}</td>
      <td>${s.avg == null ? '—' : html`<span class="tag tag--${s.avg < 6 ? 'vermelho' : s.avg < 7 ? 'amarelo' : 'verde'}">${nota(s.avg)}</span>`}</td></tr>`)}</tbody></table></div>`);
  el.querySelector('#q').addEventListener('input', (e) => {
    const q = e.target.value.toLowerCase();
    el.querySelectorAll('#lista tr').forEach((tr) => { tr.hidden = !tr.dataset.nome.includes(q); });
  });
}, R);

route('p/aluno/:id', async ({ id }) => {
  page(loading());
  const d = await api('/prof/students/' + id);
  const st = d.student;
  const graded = d.submissions.filter((s) => s.score != null && s.status === 'corrigida');
  page(html`<a href="#/p/turma/${st.class_id}" class="link-sutil">← ${st.class_name}</a>
    <div class="cabecalho"><div class="linha"><span class="avatar avatar--g">${initials(st.name)}</span><div><h1>${st.name}</h1><p>${st.class_name} · ${st.email}</p></div></div></div>
    <div class="grade grade-3">
      ${kpi('Média geral', nota(graded.length ? graded.reduce((a, s) => a + (10 * s.score) / s.points, 0) / graded.length : null))}
      ${kpi('Atividades entregues', pad2(d.submissions.length))}
      ${kpi('Assuntos com dificuldade', pad2(d.topics.filter((t) => t.pct < 60).length), 'acerto abaixo de 60%', 'vermelho')}
    </div>
    <div class="grade grade-2">
      <section class="cartao"><h2 class="cartao__titulo">Evolução das notas</h2>${lineChart(graded.map((s) => ({ label: s.title, value: (10 * s.score) / s.points })))}</section>
      <section class="cartao"><h2 class="cartao__titulo">Acerto por assunto</h2>${hbars(d.topics.map((t) => ({ label: `${t.topic} (${t.subject})`, value: t.pct })))}</section>
    </div>
    <section><div class="secao__topo"><h2>Atividades</h2></div>${d.submissions.length ? html`<div class="tabela-caixa"><table class="tabela"><thead><tr><th>Atividade</th><th>Disciplina</th><th>Status</th><th>Nota</th><th>Entregue em</th></tr></thead><tbody>
      ${d.submissions.map((s) => html`<tr><td>${s.title}</td><td>${s.subject}</td><td>${tag(s.status)}</td><td>${s.score == null ? '—' : `${nota(s.score)} / ${nota(s.points)}`}</td><td>${fmtDate(s.submitted_at)}</td></tr>`)}</tbody></table></div>` : empty('Nenhuma entrega')}</section>
    <section class="cartao"><h2 class="cartao__titulo">Materiais estudados</h2>${d.progress.length ? html`<ul class="lista-simples">${d.progress.map((p) => html`<li><span>${p.title} <span class="texto-fraco">· ${TYPE_LABEL[p.type]}</span></span><span style="width:160px">${progress(p.pct, 'verde')}</span></li>`)}</ul>` : html`<p class="texto-fraco">Ainda não abriu materiais.</p>`}</section>`);
}, R);

/* ================================================================ P06 biblioteca */
route('p/biblioteca', async (_, q) => {
  page(loading());
  const arquivados = q.arquivados === '1';
  const [docs, subs] = await Promise.all([api('/prof/documents?archived=' + (arquivados ? 1 : 0)), api('/prof/subjects')]);
  const el = page(html`${header('Biblioteca de conteúdos', 'Repositório dos arquivos usados como fonte para a IA.', html`<button class="btn btn--primario" data-upload>${icon('upload', 16)} Enviar conteúdo</button>`)}
    ${tabs([['ativos', 'Documentos'], ['arquivados', 'Arquivados']], arquivados ? 'arquivados' : 'ativos')}
    <div class="filtros"><input class="entrada entrada--busca" id="q" placeholder="Buscar documento…">
      <select class="entrada" id="disc"><option value="">Todas as disciplinas</option>${subs.map((s) => html`<option value="${s.id}">${s.name} · ${s.class_name}</option>`)}</select>
      <select class="entrada" id="pasta"><option value="">Todas as pastas</option>${[...new Set(docs.map((d) => d.folder).filter(Boolean))].map((p) => html`<option>${p}</option>`)}</select></div>
    ${docs.length ? html`<div class="tabela-caixa"><table class="tabela"><thead><tr><th>Documento</th><th>Disciplina / pasta</th><th>Status</th><th>Materiais gerados</th><th>Enviado</th><th></th></tr></thead><tbody id="lista">
      ${docs.map((d) => html`<tr data-busca="${d.title.toLowerCase()}" data-disc="${d.subject_id}" data-pasta="${d.folder}">
        <td><div class="linha">${icon('conteudo')}<div><a href="#/p/documento/${d.id}">${d.title}</a><div class="texto-fraco">${d.filename || 'texto colado'} · ${(d.size / 1024).toFixed(0)} KB${d.shared ? ' · visível aos alunos' : ' · só professor'}</div></div></div></td>
        <td>${d.subject_name}${d.topic_name ? ' · ' + d.topic_name : ''}<div class="texto-fraco">${d.folder || '—'}</div></td>
        <td>${d.status === 'processando' ? html`${tag('processando', `Processando ${d.progress}%`)}` : tag(d.status)}</td>
        <td>${d.materials}</td><td>${fmtDate(d.created_at)}</td>
        <td><div class="acoes-icone">${d.status === 'concluido' ? html`<a class="btn btn--contorno btn--p" href="#/p/estudio?doc=${d.id}">Gerar com IA</a>` : ''}<a class="btn btn--link" href="#/p/documento/${d.id}">Detalhes</a><button class="btn btn--link" data-baixar="${d.id}" data-nome="${d.filename || d.title + '.txt'}" title="Baixar o arquivo original">${icon('baixar', 16)} Baixar</button><button class="btn btn--link texto-vermelho" data-excluir="${d.id}" data-titulo="${d.title}">Excluir</button></div></td></tr>`)}
      </tbody></table></div>` : empty(arquivados ? 'Nenhum documento arquivado' : 'Nenhum documento enviado', 'Envie PDFs, documentos ou cole textos para começar.')}`);
  el.querySelector('[data-upload]').onclick = () => uploadModal();
  bindTabs(el, (a) => go('#/p/biblioteca' + (a === 'arquivados' ? '?arquivados=1' : '')));
  const filtrar = () => {
    const t = el.querySelector('#q').value.toLowerCase(), ds = el.querySelector('#disc').value, p = el.querySelector('#pasta').value;
    el.querySelectorAll('#lista tr').forEach((tr) => { tr.hidden = (t && !tr.dataset.busca.includes(t)) || (ds && tr.dataset.disc !== ds) || (p && tr.dataset.pasta !== p); });
  };
  ['#q', '#disc', '#pasta'].forEach((s) => el.querySelector(s).addEventListener('input', filtrar));
  el.querySelectorAll('[data-excluir]').forEach((b) => { b.onclick = () => excluirDocumento(b.dataset.excluir, b.dataset.titulo); });
  el.querySelectorAll('[data-baixar]').forEach((b) => { b.onclick = () => busy(b, () => download(`/prof/documents/${b.dataset.baixar}/arquivo`, b.dataset.nome)); });
  if (docs.some((d) => ['enviado', 'processando'].includes(d.status))) {
    const t = setTimeout(() => go(location.hash), 3000);
    onLeave(() => clearTimeout(t));
  }
}, R);

async function excluirDocumento(id, titulo) {
  if (!(await confirmar(`Excluir “${titulo}” definitivamente? O arquivo e o texto extraído serão apagados. Os materiais já gerados a partir dele continuam, mas não poderão ser regenerados.`, { ok: 'Excluir', perigo: true }))) return;
  try {
    await api('/prof/documents/' + id, { method: 'DELETE' });
    toast('Documento excluído');
    go(location.hash.startsWith('#/p/biblioteca') ? location.hash : '#/p/biblioteca');
  } catch (e) { toast(e.message, 'erro'); }
}

/* ================================================================ P08 processamento / detalhe do documento */
route('p/documento/:id', async ({ id }) => {
  const d = await api('/prof/documents/' + id);
  const etapa = { enviado: 1, processando: d.progress < 55 ? 2 : 3, concluido: 4, erro: 0 }[d.status];
  const etapas = ['Arquivo recebido', 'Extraindo o texto', 'IA identificando tópicos e conceitos', 'Pronto para gerar materiais'];
  const el = page(html`<a href="#/p/biblioteca" class="link-sutil">← Biblioteca</a>
    ${header(d.title, `${d.subject_name} · ${d.filename || 'texto colado'} · enviado em ${fmtDate(d.created_at)}`, html`
      <button class="btn btn--contorno" data-editar>Renomear / mover</button>
      ${d.status === 'concluido' ? html`<a class="btn btn--primario" href="#/p/estudio?doc=${d.id}">Abrir no Estúdio de IA</a>` : ''}`)}
    ${d.status === 'erro' ? aviso(html`Falha no processamento: ${d.error} <button class="btn btn--link" data-reproc>Tentar novamente</button>`, 'vermelho') : ''}
    ${d.status === 'concluido' && d.empty_pages ? aviso(`${d.empty_pages} de ${d.pages} página(s) não têm texto extraível — provavelmente são imagens escaneadas. O conteúdo delas não chega à IA; se for importante, envie a versão digital do arquivo ou cole o texto.`, 'amarelo') : ''}
    ${d.status === 'concluido' && d.chars > d.ai_chars ? aviso(`Este documento tem ${d.chars.toLocaleString('pt-BR')} caracteres, e a IA lê até ${d.ai_chars.toLocaleString('pt-BR')} por geração (cerca de ${Math.max(1, Math.floor((d.ai_chars / d.chars) * (d.pages || 1)))} página(s) dele). No Estúdio de IA, escolha o intervalo de páginas para gerar materiais de cada parte.`) : ''}
    <div class="grade grade-lateral">
      <div class="pilha">
        <section class="cartao"><div class="cartao__topo"><h2 class="cartao__titulo">Processamento da IA</h2>${tag(d.status)}</div>
          ${d.status !== 'concluido' && d.status !== 'erro' ? progress(d.progress) : ''}
          <div class="etapas">${etapas.map((t, i) => html`<div class="etapa ${i + 1 < etapa || d.status === 'concluido' ? 'etapa--feita' : i + 1 === etapa ? 'etapa--atual' : ''}"><span class="etapa__n">${i + 1 < etapa || d.status === 'concluido' ? '✓' : i + 1}</span><span>${t}</span>${i + 1 === etapa && d.status !== 'concluido' ? html`<span class="spinner"></span>` : ''}</div>`)}</div></section>
        ${d.topics.length ? html`<section class="cartao"><h2 class="cartao__titulo">Tópicos identificados pela IA</h2><div class="chips">${d.topics.map((t) => html`<span class="chip">${t}</span>`)}</div></section>` : ''}
        ${d.text_preview ? html`<section class="cartao"><div class="cartao__topo"><h2 class="cartao__titulo">Texto extraído</h2><span class="texto-fraco">${d.pages ? `${d.pages} páginas · ` : ''}${d.chars.toLocaleString('pt-BR')} caracteres</span></div><div class="texto-documento">${d.text_preview}</div>${d.text_truncated ? html`<p class="texto-fraco">A prévia mostra o início do texto; o documento completo foi extraído e está salvo.</p>` : ''}</section>` : ''}
      </div>
      <div class="pilha">
        <section class="cartao"><div class="cartao__topo"><h2 class="cartao__titulo">Materiais gerados a partir deste documento</h2></div>
          ${d.materials.length ? html`<ul class="lista-simples">${d.materials.map((m) => html`<li><span class="linha">${typeIcon(m.type)}<a href="#/p/material/${m.id}">${m.title}</a></span>${tag(m.status)}</li>`)}</ul>` : html`<p class="texto-fraco">Nenhum ainda. Gere vários formatos sem reenviar o arquivo.</p>`}</section>
        <section class="cartao"><h2 class="cartao__titulo">Arquivo</h2>
          <button class="btn btn--primario btn--bloco" data-baixar>${icon('baixar', 16)} Baixar ${d.filename ? 'arquivo original' : 'texto (.txt)'}</button>
          <label class="linha" style="gap:8px;cursor:pointer;margin:6px 0"><input type="checkbox" data-shared ${d.shared ? 'checked' : ''}> Alunos da turma podem ver e baixar</label>
          <label class="btn btn--contorno btn--bloco" style="cursor:pointer">Substituir arquivo<input type="file" data-subst accept=".pdf,.docx,.txt,.md,.html" hidden></label>
          <button class="btn btn--contorno btn--bloco" data-reproc>Reprocessar</button>
          <button class="btn btn--contorno btn--bloco" data-arquivar>${d.archived ? 'Restaurar' : 'Arquivar'}</button>
          <button class="btn btn--perigo btn--bloco" data-excluir>Excluir documento</button></section>
      </div>
    </div>`);
  el.querySelectorAll('[data-reproc]').forEach((b) => { b.onclick = async () => { await api(`/prof/documents/${id}/reprocess`, { method: 'POST' }); go(location.hash); }; });
  el.querySelector('[data-subst]').onchange = async (e) => {
    const fd = new FormData();
    fd.append('file', e.target.files[0]);
    try { await api(`/prof/documents/${id}/replace`, { method: 'POST', form: fd }); toast('Arquivo substituído. Reprocessando…'); go(location.hash); } catch (err) { toast(err.message, 'erro'); }
  };
  const salvar = (extra) => api('/prof/documents/' + id, { method: 'PUT', body: { title: d.title, folder: d.folder, topic_id: d.topic_id, archived: !!d.archived, ...extra } });
  el.querySelector('[data-baixar]').onclick = (e) => busy(e.currentTarget, () => download(`/prof/documents/${id}/arquivo`, d.filename || d.title + '.txt'));
  el.querySelector('[data-shared]').onchange = async (e) => {
    try {
      await salvar({ shared: e.target.checked });
      d.shared = e.target.checked ? 1 : 0;
      toast(e.target.checked ? 'Arquivo liberado para os alunos da turma' : 'Arquivo oculto para os alunos');
    } catch (err) { e.target.checked = !e.target.checked; toast(err.message, 'erro'); }
  };
  el.querySelector('[data-excluir]').onclick = () => excluirDocumento(id, d.title);
  el.querySelector('[data-arquivar]').onclick = async () => { await salvar({ archived: !d.archived }); toast(d.archived ? 'Documento restaurado' : 'Documento arquivado'); go('#/p/biblioteca'); };
  el.querySelector('[data-editar]').onclick = async () => {
    const sd = await api('/prof/subjects/' + d.subject_id);
    modal('Renomear / mover', html`<form id="f"><label class="campo"><span>Título</span><input class="entrada" name="title" value="${d.title}" required></label>
      <label class="campo"><span>Pasta</span><input class="entrada" name="folder" value="${d.folder}"></label>
      <label class="campo"><span>Assunto</span><select class="entrada" name="topic_id"><option value="">Sem assunto</option>${sd.topics.map((t) => html`<option value="${t.id}" ${t.id === d.topic_id ? 'selected' : ''}>${t.name}</option>`)}</select></label>
      <div class="linha linha--fim"><button class="btn btn--escuro">Salvar</button></div></form>`, {
      onMount: (m, close) => m.querySelector('#f').addEventListener('submit', async (e) => {
        e.preventDefault();
        const v = formData(e.target);
        await salvar({ title: v.title, folder: v.folder, topic_id: v.topic_id ? Number(v.topic_id) : null });
        close(); go(location.hash);
      }),
    });
  };
  if (['enviado', 'processando'].includes(d.status)) {
    const t = setTimeout(() => go(location.hash), 1500);
    onLeave(() => clearTimeout(t));
  }
}, R);

/* ================================================================ P17 desempenho */
export async function painelDesempenho(filtro) {
  const qs = new URLSearchParams(Object.entries(filtro).filter(([, v]) => v)).toString();
  const p = await api('/prof/performance?' + qs);
  const k = p.kpis;
  return html`<div class="grade grade-4" style="margin-bottom:16px">
      ${kpi('Média geral', nota(k.avg), 'escala de 0 a 10', k.avg != null && k.avg < 6 ? 'vermelho' : 'verde')}
      ${kpi('Taxa de conclusão', k.completion == null ? '—' : k.completion + '%', 'entregas / esperado')}
      ${kpi('Atividades', pad2(k.activities), `${k.answers} respostas analisadas`)}
      ${kpi('Alunos em atenção', pad2(k.at_risk), 'média abaixo de 6', k.at_risk ? 'vermelho' : '')}</div>
    <div class="grade grade-2">
      <section class="cartao"><h2 class="cartao__titulo">Evolução ao longo do tempo</h2>${lineChart(p.evolution.map((e) => ({ label: e.label, value: e.avg })))}</section>
      <section class="cartao"><h2 class="cartao__titulo">Comparação por turma</h2>${bars(p.by_class.map((c) => ({ label: c.name, value: c.avg })))}</section>
      <section class="cartao"><h2 class="cartao__titulo">Acerto por assunto</h2>${hbars(p.topics.map((t) => ({ label: `${t.topic} · ${t.subject}`, value: t.pct })))}</section>
      <section class="cartao"><h2 class="cartao__titulo">Questões com maior índice de erro</h2>${p.questions.length ? html`<ul class="lista-simples">${p.questions.map((q) => html`<li><span>${q.statement}</span><span class="tag tag--${q.error_rate >= 50 ? 'vermelho' : 'amarelo'}">${q.error_rate}% erro</span></li>`)}</ul>` : html`<p class="texto-fraco">Sem respostas corrigidas ainda.</p>`}</section>
    </div>
    ${p.review.length ? html`<section class="cartao cartao--destaque" style="margin-top:16px"><h2 class="cartao__titulo">Conteúdos que precisam de revisão</h2>
      <p class="texto-suave">Assuntos com acerto abaixo de 60%. Sugestão: gere um roteiro de revisão, flashcards ou um jogo rápido sobre eles.</p>
      <div class="chips">${p.review.map((t) => html`<span class="chip">${t.topic} · ${t.pct}%</span>`)}</div>
      <div class="linha"><a class="btn btn--primario" href="#/p/estudio">Gerar material de revisão</a><a class="btn btn--contorno" href="#/p/jogos?novo=1">Criar jogo de revisão</a></div></section>` : ''}
    <section style="margin-top:16px"><div class="secao__topo"><h2>Alunos</h2></div>${p.students.length ? html`<div class="tabela-caixa"><table class="tabela"><thead><tr><th>Aluno</th><th>Turma</th><th>Atividades corrigidas</th><th>Média</th></tr></thead><tbody>
      ${p.students.map((s) => html`<tr><td><a href="#/p/aluno/${s.id}">${s.name}</a></td><td>${s.class_name}</td><td>${s.n}</td><td><span class="tag tag--${s.avg < 6 ? 'vermelho' : s.avg < 7 ? 'amarelo' : 'verde'}">${nota(s.avg)}</span></td></tr>`)}</tbody></table></div>` : empty('Sem notas ainda')}</section>`;
}

route('p/desempenho', async (_, q) => {
  page(loading());
  const [subs, classes] = await Promise.all([api('/prof/subjects'), api('/prof/classes')]);
  const filtro = { subject_id: q.disciplina || '', class_id: q.turma || '' };
  const el = page(html`${header('Desempenho', 'Notas, conclusão, evolução e conteúdos que precisam de reforço.', html`<button class="btn btn--contorno" data-csv>Exportar CSV</button>`)}
    <div class="filtros"><select class="entrada" id="disc"><option value="">Todas as disciplinas</option>${subs.map((s) => html`<option value="${s.id}" ${String(s.id) === filtro.subject_id ? 'selected' : ''}>${s.name} · ${s.class_name}</option>`)}</select>
      <select class="entrada" id="turma"><option value="">Todas as turmas</option>${classes.map((c) => html`<option value="${c.id}" ${String(c.id) === filtro.class_id ? 'selected' : ''}>${c.name}</option>`)}</select></div>
    <div id="painel">${loading()}</div>`);
  el.querySelector('#painel').innerHTML = (await painelDesempenho(filtro)).s;
  const mudar = () => go(`#/p/desempenho?disciplina=${el.querySelector('#disc').value}&turma=${el.querySelector('#turma').value}`);
  el.querySelector('#disc').onchange = mudar;
  el.querySelector('#turma').onchange = mudar;
  const qs = new URLSearchParams(Object.entries(filtro).filter(([, v]) => v)).toString();
  el.querySelector('[data-csv]').onclick = (e) => busy(e.currentTarget, () => download('/prof/performance/export.csv?' + qs, 'desempenho.csv'));
}, R);
