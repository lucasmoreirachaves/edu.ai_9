/* EDU.AI – gestor da instituição (H01–H09) */
import {
  S, TYPE_LABEL, api, aviso, bars, bindSeg, bindTabs, busy, confirmar, download, empty, fmtDate, fmtDateTime, formData, go, hbars,
  corTextoMenu, header, html, icon, kpi, loading, modal, nota, pad2, page, progress, refreshIaStatus, resetShell, route, segmented, tabs, tag, toast,
} from './core.js';

const R = { role: 'gestor' };
const PAPEL = { professor: 'Professor', aluno: 'Aluno', secretaria: 'Secretaria', gestor: 'Gestor' };
const SIT_FAT = { aberta: ['amarelo', 'Em aberto'], paga: ['verde', 'Paga'], vencida: ['vermelho', 'Vencida'] };
const BRL = (v) => v.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 });
const medidor = (rot, usado, limite, un = '') => {
  const pct = limite ? Math.round((100 * usado) / limite) : 0;
  return html`<div><div class="linha linha--entre"><span>${rot}</span><strong>${nota(usado)}${un} / ${nota(limite)}${un}</strong></div>${progress(pct, pct > 90 ? 'vermelho' : pct > 70 ? 'amarelo' : 'verde')}</div>`;
};
const convidarLink = (token) => `${location.origin}${location.pathname}#/convite/${token}`;

/* ================================================================ H01 dashboard */
route('g/dashboard', async () => {
  page(loading());
  const d = await api('/gestor/dashboard');
  const k = d.kpis;
  const p = d.plan;
  page(html`${header('Dashboard institucional', `${S.user.institution.name} · visão geral de uso e aprendizagem`, html`<a class="btn btn--contorno" href="#/g/relatorios">Relatórios</a><button class="btn btn--primario" data-convidar>Convidar usuários</button>`)}
    <div class="grade grade-4">${kpi('Alunos ativos', pad2(k.students), `${k.active_week} pessoas acessaram nos últimos 7 dias`, 'azul')}${kpi('Professores', pad2(k.teachers), k.pending_invites ? `${k.pending_invites} convite(s) pendente(s)` : 'todos ativos')}
      ${kpi('Turmas', pad2(k.classes), `${k.activities} atividades publicadas`)}${kpi('Materiais publicados', pad2(k.materials), `${k.ai_month} gerações de IA neste mês`, 'verde')}</div>
    <div class="grade grade-lateral">
      <div class="pilha">
        <section class="cartao"><h2 class="cartao__titulo">Média por turma (0–10)</h2>${bars(d.by_class.map((c) => ({ label: c.name, value: c.avg })))}</section>
        <section class="cartao"><h2 class="cartao__titulo">Usuários ativos por semana</h2>${bars(d.weekly.map((w) => ({ label: 'Sem ' + w.week.split('-')[1], value: w.users })), { max: 1, fmtV: (v) => v ?? '' })}</section>
      </div>
      <div class="pilha">
        <section class="cartao"><div class="cartao__topo"><h2 class="cartao__titulo">Plano ${p.plan}</h2><a href="#/g/planos">Detalhes</a></div>
          ${medidor('Alunos', p.usage.students, p.limits.students)}${medidor('Professores', p.usage.teachers, p.limits.teachers)}${medidor('Gerações de IA no mês', p.usage.ai_month, p.limits.ai_month)}</section>
        <section class="cartao"><div class="cartao__topo"><h2 class="cartao__titulo">Atividade recente</h2><a href="#/g/privacidade">Auditoria</a></div>
          <ul class="lista-simples">${d.recent.map((r) => html`<li><span><strong style="font-weight:600">${r.name || 'Sistema'}</strong> · ${r.action}<br><span class="texto-fraco">${r.detail}</span></span><span class="texto-fraco">${fmtDate(r.created_at)}</span></li>`)}</ul></section>
      </div>
    </div>`).querySelector('[data-convidar]').onclick = () => convidarModal();
}, R);

/* ================================================================ H02 instituição */
route('g/instituicao', async () => {
  page(loading());
  const i = await api('/gestor/institution');
  const el = page(html`${header('Instituição e unidades', `Código de acesso: ${i.slug} · cliente desde ${fmtDate(i.created_at)}`)}
    <div class="grade grade-2">
      <form class="cartao" id="f"><h2 class="cartao__titulo">Dados da instituição</h2>
        <label class="campo"><span>Nome</span><input class="entrada" name="name" value="${i.name}" required></label>
        <div class="campos-2"><label class="campo"><span>CNPJ</span><input class="entrada" name="cnpj" value="${i.cnpj || ''}"></label>
        <label class="campo"><span>Tipo</span><select class="entrada" name="type">${['Escola', 'Curso profissionalizante', 'Preparatório', 'Faculdade'].map((t) => html`<option ${t === i.type ? 'selected' : ''}>${t}</option>`)}</select></label></div>
        <button class="btn btn--escuro">Salvar</button></form>
      <div class="pilha">
        <section class="cartao"><div class="cartao__topo"><h2 class="cartao__titulo">Unidades</h2></div>
          <ul class="lista-simples">${i.units.map((u) => html`<li><span>${u.name}<span class="texto-fraco"> · ${u.city || '—'} · ${u.classes} turma(s)</span></span><button class="btn btn--link texto-vermelho" data-delu="${u.id}">Remover</button></li>`)}</ul>
          <form class="linha" data-add="units"><input class="entrada" name="name" placeholder="Nova unidade" required style="flex:1"><input class="entrada" name="extra" placeholder="Cidade" style="width:140px"><button class="btn btn--contorno">Adicionar</button></form></section>
        <section class="cartao"><div class="cartao__topo"><h2 class="cartao__titulo">Cursos e séries</h2></div>
          <ul class="lista-simples">${i.courses.map((c) => html`<li><span>${c.name}<span class="texto-fraco"> · ${c.level || '—'} · ${c.classes} turma(s)</span></span><button class="btn btn--link texto-vermelho" data-delc="${c.id}">Remover</button></li>`)}</ul>
          <form class="linha" data-add="courses"><input class="entrada" name="name" placeholder="Novo curso (ex.: Ensino Médio)" required style="flex:1"><input class="entrada" name="extra" placeholder="Nível" style="width:140px"><button class="btn btn--contorno">Adicionar</button></form></section>
      </div>
    </div>`);
  const f = el.querySelector('#f');
  f.addEventListener('submit', (e) => {
    e.preventDefault();
    busy(f.querySelector('button'), async () => {
      await api('/gestor/institution', { method: 'PUT', body: { ...formData(f), color: S.user.institution.color, logo: S.user.institution.logo } });
      S.user = await api('/me'); resetShell(); toast('Dados salvos'); go(location.hash);
    });
  });
  el.querySelectorAll('[data-add]').forEach((fm) => fm.addEventListener('submit', async (e) => {
    e.preventDefault();
    await api('/gestor/' + fm.dataset.add, { method: 'POST', body: formData(fm) }); go(location.hash);
  }));
  el.querySelectorAll('[data-delu]').forEach((b) => { b.onclick = async () => { await api('/gestor/units/' + b.dataset.delu, { method: 'DELETE' }); go(location.hash); }; });
  el.querySelectorAll('[data-delc]').forEach((b) => { b.onclick = async () => { await api('/gestor/courses/' + b.dataset.delc, { method: 'DELETE' }); go(location.hash); }; });
}, R);

/* ================================================================ H04–H05 usuários e convites */
route('g/usuarios', async (_, q) => {
  page(loading());
  const aba = q.aba || 'professor';
  const [users, invites] = await Promise.all([api('/gestor/users'), api('/gestor/invites')]);
  const cont = (r) => users.filter((u) => u.role === r).length;
  const el = page(html`${header('Usuários', 'Cadastro, convites, papéis e permissões.', html`<button class="btn btn--contorno" data-importar>Importar CSV</button><button class="btn btn--primario" data-convidar>+ Convidar</button>`)}
    ${tabs([['professor', `Professores (${cont('professor')})`], ['aluno', `Alunos (${cont('aluno')})`], ['secretaria', `Secretaria (${cont('secretaria')})`], ['gestor', `Gestores (${cont('gestor')})`], ['convites', `Convites pendentes (${invites.length})`], ['papeis', 'Papéis e permissões']], aba)}
    <div id="aba"></div>`);
  const box = el.querySelector('#aba');
  const show = (t) => {
    history.replaceState(null, '', '#/g/usuarios?aba=' + t);
    if (t === 'convites') {
      box.innerHTML = invites.length ? html`<div class="tabela-caixa"><table class="tabela"><thead><tr><th>E-mail</th><th>Papel</th><th>Turma</th><th>Enviado</th><th>Link de ativação</th><th></th></tr></thead><tbody>
        ${invites.map((i) => html`<tr><td>${i.email}</td><td>${PAPEL[i.role]}</td><td>${i.class_name || '—'}</td><td>${fmtDate(i.created_at)}</td>
          <td><button class="btn btn--contorno btn--p" data-copiar="${convidarLink(i.token)}">Copiar link</button></td><td><button class="btn btn--link texto-vermelho" data-cancelar="${i.id}">Cancelar</button></td></tr>`)}</tbody></table></div>`.s
        : empty('Nenhum convite pendente').s;
      box.querySelectorAll('[data-copiar]').forEach((b) => { b.onclick = () => copiar(b.dataset.copiar); });
      box.querySelectorAll('[data-cancelar]').forEach((b) => { b.onclick = async () => { await api('/gestor/invites/' + b.dataset.cancelar, { method: 'DELETE' }); go(location.hash); }; });
      return;
    }
    if (t === 'papeis') {
      const linhas = [['Gerenciar instituição, unidades e cursos', 'Total', '—', '—'], ['Convidar e importar usuários', 'Total', '—', '—'], ['Planos, licenças e consumo de IA', 'Total', '—', '—'],
        ['Auditoria e privacidade', 'Responsáveis', '—', '—'], ['Enviar conteúdos e gerar materiais com IA', '—', 'Suas turmas', '—'], ['Revisar e publicar materiais', '—', 'Suas turmas', '—'],
        ['Criar atividades e jogos ao vivo', '—', 'Suas turmas', '—'], ['Ver indicadores agregados da instituição', 'Total', '—', '—'], ['Ver desempenho das turmas', 'Leitura', 'Suas turmas', '—'],
        ['Estudar materiais publicados', '—', '—', 'Autorizados'], ['Resolver atividades e participar de jogos', '—', '—', 'Autorizados'], ['Ver o próprio desempenho', '—', '—', 'Próprio']];
      box.innerHTML = html`<div class="tabela-caixa"><table class="tabela"><thead><tr><th>Capacidade</th><th>Gestor</th><th>Professor</th><th>Aluno</th></tr></thead><tbody>
        ${linhas.map(([c, ...v]) => html`<tr><td>${c}</td>${v.map((x) => html`<td class="${x === '—' ? 'nao' : 'sim'}">${x}</td>`)}</tr>`)}</tbody></table></div>
        ${aviso('Para mudar o papel de alguém, edite o usuário. O acesso à auditoria e aos dados pessoais pode ser restrito a responsáveis específicos em Auditoria e privacidade.')}`.s;
      return;
    }
    const lista = users.filter((u) => u.role === t);
    box.innerHTML = html`<div class="filtros"><input class="entrada entrada--busca" id="q" placeholder="Buscar por nome ou e-mail…"></div>
      ${lista.length ? html`<div class="tabela-caixa"><table class="tabela"><thead><tr><th>Nome</th><th>E-mail</th><th>${t === 'professor' ? 'Disciplinas' : t === 'aluno' ? 'Turmas' : 'Papel'}</th><th>Status</th><th>Último acesso</th><th></th></tr></thead><tbody id="lista">
      ${lista.map((u) => html`<tr data-busca="${(u.name + ' ' + u.email).toLowerCase()}"><td><strong style="font-weight:600">${u.name}</strong></td><td>${u.email}</td>
        <td class="texto-fraco">${t === 'professor' ? u.subjects || '—' : t === 'aluno' ? u.classes || '—' : PAPEL[t]}</td><td>${tag(u.status)}</td><td>${fmtDate(u.last_login)}</td>
        <td><div class="acoes-icone"><button class="btn btn--contorno btn--p" data-editar="${u.id}">Editar</button><button class="btn btn--link" data-senha="${u.id}">Redefinir senha</button></div></td></tr>`)}</tbody></table></div>` : empty('Ninguém aqui ainda', 'Convide por e-mail ou importe uma planilha.')}`.s;
    box.querySelector('#q')?.addEventListener('input', (e) => box.querySelectorAll('#lista tr').forEach((tr) => { tr.hidden = !tr.dataset.busca.includes(e.target.value.toLowerCase()); }));
    box.querySelectorAll('[data-editar]').forEach((b) => { b.onclick = () => editarUsuario(users.find((u) => String(u.id) === b.dataset.editar)); });
    box.querySelectorAll('[data-senha]').forEach((b) => {
      b.onclick = async () => {
        if (!(await confirmar('Gerar uma senha temporária para este usuário?'))) return;
        const r = await api(`/gestor/users/${b.dataset.senha}/reset-password`, { method: 'POST' });
        modal('Senha temporária', html`<p>Envie esta senha ao usuário. Ele pode trocá-la em Perfil.</p><p class="codigo" style="font-size:28px;text-align:center">${r.password}</p>`);
      };
    });
  };
  bindTabs(el, show);
  show(aba);
  el.querySelector('[data-convidar]').onclick = () => convidarModal(PAPEL[aba] ? aba : 'professor');
  el.querySelector('[data-importar]').onclick = () => importarModal();
}, R);

function copiar(txt) {
  navigator.clipboard?.writeText(txt).then(() => toast('Link copiado'), () => modal('Link de convite', html`<input class="entrada" value="${txt}" readonly onclick="this.select()">`));
}

async function convidarModal(role = 'professor') {
  const classes = await api('/gestor/classes');
  modal('Convidar usuários', html`<form id="f">
    <label class="campo"><span>E-mails (um por linha ou separados por vírgula)</span><textarea class="entrada" name="emails" required rows="4" placeholder="ana@escola.edu.br"></textarea></label>
    <div class="campos-2"><label class="campo"><span>Papel</span><select class="entrada" name="role">${Object.entries(PAPEL).map(([k, v]) => html`<option value="${k}" ${k === role ? 'selected' : ''}>${v}</option>`)}</select></label>
    <label class="campo"><span>Turma (alunos)</span><select class="entrada" name="class_id"><option value="">—</option>${classes.map((c) => html`<option value="${c.id}">${c.name}</option>`)}</select></label></div>
    ${aviso('Cada pessoa recebe um link de ativação para criar a senha. Copie os links gerados e envie por e-mail ou pelo canal da escola.')}
    <div class="linha linha--fim"><button type="button" class="btn btn--contorno" data-fechar>Cancelar</button><button class="btn btn--primario">Gerar convites</button></div></form>`, {
    onMount: (el, close) => el.querySelector('#f').addEventListener('submit', (e) => {
      e.preventDefault();
      const d = formData(e.target);
      busy(el.querySelector('.btn--primario'), async () => {
        const r = await api('/gestor/invites', { method: 'POST', body: { emails: d.emails.split(/[\n,;]+/).map((s) => s.trim()).filter(Boolean), role: d.role, class_id: d.class_id ? Number(d.class_id) : null } });
        close(); resultadoConvites(r);
      });
    }),
  });
}

function resultadoConvites(r) {
  modal('Convites gerados', html`<div class="tabela-caixa"><table class="tabela"><thead><tr><th>E-mail</th><th>Situação</th><th></th></tr></thead><tbody>
    ${r.map((x) => html`<tr><td>${x.email}</td><td>${x.status}</td><td>${x.token ? html`<button class="btn btn--contorno btn--p" data-copiar="${convidarLink(x.token)}">Copiar link</button>` : ''}</td></tr>`)}</tbody></table></div>
    <div class="linha linha--fim"><button class="btn btn--escuro" data-fechar>Concluir</button></div>`, {
    largo: true,
    onMount: (el) => el.querySelectorAll('[data-copiar]').forEach((b) => { b.onclick = () => copiar(b.dataset.copiar); }),
    onClose: () => go('#/g/usuarios?aba=convites'),
  });
}

function importarModal() {
  modal('Importar usuários (CSV)', html`<form id="f">
    <p class="texto-suave">Colunas: <code>nome;email;papel;turma</code>. Papel: professor, aluno, secretaria ou gestor. Turma (opcional) pelo nome exato, ex.: 9º B.</p>
    <label class="upload" style="padding:18px"><input type="file" accept=".csv,.txt" data-arq><strong>Escolher arquivo CSV</strong><span class="texto-fraco">ou cole o conteúdo abaixo</span></label>
    <textarea class="entrada" name="csv" rows="8" placeholder="nome;email;papel;turma&#10;Maria Lima;maria@escola.edu.br;aluno;9º B"></textarea>
    <div class="linha linha--fim"><button type="button" class="btn btn--contorno" data-fechar>Cancelar</button><button class="btn btn--primario">Importar</button></div></form>`, {
    largo: true,
    onMount: (el, close) => {
      const f = el.querySelector('#f');
      el.querySelector('[data-arq]').onchange = async (e) => { f.csv.value = await e.target.files[0].text(); };
      f.addEventListener('submit', (e) => {
        e.preventDefault();
        busy(f.querySelector('.btn--primario'), async () => { const r = await api('/gestor/import', { method: 'POST', body: { csv: f.csv.value } }); close(); resultadoConvites(r); });
      });
    },
  });
}

function editarUsuario(u) {
  modal('Editar usuário', html`<form id="f">
    <label class="campo"><span>Nome</span><input class="entrada" name="name" value="${u.name}" required></label>
    <p class="texto-fraco">${u.email}</p>
    <div class="campos-2"><label class="campo"><span>Papel</span><select class="entrada" name="role">${Object.entries(PAPEL).map(([k, v]) => html`<option value="${k}" ${k === u.role ? 'selected' : ''}>${v}</option>`)}</select></label>
    <label class="campo"><span>Status</span><select class="entrada" name="status"><option value="ativo">Ativo</option><option value="inativo" ${u.status === 'inativo' ? 'selected' : ''}>Desativado</option></select></label></div>
    <label class="campo"><span>Série / ano (alunos)</span><input class="entrada" name="grade" value="${u.grade || ''}"></label>
    ${aviso('Desativar impede o login, mas mantém o histórico. Mudanças de papel ficam registradas na auditoria.', 'amarelo')}
    <div class="linha linha--fim"><button type="button" class="btn btn--contorno" data-fechar>Cancelar</button><button class="btn btn--primario">Salvar</button></div></form>`, {
    onMount: (el, close) => el.querySelector('#f').addEventListener('submit', (e) => {
      e.preventDefault();
      busy(el.querySelector('.btn--primario'), async () => { await api('/gestor/users/' + u.id, { method: 'PUT', body: formData(e.target) }); close(); toast('Usuário atualizado'); go(location.hash); });
    }),
  });
}

/* ================================================================ H03 cursos e turmas */
route('g/turmas', async () => {
  page(loading());
  const [cs, inst, profs] = await Promise.all([api('/gestor/classes'), api('/gestor/institution'), api('/gestor/users?role=professor')]);
  const el = page(html`${header('Cursos e turmas', 'Crie turmas, matricule alunos e vincule professores às disciplinas.', html`<button class="btn btn--primario" data-nova>+ Nova turma</button>`)}
    ${cs.length ? html`<div class="tabela-caixa"><table class="tabela"><thead><tr><th>Turma</th><th>Curso / unidade</th><th>Alunos</th><th>Disciplinas e professores</th><th>Código</th><th></th></tr></thead><tbody>
    ${cs.map((c) => html`<tr><td><strong>${c.name}</strong><div class="texto-fraco">${c.grade || ''} · ${c.year}</div></td><td>${c.course_name || '—'}<div class="texto-fraco">${c.unit_name || ''}</div></td><td>${c.students}</td>
      <td>${c.subjects.length ? c.subjects.map((s) => html`<div>${s.name} <span class="texto-fraco">· ${s.teacher}</span></div>`) : html`<span class="texto-fraco">Nenhuma</span>`}</td><td><code>${c.code}</code></td>
      <td><div class="acoes-icone"><button class="btn btn--contorno btn--p" data-gerir="${c.id}">Gerenciar</button><button class="btn btn--link" data-editar="${c.id}">Editar</button></div></td></tr>`)}</tbody></table></div>`
    : empty('Nenhuma turma', 'Crie a primeira turma.')}`);
  const turmaModal = (c) => modal(c ? 'Editar turma' : 'Nova turma', html`<form id="f">
    <div class="campos-2"><label class="campo"><span>Nome</span><input class="entrada" name="name" value="${c?.name || ''}" required placeholder="Ex.: 9º B"></label>
    <label class="campo"><span>Série / ano</span><input class="entrada" name="grade" value="${c?.grade || ''}" placeholder="Ex.: 9º ano"></label></div>
    <div class="campos-2"><label class="campo"><span>Curso</span><select class="entrada" name="course_id"><option value="">—</option>${inst.courses.map((x) => html`<option value="${x.id}" ${x.id === c?.course_id ? 'selected' : ''}>${x.name}</option>`)}</select></label>
    <label class="campo"><span>Unidade</span><select class="entrada" name="unit_id"><option value="">—</option>${inst.units.map((x) => html`<option value="${x.id}" ${x.id === c?.unit_id ? 'selected' : ''}>${x.name}</option>`)}</select></label></div>
    <label class="campo"><span>Ano letivo</span><input class="entrada" type="number" name="year" value="${c?.year || new Date().getFullYear()}"></label>
    <div class="linha linha--entre">${c ? html`<button type="button" class="btn btn--perigo" data-excluir>Excluir turma</button>` : html`<span></span>`}<button class="btn btn--primario">Salvar</button></div></form>`, {
    onMount: (m, close) => {
      m.querySelector('#f').addEventListener('submit', (e) => {
        e.preventDefault();
        const d = formData(e.target);
        const body = { ...d, course_id: d.course_id ? Number(d.course_id) : null, unit_id: d.unit_id ? Number(d.unit_id) : null };
        busy(m.querySelector('.btn--primario'), async () => { await api('/gestor/classes' + (c ? '/' + c.id : ''), { method: c ? 'PUT' : 'POST', body }); close(); go(location.hash); });
      });
      m.querySelector('[data-excluir]')?.addEventListener('click', async () => {
        try { await api('/gestor/classes/' + c.id, { method: 'DELETE' }); close(); go(location.hash); } catch (e) { toast(e.message, 'erro'); }
      });
    },
  });
  el.querySelector('[data-nova]').onclick = () => turmaModal();
  el.querySelectorAll('[data-editar]').forEach((b) => { b.onclick = () => turmaModal(cs.find((c) => String(c.id) === b.dataset.editar)); });
  el.querySelectorAll('[data-gerir]').forEach((b) => { b.onclick = () => gerirTurma(Number(b.dataset.gerir), profs); });
}, R);

async function gerirTurma(cid, profs) {
  const [c, alunos] = await Promise.all([api('/gestor/classes/' + cid), api('/gestor/users?role=aluno')]);
  const dentro = new Set(c.students.map((s) => s.id));
  modal(`Turma ${c.name}`, html`<div class="grade grade-2" style="align-items:start">
    <section><h3 class="cartao__titulo">Alunos matriculados (${c.students.length})</h3>
      <ul class="lista-simples" style="max-height:260px;overflow-y:auto">${c.students.map((s) => html`<li><span>${s.name}</span><button class="btn btn--link texto-vermelho" data-sair="${s.id}">Remover</button></li>`)}</ul>
      <h3 class="cartao__titulo" style="margin-top:14px">Matricular alunos</h3>
      <div class="lista-checagem" style="max-height:200px">${alunos.filter((a) => !dentro.has(a.id) && a.status === 'ativo').map((a) => html`<label class="check"><input type="checkbox" value="${a.id}">${a.name} <span class="texto-fraco">${a.classes || ''}</span></label>`)}</div>
      <button class="btn btn--contorno" data-matricular style="margin-top:8px">Matricular selecionados</button></section>
    <section><div class="cartao__topo"><h3 class="cartao__titulo">Disciplinas e professores</h3><a href="#/g/disciplinas?turma=${cid}">Editar / trocar professor</a></div>
      <ul class="lista-simples">${c.subjects.map((s) => html`<li><span>${s.name}${s.active ? '' : html` <span class="tag tag--cinza">desativada</span>`}</span><span class="texto-fraco">${s.teacher}</span></li>`)}</ul>
      <form id="vinc" class="pilha" style="margin-top:12px"><input class="entrada" name="name" placeholder="Disciplina (ex.: Física)" required>
        <select class="entrada" name="teacher_id">${profs.filter((p) => p.status === 'ativo').map((p) => html`<option value="${p.id}">${p.name}</option>`)}</select>
        <button class="btn btn--escuro">Vincular professor</button></form></section></div>`, {
    largo: true,
    onMount: (el, close) => {
      const reabrir = () => { close(); gerirTurma(cid, profs); };
      el.querySelectorAll('[data-sair]').forEach((b) => { b.onclick = async () => { await api(`/gestor/classes/${cid}/students/${b.dataset.sair}`, { method: 'DELETE' }); reabrir(); }; });
      el.querySelector('[data-matricular]').onclick = async () => {
        const ids = [...el.querySelectorAll('.lista-checagem input:checked')].map((i) => Number(i.value));
        if (!ids.length) return;
        const r = await api(`/gestor/classes/${cid}/students`, { method: 'POST', body: { user_ids: ids } });
        toast(`${r.added} aluno(s) matriculado(s)`); reabrir();
      };
      el.querySelector('#vinc').addEventListener('submit', async (e) => {
        e.preventDefault();
        if (!profs.length) return toast('Convide professores primeiro', 'erro');
        await api('/gestor/subjects', { method: 'POST', body: { class_id: cid, teacher_id: Number(e.target.teacher_id.value), name: e.target.name.value } });
        toast('Professor vinculado'); reabrir();
      });
    },
    onClose: () => go(location.hash),
  });
}

/* ================================================================ conteúdos e políticas */
route('g/conteudos', async () => {
  page(loading());
  const d = await api('/gestor/contents');
  const s = d.settings;
  const el = page(html`${header('Conteúdos', 'Materiais da instituição e políticas de publicação.')}
    <div class="grade grade-4">${d.by_type.map((t) => kpi(TYPE_LABEL[t.type] || t.type, pad2(t.n), `${t.published} publicados`))}${kpi('Documentos enviados', pad2(d.documents.n), `${(d.documents.bytes / 1048576).toFixed(1)} MB`)}</div>
    <section class="cartao"><h2 class="cartao__titulo">Políticas de publicação</h2>
      <div class="switch-linha"><div>Exigir revisão antes de publicar<small>O professor precisa marcar o material como revisado antes de liberar aos alunos.</small></div><button class="switch" role="switch" aria-checked="${!!s.publish_requires_review}" data-set="publish_requires_review"></button></div>
      <div class="switch-linha"><div>Geração com IA habilitada<small>Desative para bloquear novas gerações em toda a instituição.</small></div><button class="switch" role="switch" aria-checked="${s.ai_enabled !== false}" data-set="ai_enabled"></button></div></section>
    <section><div class="secao__topo"><h2>Materiais</h2></div><div class="filtros"><input class="entrada entrada--busca" id="q" placeholder="Buscar…"></div>
      ${d.materials.length ? html`<div class="tabela-caixa"><table class="tabela"><thead><tr><th>Material</th><th>Professor</th><th>Disciplina</th><th>Status</th><th>Turmas</th><th>Atualizado</th><th></th></tr></thead><tbody id="lista">
      ${d.materials.map((m) => html`<tr data-b="${(m.title + m.teacher + m.subject_name).toLowerCase()}"><td>${m.title}<div class="texto-fraco">${TYPE_LABEL[m.type]}</div></td><td>${m.teacher}</td><td>${m.subject_name}</td><td>${tag(m.status)}</td><td>${m.classes || '—'}</td><td>${fmtDate(m.updated_at)}</td>
        <td><div class="acoes-icone"><button class="btn btn--link" data-arq="${m.id}">Arquivar</button><button class="btn btn--link texto-vermelho" data-excluir="${m.id}" data-titulo="${m.title}">Excluir</button></div></td></tr>`)}</tbody></table></div>` : empty('Nenhum material ainda')}</section>`);
  el.querySelectorAll('[data-set]').forEach((b) => {
    b.onclick = async () => {
      const v = b.getAttribute('aria-checked') !== 'true';
      await api('/gestor/settings', { method: 'PUT', body: { [b.dataset.set]: v } });
      b.setAttribute('aria-checked', String(v)); toast('Política atualizada');
    };
  });
  el.querySelector('#q').oninput = (e) => el.querySelectorAll('#lista tr').forEach((tr) => { tr.hidden = !tr.dataset.b.includes(e.target.value.toLowerCase()); });
  el.querySelectorAll('[data-excluir]').forEach((b) => {
    b.onclick = async () => {
      if (!(await confirmar(`Excluir “${b.dataset.titulo}” definitivamente? Some para os alunos e para o professor, que será notificado.`, { ok: 'Excluir', perigo: true }))) return;
      await api('/gestor/materials/' + b.dataset.excluir, { method: 'DELETE' }); toast('Material excluído'); go(location.hash);
    };
  });
  el.querySelectorAll('[data-arq]').forEach((b) => {
    b.onclick = async () => {
      if (!(await confirmar('Arquivar este material? Ele deixa de aparecer para os alunos e o professor é notificado.', { ok: 'Arquivar', perigo: true }))) return;
      await api(`/gestor/materials/${b.dataset.arq}/archive`, { method: 'POST' }); go(location.hash);
    };
  });
}, R);

/* ================================================================ H06 relatórios */
route('g/relatorios', async () => {
  page(loading());
  const r = await api('/gestor/reports');
  const el = page(html`${header('Relatórios e indicadores', 'Indicadores agregados de participação e desempenho (sem dados individuais de alunos).', html`<button class="btn btn--contorno" data-csv>Exportar CSV</button>`)}
    <div class="grade grade-2">
      <section class="cartao"><h2 class="cartao__titulo">Média por turma (0–10)</h2>${bars(r.by_class.map((c) => ({ label: c.name, value: c.avg })))}</section>
      <section class="cartao"><h2 class="cartao__titulo">Taxa de conclusão por turma</h2>${hbars(r.by_class.map((c) => ({ label: c.name, value: c.completion })))}</section>
      <section class="cartao"><h2 class="cartao__titulo">Média por disciplina</h2>${hbars(r.by_subject.map((s) => ({ label: s.name, value: s.avg })), { max: 10, suffix: '', cor: (v) => (v < 5 ? 'vermelho' : v < 7 ? 'amarelo' : 'verde') })}</section>
      <section class="cartao"><h2 class="cartao__titulo">Entregas por semana</h2>${bars(r.weekly.map((w) => ({ label: 'S' + w.week.split('-')[1], value: w.submissions })), { max: 1, fmtV: (v) => v ?? '' })}</section>
      <section class="cartao"><h2 class="cartao__titulo">Assuntos com menor acerto</h2>${hbars(r.topics.map((t) => ({ label: `${t.topic} · ${t.subject}`, value: t.pct })))}</section>
      <section class="cartao"><h2 class="cartao__titulo">Uso pelos professores</h2><div class="tabela-caixa"><table class="tabela"><thead><tr><th>Professor</th><th>Materiais</th><th>Publicados</th><th>Atividades</th><th>Jogos</th></tr></thead><tbody>
        ${r.teachers.map((t) => html`<tr><td>${t.name}</td><td>${t.materials}</td><td>${t.published}</td><td>${t.activities}</td><td>${t.games}</td></tr>`)}</tbody></table></div></section>
    </div>`);
  el.querySelector('[data-csv]').onclick = (e) => busy(e.currentTarget, () => download('/gestor/reports/export.csv', 'relatorio-institucional.csv'));
}, R);

/* ================================================================ H07 planos e uso */
route('g/planos', async () => {
  page(loading());
  const [p, fats] = await Promise.all([api('/gestor/plan'), api('/gestor/faturas')]);
  const vencidas = fats.filter((f) => f.situacao === 'vencida');
  const el = page(html`${header('Planos, uso e faturas', 'Assinatura, limites, consumo de IA e mensalidades da plataforma.',
    html`<a class="btn btn--contorno" href="#/atendimento/novo?destino=plataforma&categoria=financeiro">Dúvida sobre fatura</a>`)}
    ${vencidas.length ? aviso(`Há ${vencidas.length} fatura(s) vencida(s). Em caso de dúvida, abra um chamado para o suporte da plataforma.`, 'vermelho') : ''}
    <section class="cartao" id="faturas"><h2 class="cartao__titulo">Faturas da plataforma</h2>
      ${fats.length ? html`<div class="tabela-caixa"><table class="tabela"><thead><tr><th>Referência</th><th>Descrição</th><th>Valor</th><th>Vencimento</th><th>Situação</th><th>Pagamento</th></tr></thead><tbody>
        ${fats.map((f) => html`<tr><td>${f.reference}</td><td class="texto-fraco">${f.description || '—'}</td><td><strong>${BRL(f.amount)}</strong></td><td>${fmtDate(f.due_date)}</td>
          <td><span class="tag tag--${SIT_FAT[f.situacao][0]}">${SIT_FAT[f.situacao][1]}</span></td><td>${f.paid_at ? html`${fmtDate(f.paid_at)} <span class="texto-fraco">${f.payment_method || ''}</span>` : '—'}</td></tr>`)}</tbody></table></div>`
    : html`<p class="texto-suave">Nenhuma fatura emitida ainda.</p>`}</section>
    <div class="grade grade-lateral">
      <div class="pilha">
        <section class="cartao"><h2 class="cartao__titulo">Consumo no plano ${p.plan}</h2>
          ${medidor('Alunos ativos', p.usage.students, p.limits.students)}${medidor('Professores ativos', p.usage.teachers, p.limits.teachers)}
          ${medidor('Armazenamento', p.usage.storage_mb, p.limits.storage_mb, ' MB')}${medidor('Gerações de IA neste mês', p.usage.ai_month, p.limits.ai_month)}</section>
        <section class="cartao"><h2 class="cartao__titulo">Gerações de IA por dia (30 dias)</h2>${bars(p.daily.map((d) => ({ label: d.day.slice(8), value: d.n })), { max: 1, height: 150, fmtV: (v) => v ?? '' })}</section>
        <section class="cartao"><h2 class="cartao__titulo">Histórico mensal</h2><ul class="lista-simples">${p.history.map((h) => html`<li><span>${h.month}</span><strong>${h.n} gerações</strong></li>`)}</ul></section>
      </div>
      <div class="pilha">
        <section class="cartao"><h2 class="cartao__titulo">Uso por recurso (mês)</h2><ul class="lista-simples">${p.by_kind.map((k) => html`<li><span>${TYPE_LABEL[k.kind] || k.kind}</span><strong>${k.n}</strong></li>`)}</ul></section>
        <section class="cartao"><h2 class="cartao__titulo">Modelos utilizados</h2><ul class="lista-simples">${p.by_provider.map((k) => html`<li><span>${k.provider} · ${k.model}<br><span class="texto-fraco">${nota(k.avg_s)} s em média</span></span><strong>${k.n}</strong></li>`)}</ul></section>
      </div>
    </div>
    <section><div class="secao__topo"><h2>Trocar de plano</h2></div>
      ${p.request ? aviso(html`Pedido de mudança para o plano <strong>${p.request.plan}</strong> enviado em ${fmtDate(p.request.created_at)}. A equipe da plataforma confirma a contratação e libera o novo plano.`, 'amarelo')
    : aviso('A troca de plano é confirmada pela equipe da plataforma (contrato e cobrança). Ao pedir, você é avisado quando for aprovada.')}
      <div class="grade grade-3">${Object.entries(p.plans).map(([n, l]) => html`<div class="cartao ${n === p.plan ? 'cartao--destaque' : ''}">
      <h3>${n}</h3><p style="font-size:24px;font-weight:800">${BRL(l.price)}<span class="texto-fraco">/mês</span></p>
      <ul class="lista-marcadores texto-suave"><li>${nota(l.students)} alunos</li><li>${l.teachers} professores</li><li>${nota(l.ai_month)} gerações de IA/mês</li><li>${nota(l.storage_mb / 1024)} GB</li></ul>
      ${n === p.plan ? tag('publicado', 'Plano atual') : p.request?.plan === n ? tag('pendente', 'Pedido enviado') : html`<button class="btn btn--escuro btn--bloco" data-plano="${n}">Pedir o plano ${n}</button>`}</div>`)}</div></section>`);
  el.querySelectorAll('[data-plano]').forEach((b) => {
    b.onclick = async () => {
      if (!(await confirmar(`Pedir a mudança para o plano ${b.dataset.plano}? A equipe da plataforma vai confirmar a contratação.`, { ok: 'Enviar pedido' }))) return;
      await api('/gestor/plan', { method: 'PUT', body: { plan: b.dataset.plano } }); toast('Pedido enviado'); go(location.hash);
    };
  });
}, R);

/* ================================================================ H09 configurações */
route('g/configuracoes', async (_, q) => {
  page(loading());
  const [cfg, inst] = await Promise.all([api('/gestor/settings'), api('/gestor/institution')]);
  const s = cfg.settings, ia = cfg.ia;
  const aba = q.aba || 'identidade';
  const sw = (key, label, desc) => html`<div class="switch-linha"><div>${label}<small>${desc}</small></div><button class="switch" role="switch" aria-checked="${!!s[key]}" data-set="${key}"></button></div>`;
  const el = page(html`${header('Configurações', 'Identidade visual, IA, acesso e notificações.')}
    ${tabs([['identidade', 'Identidade visual'], ['ia', 'IA local e padrão'], ['ia-link', 'Link da API (IA)'], ['ia-chave', 'Chave da API (IA)'], ['acesso', 'Domínio e acesso'], ['notificacoes', 'Notificações'], ['integracoes', 'Integrações']], aba)}<div id="aba"></div>`);
  let nuvem = await api('/gestor/ia-nuvem');
  const box = el.querySelector('#aba');
  const ligarSwitches = () => box.querySelectorAll('[data-set]').forEach((b) => {
    b.onclick = async () => {
      const v = b.getAttribute('aria-checked') !== 'true';
      await api('/gestor/settings', { method: 'PUT', body: { [b.dataset.set]: v } });
      s[b.dataset.set] = v; b.setAttribute('aria-checked', String(v)); toast('Configuração salva');
    };
  });
  const show = (t) => {
    history.replaceState(null, '', '#/g/configuracoes?aba=' + t);
    if (t === 'identidade') {
      box.innerHTML = html`<form class="cartao" id="f" style="max-width:640px"><h2 class="cartao__titulo">Identidade visual</h2>
        <p class="texto-suave">O logotipo, a cor e a cor do texto aparecem no menu lateral de todos da instituição (professores, alunos, secretaria e gestores).</p>
        <div class="linha"><div id="prev" style="width:64px;height:64px;border-radius:14px;display:grid;place-items:center;background:${inst.color}">${inst.logo ? html`<img src="${inst.logo}" alt="" style="width:64px;height:64px;border-radius:14px;object-fit:cover">` : html`<span style="color:#fff;font-weight:800">${inst.name[0]}</span>`}</div>
          <label class="btn btn--contorno" style="cursor:pointer">Enviar logotipo<input type="file" accept="image/*" hidden data-logo></label>${inst.logo ? html`<button type="button" class="btn btn--link" data-semlogo>Remover</button>` : ''}</div>
        <div class="identidade-cores">
          <div class="pilha">
            <label class="campo"><span>Cor principal do menu</span><input class="entrada" type="color" name="color" value="${inst.color}" style="height:44px;padding:4px;max-width:160px"></label>
            <div class="campo"><span>Cor do texto do menu</span>${segmented('texto', [['auto', 'Automático'], ['branco', 'Branco'], ['preto', 'Preto']], s.menu_text || 'auto')}
              <small class="texto-fraco" data-sugestao></small></div>
          </div>
          <div class="campo"><span>Pré-visualização</span>
            <div class="previa-menu" data-previa><span class="previa-menu__titulo">${inst.name}</span><span class="previa-menu__item previa-menu__item--ativo">${icon('casa', 14)} Início</span>
              <span class="previa-menu__item">${icon('livro', 14)} Minhas matérias</span><span class="previa-menu__item">${icon('chat', 14)} Atendimento</span></div></div>
        </div>
        <label class="campo"><span>Mensagem de boas-vindas (opcional)</span><input class="entrada" data-welcome value="${s.welcome || ''}"></label>
        <button class="btn btn--escuro">Salvar identidade</button></form>`.s;
      const corInput = box.querySelector('[name=color]');
      const getTexto = bindSeg(box, 'texto', () => atualizarPrevia());
      const atualizarPrevia = () => {
        const escolha = getTexto() || 'auto';
        const final = corTextoMenu(corInput.value, escolha);
        const p = box.querySelector('[data-previa]');
        p.style.background = corInput.value;
        p.className = 'previa-menu previa-menu--' + final;
        const marca = box.querySelector('#prev');
        if (!marca.querySelector('img')) {
          marca.style.background = corInput.value;
          const letra = marca.querySelector('span');
          if (letra) letra.style.color = final === 'preto' ? '#0F172A' : '#fff';
        }
        const sugerido = corTextoMenu(corInput.value, 'auto');
        box.querySelector('[data-sugestao]').textContent = escolha === 'auto'
          ? `Usando ${final} (o que tem mais contraste com esta cor).`
          : escolha === sugerido ? 'Boa escolha: é a cor com mais contraste.' : `Dica: com esta cor, o texto ${sugerido} fica mais legível.`;
      };
      corInput.addEventListener('input', atualizarPrevia);
      atualizarPrevia();
      let logo = inst.logo;
      box.querySelector('[data-logo]').onchange = (e) => {
        const file = e.target.files[0];
        if (!file) return;
        if (file.size > 300 * 1024) return toast('Imagem maior que 300 KB', 'erro');
        const rd = new FileReader();
        rd.onload = () => { logo = rd.result; box.querySelector('#prev').innerHTML = html`<img src="${logo}" alt="" style="width:64px;height:64px;border-radius:14px;object-fit:cover">`.s; };
        rd.readAsDataURL(file);
      };
      box.querySelector('[data-semlogo]')?.addEventListener('click', () => { logo = null; box.querySelector('#prev').innerHTML = ''; });
      box.querySelector('#f').addEventListener('submit', (e) => {
        e.preventDefault();
        busy(e.target.querySelector('.btn--escuro'), async () => {
          await api('/gestor/institution', { method: 'PUT', body: { name: inst.name, cnpj: inst.cnpj || '', type: inst.type, color: e.target.color.value, logo } });
          await api('/gestor/settings', { method: 'PUT', body: { welcome: box.querySelector('[data-welcome]').value, menu_text: getTexto() || 'auto' } });
          S.user = await api('/me'); resetShell(); toast('Identidade atualizada'); go(location.hash);
        });
      });
    }
    if (t === 'ia-link' || t === 'ia-chave') {
      const link = t === 'ia-link';
      box.innerHTML = html`<div class="grade grade-lateral"><form class="cartao" id="fn">
        <div class="cartao__topo"><h2 class="cartao__titulo">${link ? html`${icon('link', 16)} Link da API da IA em nuvem` : html`${icon('chave', 16)} Chave da API da IA em nuvem`}</h2>${nuvem.ready ? tag('publicado', 'Configurada') : tag('pendente', 'Incompleta')}</div>
        <p class="texto-suave">A IA contratada pela instituição vale para <strong>todos</strong>: professores, alunos, secretaria e gestores. Cada pessoa pode alternar entre esta IA em nuvem e a IA local (Ollama) no Chat com IA ou no próprio perfil.</p>
        ${link ? html`<label class="campo"><span>Link da API (formato “chat completions”)</span><input class="entrada" name="url" value="${nuvem.url}" placeholder="https://api.openai.com/v1" required></label>
          <label class="campo"><span>Modelo</span><input class="entrada" name="model" value="${nuvem.model}" placeholder="Ex.: gpt-4o-mini, llama-3.1-70b-versatile, deepseek-chat"></label>
          <p class="texto-fraco">Pode ser a base da API (…/v1) ou o endereço completo (…/v1/chat/completions). Funciona com OpenAI, OpenRouter, Groq, DeepSeek, Mistral, Together, Gemini (endpoint compatível) e outras.</p>`
    : html`<p>Chave atual: ${nuvem.has_key ? html`<code>${nuvem.key_masked}</code>` : html`<span class="texto-fraco">nenhuma</span>`}</p>
          <label class="campo"><span>${nuvem.has_key ? 'Nova chave da API (substitui a atual)' : 'Chave da API'}</span><input class="entrada" name="key" type="password" autocomplete="off" required placeholder="Cole aqui a chave fornecida pelo provedor"></label>
          ${aviso('Por segurança, a chave não é mostrada de novo depois de salva (só os 4 últimos caracteres) e não aparece na auditoria.', 'amarelo')}`}
        <div class="linha linha--entre">${!link && nuvem.has_key ? html`<button type="button" class="btn btn--link texto-vermelho" data-apagar>Remover chave</button>` : html`<span></span>`}<button class="btn btn--escuro" type="submit">Salvar ${link ? 'link' : 'chave'}</button></div></form>
        <aside class="pilha"><section class="cartao"><h2 class="cartao__titulo">Situação</h2><ul class="lista-simples">
          <li><span>Link</span>${nuvem.url ? tag('publicado', 'Cadastrado') : tag('pendente', 'Falta')}</li><li><span>Chave</span>${nuvem.has_key ? tag('publicado', 'Cadastrada') : tag('pendente', 'Falta')}</li>
          <li><span>Último teste</span>${nuvem.tested_at ? (nuvem.test_ok ? tag('publicado', 'OK') : tag('erro', 'Falhou')) : html`<span class="texto-fraco">—</span>`}</li></ul>
          <button class="btn btn--contorno btn--bloco" data-testar ${nuvem.ready ? '' : 'disabled'}>Testar conexão</button><p class="texto-fraco" data-res></p></section>
          ${aviso('Com IA externa, os textos dos documentos e as dúvidas dos alunos são enviados ao provedor. Confirme o contrato de tratamento de dados (LGPD) e que o provedor não usa os dados para treinar modelos.', 'amarelo')}</aside></div>`.s;
      box.querySelector('#fn').addEventListener('submit', (e) => {
        e.preventDefault();
        busy(e.target.querySelector('[type=submit]'), async () => {
          nuvem = await api('/gestor/ia-nuvem', { method: 'PUT', body: formData(e.target) });
          toast(link ? 'Link da API salvo' : 'Chave da API salva'); refreshIaStatus();
          show(link && !nuvem.has_key ? 'ia-chave' : !link && !nuvem.url ? 'ia-link' : t);
        });
      });
      box.querySelector('[data-apagar]')?.addEventListener('click', async () => {
        if (!(await confirmar('Remover a chave da API? Todos passam a usar a IA local até uma nova chave ser cadastrada.', { ok: 'Remover', perigo: true }))) return;
        nuvem = await api('/gestor/ia-nuvem', { method: 'PUT', body: { key: '-' } }); refreshIaStatus(); show(t);
      });
      box.querySelector('[data-testar]').addEventListener('click', (e) => busy(e.currentTarget, async () => {
        const r = await api('/gestor/ia-nuvem/testar', { method: 'POST' });
        box.querySelector('[data-res]').textContent = r.ok ? `Conectado! Resposta: “${r.message}”` : `Falhou: ${r.message}`;
        nuvem = await api('/gestor/ia-nuvem');
        toast(r.ok ? 'IA em nuvem respondeu' : 'A IA em nuvem não respondeu', r.ok ? 'ok' : 'erro');
      }));
    }
    if (t === 'ia') {
      const ollama = ia.provider_name === 'ollama';
      box.innerHTML = html`<section class="cartao" style="max-width:720px"><div class="cartao__topo"><h2 class="cartao__titulo">IA da instituição</h2>${nuvem.ready ? tag('publicado', 'Nuvem configurada') : tag('pendente', 'Só IA local')}</div>
        <p class="texto-suave">Duas opções para todos da instituição: a <strong>IA em nuvem</strong> contratada pela escola (cadastre o link e a chave da API nas abas ao lado) e a <strong>IA local</strong> (Ollama, no próprio servidor). Cada pessoa pode alternar no chat ou no perfil; aqui você define o padrão.</p>
        <div class="campo"><span>IA padrão para quem não escolheu</span>${segmented('modo-padrao', [['nuvem', 'IA em nuvem (API)'], ['local', 'IA local (Ollama)']], nuvem.default_mode)}</div>
        ${!nuvem.ready && nuvem.default_mode === 'nuvem' ? aviso('A IA em nuvem ainda não tem link e chave: enquanto isso, todos usam a IA local.', 'amarelo') : ''}
        <div class="linha"><a class="btn btn--contorno btn--p" href="#/g/configuracoes?aba=ia-link">${icon('link', 14)} Link da API</a><a class="btn btn--contorno btn--p" href="#/g/configuracoes?aba=ia-chave">${icon('chave', 14)} Chave da API</a></div>
        ${sw('ai_enabled', 'Geração com IA habilitada', 'Bloqueia novas gerações quando desativado.')}</section>
      <section class="cartao" style="max-width:720px"><div class="cartao__topo"><h2 class="cartao__titulo">IA local · ${ia.provider_label}</h2>${ia.provider !== 'simulada' ? tag('publicado', 'Conectado') : tag('erro', ia.online ? 'Modelo não disponível' : 'Fora do ar')}</div>
        ${ollama ? html`<p class="texto-suave">A plataforma usa modelos locais via <strong>Ollama</strong> em <code>${ia.url}</code>. Os documentos não saem do servidor da instituição.</p>`
    : html`<p class="texto-suave">A plataforma usa uma IA em nuvem (<code>${ia.url}</code>).</p>${ia.external ? aviso('Com IA em nuvem, o texto dos documentos e as dúvidas dos alunos são enviados ao provedor externo. Confirme que há contrato de tratamento de dados (LGPD) e que o provedor não usa os dados para treinar modelos.', 'amarelo') : ''}`}
        ${ia.online ? '' : aviso(ollama ? html`Instale o Ollama em <strong>ollama.com</strong>, rode <code>ollama pull ${s.ai_model}</code> e reinicie. Enquanto isso, a plataforma usa um gerador local simplificado.` : 'O provedor de IA não respondeu ou não está configurado. Enquanto isso, a plataforma usa um gerador local simplificado.', 'amarelo')}
        <form id="f" class="pilha"><label class="campo"><span>Modelo usado pela instituição</span>
          ${ia.models.length ? html`<select class="entrada" name="ai_model">${[...new Set([s.ai_model, ...ia.models])].map((m) => html`<option ${m === s.ai_model ? 'selected' : ''}>${m}</option>`)}</select>` : html`<input class="entrada" name="ai_model" value="${s.ai_model}">`}</label>
          ${ollama ? html`<p class="texto-fraco">Sugestões para português: <code>llama3.2</code> (leve), <code>qwen2.5:7b</code>, <code>gemma2:9b</code>, <code>llama3.1:8b</code>.</p>` : ''}
          <button class="btn btn--escuro">Salvar modelo</button></form></section>`.s;
      ligarSwitches();
      bindSeg(box, 'modo-padrao', async (v) => {
        try { nuvem = await api('/gestor/ia-nuvem', { method: 'PUT', body: { default_mode: v } }); toast('IA padrão salva'); refreshIaStatus(); show('ia'); } catch (err) { toast(err.message, 'erro'); }
      });
      box.querySelector('#f').addEventListener('submit', async (e) => {
        e.preventDefault();
        await api('/gestor/settings', { method: 'PUT', body: { ai_model: e.target.ai_model.value } }); toast('Modelo salvo'); go(location.hash);
      });
    }
    if (t === 'acesso') {
      box.innerHTML = html`<section class="cartao" style="max-width:720px"><h2 class="cartao__titulo">Domínio e acesso</h2>
        <p>Código da instituição para login: <code>${inst.slug}</code></p>
        ${cfg.email_configured ? aviso('Envio de e-mail configurado: convites, recuperação de senha, respostas do atendimento e resumos semanais são enviados automaticamente.')
    : aviso('Envio de e-mail não configurado no servidor (variável EDU_SMTP_HOST). Os convites precisam ser copiados e enviados manualmente, e “Esqueci minha senha” não entrega o link: redefina a senha em Usuários.', 'amarelo')}
        ${sw('allow_class_code', 'Permitir cadastro de alunos pelo código da turma', 'Alunos criam a própria conta com o código mostrado ao professor.')}
        ${sw('publish_requires_review', 'Exigir revisão antes de publicar', 'Materiais precisam ser marcados como revisados pelo professor.')}</section>`.s;
      ligarSwitches();
    }
    if (t === 'notificacoes') {
      box.innerHTML = html`<section class="cartao" style="max-width:720px"><h2 class="cartao__titulo">Notificações</h2>
        ${sw('notify_new_activity', 'Avisar alunos sobre novas atividades', 'Notificação na plataforma quando uma atividade é publicada.')}
        ${sw('notify_grades', 'Avisar alunos quando a nota é publicada', '')}
        ${sw('notify_weekly_report', 'Relatório semanal para gestores', 'Resumo de uso e desempenho por e-mail, toda segunda-feira.')}
        <form class="linha" id="f-sla" style="margin-top:16px;align-items:flex-end"><label class="campo" style="margin:0"><span>Prazo de resposta do atendimento (dias)</span><input class="entrada" type="number" name="ticket_sla_days" min="1" max="60" value="${s.ticket_sla_days || 5}" style="max-width:120px"></label><button class="btn btn--contorno">Salvar prazo</button></form></section>`.s;
      ligarSwitches();
      box.querySelector('#f-sla').addEventListener('submit', async (e) => {
        e.preventDefault();
        try { await api('/gestor/settings', { method: 'PUT', body: { ticket_sla_days: Number(e.target.ticket_sla_days.value) } }); toast('Prazo salvo'); } catch (err) { toast(err.message, 'erro'); }
      });
    }
    if (t === 'integracoes') {
      box.innerHTML = html`<div class="grade grade-3">${[['Importação por CSV', 'Disponível', 'Importe professores e alunos em Usuários → Importar CSV.'], ['Google Workspace / Microsoft 365 (SSO)', 'Em breve', 'Login único com a conta da escola.'], ['Sistemas de gestão escolar', 'Sob demanda', 'Sincronização de turmas e matrículas via API.']].map(([n, st, d]) => html`<div class="cartao"><h3>${n}</h3>${st === 'Disponível' ? tag('publicado', st) : tag('cinza', st)}<p class="texto-suave">${d}</p></div>`)}</div>`.s;
    }
  };
  bindTabs(el, show);
  show(aba);
}, R);

/* ================================================================ H08 auditoria e privacidade */
route('g/privacidade', async (_, q) => {
  page(loading());
  const aba = q.aba || 'auditoria';
  let logs, reqs, cfg;
  try { [logs, reqs, cfg] = await Promise.all([api('/gestor/audit'), api('/gestor/data-requests'), api('/gestor/settings')]); } catch (e) {
    return page(html`${header('Auditoria e privacidade')}${aviso(e.message, 'vermelho')}`);
  }
  const s = cfg.settings;
  const abertas = reqs.filter((r) => r.status === 'aberta').length;
  const el = page(html`${header('Auditoria e privacidade', 'Registros administrativos, solicitações de titulares (LGPD) e retenção de dados.')}
    ${tabs([['auditoria', 'Registros de auditoria'], ['lgpd', `Solicitações LGPD (${abertas})`], ['retencao', 'Retenção de dados'], ['responsaveis', 'Responsáveis']], aba)}<div id="aba"></div>`);
  const box = el.querySelector('#aba');
  const show = (t) => {
    history.replaceState(null, '', '#/g/privacidade?aba=' + t);
    if (t === 'auditoria') {
      box.innerHTML = html`<div class="filtros"><input class="entrada entrada--busca" id="q" placeholder="Filtrar por pessoa, ação ou detalhe…"></div>
        <div class="tabela-caixa"><table class="tabela"><thead><tr><th>Quando</th><th>Quem</th><th>Ação</th><th>Detalhe</th></tr></thead><tbody id="lista">
        ${logs.map((l) => html`<tr data-b="${`${l.user_name} ${l.action} ${l.detail}`.toLowerCase()}"><td>${fmtDateTime(l.created_at)}</td><td>${l.user_name || 'Sistema'} <span class="texto-fraco">${l.role ? PAPEL[l.role] : ''}</span></td><td><code>${l.action}</code></td><td>${l.detail}</td></tr>`)}</tbody></table></div>`.s;
      box.querySelector('#q').oninput = (e) => box.querySelectorAll('#lista tr').forEach((tr) => { tr.hidden = !tr.dataset.b.includes(e.target.value.toLowerCase()); });
    }
    if (t === 'lgpd') {
      const K = { exportacao: 'Cópia dos dados', correcao: 'Correção', exclusao: 'Exclusão / anonimização' };
      box.innerHTML = reqs.length ? html`<div class="tabela-caixa"><table class="tabela"><thead><tr><th>Titular</th><th>Pedido</th><th>Aberto em</th><th>Status</th><th></th></tr></thead><tbody>
        ${reqs.map((r) => html`<tr><td>${r.name}<div class="texto-fraco">${r.email} · ${PAPEL[r.role]}</div></td><td>${K[r.kind]}${r.detail ? html`<div class="texto-fraco">${r.detail}</div>` : ''}</td><td>${fmtDate(r.created_at)}</td><td>${tag(r.status)}</td>
          <td>${r.status === 'aberta' ? html`<div class="acoes-icone">${r.kind === 'exportacao' ? html`<button class="btn btn--contorno btn--p" data-exportar="${r.user_id}">Baixar dados</button>` : ''}
            <button class="btn btn--verde btn--p" data-resolver="${r.id}" data-k="${r.kind}">Concluir</button><button class="btn btn--link" data-recusar="${r.id}">Recusar</button></div>` : fmtDate(r.resolved_at)}</td></tr>`)}</tbody></table></div>
        ${aviso('Concluir uma exclusão anonimiza o usuário (nome, e-mail e senha) e mantém apenas dados agregados necessários aos relatórios.', 'amarelo')}`.s
        : empty('Nenhuma solicitação', 'Os titulares abrem pedidos em Perfil → Privacidade.').s;
      box.querySelectorAll('[data-exportar]').forEach((b) => {
        b.onclick = async () => {
          const d = await api(`/gestor/users/${b.dataset.exportar}/export`);
          const blob = new Blob([JSON.stringify(d, null, 2)], { type: 'application/json' });
          const a = Object.assign(document.createElement('a'), { href: URL.createObjectURL(blob), download: `dados-usuario-${b.dataset.exportar}.json` });
          document.body.append(a); a.click(); a.remove();
        };
      });
      const resolver = async (id, status, msg) => {
        if (!(await confirmar(msg, { ok: status === 'concluida' ? 'Concluir' : 'Recusar', perigo: true }))) return;
        await api(`/gestor/data-requests/${id}/resolve`, { method: 'POST', body: { status } }); go(location.hash);
      };
      box.querySelectorAll('[data-resolver]').forEach((b) => { b.onclick = () => resolver(b.dataset.resolver, 'concluida', b.dataset.k === 'exclusao' ? 'Concluir a exclusão? O usuário será anonimizado e desativado. Isso não pode ser desfeito.' : 'Marcar a solicitação como concluída?'); });
      box.querySelectorAll('[data-recusar]').forEach((b) => { b.onclick = () => resolver(b.dataset.recusar, 'recusada', 'Recusar esta solicitação?'); });
    }
    if (t === 'retencao') {
      box.innerHTML = html`<form class="cartao" id="f" style="max-width:640px"><h2 class="cartao__titulo">Política de retenção</h2>
        <p class="texto-suave">Registros de auditoria e notificações lidas mais antigos que o prazo podem ser removidos.</p>
        <label class="campo"><span>Prazo de retenção (dias)</span><input class="entrada" type="number" name="retention_days" min="30" value="${s.retention_days}" style="max-width:160px"></label>
        <div class="linha"><button class="btn btn--escuro">Salvar prazo</button><button type="button" class="btn btn--perigo" data-aplicar>Aplicar retenção agora</button></div></form>`.s;
      box.querySelector('#f').addEventListener('submit', async (e) => {
        e.preventDefault();
        await api('/gestor/settings', { method: 'PUT', body: { retention_days: Number(e.target.retention_days.value) } }); toast('Prazo salvo');
      });
      box.querySelector('[data-aplicar]').onclick = async () => {
        if (!(await confirmar(`Remover registros com mais de ${s.retention_days} dias?`, { ok: 'Aplicar', perigo: true }))) return;
        const r = await api('/gestor/retention/apply', { method: 'POST' });
        toast(`${r.audit_removed} registros e ${r.notifications_removed} notificações removidos`);
      };
    }
    if (t === 'responsaveis') {
      const sel = new Set(s.privacy_admins || []);
      box.innerHTML = html`<form class="cartao" id="f" style="max-width:640px"><h2 class="cartao__titulo">Quem pode ver auditoria e dados pessoais</h2>
        <p class="texto-suave">Se ninguém for marcado, todos os gestores têm acesso. Marque para restringir.</p>
        <div class="lista-checagem">${cfg.gestores.map((g) => html`<label class="check"><input type="checkbox" value="${g.id}" ${sel.has(g.id) ? 'checked' : ''}>${g.name}</label>`)}</div>
        <button class="btn btn--escuro">Salvar responsáveis</button></form>`.s;
      box.querySelector('#f').addEventListener('submit', async (e) => {
        e.preventDefault();
        const ids = [...e.target.querySelectorAll('input:checked')].map((i) => Number(i.value));
        if (ids.length && !ids.includes(S.user.id) && !(await confirmar('Você não está na lista e perderá acesso a esta área. Continuar?', { perigo: true }))) return;
        try { await api('/gestor/settings', { method: 'PUT', body: { privacy_admins: ids } }); toast('Responsáveis salvos'); go(location.hash); } catch (err) { toast(err.message, 'erro'); }
      });
    }
  };
  bindTabs(el, show);
  show(aba);
}, R);

