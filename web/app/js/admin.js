/* EDU.AI – administração geral da plataforma (acima das instituições)
   Painel, instituições, faturas das mensalidades, chamados das escolas, administradores e IA própria. */
import {
  S, api, aviso, bars, busy, confirmar, empty, fmtDate, formData, go, header, homeOf, html, icon, kpi, loading, modal, pad2, page,
  refreshIaStatus, resetShell, route, segmented, bindSeg, setSession, tag, toast,
} from './core.js';

const R = { role: 'superadmin' };
const PAPEL = { professor: 'Professor', aluno: 'Aluno', gestor: 'Gestor', secretaria: 'Secretaria' };
const BRL = (v) => Number(v || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
const SIT = { aberta: ['amarelo', 'Em aberto'], paga: ['verde', 'Paga'], vencida: ['vermelho', 'Vencida'], cancelada: ['cinza', 'Cancelada'] };
const sitTag = (f) => { const [c, t] = SIT[f.situacao || f.status] || ['cinza', f.status]; return html`<span class="tag tag--${c}">${t}</span>`; };
const mesAtual = () => new Date().toISOString().slice(0, 7);
const mesNome = (ref) => { const [a, m] = ref.split('-'); return new Date(a, m - 1, 1).toLocaleDateString('pt-BR', { month: 'short', year: '2-digit' }); };
const TIPOS = ['Escola', 'Curso profissionalizante', 'Preparatório', 'Faculdade'];

/** Entra na conta de outro usuário para dar suporte (fica registrado na auditoria). */
export async function acessarComo(u) {
  if (!(await confirmar(`Acessar a plataforma como ${u.name} (${PAPEL[u.role]} · ${u.institution})? Tudo o que você fizer ficará registrado na auditoria da instituição.`, { ok: 'Acessar' }))) return;
  const r = await api(`/plataforma/acessar/${u.id}`, { method: 'POST' });
  setSession(r.token, r.user);
  resetShell();
  go(homeOf(r.user.role));
}

const tabelaUsuarios = (lista, comInstituicao) => (lista.length ? html`<div class="tabela-caixa"><table class="tabela"><thead><tr><th>Nome</th><th>E-mail</th>${comInstituicao ? html`<th>Instituição</th>` : ''}<th>Papel</th><th>Status</th><th>Último acesso</th><th></th></tr></thead><tbody>
  ${lista.map((u) => html`<tr><td><strong style="font-weight:600">${u.name}</strong></td><td>${u.email}</td>
    ${comInstituicao ? html`<td><a href="#/admin/instituicao/${u.institution_id}">${u.institution}</a><div class="texto-fraco"><code>${u.slug}</code></div></td>` : ''}
    <td>${PAPEL[u.role] || u.role}</td><td>${tag(u.status)}</td><td>${fmtDate(u.last_login)}</td>
    <td>${u.status === 'ativo' ? html`<button class="btn btn--contorno btn--p" data-acessar="${u.id}">Acessar como</button>` : ''}</td></tr>`)}</tbody></table></div>`
  : empty('Nenhum usuário encontrado'));

function ligarAcessar(el, lista) {
  el.querySelectorAll('[data-acessar]').forEach((b) => {
    b.onclick = () => acessarComo(lista.find((u) => String(u.id) === b.dataset.acessar)).catch((e) => toast(e.message, 'erro'));
  });
}

/* ================================================================ painel */
route('admin/painel', async () => {
  page(loading());
  const [d, vencidas, pedidos, chamados] = await Promise.all([api('/plataforma/resumo'), api('/plataforma/faturas?status=vencida'),
    api('/plataforma/pedidos-plano'), api('/chamados')]);
  const k = d.kpis;
  const abertos = chamados.filter((t) => ['aberto', 'em_andamento'].includes(t.status));
  const el = page(html`${header(`Olá, ${S.user.name.split(' ')[0]}`, 'Visão geral da plataforma: clientes, receita, cobranças e suporte.',
    html`<a class="btn btn--contorno" href="#/admin/faturas">${icon('fatura', 16)} Faturas</a><a class="btn btn--primario" href="#/admin/nova-instituicao">+ Nova instituição</a>`)}
    <div class="grade grade-4">${kpi('Instituições ativas', pad2(k.ativas), `${k.instituicoes} cadastradas`)}${kpi('Receita mensal recorrente', BRL(k.mrr), 'soma dos planos ativos')}
      ${kpi('Recebido no mês', BRL(k.recebido_mes), 'faturas pagas', 'verde')}${kpi('Em aberto', BRL(k.em_aberto), k.vencidas ? `${k.vencidas} vencida(s): ${BRL(k.valor_vencido)}` : 'nenhuma vencida', k.vencidas ? 'vermelho' : 'verde')}</div>
    <div class="grade grade-4">${kpi('Usuários', pad2(k.usuarios), `${k.professores} professores · ${k.alunos} alunos`)}${kpi('Gerações de IA no mês', pad2(k.ia_mes))}
      ${kpi('Chamados abertos', pad2(k.chamados_abertos), 'das instituições', k.chamados_abertos ? 'vermelho' : '')}${kpi('Pedidos de plano', pad2(k.pedidos_plano), 'aguardando aprovação')}</div>
    <div class="grade grade-2">
      <section class="cartao"><h2 class="cartao__titulo">Receita por mês</h2>
        ${bars(d.receita_meses.slice().reverse().map((m) => ({ label: mesNome(m.mes), value: m.pago })), { max: 1, fmtV: (v) => (v >= 1000 ? `${(v / 1000).toLocaleString('pt-BR', { maximumFractionDigits: 1 })} mil` : BRL(v)) })}
        <p class="texto-fraco">Valores pagos por referência da fatura.</p></section>
      <section class="cartao"><div class="cartao__topo"><h2 class="cartao__titulo">Faturas vencidas</h2><a href="#/admin/faturas?status=vencida" class="link-sutil">Ver todas</a></div>
        ${vencidas.length ? html`<ul class="lista-simples">${vencidas.slice(0, 6).map((f) => html`<li><span><strong>${f.institution}</strong><br><span class="texto-fraco">${f.reference} · venceu ${fmtDate(f.due_date)}</span></span><strong class="texto-vermelho">${BRL(f.amount)}</strong></li>`)}</ul>`
    : empty('Nenhuma fatura vencida', 'Todas as cobranças estão em dia.')}</section>
    </div>
    <div class="grade grade-2">
      <section class="cartao"><div class="cartao__topo"><h2 class="cartao__titulo">Chamados abertos</h2><a href="#/admin/chamados" class="link-sutil">Ver fila</a></div>
        ${abertos.length ? html`<ul class="lista-simples">${abertos.slice(0, 6).map((t) => html`<li><a href="#/admin/chamado/${t.id}"><strong>${t.subject}</strong></a><span class="texto-fraco">${t.institution_name}</span></li>`)}</ul>` : empty('Nenhum chamado aberto')}</section>
      <section class="cartao"><h2 class="cartao__titulo">Pedidos de troca de plano</h2>
        ${pedidos.length ? html`<ul class="lista-simples">${pedidos.map((p) => html`<li><span><strong>${p.institution}</strong>: ${p.current_plan} → <strong>${p.plan}</strong><br><span class="texto-fraco">pedido por ${p.requester} em ${fmtDate(p.created_at)}</span></span>
          <span class="acoes-icone"><button class="btn btn--verde btn--p" data-aprovar="${p.id}">Aprovar</button><button class="btn btn--link texto-vermelho" data-recusar="${p.id}">Recusar</button></span></li>`)}</ul>` : empty('Nenhum pedido pendente')}</section>
    </div>`);
  ligarPedidos(el);
}, R);

function ligarPedidos(el) {
  el.querySelectorAll('[data-aprovar],[data-recusar]').forEach((b) => {
    b.onclick = async () => {
      const approve = !!b.dataset.aprovar;
      if (!(await confirmar(approve ? 'Aprovar a troca de plano? Confirme antes que a contratação foi feita.' : 'Recusar o pedido?', { ok: approve ? 'Aprovar' : 'Recusar', perigo: !approve }))) return;
      await api(`/plataforma/pedidos-plano/${b.dataset.aprovar || b.dataset.recusar}`, { method: 'POST', body: { approve } }); go(location.hash);
    };
  });
}

/* ================================================================ instituições */
route('admin/instituicoes', async (_, q) => {
  page(loading());
  const [d, pedidos] = await Promise.all([api('/plataforma/resumo'), api('/plataforma/pedidos-plano')]);
  const busca = (q.q || '').toLowerCase();
  const lista = d.instituicoes.filter((i) => !busca || (i.name + ' ' + i.slug).toLowerCase().includes(busca));
  const el = page(html`${header('Instituições', 'Escolas e cursos clientes da plataforma. Cadastre novas instituições aqui ou deixe que elas se cadastrem pela tela de login.',
    html`<a class="btn btn--primario" href="#/admin/nova-instituicao">+ Cadastrar instituição</a>`)}
    ${pedidos.length ? html`<section class="cartao"><h2 class="cartao__titulo">Pedidos de troca de plano (${pedidos.length})</h2><ul class="lista-simples">
      ${pedidos.map((p) => html`<li><span><strong>${p.institution}</strong>: ${p.current_plan} → <strong>${p.plan}</strong><br><span class="texto-fraco">pedido por ${p.requester} em ${fmtDate(p.created_at)}</span></span>
        <span class="acoes-icone"><button class="btn btn--verde btn--p" data-aprovar="${p.id}">Aprovar</button><button class="btn btn--link texto-vermelho" data-recusar="${p.id}">Recusar</button></span></li>`)}</ul></section>` : ''}
    <form class="filtros" id="fb"><input class="entrada entrada--busca" name="q" value="${q.q || ''}" placeholder="Buscar instituição…"><button class="btn btn--contorno">Buscar</button></form>
    ${lista.length ? html`<div class="tabela-caixa"><table class="tabela"><thead><tr><th>Instituição</th><th>Plano</th><th>Usuários</th><th>IA no mês</th><th>Em aberto</th><th>Último acesso</th><th>Status</th><th></th></tr></thead><tbody>
    ${lista.map((i) => html`<tr><td><a href="#/admin/instituicao/${i.id}"><strong>${i.name}</strong></a><div class="texto-fraco">código <code>${i.slug}</code> · desde ${fmtDate(i.created_at)}</div></td>
      <td>${i.plan}<div class="texto-fraco">${BRL(d.precos[i.plan])}/mês</div></td><td>${i.gestores + i.secretarias + i.professores + i.alunos}<div class="texto-fraco">${i.professores} prof. · ${i.alunos} alunos</div></td>
      <td>${i.ia_mes}</td><td>${i.em_aberto ? BRL(i.em_aberto) : '—'}${i.faturas_vencidas ? html` <span class="tag tag--vermelho">${i.faturas_vencidas} vencida(s)</span>` : ''}</td><td>${fmtDate(i.ultimo_acesso)}</td>
      <td>${i.active ? tag('ativo', 'Ativa') : tag('erro', 'Suspensa')}</td><td><button class="btn btn--contorno btn--p" data-editar="${i.id}">Editar</button></td></tr>`)}</tbody></table></div>`
    : empty('Nenhuma instituição encontrada')}`);
  ligarPedidos(el);
  el.querySelector('#fb').addEventListener('submit', (e) => { e.preventDefault(); go('#/admin/instituicoes?q=' + encodeURIComponent(e.target.q.value)); });
  el.querySelectorAll('[data-editar]').forEach((b) => { b.onclick = () => editarInstituicao(d.instituicoes.find((i) => String(i.id) === b.dataset.editar), d.planos); });
}, R);

route('admin/nova-instituicao', async () => {
  const d = await api('/plataforma/resumo');
  const el = page(html`<a href="#/admin/instituicoes" class="link-sutil">← Instituições</a>
    ${header('Cadastrar instituição', 'Crie a instituição e a conta do gestor. Depois, o gestor convida professores, secretaria e alunos.')}
    <form id="f" class="grade grade-2" style="align-items:start">
      <section class="cartao"><h2 class="cartao__titulo">${icon('predio', 16)} Dados da instituição</h2>
        <label class="campo"><span>Nome da instituição</span><input class="entrada" name="name" required placeholder="Ex.: Colégio Exemplo"></label>
        <div class="campos-2"><label class="campo"><span>CNPJ</span><input class="entrada" name="cnpj" placeholder="00.000.000/0001-00"></label>
        <label class="campo"><span>Tipo</span><select class="entrada" name="type">${TIPOS.map((t) => html`<option>${t}</option>`)}</select></label></div>
        <label class="campo"><span>Cor principal</span><input class="entrada" type="color" name="color" value="#172033" style="height:44px;padding:4px;max-width:160px"></label>
        <label class="campo"><span>Unidades (uma por linha)</span><textarea class="entrada" name="units" rows="2" placeholder="Unidade Centro"></textarea></label>
        <label class="campo"><span>Cursos ou segmentos (um por linha)</span><textarea class="entrada" name="courses" rows="3" placeholder="Ensino Fundamental II&#10;Ensino Médio"></textarea></label>
      </section>
      <div class="pilha">
        <section class="cartao"><h2 class="cartao__titulo">${icon('usuarios', 16)} Gestor da instituição</h2>
          <label class="campo"><span>Nome</span><input class="entrada" name="admin_name" required></label>
          <label class="campo"><span>E-mail</span><input class="entrada" type="email" name="admin_email" required></label>
          <label class="campo"><span>Senha inicial (vazio = gerar automaticamente)</span><input class="entrada" name="admin_password" minlength="8"></label></section>
        <section class="cartao"><h2 class="cartao__titulo">${icon('fatura', 16)} Plano e cobrança</h2>
          <div class="grade grade-3">${d.planos.map((p) => html`<label class="opcao" style="min-height:auto"><input type="radio" name="plan" value="${p}" ${p === 'Escola Pro' ? 'checked' : ''}><strong>${p}</strong><small>${BRL(d.precos[p])}/mês</small></label>`)}</div>
          <label class="check"><input type="checkbox" name="first_invoice" checked> Emitir já a fatura deste mês</label>
          <label class="campo"><span>Dia do vencimento</span><input class="entrada" type="number" name="due_day" min="1" max="28" value="10" style="max-width:120px"></label></section>
        <div class="linha linha--fim"><a class="btn btn--contorno" href="#/admin/instituicoes">Cancelar</a><button class="btn btn--primario" type="submit">Cadastrar instituição</button></div>
      </div></form>`);
  const f = el.querySelector('#f');
  f.addEventListener('submit', (e) => {
    e.preventDefault();
    busy(f.querySelector('[type=submit]'), async () => {
      const v = formData(f);
      const body = { ...v, plan: f.querySelector('[name=plan]:checked').value, units: v.units.split('\n'), courses: v.courses.split('\n'), due_day: v.due_day || 10 };
      const r = await api('/plataforma/instituicoes', { method: 'POST', body });
      modal('Instituição cadastrada', html`<p>Envie estes dados de acesso ao gestor da instituição:</p>
        <div class="tabela-caixa"><table class="tabela"><tbody><tr><td>Código da instituição</td><td><code>${r.slug}</code></td></tr>
        <tr><td>E-mail</td><td>${r.admin_email}</td></tr><tr><td>Senha</td><td><code>${r.admin_password}</code></td></tr></tbody></table></div>
        ${aviso('Peça para o gestor trocar a senha no primeiro acesso, em Configurações → Perfil.', 'amarelo')}
        <div class="linha linha--fim"><button class="btn btn--escuro" data-fechar>Abrir a instituição</button></div>`, { onClose: () => go('#/admin/instituicao/' + r.id) });
    });
  });
}, R);

function editarInstituicao(i, planos) {
  modal(`Editar ${i.name}`, html`<form id="f">
    <label class="campo"><span>Nome</span><input class="entrada" name="name" value="${i.name}" required></label>
    <label class="campo"><span>CNPJ</span><input class="entrada" name="cnpj" value="${i.cnpj || ''}"></label>
    <label class="campo"><span>Plano</span><select class="entrada" name="plan">${planos.map((p) => html`<option ${p === i.plan ? 'selected' : ''}>${p}</option>`)}</select></label>
    <label class="check"><input type="checkbox" name="active" ${i.active ? 'checked' : ''}> Instituição ativa (desmarque para suspender: ninguém dela consegue entrar)</label>
    <div class="linha linha--fim"><button type="button" class="btn btn--contorno" data-fechar>Cancelar</button><button class="btn btn--primario">Salvar</button></div></form>`, {
    onMount: (el, close) => el.querySelector('#f').addEventListener('submit', (e) => {
      e.preventDefault();
      busy(el.querySelector('.btn--primario'), async () => {
        await api('/plataforma/instituicoes/' + i.id, { method: 'PUT', body: formData(e.target) });
        close(); toast('Instituição atualizada'); go(location.hash);
      });
    }),
  });
}

route('admin/instituicao/:id', async ({ id }) => {
  page(loading());
  const [d, us, fats] = await Promise.all([api('/plataforma/resumo'), api('/plataforma/usuarios?institution_id=' + id), api('/plataforma/faturas?institution_id=' + id)]);
  const i = d.instituicoes.find((x) => String(x.id) === id);
  if (!i) return page(empty('Instituição não encontrada'));
  const el = page(html`<a href="#/admin/instituicoes" class="link-sutil">← Instituições</a>
    ${header(i.name, `Código ${i.slug} · plano ${i.plan} (${BRL(d.precos[i.plan])}/mês) · ${i.active ? 'ativa' : 'suspensa'}${i.cnpj ? ' · CNPJ ' + i.cnpj : ''}`,
    html`<button class="btn btn--contorno" data-editar>Editar</button><button class="btn btn--primario" data-fatura>+ Nova fatura</button>`)}
    <div class="grade grade-4">${kpi('Gestores', pad2(i.gestores))}${kpi('Professores', pad2(i.professores))}${kpi('Alunos', pad2(i.alunos))}${kpi('Em aberto', BRL(i.em_aberto), i.faturas_vencidas ? `${i.faturas_vencidas} vencida(s)` : '', i.faturas_vencidas ? 'vermelho' : '')}</div>
    <section class="cartao"><h2 class="cartao__titulo">Faturas</h2>${tabelaFaturas(fats, false)}</section>
    ${aviso('“Acessar como” abre a plataforma exatamente como esse usuário vê, para dar suporte ou configurar a instituição. Uma faixa no topo permite voltar ao administrador geral.')}
    ${tabelaUsuarios(us, false)}`);
  ligarAcessar(el, us);
  ligarFaturas(el, fats);
  el.querySelector('[data-editar]').onclick = () => editarInstituicao(i, d.planos);
  el.querySelector('[data-fatura]').onclick = () => novaFatura(d.instituicoes, i.id, d.precos);
}, R);

/* ================================================================ faturas */
const tabelaFaturas = (lista, comInstituicao = true) => (lista.length ? html`<div class="tabela-caixa"><table class="tabela"><thead><tr>${comInstituicao ? html`<th>Instituição</th>` : ''}<th>Referência</th><th>Descrição</th><th>Valor</th><th>Vencimento</th><th>Situação</th><th>Pagamento</th><th></th></tr></thead><tbody>
  ${lista.map((f) => html`<tr>${comInstituicao ? html`<td><a href="#/admin/instituicao/${f.institution_id}"><strong>${f.institution}</strong></a><div class="texto-fraco">${f.plan}</div></td>` : ''}
    <td>${f.reference}</td><td class="texto-fraco">${f.description || '—'}</td><td><strong>${BRL(f.amount)}</strong></td><td>${fmtDate(f.due_date)}</td><td>${sitTag(f)}</td>
    <td>${f.status === 'paga' ? html`${fmtDate(f.paid_at)}<div class="texto-fraco">${f.payment_method || ''}</div>` : '—'}</td>
    <td class="acoes-icone">${f.status === 'aberta' ? html`<button class="btn btn--verde btn--p" data-baixa="${f.id}">Dar baixa</button><button class="btn btn--link" data-editar-f="${f.id}">Editar</button><button class="btn btn--link texto-vermelho" data-cancelar-f="${f.id}">Cancelar</button>`
    : f.status === 'paga' ? html`<button class="btn btn--link" data-reabrir="${f.id}">Estornar</button>` : html`<button class="btn btn--link" data-reabrir="${f.id}">Reabrir</button>`}</td></tr>`)}</tbody></table></div>`
  : empty('Nenhuma fatura', 'Gere as mensalidades do mês ou crie uma fatura avulsa.'));

function ligarFaturas(el, lista) {
  const achar = (id) => lista.find((f) => String(f.id) === id);
  el.querySelectorAll('[data-baixa]').forEach((b) => {
    b.onclick = () => {
      const f = achar(b.dataset.baixa);
      modal(`Dar baixa: ${f.reference}`, html`<form id="fb"><p>${f.institution || ''} · <strong>${BRL(f.amount)}</strong></p>
        <div class="campos-2"><label class="campo"><span>Data do pagamento</span><input class="entrada" type="date" name="paid_at" value="${new Date().toISOString().slice(0, 10)}" required></label>
        <label class="campo"><span>Forma de pagamento</span><select class="entrada" name="payment_method">${['PIX', 'Boleto', 'Cartão de crédito', 'Transferência', 'Outro'].map((x) => html`<option>${x}</option>`)}</select></label></div>
        <label class="campo"><span>Observação (opcional)</span><input class="entrada" name="notes"></label>
        <div class="linha linha--fim"><button type="button" class="btn btn--contorno" data-fechar>Cancelar</button><button class="btn btn--verde">Confirmar pagamento</button></div></form>`, {
        onMount: (m, close) => m.querySelector('#fb').addEventListener('submit', (e) => {
          e.preventDefault();
          busy(m.querySelector('.btn--verde'), async () => {
            await api('/plataforma/faturas/' + f.id, { method: 'PUT', body: { ...formData(e.target), status: 'paga' } });
            close(); toast('Pagamento registrado'); go(location.hash);
          });
        }),
      });
    };
  });
  el.querySelectorAll('[data-editar-f]').forEach((b) => {
    b.onclick = () => {
      const f = achar(b.dataset.editarF);
      modal(`Editar fatura ${f.reference}`, html`<form id="fe"><div class="campos-2">
        <label class="campo"><span>Valor (R$)</span><input class="entrada" type="number" step="0.01" min="0" name="amount" value="${f.amount}" required></label>
        <label class="campo"><span>Vencimento</span><input class="entrada" type="date" name="due_date" value="${f.due_date}" required></label></div>
        <label class="campo"><span>Observação</span><input class="entrada" name="notes" value="${f.notes || ''}"></label>
        <div class="linha linha--fim"><button type="button" class="btn btn--contorno" data-fechar>Cancelar</button><button class="btn btn--primario">Salvar</button></div></form>`, {
        onMount: (m, close) => m.querySelector('#fe').addEventListener('submit', (e) => {
          e.preventDefault();
          busy(m.querySelector('.btn--primario'), async () => { await api('/plataforma/faturas/' + f.id, { method: 'PUT', body: formData(e.target) }); close(); go(location.hash); });
        }),
      });
    };
  });
  el.querySelectorAll('[data-cancelar-f],[data-reabrir]').forEach((b) => {
    b.onclick = async () => {
      const cancelar = !!b.dataset.cancelarF;
      if (!(await confirmar(cancelar ? 'Cancelar esta fatura? Ela deixa de aparecer para a instituição.' : 'Voltar a fatura para “em aberto”?', { ok: cancelar ? 'Cancelar fatura' : 'Reabrir', perigo: cancelar }))) return;
      await busy(b, async () => { await api('/plataforma/faturas/' + (b.dataset.cancelarF || b.dataset.reabrir), { method: 'PUT', body: { status: cancelar ? 'cancelada' : 'aberta' } }); go(location.hash); });
    };
  });
}

function novaFatura(instituicoes, fixa, precos) {
  modal('Nova fatura', html`<form id="fn">
    <label class="campo"><span>Instituição</span><select class="entrada" name="institution_id" ${fixa ? 'disabled' : ''}>${instituicoes.map((i) => html`<option value="${i.id}" ${i.id === fixa ? 'selected' : ''}>${i.name} (${i.plan})</option>`)}</select></label>
    <div class="campos-2"><label class="campo"><span>Referência (mês)</span><input class="entrada" type="month" name="reference" value="${mesAtual()}" required></label>
    <label class="campo"><span>Vencimento</span><input class="entrada" type="date" name="due_date" value="${mesAtual()}-10" required></label></div>
    <label class="campo"><span>Valor (R$) — vazio = preço do plano</span><input class="entrada" type="number" step="0.01" min="0" name="amount" data-valor></label>
    <label class="campo"><span>Descrição</span><input class="entrada" name="description" placeholder="Mensalidade, implantação, treinamento…"></label>
    <div class="linha linha--fim"><button type="button" class="btn btn--contorno" data-fechar>Cancelar</button><button class="btn btn--primario">Emitir fatura</button></div></form>`, {
    onMount: (m, close) => {
      const f = m.querySelector('#fn');
      const sugerir = () => { const i = instituicoes.find((x) => String(x.id) === f.institution_id.value); f.amount.placeholder = i ? String(precos[i.plan]) : ''; };
      f.institution_id.onchange = sugerir; sugerir();
      f.addEventListener('submit', (e) => {
        e.preventDefault();
        busy(m.querySelector('.btn--primario'), async () => {
          const v = formData(f);
          await api('/plataforma/faturas', { method: 'POST', body: { ...v, institution_id: Number(f.institution_id.value), amount: v.amount === null ? null : v.amount } });
          close(); toast('Fatura emitida e gestores avisados'); go(location.hash);
        });
      });
    },
  });
}

route('admin/faturas', async (_, q) => {
  page(loading());
  const filtro = { status: q.status || '', reference: q.mes || '', institution_id: q.inst || '' };
  const qs = new URLSearchParams(Object.entries(filtro).filter(([, v]) => v));
  const [lista, d] = await Promise.all([api('/plataforma/faturas?' + qs), api('/plataforma/resumo')]);
  const soma = (fn) => lista.filter(fn).reduce((s, f) => s + f.amount, 0);
  const el = page(html`${header('Faturas', 'Mensalidades da plataforma cobradas de cada instituição. Os gestores veem as faturas em Planos, uso e faturas e recebem um aviso a cada emissão.',
    html`<button class="btn btn--contorno" data-csv>Exportar CSV</button><button class="btn btn--contorno" data-avulsa>+ Fatura avulsa</button><button class="btn btn--primario" data-gerar>Gerar mensalidades do mês</button>`)}
    <div class="grade grade-4">${kpi('Total listado', BRL(soma(() => true)), `${lista.length} fatura(s)`)}${kpi('Pagas', BRL(soma((f) => f.status === 'paga')), '', 'verde')}
      ${kpi('Em aberto', BRL(soma((f) => f.situacao === 'aberta')))}${kpi('Vencidas', BRL(soma((f) => f.situacao === 'vencida')), `${lista.filter((f) => f.situacao === 'vencida').length} fatura(s)`, 'vermelho')}</div>
    <form class="filtros" id="ff">
      <select class="entrada" name="status" style="max-width:180px"><option value="">Todas as situações</option>${Object.entries(SIT).map(([k, [, t]]) => html`<option value="${k}" ${k === filtro.status ? 'selected' : ''}>${t}</option>`)}</select>
      <input class="entrada" type="month" name="mes" value="${filtro.reference}" style="max-width:180px" aria-label="Mês de referência">
      <select class="entrada" name="inst" style="max-width:260px"><option value="">Todas as instituições</option>${d.instituicoes.map((i) => html`<option value="${i.id}" ${String(i.id) === filtro.institution_id ? 'selected' : ''}>${i.name}</option>`)}</select>
      <button class="btn btn--contorno">Filtrar</button></form>
    ${tabelaFaturas(lista)}`);
  ligarFaturas(el, lista);
  el.querySelector('#ff').addEventListener('submit', (e) => {
    e.preventDefault();
    const v = new URLSearchParams(Object.entries(formData(e.target)).filter(([, x]) => x));
    go('#/admin/faturas?' + v);
  });
  el.querySelector('[data-avulsa]').onclick = () => novaFatura(d.instituicoes.filter((i) => i.active), null, d.precos);
  el.querySelector('[data-gerar]').onclick = () => modal('Gerar mensalidades do mês', html`<form id="fg">
    <p class="texto-suave">Emite uma fatura com o preço do plano para cada instituição ativa que ainda não tem fatura nesta referência. Os gestores recebem aviso na plataforma e por e-mail.</p>
    <div class="campos-2"><label class="campo"><span>Referência</span><input class="entrada" type="month" name="reference" value="${mesAtual()}" required></label>
    <label class="campo"><span>Dia do vencimento</span><input class="entrada" type="number" name="due_day" min="1" max="28" value="10" required></label></div>
    <div class="linha linha--fim"><button type="button" class="btn btn--contorno" data-fechar>Cancelar</button><button class="btn btn--primario">Gerar faturas</button></div></form>`, {
    onMount: (m, close) => m.querySelector('#fg').addEventListener('submit', (e) => {
      e.preventDefault();
      busy(m.querySelector('.btn--primario'), async () => {
        const r = await api('/plataforma/faturas/gerar-mes', { method: 'POST', body: formData(e.target) });
        close(); toast(`${r.criadas} fatura(s) emitida(s)${r.ja_existiam ? ` · ${r.ja_existiam} já existiam` : ''}`); go(location.hash);
      });
    }),
  });
  el.querySelector('[data-csv]').onclick = () => {
    const linhas = [['Instituição', 'Referência', 'Descrição', 'Valor', 'Vencimento', 'Situação', 'Pago em', 'Forma'],
      ...lista.map((f) => [f.institution, f.reference, f.description || '', String(f.amount).replace('.', ','), f.due_date, SIT[f.situacao][1], f.paid_at || '', f.payment_method || ''])];
    const csv = '﻿' + linhas.map((l) => l.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(';')).join('\n');
    const a = Object.assign(document.createElement('a'), { href: URL.createObjectURL(new Blob([csv], { type: 'text/csv' })), download: `faturas-${filtro.reference || 'todas'}.csv` });
    document.body.append(a); a.click(); a.remove();
  };
}, R);

/* ================================================================ administradores gerais */
route('admin/administradores', async () => {
  page(loading());
  const lista = await api('/plataforma/administradores');
  const el = page(html`${header('Administradores da plataforma', 'Pessoas com acesso total à administração geral: instituições, faturas, chamados e “acessar como”.', html`<button class="btn btn--primario" data-novo>+ Novo administrador</button>`)}
    ${aviso('Administradores gerais entram pela página exclusiva #/admin/login. Recomende a verificação em duas etapas (Meu perfil).', 'amarelo')}
    <div class="tabela-caixa"><table class="tabela"><thead><tr><th>Nome</th><th>E-mail</th><th>Duas etapas</th><th>Último acesso</th><th>Status</th><th></th></tr></thead><tbody>
    ${lista.map((a) => html`<tr><td><strong style="font-weight:600">${a.name}</strong>${a.id === S.user.id ? html` <span class="tag tag--azul">Você</span>` : ''}</td><td>${a.email}</td>
      <td>${a.two_factor ? tag('ativo', 'Ativada') : tag('inativo', 'Desativada')}</td><td>${fmtDate(a.last_login)}</td><td>${tag(a.status)}</td>
      <td>${a.id === S.user.id ? '' : a.status === 'ativo' ? html`<button class="btn btn--link texto-vermelho" data-st="inativo" data-id="${a.id}">Desativar</button>` : html`<button class="btn btn--link" data-st="ativo" data-id="${a.id}">Reativar</button>`}</td></tr>`)}</tbody></table></div>`);
  el.querySelectorAll('[data-st]').forEach((b) => {
    b.onclick = async () => {
      if (b.dataset.st === 'inativo' && !(await confirmar('Desativar este administrador? Ele perde o acesso na hora.', { ok: 'Desativar', perigo: true }))) return;
      await busy(b, async () => { await api('/plataforma/administradores/' + b.dataset.id, { method: 'PUT', body: { status: b.dataset.st } }); go(location.hash); });
    };
  });
  el.querySelector('[data-novo]').onclick = () => modal('Novo administrador geral', html`<form id="fa">
    <label class="campo"><span>Nome</span><input class="entrada" name="name" required></label>
    <label class="campo"><span>E-mail</span><input class="entrada" type="email" name="email" required></label>
    <label class="campo"><span>Senha inicial (mín. 10 caracteres; vazio = gerar)</span><input class="entrada" name="password" minlength="10"></label>
    ${aviso('O novo administrador terá acesso a todas as instituições e faturas.', 'amarelo')}
    <div class="linha linha--fim"><button type="button" class="btn btn--contorno" data-fechar>Cancelar</button><button class="btn btn--primario">Cadastrar</button></div></form>`, {
    onMount: (m, close) => m.querySelector('#fa').addEventListener('submit', (e) => {
      e.preventDefault();
      busy(m.querySelector('.btn--primario'), async () => {
        const r = await api('/plataforma/administradores', { method: 'POST', body: formData(e.target) });
        close();
        modal('Administrador cadastrado', html`<p>Envie os dados de acesso com segurança:</p>
          <div class="tabela-caixa"><table class="tabela"><tbody><tr><td>Endereço</td><td><code>${location.origin}${location.pathname}#/admin/login</code></td></tr>
          <tr><td>E-mail</td><td>${r.email}</td></tr><tr><td>Senha</td><td><code>${r.password}</code></td></tr></tbody></table></div>
          <div class="linha linha--fim"><button class="btn btn--escuro" data-fechar>Concluir</button></div>`, { onClose: () => go(location.hash) });
      });
    }),
  });
}, R);

/* ================================================================ busca de usuários em todas as instituições */
route('admin/usuarios', async (_, q) => {
  page(loading());
  const busca = q.q || '';
  const us = await api('/plataforma/usuarios?q=' + encodeURIComponent(busca));
  const el = page(html`${header('Todos os usuários', 'Busque em todas as instituições.')}
    <form class="filtros" id="f"><input class="entrada entrada--busca" name="q" value="${busca}" placeholder="Nome ou e-mail…"><button class="btn btn--contorno">Buscar</button></form>
    ${tabelaUsuarios(us, true)}`);
  el.querySelector('#f').addEventListener('submit', (e) => { e.preventDefault(); go('#/admin/usuarios?q=' + encodeURIComponent(e.target.q.value)); });
  ligarAcessar(el, us);
}, R);

/* ================================================================ IA própria do administrador */
route('admin/ia', async () => {
  page(loading());
  const [p, st] = await Promise.all([api('/me/ia'), api('/ia/status')]);
  const el = page(html`${header('Minha IA', 'Link e chave da API da IA em nuvem que VOCÊ usa no chat (independentes dos outros administradores e das instituições). Sem chave, você usa a IA local (Ollama).')}
    <div class="grade grade-lateral">
      <form class="cartao" id="f">
        <h2 class="cartao__titulo">${icon('link', 16)} IA em nuvem</h2>
        <label class="campo"><span>Link da API (formato “chat completions”)</span><input class="entrada" name="url" value="${p.url}" placeholder="https://api.openai.com/v1"></label>
        <label class="campo"><span>Chave da API ${p.key_masked ? html`<span class="texto-fraco">· atual: ${p.key_masked}</span>` : ''}</span><input class="entrada" name="key" type="password" autocomplete="off" placeholder="${p.key_masked ? 'Deixe vazio para manter a chave atual' : 'Cole a chave'}"></label>
        <label class="campo"><span>Modelo</span><input class="entrada" name="model" value="${p.model}" placeholder="Ex.: gpt-4o-mini, llama-3.1-70b, deepseek-chat"></label>
        <h2 class="cartao__titulo">${icon('robo', 16)} IA local (Ollama)</h2>
        <label class="campo"><span>Modelo local (vazio = padrão do servidor)</span><input class="entrada" name="local_model" value="${p.local_model}" placeholder="llama3.2"></label>
        <div class="campo"><span>Usar</span>${segmented('modo', [['', 'Automático'], ['nuvem', 'IA em nuvem'], ['local', 'IA local (Ollama)']], p.mode)}</div>
        <div class="linha linha--entre">${p.key_masked ? html`<button type="button" class="btn btn--link texto-vermelho" data-apagar>Apagar chave</button>` : html`<span></span>`}<button class="btn btn--primario" type="submit">Salvar</button></div>
      </form>
      <aside class="pilha"><section class="cartao"><h2 class="cartao__titulo">Situação</h2>
        <ul class="lista-simples"><li><span>Em uso</span><strong>${p.active === 'nuvem' ? 'IA em nuvem' : 'IA local'}</strong></li>
        <li><span>Conexão</span>${st.provider !== 'simulada' ? tag('publicado', 'Conectada') : tag('erro', 'Indisponível')}</li><li><span>Modelo</span><span>${st.model || '—'}</span></li></ul>
        <a class="btn btn--escuro btn--bloco" href="#/chat">${icon('robo', 16)} Abrir o chat com IA</a></section>
        ${aviso('A chave fica guardada no servidor e nunca é mostrada de novo — só os 4 últimos caracteres. Funciona com qualquer API compatível com “chat completions” (OpenAI, OpenRouter, Groq, DeepSeek, Mistral, Gemini compatível…).')}</aside>
    </div>`);
  const getModo = bindSeg(el, 'modo');
  el.querySelector('#f').addEventListener('submit', (e) => {
    e.preventDefault();
    busy(e.target.querySelector('[type=submit]'), async () => {
      await api('/me/ia', { method: 'PUT', body: { ...formData(e.target), mode: getModo() || '' } });
      toast('IA salva'); refreshIaStatus(); go(location.hash);
    });
  });
  el.querySelector('[data-apagar]')?.addEventListener('click', async () => {
    if (!(await confirmar('Apagar a sua chave da API?', { ok: 'Apagar', perigo: true }))) return;
    await api('/me/ia', { method: 'PUT', body: { mode: p.mode, key: '-' } }); refreshIaStatus(); go(location.hash);
  });
}, R);
