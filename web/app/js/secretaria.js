/* EDU.AI – painel da secretaria escolar: alunos (foto e dados), carteirinhas e declarações automáticas.
   A fila de atendimento da secretaria fica em suporte.js (#/s/atendimento). O gestor também acessa. */
import {
  S, ago, api, aviso, busy, empty, fmtDate, formData, go, header, html, icon, initials, kpi, loading, page, pad2, route, tag, toast,
} from './core.js';

const R = { role: ['secretaria', 'gestor'] };
const nasc = (d) => (d ? d.split('-').reverse().join('/') : '—');
const verificarUrl = (code) => `${location.origin}${location.pathname}#/verificar/${code}`;

/** Recorta a foto no formato 3x4 e reduz (JPEG ~80 KB): pronta para a carteirinha. */
function prepararFoto(file) {
  return new Promise((resolve, reject) => {
    if (!file.type.startsWith('image/')) return reject(new Error('Escolha uma imagem (JPG, PNG ou WebP)'));
    const img = new Image();
    img.onload = () => {
      const alvoW = 480, alvoH = 640, razao = 3 / 4;
      let sw = img.width, sh = img.height, sx = 0, sy = 0;
      if (sw / sh > razao) { sw = sh * razao; sx = (img.width - sw) / 2; } else { sh = sw / razao; sy = Math.max(0, (img.height - sh) / 3); }
      const c = Object.assign(document.createElement('canvas'), { width: alvoW, height: alvoH });
      c.getContext('2d').drawImage(img, sx, sy, sw, sh, 0, 0, alvoW, alvoH);
      URL.revokeObjectURL(img.src);
      resolve(c.toDataURL('image/jpeg', 0.85));
    };
    img.onerror = () => reject(new Error('Não foi possível ler a imagem'));
    img.src = URL.createObjectURL(file);
  });
}

/* ================================================================ início */
route('s/painel', async () => {
  page(loading());
  const [r, fila] = await Promise.all([api('/secretaria/resumo'), api('/chamados')]);
  const abertos = fila.filter((t) => ['aberto', 'em_andamento'].includes(t.status) && t.target === 'secretaria');
  page(html`${header(S.user.role === 'gestor' ? 'Secretaria e documentos' : `Olá, ${S.user.name.split(' ')[0]}`, 'Atendimento de alunos e professores, cadastro, carteirinhas de estudante e declarações.',
    html`<a class="btn btn--contorno" href="#/s/carteirinhas">${icon('cracha', 16)} Carteirinhas</a><a class="btn btn--primario" href="#/s/declaracoes">${icon('carimbo', 16)} Nova declaração</a>`)}
    <div class="grade grade-4">${kpi('Chamados abertos', pad2(r.chamados_abertos), r.pedidos_documento ? `${r.pedidos_documento} pedido(s) de documento` : 'nenhum pedido de documento', r.chamados_abertos ? 'vermelho' : 'verde')}
      ${kpi('Alunos ativos', pad2(r.alunos))}${kpi('Alunos sem foto', pad2(r.sem_foto), 'necessária para a carteirinha', r.sem_foto ? 'amarelo' : 'verde')}${kpi('Documentos no mês', pad2(r.documentos_mes), 'declarações e carteirinhas')}</div>
    <div class="grade grade-2">
      <section class="cartao"><div class="cartao__topo"><h2 class="cartao__titulo">Fila de atendimento</h2><a class="link-sutil" href="#/s/atendimento">Ver todos</a></div>
        ${abertos.length ? html`<ul class="lista-simples">${abertos.slice(0, 8).map((t) => html`<li><a href="#/s/chamado/${t.id}"><strong>${t.subject}</strong></a><span class="texto-fraco">${t.requester} · ${ago(t.updated_at)}</span></li>`)}</ul>`
    : html`${empty('Nenhum chamado aberto', 'Tudo em dia por aqui.')}`}</section>
      <section class="cartao"><div class="cartao__topo"><h2 class="cartao__titulo">Últimos documentos emitidos</h2></div>
        ${r.ultimos.length ? html`<ul class="lista-simples">${r.ultimos.map((d) => html`<li><span>${d.kind === 'carteirinha' ? html`<strong>${d.title}</strong>` : html`<a href="#/s/documento/${d.id}"><strong>${d.title}</strong></a>`}<br><span class="texto-fraco">${d.student} · ${fmtDate(d.created_at)}</span></span><code>${d.code}</code></li>`)}</ul>`
    : empty('Nenhum documento emitido ainda')}</section>
    </div>
    <div class="grade grade-4">${[['#/s/atendimento', 'Atendimento', 'Responder alunos e professores', 'chat'], ['#/s/alunos', 'Alunos', 'Fotos, matrícula e documentos', 'turma'],
      ['#/s/carteirinhas', 'Carteirinhas', 'Gerar e imprimir por turma', 'cracha'], ['#/atendimento/novo?destino=gestao', 'Chamado à gestão', 'Pedidos para o gestor da escola', 'ajuda']]
      .map(([h, t, d, i]) => html`<a class="cartao" href="${h}" style="color:inherit;text-decoration:none"><span class="tipo-icone">${icon(i)}</span><h3 class="cartao__titulo">${t}</h3><p class="texto-fraco">${d}</p></a>`)}</div>`);
}, R);

/* ================================================================ alunos */
route('s/alunos', async (_, q) => {
  page(loading());
  const qs = new URLSearchParams();
  if (q.q) qs.set('q', q.q);
  if (q.turma) qs.set('class_id', q.turma);
  const [lista, turmas] = await Promise.all([api('/secretaria/alunos?' + qs), api('/secretaria/turmas')]);
  const el = page(html`${header('Alunos', 'Dados cadastrais usados nas carteirinhas e declarações: foto, matrícula, nascimento e documento.')}
    <form class="filtros" id="fb"><input class="entrada entrada--busca" name="q" value="${q.q || ''}" placeholder="Nome, e-mail ou matrícula…">
      <select class="entrada" name="turma" style="max-width:220px"><option value="">Todas as turmas</option>${turmas.map((t) => html`<option value="${t.id}" ${String(t.id) === q.turma ? 'selected' : ''}>${t.name} (${t.students})</option>`)}</select>
      <button class="btn btn--contorno">Filtrar</button><button type="button" class="btn btn--primario" data-cart disabled>${icon('cracha', 16)} Carteirinhas dos selecionados</button></form>
    ${lista.length ? html`<div class="tabela-caixa"><table class="tabela"><thead><tr><th><input type="checkbox" data-todos aria-label="Selecionar todos"></th><th>Aluno</th><th>Matrícula</th><th>Turma(s)</th><th>Nascimento</th><th>Foto</th><th></th></tr></thead><tbody>
      ${lista.map((a) => html`<tr><td><input type="checkbox" data-sel="${a.id}" aria-label="Selecionar ${a.name}"></td><td><strong style="font-weight:600">${a.name}</strong><div class="texto-fraco">${a.email}</div></td>
        <td>${a.registration || html`<span class="texto-fraco">automática</span>`}</td><td>${a.classes || '—'}</td><td>${nasc(a.birth_date)}</td>
        <td>${a.has_photo ? tag('publicado', 'Com foto') : tag('pendente', 'Sem foto')}</td><td><a class="btn btn--contorno btn--p" href="#/s/aluno/${a.id}">Ficha</a></td></tr>`)}</tbody></table></div>`
    : empty('Nenhum aluno encontrado')}`);
  el.querySelector('#fb').addEventListener('submit', (e) => {
    e.preventDefault();
    const v = new URLSearchParams(Object.entries(formData(e.target)).filter(([, x]) => x));
    go('#/s/alunos?' + v);
  });
  const btn = el.querySelector('[data-cart]');
  const sel = () => [...el.querySelectorAll('[data-sel]:checked')].map((c) => c.dataset.sel);
  el.querySelectorAll('[data-sel]').forEach((c) => { c.onchange = () => { btn.disabled = !sel().length; }; });
  el.querySelector('[data-todos]')?.addEventListener('change', (e) => { el.querySelectorAll('[data-sel]').forEach((c) => { c.checked = e.target.checked; }); btn.disabled = !sel().length; });
  btn.onclick = () => go('#/s/carteirinhas?alunos=' + sel().join(','));
}, R);

route('s/aluno/:id', async ({ id }) => {
  page(loading());
  const a = await api('/secretaria/alunos/' + id);
  const el = page(html`<a href="#/s/alunos" class="link-sutil">← Alunos</a>
    ${header(a.name, `${a.email}${a.classes.length ? ' · ' + a.classes.map((c) => c.name).join(', ') : ''}`,
    html`<a class="btn btn--contorno" href="#/s/carteirinhas?alunos=${a.id}">${icon('cracha', 16)} Carteirinha</a><a class="btn btn--primario" href="#/s/declaracoes?aluno=${a.id}">${icon('carimbo', 16)} Declaração</a>`)}
    <div class="grade grade-lateral-e">
      <section class="cartao centro-conteudo">
        <div class="foto-aluno" id="foto">${a.photo ? html`<img src="${a.photo}" alt="Foto de ${a.name}">` : html`<span>${initials(a.name)}</span>`}</div>
        <label class="btn btn--escuro btn--bloco" style="cursor:pointer">${icon('upload', 16)} ${a.photo ? 'Trocar foto' : 'Selecionar foto'}<input type="file" accept="image/*" hidden data-foto></label>
        <label class="btn btn--contorno btn--bloco" style="cursor:pointer">${icon('olho', 16)} Tirar foto (celular)<input type="file" accept="image/*" capture="user" hidden data-foto></label>
        ${a.photo ? html`<button class="btn btn--link texto-vermelho" data-sem-foto>Remover foto</button>` : ''}
        <p class="texto-fraco">A foto é recortada no formato 3x4 automaticamente.</p>
      </section>
      <div class="pilha">
        <form class="cartao" id="f"><h2 class="cartao__titulo">Dados para documentos</h2>
          <div class="campos-2"><label class="campo"><span>Número de matrícula</span><input class="entrada" name="registration" value="${a.registration || ''}" placeholder="Gerado automaticamente se vazio"></label>
          <label class="campo"><span>Data de nascimento</span><input class="entrada" type="date" name="birth_date" value="${a.birth_date || ''}"></label></div>
          <label class="campo"><span>Documento (RG ou CPF)</span><input class="entrada" name="document_id" value="${a.document_id || ''}"></label>
          <div class="linha linha--fim"><button class="btn btn--escuro" type="submit">Salvar dados</button></div></form>
        <section class="cartao"><h2 class="cartao__titulo">Turmas</h2>${a.classes.length ? html`<ul class="lista-simples">${a.classes.map((c) => html`<li><strong>${c.name}</strong><span class="texto-fraco">${c.course || c.grade || ''} · ${c.year}</span></li>`)}</ul>` : html`<p class="texto-fraco">Sem turma.</p>`}</section>
        <section class="cartao"><h2 class="cartao__titulo">Documentos emitidos</h2>
          ${a.documents.length ? html`<ul class="lista-simples">${a.documents.map((d) => html`<li><span>${d.kind === 'carteirinha' ? d.title : html`<a href="#/s/documento/${d.id}">${d.title}</a>`}<br><span class="texto-fraco">${fmtDate(d.created_at)}</span></span><code>${d.code}</code></li>`)}</ul>` : html`<p class="texto-fraco">Nenhum documento ainda.</p>`}</section>
      </div></div>`);
  el.querySelectorAll('[data-foto]').forEach((inp) => {
    inp.onchange = async () => {
      const file = inp.files[0];
      if (!file) return;
      try {
        const foto = await prepararFoto(file);
        await api(`/secretaria/alunos/${id}/foto`, { method: 'PUT', body: { photo: foto } });
        toast('Foto salva'); go(location.hash);
      } catch (e) { toast(e.message, 'erro'); }
    };
  });
  el.querySelector('[data-sem-foto]')?.addEventListener('click', async () => { await api(`/secretaria/alunos/${id}/foto`, { method: 'PUT', body: { photo: null } }); go(location.hash); });
  el.querySelector('#f').addEventListener('submit', (e) => {
    e.preventDefault();
    busy(e.target.querySelector('[type=submit]'), async () => { await api('/secretaria/alunos/' + id, { method: 'PUT', body: formData(e.target) }); toast('Dados salvos'); go(location.hash); });
  });
}, R);

/* ================================================================ carteirinhas */
const carteirinha = (inst, c) => html`<div class="carteirinha" style="--cor:${inst.color || '#172033'}">
  <div class="carteirinha__topo">${inst.logo ? html`<img src="${inst.logo}" alt="">` : html`<span class="carteirinha__marca">${inst.name[0]}</span>`}<div><strong>${inst.name}</strong><span>CARTEIRA DE ESTUDANTE</span></div></div>
  <div class="carteirinha__corpo">
    <div class="carteirinha__foto">${c.photo ? html`<img src="${c.photo}" alt="">` : html`<span>${initials(c.name)}</span>`}</div>
    <dl><dt>Nome</dt><dd class="carteirinha__nome">${c.name}</dd>${c.course ? html`<dd class="carteirinha__curso">${c.course}</dd>` : ''}
      <div class="carteirinha__linha"><div><dt>Matrícula</dt><dd>${c.registration}</dd></div><div><dt>Nascimento</dt><dd>${nasc(c.birth_date)}</dd></div></div>
      <div class="carteirinha__linha"><div><dt>Turma</dt><dd>${c.class_name || '—'}</dd></div><div><dt>Validade</dt><dd>${nasc(c.valid_until)}</dd></div></div></dl>
  </div>
  <div class="carteirinha__rodape"><span>${c.document_id ? 'Doc. ' + c.document_id : inst.cnpj ? 'CNPJ ' + inst.cnpj : ''}</span><span>Cód. ${c.code}</span></div>
</div>`;

route('s/carteirinhas', async (_, q) => {
  page(loading());
  const turmas = await api('/secretaria/turmas');
  const pre = q.alunos || q.aluno || '';
  const el = page(html`${header('Carteirinhas de estudante', 'Selecione a turma ou os alunos: nome, foto, matrícula, turma e validade são puxados do sistema. Imprima em papel A4 (10 por folha) ou cartão PVC.')}
    <form class="cartao nao-imprimir" id="f">
      <div class="campos-2"><label class="campo"><span>Turma</span><select class="entrada" name="turma"><option value="">${pre ? 'Alunos selecionados' : 'Escolha uma turma…'}</option>${turmas.map((t) => html`<option value="${t.id}">${t.name} (${t.students} alunos)</option>`)}</select></label>
      <label class="campo"><span>Validade</span><input class="entrada" type="date" name="valid_until" value="${new Date().getFullYear()}-12-31" required></label></div>
      <div id="alunos"></div>
      <div class="linha linha--fim"><button class="btn btn--primario" type="submit">${icon('cracha', 16)} Gerar carteirinhas</button></div></form>
    <div id="saida"></div>`);
  const f = el.querySelector('#f');
  const box = el.querySelector('#alunos');
  const carregar = async (turma, marcados) => {
    if (!turma && !marcados.length) { box.innerHTML = ''; return; }
    const lista = await api('/secretaria/alunos' + (turma ? '?class_id=' + turma : ''));
    const visiveis = turma ? lista : lista.filter((a) => marcados.includes(String(a.id)));
    box.innerHTML = html`<p class="texto-suave">${visiveis.length} aluno(s). Desmarque quem não precisa de carteirinha.</p>
      <div class="lista-alunos-cart">${visiveis.map((a) => html`<label class="check"><input type="checkbox" name="sid" value="${a.id}" checked> ${a.name} ${a.has_photo ? '' : html`<span class="tag tag--amarelo">sem foto</span>`}</label>`)}</div>`.s;
  };
  f.turma.onchange = () => carregar(f.turma.value, []);
  if (pre) carregar('', pre.split(','));
  f.addEventListener('submit', (e) => {
    e.preventDefault();
    const ids = [...f.querySelectorAll('[name=sid]:checked')].map((c) => Number(c.value));
    if (!ids.length) return toast('Escolha uma turma ou alunos', 'erro');
    busy(f.querySelector('[type=submit]'), async () => {
      const r = await api('/secretaria/carteirinhas', { method: 'POST', body: { student_ids: ids, valid_until: f.valid_until.value } });
      const semFoto = r.cards.filter((c) => !c.photo).length;
      el.querySelector('#saida').innerHTML = html`<div class="linha linha--entre nao-imprimir"><h2 class="cartao__titulo">${r.cards.length} carteirinha(s) prontas</h2><button class="btn btn--escuro" data-imprimir>Imprimir / salvar PDF</button></div>
        ${semFoto ? html`<div class="nao-imprimir">${aviso(`${semFoto} aluno(s) sem foto: envie a foto na ficha do aluno e gere de novo.`, 'amarelo')}</div>` : ''}
        <div class="folha-carteirinhas area-impressao">${r.cards.map((c) => carteirinha(r.institution, c))}</div>`.s;
      el.querySelector('[data-imprimir]').onclick = () => window.print();
      el.querySelector('#saida').scrollIntoView({ behavior: 'smooth' });
    });
  });
}, R);

/* ================================================================ declarações */
route('s/declaracoes', async (_, q) => {
  page(loading());
  const [modelos, alunos, docs] = await Promise.all([api('/secretaria/declaracoes/modelos'), api('/secretaria/alunos'), api('/secretaria/documentos')]);
  const chamado = q.chamado ? Number(q.chamado) : null;
  const el = page(html`${header('Declarações', 'Escolha o aluno e o modelo: o texto é montado com os dados do sistema. Revise, ajuste se precisar (ou peça para a IA redigir) e emita.')}
    ${chamado ? aviso(html`Emitindo a partir do chamado <a href="#/s/chamado/${chamado}">#${chamado}</a>: ao emitir, o chamado é respondido e marcado como resolvido.`) : ''}
    <div class="grade grade-2" style="align-items:start">
      <form class="cartao" id="f">
        <label class="campo"><span>Aluno</span><input class="entrada" list="lista-alunos" name="aluno_busca" placeholder="Digite o nome ou a matrícula…" autocomplete="off" required>
          <datalist id="lista-alunos">${alunos.map((a) => html`<option value="${a.name} · ${a.registration || 'mat. ' + a.id}" data-id="${a.id}">`)}</datalist></label>
        <label class="campo"><span>Modelo</span><select class="entrada" name="kind">${modelos.map((m) => html`<option value="${m.kind}">${m.title}</option>`)}</select></label>
        <label class="campo"><span>Finalidade (opcional)</span><input class="entrada" name="purpose" placeholder="Ex.: estágio, passe escolar, outro colégio"></label>
        <label class="campo"><span data-extra-label>Observação (opcional)</span><textarea class="entrada" name="extra" rows="2"></textarea></label>
        <div class="linha"><button type="button" class="btn btn--contorno" data-previa>Montar texto</button><button type="button" class="btn btn--contorno" data-ia>${icon('ia', 16)} Redigir com IA</button></div>
        <label class="campo"><span>Título</span><input class="entrada" name="title"></label>
        <label class="campo"><span>Texto da declaração (revise antes de emitir)</span><textarea class="entrada" name="body" rows="10" placeholder="Clique em “Montar texto”…"></textarea></label>
        <div class="linha linha--fim"><button class="btn btn--primario" type="submit">${icon('carimbo', 16)} Emitir declaração</button></div>
      </form>
      <section class="cartao"><h2 class="cartao__titulo">Emitidas recentemente</h2>
        ${docs.filter((d) => d.kind !== 'carteirinha').length ? html`<ul class="lista-simples">${docs.filter((d) => d.kind !== 'carteirinha').slice(0, 15).map((d) => html`<li><span><a href="#/s/documento/${d.id}"><strong>${d.title}</strong></a><br><span class="texto-fraco">${d.student} · ${fmtDate(d.created_at)} · por ${d.issued_by || '—'}</span></span><code>${d.code}</code></li>`)}</ul>`
    : empty('Nenhuma declaração emitida ainda')}</section>
    </div>`);
  const f = el.querySelector('#f');
  const idDoAluno = () => {
    const op = [...el.querySelectorAll('#lista-alunos option')].find((o) => o.value === f.aluno_busca.value);
    return op ? Number(op.dataset.id) : null;
  };
  if (q.aluno) {
    const a = alunos.find((x) => String(x.id) === q.aluno);
    if (a) f.aluno_busca.value = `${a.name} · ${a.registration || 'mat. ' + a.id}`;
  }
  const extraLabel = () => { el.querySelector('[data-extra-label]').textContent = modelos.find((m) => m.kind === f.kind.value)?.extra_label || 'Observação'; };
  f.kind.onchange = () => { extraLabel(); f.body.value = ''; f.title.value = ''; };
  extraLabel();
  const dados = () => {
    const sid = idDoAluno();
    if (!sid) throw new Error('Escolha um aluno da lista');
    return { student_id: sid, kind: f.kind.value, purpose: f.purpose.value, extra: f.extra.value, ticket_id: chamado };
  };
  el.querySelector('[data-previa]').onclick = (e) => busy(e.currentTarget, async () => {
    const r = await api('/secretaria/declaracoes/previa', { method: 'POST', body: dados() });
    f.title.value = r.title; f.body.value = r.body;
  });
  el.querySelector('[data-ia]').onclick = (e) => busy(e.currentTarget, async () => {
    const r = await api('/secretaria/declaracoes/redigir-ia', { method: 'POST', body: { ...dados(), body: f.body.value } });
    f.title.value = r.title; f.body.value = r.body;
    if (r.message) toast(r.message, 'erro'); else toast('Texto redigido pela IA: revise antes de emitir');
  });
  f.addEventListener('submit', (e) => {
    e.preventDefault();
    busy(f.querySelector('[type=submit]'), async () => {
      const r = await api('/secretaria/declaracoes', { method: 'POST', body: { ...dados(), title: f.title.value, body: f.body.value } });
      toast('Declaração emitida: o aluno já pode vê-la em Meus documentos');
      go('#/s/documento/' + r.id);
    });
  });
}, R);

/** Documento imprimível (timbre, texto, local e data, assinatura e código de verificação). */
const documentoView = (d, voltar) => html`<div class="nao-imprimir linha linha--entre"><a href="${voltar}" class="link-sutil">← Voltar</a><button class="btn btn--escuro" data-imprimir>Imprimir / salvar PDF</button></div>
  <article class="declaracao area-impressao">
    <header class="declaracao__timbre" style="border-color:${d.institution.color || '#172033'}">
      ${d.institution.logo ? html`<img src="${d.institution.logo}" alt="">` : ''}
      <div><strong>${d.institution.name}</strong>${d.institution.cnpj ? html`<span>CNPJ ${d.institution.cnpj}</span>` : ''}${d.institution.unit ? html`<span>${d.institution.unit}${d.institution.city ? ' · ' + d.institution.city : ''}</span>` : ''}</div>
    </header>
    <h1>${d.title.toUpperCase()}</h1>
    <div class="declaracao__texto">${d.body.split(/\n{2,}/).map((p) => html`<p>${p}</p>`)}</div>
    <p class="declaracao__data">${d.place_date}.</p>
    <div class="declaracao__assinatura"><span></span><strong>${d.signer || ' '}</strong><small>${d.signer_role}</small></div>
    <footer class="declaracao__rodape">Documento emitido pela plataforma EDU.AI · código de verificação <strong>${d.code}</strong> · confira em ${verificarUrl(d.code)}</footer>
  </article>`;

route('s/documento/:id', async ({ id }) => {
  page(loading());
  const d = await api('/secretaria/documentos/' + id);
  const el = page(documentoView(d, d.ticket_id ? '#/s/chamado/' + d.ticket_id : '#/s/declaracoes'));
  el.querySelector('[data-imprimir]').onclick = () => window.print();
}, R);

/* ================================================================ aluno: meus documentos */
route('documentos', async () => {
  page(loading());
  const lista = await api('/documentos/meus');
  page(html`${header('Meus documentos', 'Declarações emitidas pela secretaria. Abra para imprimir ou salvar em PDF.', html`<a class="btn btn--primario" href="#/atendimento/novo?destino=secretaria&categoria=documento">Pedir um documento</a>`)}
    ${lista.length ? html`<div class="lista-itens">${lista.map((d) => html`<a class="item" href="#/documentos/${d.id}" style="color:inherit;text-decoration:none">
      <div class="item__info"><span class="tipo-icone">${icon('carimbo')}</span><div><strong>${d.title}</strong><small>Emitida em ${fmtDate(d.created_at)} · código ${d.code}</small></div></div>${tag('publicado', 'Disponível')}</a>`)}</div>`
    : empty('Nenhum documento ainda', 'Peça declarações, histórico ou boletim pelo Atendimento.')}`);
});

route('documentos/:id', async ({ id }) => {
  page(loading());
  const d = await api('/documentos/meus/' + id);
  const el = page(documentoView(d, '#/documentos'));
  el.querySelector('[data-imprimir]').onclick = () => window.print();
});

/* ================================================================ verificação pública */
route('verificar/:code', async ({ code }) => {
  let d = null;
  try { d = await api('/documentos/verificar/' + encodeURIComponent(code)); } catch { /* inválido */ }
  page(html`<div class="centralizado"><div class="cartao" style="width:min(480px,100%)">
    <h1 style="font-size:22px;font-weight:800">Verificação de documento</h1>
    ${d ? html`${aviso(html`Documento <strong>autêntico</strong>, emitido pela plataforma EDU.AI.`, 'verde')}
      <ul class="lista-simples"><li><span>Documento</span><strong>${d.title}</strong></li><li><span>Instituição</span><strong>${d.institution}</strong></li>
      <li><span>Estudante</span><strong>${d.student}</strong></li><li><span>Emitido em</span><strong>${fmtDate(d.created_at)}</strong></li><li><span>Código</span><code>${code.toUpperCase()}</code></li></ul>`
    : aviso('Código não encontrado. Confira se foi digitado exatamente como está no documento.', 'vermelho')}
    <a class="btn btn--contorno" href="#/login">Ir para a plataforma</a></div></div>`, { bare: true });
}, { public: true });
