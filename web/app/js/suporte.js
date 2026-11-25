/* EDU.AI – suporte à comunidade escolar: atendimento/ouvidoria, calendário escolar e grade de disciplinas */
import {
  S, ago, api, aviso, bindTabs, busy, confirmar, download, effRole, empty, fmtDate, fmtDateTime, formData, go, header, html, icon, kpi,
  loading, modal, page, pad2, route, tabs, tag, toast,
} from './core.js';

const PAPEL = { professor: 'Professor', aluno: 'Aluno', gestor: 'Gestão', secretaria: 'Secretaria', admin: 'Suporte da plataforma' };
const ST = {
  aberto: ['amarelo', 'Aberto'], em_andamento: ['azul', 'Em andamento'], aguardando: ['amarelo', 'Aguardando você'],
  resolvido: ['verde', 'Resolvido'], fechado: ['cinza', 'Fechado'],
};
const stTag = (s, staff) => {
  const [cor, txt] = ST[s] || ['cinza', s];
  return html`<span class="tag tag--${cor}">${s === 'aguardando' && staff ? 'Aguardando solicitante' : txt}</span>`;
};
const kb = (n) => (n > 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`);
const ANEXOS = '.pdf,.png,.jpg,.jpeg,.webp,.docx,.doc,.odt,.xlsx,.xls,.ods,.csv,.txt,.zip';
const DESTINO_TAG = { secretaria: 'azul', gestao: 'amarelo', plataforma: 'verde' };
const destinoTag = (t) => html`<span class="tag tag--${DESTINO_TAG[t.target] || 'cinza'}">${t.target_label}</span>`;
/** Onde cada perfil vê a lista dos próprios chamados. */
const meusChamados = () => (effRole() === 'gestor' ? '#/g/suporte' : '#/atendimento');

/* ================================================================ meus chamados (aluno, professor e secretaria) */
route('atendimento', async (_, q) => {
  const papel = effRole();
  if (papel === 'gestor') return go('#/g/suporte');
  if (papel === 'admin') return go('#/admin/chamados');
  page(loading());
  const lista = await api('/chamados?mine=1');
  const aba = q.aba || 'abertos';
  const grupos = { abertos: lista.filter((t) => !['resolvido', 'fechado'].includes(t.status)), encerrados: lista.filter((t) => ['resolvido', 'fechado'].includes(t.status)) };
  const sec = papel === 'secretaria';
  const atalhos = sec
    ? [['gestao', 'administrativo', 'Assunto administrativo', 'Pedidos e avisos à gestão', 'predio'], ['gestao', 'recursos', 'Recursos e infraestrutura', 'Materiais, equipamentos, manutenção', 'config'],
      ['gestao', 'pedagogico', 'Coordenação pedagógica', 'Dúvidas sobre notas, turmas e professores', 'grafico'], ['gestao', 'suporte', 'Problema na plataforma', 'Algo não funciona como deveria', 'alerta']]
    : [['secretaria', 'documento', 'Solicitar documento', 'Declarações, histórico, boletim', 'conteudo'], ['secretaria', 'secretaria', 'Secretaria', 'Matrícula, cadastro, transferência', 'predio'],
      ['gestao', 'pedagogico', 'Coordenação / gestão', 'Notas, frequência, revisão de prova', 'grafico'], ['secretaria', 'denuncia', 'Ouvidoria', 'Reclamações e denúncias (pode ser anônimo)', 'escudo']];
  const el = page(html`${header(sec ? 'Chamados à gestão' : 'Atendimento e secretaria',
    sec ? 'Abra chamados para o gestor da instituição e acompanhe as respostas. Você pode anexar arquivos.'
      : 'Fale com a secretaria ou com a gestão da escola: peça documentos, tire dúvidas ou registre uma reclamação, sugestão ou denúncia.',
    html`<a class="btn btn--primario" href="#/atendimento/novo">+ Novo chamado</a>`)}
    <div class="grade grade-4">${atalhos.map(([d, c, t, desc, i]) => html`<a class="cartao" href="#/atendimento/novo?destino=${d}&categoria=${c}" style="color:inherit;text-decoration:none"><span class="tipo-icone">${icon(i)}</span><h3 class="cartao__titulo">${t}</h3><p class="texto-fraco">${desc}</p></a>`)}</div>
    ${tabs([['abertos', `Em andamento (${grupos.abertos.length})`], ['encerrados', `Encerrados (${grupos.encerrados.length})`]], aba)}<div id="lista"></div>`);
  const show = (t) => {
    history.replaceState(null, '', '#/atendimento?aba=' + t);
    const l = grupos[t];
    el.querySelector('#lista').innerHTML = (l.length ? html`<div class="lista-itens">${l.map((x) => html`<a class="item" href="#/atendimento/${x.id}" style="color:inherit;text-decoration:none">
      <div class="item__info"><span class="tipo-icone">${icon('chat')}</span><div><strong>${x.subject}</strong><small><span class="protocolo">#${x.protocol}</span> · ${x.target_label} · ${x.category_label} · atualizado ${ago(x.updated_at)}${x.anonymous ? ' · anônimo' : ''}</small></div></div>
      <div class="linha">${x.waiting_me ? html`<span class="tag tag--vermelho">Responder</span>` : ''}${stTag(x.status)}</div></a>`)}</div>`
      : empty(t === 'abertos' ? 'Nenhum chamado em andamento' : 'Nenhum chamado encerrado', 'Use “Novo chamado” para abrir um pedido.')).s;
  };
  bindTabs(el, show);
  show(aba);
});

/* ================================================================ novo chamado (qualquer perfil que abre chamados) */
route('atendimento/novo', async (_, q) => {
  if (effRole() === 'admin') return go('#/admin/chamados');
  const op = await api('/chamados/opcoes' + (q.destino ? '?target=' + q.destino : ''));
  const destinos = Object.entries(op.targets);
  if (!destinos.length) return go(meusChamados());
  let destino = op.targets[q.destino] ? q.destino : op.target;
  const el = page(html`<a href="${meusChamados()}" class="link-sutil">← Meus chamados</a>
    ${header('Novo chamado', 'Você acompanha tudo por aqui e recebe um aviso a cada resposta. Anexe arquivos se precisar (até 10 MB).')}
    <form class="cartao" id="f" style="max-width:720px">
      ${destinos.length > 1 ? html`<div class="campo"><span>Enviar para</span><div class="grade grade-2">${destinos.map(([k, v]) => html`<label class="opcao" style="min-height:auto"><input type="radio" name="target" value="${k}" ${k === destino ? 'checked' : ''}><strong>${v}</strong><small>${k === 'secretaria' ? 'Documentos, matrícula, cadastro e atendimento geral' : k === 'gestao' ? 'Coordenação e direção da instituição' : 'Equipe da plataforma EDU.AI'}</small></label>`)}</div></div>`
    : html`<p class="texto-suave">Destino: <strong>${destinos[0][1]}</strong>${destino === 'plataforma' ? ` · resposta em até ${op.sla_days} dia(s) úteis` : ''}</p><input type="hidden" name="target" value="${destino}">`}
      <label class="campo"><span>Assunto</span><select class="entrada" name="category"></select></label>
      <label class="campo" data-doc><span>Documento</span><select class="entrada" name="document_type">${op.documents.map((d) => html`<option>${d}</option>`)}</select></label>
      <label class="campo"><span>Título</span><input class="entrada" name="subject" maxlength="150" placeholder="Resumo do pedido"></label>
      <label class="campo"><span>Descreva o pedido</span><textarea class="entrada" name="body" rows="6" required minlength="5" maxlength="5000" placeholder="Explique o que você precisa. Para documentos, diga para que é (estágio, transporte, outro colégio…)."></textarea></label>
      <label class="campo"><span>Anexo (opcional) · PDF, imagem, documento, planilha, TXT ou ZIP até 10 MB</span><input class="entrada" type="file" name="file" accept="${ANEXOS}"></label>
      <label class="check" data-anon><input type="checkbox" name="anonymous"> Enviar de forma anônima</label>
      <div data-anon-aviso hidden>${aviso('A escola não verá o seu nome nem o seu e-mail. A plataforma guarda o vínculo apenas para entregar as respostas a você. Para pedidos que dependem de quem você é (documentos, notas), não use o anonimato.', 'amarelo')}</div>
      <div class="linha linha--fim"><a class="btn btn--contorno" href="${meusChamados()}">Cancelar</a><button class="btn btn--primario" type="submit">Enviar chamado</button></div>
    </form>`);
  const f = el.querySelector('#f');
  const fillCats = (cat) => {
    const cats = op.categories_by_target[destino] || op.categories;
    f.category.innerHTML = html`${Object.entries(cats).map(([k, v]) => html`<option value="${k}" ${k === cat ? 'selected' : ''}>${v}</option>`)}`.s;
  };
  const sync = () => {
    const c = f.category.value;
    el.querySelector('[data-doc]').hidden = c !== 'documento';
    const anon = op.anonymous_allowed.includes(c) && destino !== 'plataforma';
    el.querySelector('[data-anon]').hidden = !anon;
    if (!anon) f.anonymous.checked = false;
    el.querySelector('[data-anon-aviso]').hidden = !f.anonymous.checked;
  };
  fillCats(q.categoria);
  f.querySelectorAll('[name=target]').forEach((r) => r.addEventListener('change', () => { destino = r.value; fillCats(); sync(); }));
  f.category.onchange = sync; f.anonymous.onchange = sync; sync();
  f.addEventListener('submit', (e) => {
    e.preventDefault();
    busy(f.querySelector('[type=submit]'), async () => {
      const fd = new FormData();
      const c = f.category.value;
      fd.append('target', destino);
      fd.append('category', c);
      fd.append('subject', f.subject.value.trim() || (c === 'documento' ? f.document_type.value : ''));
      fd.append('body', f.body.value);
      fd.append('anonymous', f.anonymous.checked ? 'true' : 'false');
      if (c === 'documento') fd.append('document_type', f.document_type.value);
      if (f.file.files[0]) fd.append('file', f.file.files[0]);
      const r = await api('/chamados', { method: 'POST', form: fd });
      toast(`Chamado #${r.protocol} aberto`);
      go('#/atendimento/' + r.id);
    });
  });
});

/** Conversa de um chamado: mesma tela para quem pediu e para a equipe (com controles extras). */
export async function telaChamado(id, voltar) {
  page(loading());
  const t = await api('/chamados/' + id);
  const staff = t.is_staff;
  const papel = effRole();
  const podeDeclarar = staff && ['secretaria', 'gestor'].includes(papel) && t.requester_role === 'aluno' && t.user_id;
  const el = page(html`<a href="${voltar}" class="link-sutil">← Voltar</a>
    ${header(t.subject, html`<span class="protocolo">#${t.protocol}</span> · ${t.target_label} · ${t.category_label} · aberto em ${fmtDateTime(t.created_at)}`, stTag(t.status, staff))}
    <div class="grade grade-lateral">
      <div class="pilha">
        ${t.overdue && staff ? aviso(`Prazo de resposta vencido (${fmtDateTime(t.due_at)}).`, 'vermelho') : ''}
        <div class="conversa">${t.messages.map((m) => html`<div class="msg ${m.mine ? 'msg--minha' : ''} ${m.internal ? 'msg--interna' : ''}">
          <div class="msg__topo"><strong>${m.mine ? 'Você' : m.name}${m.role ? html` <span class="texto-fraco">· ${PAPEL[m.role] || m.role}</span>` : ''}${m.internal ? ' · nota interna (só a equipe vê)' : ''}</strong><span>${fmtDateTime(m.created_at)}</span></div>
          <div class="msg__corpo">${m.body}</div>
          ${m.attachment_name ? html`<button class="btn btn--contorno btn--p msg__anexo" data-anexo="${m.id}" data-nome="${m.attachment_name}">${icon('anexo', 14)} ${m.attachment_name} (${kb(m.attachment_size || 0)})</button>` : ''}</div>`)}</div>
        ${t.can_reply ? html`<form class="cartao" id="f"><h2 class="cartao__titulo">${staff ? 'Responder' : 'Enviar mensagem'}</h2>
          <textarea class="entrada" name="body" rows="4" maxlength="5000" placeholder="${staff ? 'Escreva a resposta para o solicitante…' : 'Complemente o seu pedido ou responda…'}"></textarea>
          <label class="campo"><span>${icon('anexo', 14)} Anexar arquivo (opcional, até 10 MB)</span><input class="entrada" type="file" name="file" accept="${ANEXOS}"></label>
          ${staff ? html`<div class="campos-2"><label class="campo"><span>Situação depois de enviar</span><select class="entrada" name="status"><option value="">Manter / em andamento</option><option value="aguardando">Aguardando o solicitante</option><option value="resolvido">Resolvido</option></select></label>
            <label class="check" style="margin-top:26px"><input type="checkbox" name="internal"> Nota interna (o solicitante não vê)</label></div>` : ''}
          <div class="linha linha--fim"><button class="btn btn--primario" type="submit">Enviar</button></div></form>`
    : aviso('Este chamado foi fechado. Se precisar, abra um novo chamado.')}
      </div>
      <aside class="pilha">
        <section class="cartao"><h2 class="cartao__titulo">Detalhes</h2><ul class="lista-simples">
          <li><span>Situação</span>${stTag(t.status, staff)}</li>
          <li><span>Destino</span>${destinoTag(t)}</li>
          ${staff ? html`${t.target === 'plataforma' ? html`<li><span>Instituição</span><strong>${t.institution_name}</strong></li>` : ''}
            <li><span>Solicitante</span><strong>${t.requester}${t.requester_role ? html` <span class="texto-fraco">· ${PAPEL[t.requester_role]}</span>` : ''}</strong></li>
            ${t.requester_classes ? html`<li><span>Turma(s)</span><span>${t.requester_classes}</span></li>` : ''}
            ${t.requester_email ? html`<li><span>E-mail</span><span>${t.requester_email}</span></li>` : ''}
            <li><span>Responsável</span><span>${t.assignee || '—'}</span></li>` : ''}
          <li><span>Prazo de resposta</span><span>${fmtDate(t.due_at)}</span></li>
          ${t.rating ? html`<li><span>Avaliação</span><strong>${'★'.repeat(t.rating)}${'☆'.repeat(5 - t.rating)}</strong></li>` : ''}</ul>
          ${t.anonymous ? aviso(staff ? 'Chamado anônimo: a identidade de quem enviou não é mostrada.' : 'Você enviou este chamado de forma anônima.', 'amarelo') : ''}</section>
        <section class="cartao pilha"><h2 class="cartao__titulo">Ações</h2>
          ${staff ? html`${podeDeclarar ? html`<a class="btn btn--primario btn--bloco" href="#/s/declaracoes?aluno=${t.user_id}&chamado=${t.id}">${icon('carimbo', 16)} Emitir declaração para o aluno</a>
              <a class="btn btn--contorno btn--bloco" href="#/s/carteirinhas?aluno=${t.user_id}">${icon('cracha', 16)} Gerar carteirinha</a>` : ''}
            ${t.assignee ? '' : html`<button class="btn btn--escuro btn--bloco" data-assumir>Assumir este chamado</button>`}
            ${t.status !== 'resolvido' && t.status !== 'fechado' ? html`<button class="btn btn--verde btn--bloco" data-st="resolvido">Marcar como resolvido</button>` : ''}
            ${t.status !== 'fechado' ? html`<button class="btn btn--contorno btn--bloco" data-st="fechado">Fechar chamado</button>` : ''}
            ${t.target === 'secretaria' && t.status !== 'fechado' ? html`<button class="btn btn--link btn--bloco" data-encaminhar="gestao">Encaminhar para a gestão</button>` : ''}
            ${t.target === 'gestao' && papel === 'gestor' && t.status !== 'fechado' ? html`<button class="btn btn--link btn--bloco" data-encaminhar="secretaria">Encaminhar para a secretaria</button>` : ''}`
    : html`${t.status === 'resolvido' && !t.rating ? html`<p class="texto-suave">O seu pedido foi atendido? Avalie o atendimento:</p><div class="linha">${[1, 2, 3, 4, 5].map((n) => html`<button class="btn btn--contorno btn--p" data-nota="${n}">${n} ★</button>`)}</div>` : ''}
            ${t.status === 'resolvido' ? html`<button class="btn btn--contorno btn--bloco" data-st="aberto">Ainda não resolveu: reabrir</button>` : ''}
            ${!['resolvido', 'fechado'].includes(t.status) ? html`<button class="btn btn--contorno btn--bloco" data-st="fechado">Não preciso mais: fechar</button>` : ''}
            ${S.user.role === 'aluno' ? html`<a class="btn btn--link btn--bloco" href="#/documentos">Ver meus documentos</a>` : ''}`}
        </section>
      </aside>
    </div>`);
  el.querySelectorAll('[data-anexo]').forEach((b) => { b.onclick = () => busy(b, () => download(`/chamados/${id}/anexo/${b.dataset.anexo}`, b.dataset.nome)); });
  const f = el.querySelector('#f');
  f?.addEventListener('submit', (e) => {
    e.preventDefault();
    busy(f.querySelector('[type=submit]'), async () => {
      const fd = new FormData();
      fd.append('body', f.body.value);
      if (staff) { fd.append('status', f.status.value); fd.append('internal', f.internal.checked ? 'true' : 'false'); }
      if (f.file.files[0]) fd.append('file', f.file.files[0]);
      await api(`/chamados/${id}/mensagens`, { method: 'POST', form: fd });
      toast('Mensagem enviada'); go(location.hash);
    });
  });
  el.querySelector('[data-assumir]')?.addEventListener('click', (e) => busy(e.currentTarget, async () => { await api(`/chamados/${id}/assumir`, { method: 'POST' }); go(location.hash); }));
  el.querySelectorAll('[data-encaminhar]').forEach((b) => {
    b.onclick = async () => {
      if (!(await confirmar(`Encaminhar o chamado para ${b.dataset.encaminhar === 'gestao' ? 'a gestão' : 'a secretaria'}?`, { ok: 'Encaminhar' }))) return;
      await busy(b, async () => { await api(`/chamados/${id}/encaminhar`, { method: 'POST', body: { target: b.dataset.encaminhar } }); toast('Chamado encaminhado'); go(voltar); });
    };
  });
  el.querySelectorAll('[data-st]').forEach((b) => {
    b.onclick = async () => {
      if (b.dataset.st === 'fechado' && !(await confirmar('Fechar o chamado? Depois de fechado, ele não recebe novas mensagens.', { ok: 'Fechar' }))) return;
      await busy(b, async () => { await api(`/chamados/${id}/status`, { method: 'POST', body: { status: b.dataset.st } }); go(location.hash); });
    };
  });
  el.querySelectorAll('[data-nota]').forEach((b) => { b.onclick = () => busy(b, async () => { await api(`/chamados/${id}/avaliar`, { method: 'POST', body: { rating: Number(b.dataset.nota) } }); toast('Obrigado pela avaliação!'); go(location.hash); }); });
}

route('atendimento/:id', ({ id }) => telaChamado(id, meusChamados()));

/* ================================================================ filas de atendimento (secretaria, gestão e plataforma) */
/**
 * Fila da equipe. `base`: rota da lista; `detalhe`: prefixo do link de cada chamado.
 * `plataforma`: mostra a instituição de cada chamado (administrador geral).
 */
export async function filaChamados(q, { base, detalhe, titulo, sub, plataforma = false, destinos = false }) {
  page(loading());
  const [lista, res, op] = await Promise.all([api('/chamados'), api('/chamados/resumo/gestao'), api('/chamados/opcoes')]);
  const filtro = { status: q.status || 'ativos', categoria: q.categoria || '', destino: q.destino || '' };
  const el = page(html`${header(titulo, sub)}
    <div class="grade grade-4">${kpi('Abertos', pad2((res.by_status.aberto || 0) + (res.by_status.em_andamento || 0)), res.overdue ? `${res.overdue} com prazo vencido` : 'nenhum atrasado', res.overdue ? 'vermelho' : 'verde')}
      ${kpi('Aguardando solicitante', pad2(res.by_status.aguardando || 0))}${kpi('Tempo médio até resolver', res.avg_hours == null ? '—' : res.avg_hours < 48 ? `${res.avg_hours} h` : `${Math.round(res.avg_hours / 24)} dias`, 'últimos 90 dias')}
      ${kpi('Satisfação', res.avg_rating == null ? '—' : `${res.avg_rating} / 5`, 'avaliação de quem pediu')}</div>
    <div class="filtros"><select class="entrada" id="fs" style="max-width:220px">${[['ativos', 'Abertos e em andamento'], ['aguardando', 'Aguardando solicitante'], ['resolvido', 'Resolvidos'], ['fechado', 'Fechados'], ['todos', 'Todos']].map(([v, l]) => html`<option value="${v}" ${v === filtro.status ? 'selected' : ''}>${l}</option>`)}</select>
      ${destinos ? html`<select class="entrada" id="fd" style="max-width:220px"><option value="">Secretaria e gestão</option><option value="secretaria" ${filtro.destino === 'secretaria' ? 'selected' : ''}>Só secretaria</option><option value="gestao" ${filtro.destino === 'gestao' ? 'selected' : ''}>Só para a gestão</option></select>` : ''}
      <select class="entrada" id="fc" style="max-width:280px"><option value="">Todos os assuntos</option>${[...new Set(lista.map((t) => t.category))].map((k) => html`<option value="${k}" ${k === filtro.categoria ? 'selected' : ''}>${op.all_categories[k] || k}</option>`)}</select></div>
    <div id="lista"></div>`);
  const render = () => {
    const l = lista.filter((t) => (filtro.status === 'todos' || (filtro.status === 'ativos' ? ['aberto', 'em_andamento'].includes(t.status) : t.status === filtro.status))
      && (!filtro.categoria || t.category === filtro.categoria) && (!filtro.destino || t.target === filtro.destino));
    el.querySelector('#lista').innerHTML = (l.length ? html`<div class="tabela-caixa"><table class="tabela"><thead><tr><th>Protocolo</th><th>Assunto</th>${plataforma ? html`<th>Instituição</th>` : ''}<th>Solicitante</th>${destinos ? html`<th>Destino</th>` : ''}<th>Situação</th><th>Prazo</th><th>Responsável</th><th></th></tr></thead><tbody>
      ${l.map((t) => html`<tr><td class="protocolo">#${t.protocol}</td><td><strong style="font-weight:600">${t.subject}</strong><div class="texto-fraco">${t.category_label}</div></td>
        ${plataforma ? html`<td>${t.institution_name}</td>` : ''}
        <td>${t.requester}${t.requester_role ? html`<div class="texto-fraco">${PAPEL[t.requester_role]}</div>` : ''}</td>${destinos ? html`<td>${destinoTag(t)}</td>` : ''}<td>${stTag(t.status, true)}${t.waiting_me ? html` <span class="tag tag--vermelho">Nova mensagem</span>` : ''}</td>
        <td>${t.overdue ? html`<span class="tag tag--vermelho">Vencido</span>` : fmtDate(t.due_at)}</td><td>${t.assignee || '—'}</td>
        <td><a class="btn btn--contorno btn--p" href="${detalhe}${t.id}">Abrir</a></td></tr>`)}</tbody></table></div>`
      : empty('Nenhum chamado neste filtro')).s;
  };
  el.querySelector('#fs').onchange = (e) => { filtro.status = e.target.value; render(); };
  el.querySelector('#fc').onchange = (e) => { filtro.categoria = e.target.value; render(); };
  el.querySelector('#fd')?.addEventListener('change', (e) => { filtro.destino = e.target.value; render(); });
  render();
  return el;
}

route('g/atendimento', (_, q) => filaChamados(q, { base: '#/g/atendimento', detalhe: '#/g/chamado/', destinos: true, titulo: 'Atendimento e ouvidoria',
  sub: 'Chamados de alunos, professores e da secretaria (os pedidos à secretaria também aparecem aqui). O prazo de resposta é definido em Configurações → Notificações.' }), { role: 'gestor' });
route('g/chamado/:id', ({ id }) => telaChamado(id, '#/g/atendimento'), { role: 'gestor' });

route('s/atendimento', (_, q) => filaChamados(q, { base: '#/s/atendimento', detalhe: '#/s/chamado/', titulo: 'Atendimento da secretaria',
  sub: 'Pedidos de alunos e professores: documentos, matrícula, cadastro e dúvidas. Responda com anexos e emita declarações direto do chamado.' }), { role: ['secretaria', 'gestor'] });
route('s/chamado/:id', ({ id }) => telaChamado(id, effRole() === 'gestor' ? '#/g/atendimento' : '#/s/atendimento'), { role: ['secretaria', 'gestor'] });

/* ================================================================ gestor: chamados para o suporte da plataforma */
route('g/suporte', async () => {
  page(loading());
  const lista = await api('/chamados?mine=1');
  const ativos = lista.filter((t) => !['resolvido', 'fechado'].includes(t.status));
  page(html`${header('Suporte da plataforma', 'Abra chamados para a equipe da plataforma EDU.AI: faturas, problemas técnicos, configuração da IA, planos e sugestões. Anexe prints ou documentos.',
    html`<a class="btn btn--primario" href="#/atendimento/novo?destino=plataforma">+ Novo chamado ao suporte</a>`)}
    <div class="grade grade-4">${[['financeiro', 'Faturas e pagamentos', 'fatura'], ['suporte', 'Problema técnico', 'alerta'], ['ia', 'Configuração da IA', 'robo'], ['plano', 'Plano e limites', 'plano']]
      .map(([c, t, i]) => html`<a class="cartao" href="#/atendimento/novo?destino=plataforma&categoria=${c}" style="color:inherit;text-decoration:none"><span class="tipo-icone">${icon(i)}</span><h3 class="cartao__titulo">${t}</h3></a>`)}</div>
    <h2 class="cartao__titulo">Meus chamados (${ativos.length} em andamento)</h2>
    ${lista.length ? html`<div class="lista-itens">${lista.map((x) => html`<a class="item" href="#/atendimento/${x.id}" style="color:inherit;text-decoration:none">
      <div class="item__info"><span class="tipo-icone">${icon('chat')}</span><div><strong>${x.subject}</strong><small><span class="protocolo">#${x.protocol}</span> · ${x.category_label} · atualizado ${ago(x.updated_at)}</small></div></div>
      <div class="linha">${x.waiting_me ? html`<span class="tag tag--vermelho">Responder</span>` : ''}${stTag(x.status)}</div></a>`)}</div>` : empty('Nenhum chamado aberto ao suporte')}`);
}, { role: 'gestor' });

/* ================================================================ administrador geral: chamados das instituições */
route('admin/chamados', (_, q) => filaChamados(q, { base: '#/admin/chamados', detalhe: '#/admin/chamado/', plataforma: true, titulo: 'Chamados das instituições',
  sub: 'Chamados que os gestores das instituições abrem para o suporte da plataforma.' }), { role: 'superadmin' });
route('admin/chamado/:id', ({ id }) => telaChamado(id, '#/admin/chamados'), { role: 'superadmin' });

/* ================================================================ calendário escolar */
const MESES = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro'];
const SEMANA = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom'];
const mesVizinho = (m, d) => { const [a, n] = m.split('-').map(Number); const x = new Date(a, n - 1 + d, 1); return `${x.getFullYear()}-${String(x.getMonth() + 1).padStart(2, '0')}`; };

async function telaCalendario(q, gestao) {
  page(loading());
  const qs = new URLSearchParams();
  if (q.mes) qs.set('mes', q.mes);
  if (q.turma) qs.set('turma', q.turma);
  const c = await api('/calendario?' + qs);
  const base = gestao ? '#/g/calendario' : '#/calendario';
  const link = (mes) => `${base}?mes=${mes}${q.turma ? '&turma=' + q.turma : ''}`;
  const [ano, mes] = c.month.split('-').map(Number);
  const vazios = (new Date(ano, mes - 1, 1).getDay() + 6) % 7;
  const podeEditar = c.can_edit;
  const el = page(html`${header('Calendário escolar', gestao ? 'Defina os períodos letivos, os dias de aula, feriados, recessos, provas e eventos.' : 'Dias de aula, feriados, provas, eventos e prazos das atividades.',
    html`${podeEditar ? html`<button class="btn btn--primario" data-evento>+ ${gestao ? 'Evento ou feriado' : 'Prova ou evento'}</button>` : ''}${gestao ? html`<button class="btn btn--contorno" data-periodos>Períodos letivos</button>` : ''}`)}
    ${!c.terms.length ? aviso(gestao ? 'Nenhum período letivo cadastrado: cadastre o ano ou semestre letivo em “Períodos letivos” para marcar os dias de aula.' : 'A escola ainda não publicou o período letivo. Feriados e eventos já cadastrados aparecem abaixo.', 'amarelo') : ''}
    <section class="cartao">
      <div class="linha linha--entre" style="margin-bottom:12px;flex-wrap:wrap">
        <div class="linha"><a class="btn btn--contorno btn--p" href="${link(mesVizinho(c.month, -1))}" aria-label="Mês anterior">←</a>
          <h2 class="cartao__titulo" style="margin:0;min-width:180px;text-align:center">${MESES[mes - 1][0].toUpperCase() + MESES[mes - 1].slice(1)} de ${ano}</h2>
          <a class="btn btn--contorno btn--p" href="${link(mesVizinho(c.month, 1))}" aria-label="Próximo mês">→</a>
          <a class="btn btn--link" href="${link(c.today.slice(0, 7))}">Hoje</a></div>
        <div class="linha">${c.classes.length > 1 ? html`<select class="entrada" id="turma" style="max-width:220px"><option value="">${gestao ? 'Toda a escola' : 'Todas as minhas turmas'}</option>${c.classes.map((t) => html`<option value="${t.id}" ${String(t.id) === q.turma ? 'selected' : ''}>${t.name}</option>`)}</select>` : ''}
          <span class="tag tag--verde">${c.class_days} dia(s) de aula</span></div>
      </div>
      <div class="cal" role="grid" aria-label="Calendário de ${MESES[mes - 1]}">${SEMANA.map((d) => html`<div class="cal__cab">${d}</div>`)}
        ${Array.from({ length: vazios }, () => html`<div class="cal__dia cal__dia--vazio" aria-hidden="true"></div>`)}
        ${c.days.map((d) => html`<button type="button" class="cal__dia ${d.class_day ? 'cal__dia--aula' : ''} ${d.date === c.today ? 'cal__dia--hoje' : ''}" data-dia="${d.date}"
            aria-label="${fmtDate(d.date)}${d.class_day ? ', dia de aula' : ''}${d.events.length ? ', ' + d.events.map((e) => e.title).join(', ') : ''}">
          <span class="cal__num">${Number(d.date.slice(8))}${d.class_day ? html`<span class="cal__aula">aula</span>` : ''}</span>
          ${d.events.slice(0, 3).map((e) => html`<span class="cal__ev cal__ev--${e.kind}" title="${e.kind_label}: ${e.title}">${e.title}</span>`)}
          ${d.activities.slice(0, 2).map((a) => html`<span class="cal__ev cal__ev--atividade" title="Prazo: ${a.title}">Prazo: ${a.title}</span>`)}
          ${d.events.length + d.activities.length > 5 ? html`<small class="texto-fraco">+${d.events.length + d.activities.length - 5}</small>` : ''}</button>`)}</div>
      <div class="cal-legenda" style="margin-top:12px"><span><i style="background:var(--tag-verde-bg);border:1px solid var(--verde)"></i>Dia de aula</span><span><i style="background:var(--tag-vermelho-bg)"></i>Feriado / recesso / sem aula</span>
        <span><i style="background:var(--tag-amarelo-bg)"></i>Prova</span><span><i style="background:var(--tag-azul-bg)"></i>Evento / reunião / aula extra</span><span><i style="background:var(--tag-cinza-bg)"></i>Prazo de atividade</span></div>
    </section>
    <section><div class="secao__topo"><h2>Neste mês</h2></div>${(() => {
      const evs = [];
      const vistos = new Set();
      c.days.forEach((d) => d.events.forEach((e) => { if (!vistos.has(e.id)) { vistos.add(e.id); evs.push(e); } }));
      return evs.length ? html`<div class="lista-itens">${evs.map((e) => html`<div class="item"><div class="item__info"><span class="cal__ev cal__ev--${e.kind}" style="white-space:normal">${e.kind_label}</span>
        <div><strong>${e.title}</strong><small>${fmtDate(e.date)}${e.end_date ? ' a ' + fmtDate(e.end_date) : ''} · ${e.class_name || 'Toda a escola'}${e.description ? ' · ' + e.description : ''}</small></div></div>
        ${podeEditar && (gestao || e.created_by === S.user.id) ? html`<div class="acoes-icone"><button class="btn btn--link" data-editar-ev="${e.id}">Editar</button><button class="btn btn--link texto-vermelho" data-excluir-ev="${e.id}">Excluir</button></div>` : ''}</div>`)}</div>`
        : empty('Nenhum evento neste mês');
    })()}</section>`);
  el.querySelector('#turma')?.addEventListener('change', (e) => go(`${base}?mes=${c.month}${e.target.value ? '&turma=' + e.target.value : ''}`));
  const todos = new Map();
  c.days.forEach((d) => d.events.forEach((e) => todos.set(String(e.id), e)));
  el.querySelectorAll('[data-dia]').forEach((b) => {
    b.onclick = () => {
      const d = c.days.find((x) => x.date === b.dataset.dia);
      modal(fmtDate(d.date), html`<p>${d.class_day ? tag('ativo', 'Dia de aula') : tag('inativo', 'Sem aula')}</p>
        ${d.events.length ? html`<ul class="lista-simples">${d.events.map((e) => html`<li><span><strong>${e.title}</strong><br><span class="texto-fraco">${e.kind_label} · ${e.class_name || 'Toda a escola'}${e.description ? ' · ' + e.description : ''}</span></span></li>`)}</ul>` : ''}
        ${d.activities.length ? html`<h3 class="cartao__titulo" style="margin-top:12px">Prazos de atividades</h3><ul class="lista-simples">${d.activities.map((a) => html`<li><a href="${S.user.role === 'aluno' ? '#/a/atividade/' : '#/p/atividade/'}${a.id}">${a.title}</a><span class="texto-fraco">${a.subject_name}${a.class_name ? ' · ' + a.class_name : ''}</span></li>`)}</ul>` : ''}
        ${!d.events.length && !d.activities.length ? html`<p class="texto-fraco">Nada marcado neste dia.</p>` : ''}
        ${podeEditar ? html`<div class="linha linha--fim" style="margin-top:16px"><button class="btn btn--escuro" data-novo-dia>+ Marcar neste dia</button></div>` : ''}`, {
        onMount: (m, close) => m.querySelector('[data-novo-dia]')?.addEventListener('click', () => { close(); eventoModal(c, gestao, { date: d.date }); }),
      });
    };
  });
  el.querySelector('[data-evento]')?.addEventListener('click', () => eventoModal(c, gestao, q.turma ? { class_id: Number(q.turma) } : {}));
  el.querySelector('[data-periodos]')?.addEventListener('click', () => periodosModal(c));
  el.querySelectorAll('[data-editar-ev]').forEach((b) => { b.onclick = () => eventoModal(c, gestao, todos.get(b.dataset.editarEv)); });
  el.querySelectorAll('[data-excluir-ev]').forEach((b) => {
    b.onclick = async () => {
      if (!(await confirmar(`Excluir “${todos.get(b.dataset.excluirEv).title}” do calendário?`, { ok: 'Excluir', perigo: true }))) return;
      await api('/calendario/eventos/' + b.dataset.excluirEv, { method: 'DELETE' }); toast('Evento excluído'); go(location.hash);
    };
  });
}

function eventoModal(c, gestao, ev = {}) {
  const tipos = Object.entries(c.kinds).filter(([k]) => gestao || ['prova', 'evento', 'aula_extra'].includes(k));
  modal(ev.id ? 'Editar evento' : 'Novo evento no calendário', html`<form id="f">
    <div class="campos-2"><label class="campo"><span>Tipo</span><select class="entrada" name="kind">${tipos.map(([k, v]) => html`<option value="${k}" ${k === (ev.kind || (gestao ? 'feriado' : 'prova')) ? 'selected' : ''}>${v}</option>`)}</select></label>
    <label class="campo"><span>Para</span><select class="entrada" name="class_id">${gestao ? html`<option value="">Toda a escola</option>` : ''}${c.classes.map((t) => html`<option value="${t.id}" ${t.id === ev.class_id ? 'selected' : ''}>${t.name}</option>`)}</select></label></div>
    <label class="campo"><span>Título</span><input class="entrada" name="title" required maxlength="150" value="${ev.title || ''}" placeholder="Ex.: Proclamação da República"></label>
    <div class="campos-2"><label class="campo"><span>Data</span><input class="entrada" type="date" name="date" required value="${ev.date || ''}"></label>
    <label class="campo"><span>Até (opcional, para períodos)</span><input class="entrada" type="date" name="end_date" value="${ev.end_date || ''}"></label></div>
    <label class="campo"><span>Detalhes (opcional)</span><textarea class="entrada" name="description" maxlength="1000">${ev.description || ''}</textarea></label>
    ${ev.id ? '' : html`<label class="check"><input type="checkbox" name="notify" checked> Avisar alunos e professores envolvidos</label>`}
    ${aviso('Feriados, recessos e “sem aula” tiram a aula dos dias marcados. “Aula extra / reposição” cria aula mesmo em sábado ou domingo.')}
    <div class="linha linha--fim"><button type="button" class="btn btn--contorno" data-fechar>Cancelar</button><button class="btn btn--primario">Salvar</button></div></form>`, {
    onMount: (m, close) => m.querySelector('#f').addEventListener('submit', (e) => {
      e.preventDefault();
      const d = formData(e.target);
      const body = { ...d, class_id: d.class_id ? Number(d.class_id) : null, end_date: d.end_date || null, notify: ev.id ? false : !!d.notify };
      busy(m.querySelector('.btn--primario'), async () => {
        await api('/calendario/eventos' + (ev.id ? '/' + ev.id : ''), { method: ev.id ? 'PUT' : 'POST', body });
        close(); toast('Calendário atualizado'); go(location.hash);
      });
    }),
  });
}

function periodosModal(c) {
  const DIAS = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo'];
  const form = (t = {}) => html`<form class="pilha" data-periodo="${t.id || ''}">
    <div class="campos-2"><label class="campo"><span>Nome</span><input class="entrada" name="name" required value="${t.name || ''}" placeholder="Ex.: Ano letivo ${new Date().getFullYear()}"></label>
    <div class="campos-2"><label class="campo"><span>Início</span><input class="entrada" type="date" name="start_date" required value="${t.start_date || ''}"></label>
    <label class="campo"><span>Fim</span><input class="entrada" type="date" name="end_date" required value="${t.end_date || ''}"></label></div></div>
    <div class="linha" style="flex-wrap:wrap">${DIAS.map((d, i) => html`<label class="check"><input type="checkbox" data-wd="${i}" ${(t.weekdays || [0, 1, 2, 3, 4]).includes(i) ? 'checked' : ''}> ${d}</label>`)}</div>
    <div class="linha linha--fim">${t.id ? html`<button type="button" class="btn btn--link texto-vermelho" data-excluir-periodo="${t.id}">Excluir</button>` : ''}<button class="btn ${t.id ? 'btn--contorno' : 'btn--primario'}">${t.id ? 'Salvar alterações' : 'Adicionar período'}</button></div></form>`;
  modal('Períodos letivos e dias de aula', html`<p class="texto-suave">Cada período define as datas e os dias da semana em que há aula. Depois, marque feriados e recessos no calendário.</p>
    ${c.terms.map((t) => html`<section class="cartao" style="margin-bottom:12px">${form(t)}</section>`)}
    <section class="cartao"><h3 class="cartao__titulo">Novo período</h3>${form()}</section>`, {
    largo: true,
    onMount: (m, close) => {
      m.querySelectorAll('[data-periodo]').forEach((f) => f.addEventListener('submit', (e) => {
        e.preventDefault();
        const d = formData(f);
        const body = { name: d.name, start_date: d.start_date, end_date: d.end_date, weekdays: [...f.querySelectorAll('[data-wd]:checked')].map((x) => Number(x.dataset.wd)) };
        const tid = f.dataset.periodo;
        busy(f.querySelector('.btn:last-child'), async () => {
          await api('/calendario/periodos' + (tid ? '/' + tid : ''), { method: tid ? 'PUT' : 'POST', body });
          close(); toast('Período salvo'); go(location.hash);
        });
      }));
      m.querySelectorAll('[data-excluir-periodo]').forEach((b) => {
        b.onclick = async () => {
          if (!(await confirmar('Excluir este período letivo? Os dias deixam de aparecer como dias de aula.', { ok: 'Excluir', perigo: true }))) return;
          await api('/calendario/periodos/' + b.dataset.excluirPeriodo, { method: 'DELETE' }); close(); go(location.hash);
        };
      });
    },
  });
}

route('calendario', (_, q) => (S.user.role === 'gestor' ? go('#/g/calendario') : telaCalendario(q, false)));
route('g/calendario', (_, q) => telaCalendario(q, true), { role: 'gestor' });

/* ================================================================ disciplinas e professores (gestão) */
route('g/disciplinas', async (_, q) => {
  page(loading());
  const [subs, classes, profs] = await Promise.all([api('/gestor/subjects'), api('/gestor/classes'), api('/gestor/users?role=professor')]);
  const ativos = profs.filter((p) => p.status === 'ativo');
  const turma = q.turma || '';
  const el = page(html`${header('Disciplinas e professores', 'A coordenação define quais disciplinas cada turma tem e qual professor dá cada uma. O professor só organiza os conteúdos.', html`<button class="btn btn--primario" data-nova>+ Nova disciplina</button>`)}
    ${!ativos.length ? aviso('Nenhum professor ativo. Convide professores em Usuários antes de criar disciplinas.', 'amarelo') : ''}
    <div class="filtros"><select class="entrada" id="turma" style="max-width:240px"><option value="">Todas as turmas</option>${classes.map((c) => html`<option value="${c.id}" ${String(c.id) === turma ? 'selected' : ''}>${c.name}</option>`)}</select></div>
    ${(() => {
      const l = subs.filter((s) => !turma || String(s.class_id) === turma);
      return l.length ? html`<div class="tabela-caixa"><table class="tabela"><thead><tr><th>Turma</th><th>Disciplina</th><th>Professor</th><th>Situação</th><th>Publicados</th><th>Atividades</th><th></th></tr></thead><tbody>
        ${l.map((s) => html`<tr><td>${s.class_name}</td><td><strong style="font-weight:600">${s.name}</strong></td><td>${s.teacher}</td><td>${s.active ? tag('ativo', 'Ativa') : tag('inativo', 'Desativada')}</td>
          <td>${s.published}</td><td>${s.activities}</td><td><button class="btn btn--contorno btn--p" data-editar="${s.id}">Editar</button></td></tr>`)}</tbody></table></div>`
        : empty('Nenhuma disciplina', 'Crie a primeira disciplina e escolha o professor.');
    })()}`);
  el.querySelector('#turma').onchange = (e) => go('#/g/disciplinas' + (e.target.value ? '?turma=' + e.target.value : ''));
  const form = (s) => modal(s ? 'Editar disciplina' : 'Nova disciplina', html`<form id="f">
    <label class="campo"><span>Disciplina</span><input class="entrada" name="name" required value="${s?.name || ''}" placeholder="Ex.: Matemática"></label>
    <div class="campos-2"><label class="campo"><span>Turma</span><select class="entrada" name="class_id">${classes.map((c) => html`<option value="${c.id}" ${c.id === (s?.class_id ?? Number(turma)) ? 'selected' : ''}>${c.name}</option>`)}</select></label>
    <label class="campo"><span>Professor responsável</span><select class="entrada" name="teacher_id">${ativos.map((p) => html`<option value="${p.id}" ${p.id === s?.teacher_id ? 'selected' : ''}>${p.name}</option>`)}</select></label></div>
    ${s ? html`<label class="check"><input type="checkbox" name="active" ${s.active ? 'checked' : ''}> Disciplina ativa (desativada: some para os alunos, mas o histórico fica)</label>
      ${aviso('Ao trocar o professor, os materiais, atividades e jogos da disciplina passam para o novo professor. Os dois são avisados.')}` : ''}
    <div class="linha linha--entre">${s ? html`<button type="button" class="btn btn--perigo" data-excluir>Excluir</button>` : html`<span></span>`}<button class="btn btn--primario">Salvar</button></div></form>`, {
    onMount: (m, close) => {
      m.querySelector('#f').addEventListener('submit', (e) => {
        e.preventDefault();
        const d = formData(e.target);
        const body = { name: d.name, class_id: Number(d.class_id), teacher_id: Number(d.teacher_id), active: s ? !!d.active : true };
        busy(m.querySelector('.btn--primario'), async () => {
          await api('/gestor/subjects' + (s ? '/' + s.id : ''), { method: s ? 'PUT' : 'POST', body });
          close(); toast('Disciplina salva'); go(location.hash);
        });
      });
      m.querySelector('[data-excluir]')?.addEventListener('click', async () => {
        try { await api('/gestor/subjects/' + s.id, { method: 'DELETE' }); close(); toast('Disciplina excluída'); go(location.hash); } catch (err) { toast(err.message, 'erro'); }
      });
    },
  });
  el.querySelector('[data-nova]').onclick = () => (ativos.length ? form() : toast('Convide professores primeiro', 'erro'));
  el.querySelectorAll('[data-editar]').forEach((b) => { b.onclick = () => form(subs.find((s) => String(s.id) === b.dataset.editar)); });
}, { role: 'gestor' });
