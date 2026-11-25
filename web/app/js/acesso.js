/* EDU.AI – acesso (L01–L07): login, onboarding, convite, perfil, notificações, ajuda e busca */
import {
  S, ago, api, aviso, busy, confirmar, effRole, fail, formData, go, header, homeOf, html, icon, initials, logo, logout, logoSvg, modal,
  page, query, refreshIaStatus, resetShell, route, segmented, bindSeg, setSession, tag, toast,
} from './core.js';

const marca = (titulo) => html`
  <section class="acesso__marca">
    ${logo('../index.html')}
    <h1>${titulo}</h1>
    <ul>
      <li>${icon('ia')} IA que gera resumos, mapas mentais e exercícios</li>
      <li>${icon('jogo')} Jogos ao vivo para engajar a turma</li>
      <li>${icon('grafico')} Indicadores para professores e gestores</li>
    </ul>
  </section>`;

function entrar(res) {
  setSession(res.token, res.user);
  resetShell();
  go(homeOf(effRole(res.user)));
}

/* ---------------------------------------------------------------- demonstração */
// Escola de teste criada pelo servidor (server/app/seed.py), separada das instituições reais.
const DEMO_INST = 'escola-teste';
const DEMO_SENHA = 'Teste@2026';
const DEMO = {
  professor: { label: 'Entrar como professora', email: 'professor@escolateste.edu.br' },
  aluno: { label: 'Entrar como aluna', email: 'aluno@escolateste.edu.br' },
  gestor: { label: 'Entrar como gestora', email: 'gestor@escolateste.edu.br' },
  secretaria: { label: 'Entrar como secretaria', email: 'secretaria@escolateste.edu.br' },
};

/** Login automático: #/demo/professor, #/demo/aluno, #/demo/gestor ou #/demo/secretaria. */
route('demo/:perfil', async ({ perfil }) => {
  const d = DEMO[perfil];
  if (!d) return go('#/login');
  page(html`<div class="carregando" style="min-height:100vh"><span class="spinner"></span> Entrando na demonstração…</div>`, { bare: true });
  try {
    entrar(await api('/auth/login', { method: 'POST', body: { institution: DEMO_INST, email: d.email, password: DEMO_SENHA } }));
  } catch (e) {
    toast('Demonstração indisponível: ' + e.message, 'erro');
    go('#/login');
  }
}, { public: true });

/* ---------------------------------------------------------------- L01 login */
route('login', async () => {
  if (S.user) return go(homeOf(effRole()));
  const lembrado = localStorage.getItem('edu_inst') || DEMO_INST;
  const el = page(html`<div class="acesso">
    ${marca('Do material do professor à aprendizagem de cada aluno.')}
    <section class="acesso__lado"><div class="acesso__caixa">
      <h1>Entrar na plataforma</h1>
      <p class="texto-suave">Use o e-mail cadastrado pela sua instituição.</p>
      <form id="f-login">
        <label class="campo"><span>Código da instituição</span><input class="entrada" name="institution" required value="${lembrado}" placeholder="ex.: escola-exemplo" autocomplete="organization"></label>
        <label class="campo"><span>E-mail</span><input class="entrada" name="email" type="email" required placeholder="nome@instituicao.edu.br" autocomplete="username"></label>
        <label class="campo"><span>Senha</span><input class="entrada" name="password" type="password" required placeholder="••••••••" autocomplete="current-password"></label>
        <div class="linha linha--entre"><label class="check"><input type="checkbox" checked> Manter conectado</label><a href="#" data-esqueci class="link-sutil">Esqueci minha senha</a></div>
        <button class="btn btn--primario btn--bloco btn--g" type="submit">Entrar</button>
      </form>
      <p class="link-sutil centro">Aluno com código da turma? <a href="#/entrar-turma">Criar conta com o código</a></p>
      <p class="link-sutil centro">Nova instituição? <a href="#/cadastro">Cadastre sua escola</a></p>
      <p class="link-sutil centro"><a href="#/admin/login">Acesso do administrador da plataforma</a></p>
      <div class="contas-demo"><strong>Experimente a demonstração</strong> — entra na hora, com dados de exemplo:
        <div class="linha" style="margin-top:8px">${Object.entries(DEMO).map(([k, d]) => html`<a class="btn btn--contorno btn--p" href="#/demo/${k}">${d.label}</a>`)}</div></div>
    </div></section></div>`, { bare: true });
  const f = el.querySelector('#f-login');
  f.addEventListener('submit', async (e) => {
    e.preventDefault();
    await busy(f.querySelector('button[type=submit]'), async () => {
      const d = formData(f);
      localStorage.setItem('edu_inst', d.institution);
      const r = await api('/auth/login', { method: 'POST', body: d });
      if (r.needs_2fa) return pedirCodigo(r.ticket);
      entrar(r);
    });
  });
  el.querySelector('[data-esqueci]').onclick = (e) => { e.preventDefault(); esqueciModal(f.institution.value, f.email.value); };
}, { public: true });

/* ---------------------------------------------------------------- login exclusivo do administrador geral */
route('admin/login', async () => {
  if (S.user) return go(homeOf(effRole()));
  const el = page(html`<div class="admin-login">
    <form class="admin-login__caixa" id="f-admin">
      <div class="linha"><span class="logo__marca">${logoSvg}</span><div><strong style="font-size:18px">EDU.AI</strong><div class="texto-fraco">Administração da plataforma</div></div></div>
      <h1>Acesso administrativo</h1>
      <p class="texto-suave">Área restrita aos administradores gerais da plataforma: instituições, faturas, chamados das escolas e administradores.</p>
      <label class="campo"><span>E-mail</span><input class="entrada" name="email" type="email" required autocomplete="username"></label>
      <label class="campo"><span>Senha</span><input class="entrada" name="password" type="password" required autocomplete="current-password"></label>
      <button class="btn btn--primario btn--bloco btn--g" type="submit">${icon('admin', 16)} Entrar como administrador</button>
      <p class="link-sutil centro"><a href="#/login">← Voltar ao login das instituições</a></p>
    </form></div>`, { bare: true });
  const f = el.querySelector('#f-admin');
  f.addEventListener('submit', (e) => {
    e.preventDefault();
    busy(f.querySelector('[type=submit]'), async () => {
      const r = await api('/auth/admin-login', { method: 'POST', body: formData(f) });
      if (r.needs_2fa) return pedirCodigo(r.ticket);
      entrar(r);
    });
  });
}, { public: true });

/** Segundo passo do login: código de 6 dígitos do app autenticador. */
function pedirCodigo(ticket) {
  modal('Verificação em duas etapas', html`<form id="f2">
    <p class="texto-suave">Abra o app autenticador no seu celular e digite o código de 6 dígitos da EDU.AI.</p>
    <label class="campo"><span>Código</span><input class="entrada" name="code" inputmode="numeric" autocomplete="one-time-code" pattern="[0-9 ]{6,7}" maxlength="7" required style="font-size:24px;letter-spacing:6px;text-align:center"></label>
    <p class="texto-fraco">Perdeu o celular? Peça à coordenação para redefinir a sua senha; a verificação em duas etapas precisa ser reconfigurada depois.</p>
    <button class="btn btn--primario btn--bloco">Entrar</button></form>`, {
    onMount: (el, close) => el.querySelector('#f2').addEventListener('submit', (e) => {
      e.preventDefault();
      busy(el.querySelector('.btn--primario'), async () => {
        const r = await api('/auth/2fa', { method: 'POST', body: { ticket, code: e.target.code.value } });
        close(); entrar(r);
      });
    }),
  });
}

function esqueciModal(institution, email) {
  modal('Esqueci minha senha', html`<form id="fe">
    <p class="texto-suave">Enviaremos um link para criar uma nova senha. Ele vale por 1 hora.</p>
    <label class="campo"><span>Código da instituição</span><input class="entrada" name="institution" required value="${institution || ''}"></label>
    <label class="campo"><span>E-mail</span><input class="entrada" type="email" name="email" required value="${email || ''}"></label>
    <button class="btn btn--primario btn--bloco">Enviar link</button></form>`, {
    onMount: (el, close) => el.querySelector('#fe').addEventListener('submit', (e) => {
      e.preventDefault();
      busy(el.querySelector('.btn--primario'), async () => {
        const r = await api('/auth/forgot', { method: 'POST', body: formData(e.target) });
        close();
        modal('Verifique o seu e-mail', html`<p>Se o e-mail estiver cadastrado, você vai receber o link em alguns minutos. Confira também a caixa de spam.</p>
          ${r.email_configured ? '' : aviso('Esta instalação ainda não tem envio de e-mail configurado. Se o link não chegar, peça à coordenação para redefinir a sua senha.', 'amarelo')}
          <div class="linha linha--fim"><button class="btn btn--escuro" data-fechar>Entendi</button></div>`);
      });
    }),
  });
}

route('redefinir-senha/:token', async ({ token }) => {
  const el = page(html`<div class="centralizado">${logo('../index.html')}
    <form class="cartao" style="width:min(440px,100%)" id="f">
      <h1 style="font-size:24px;font-weight:800">Criar nova senha</h1>
      <label class="campo"><span>Nova senha (mín. 8 caracteres)</span><input class="entrada" type="password" name="password" minlength="8" required autocomplete="new-password"></label>
      <label class="campo"><span>Confirmar senha</span><input class="entrada" type="password" name="confirm" minlength="8" required autocomplete="new-password"></label>
      <button class="btn btn--primario btn--bloco" type="submit">Salvar nova senha</button>
      <p class="link-sutil centro"><a href="#/login">Voltar ao login</a></p>
    </form></div>`, { bare: true });
  const f = el.querySelector('#f');
  f.addEventListener('submit', async (e) => {
    e.preventDefault();
    const d = formData(f);
    if (d.password !== d.confirm) return fail(new Error('As senhas não conferem'));
    await busy(f.querySelector('[type=submit]'), async () => {
      await api('/auth/reset', { method: 'POST', body: { token, password: d.password } });
      toast('Senha alterada. Entre com a nova senha.');
      go('#/login');
    });
  });
}, { public: true });

/* ---------------------------------------------------------------- L02 onboarding da instituição */
route('cadastro', async () => {
  const dados = { units: [], courses: [], invites: [], plan: 'Essencial', color: '#172033', type: 'Escola' };
  let passo = 1;
  const etapas = ['Dados da instituição', 'Unidades e cursos', 'Convidar equipe', 'Plano'];
  const render = () => {
    const el = page(html`<div class="centralizado">${logo('../index.html')}
      <div class="passos">${etapas.map((t, i) => html`${i ? html`<span class="passos__linha"></span>` : ''}<span class="passo ${i + 1 < passo ? 'passo--feito' : i + 1 === passo ? 'passo--atual' : ''}"><span class="passo__n">${i + 1}</span>${t}</span>`)}</div>
      <form class="cartao" style="width:min(640px,100%)" id="f">${corpo()}
        <div class="linha linha--entre" style="margin-top:20px"><button type="button" class="btn btn--contorno" data-voltar>${passo === 1 ? 'Cancelar' : 'Voltar'}</button><button class="btn btn--primario" type="submit">${passo === 4 ? 'Criar instituição' : 'Continuar'}</button></div>
      </form></div>`, { bare: true });
    const f = el.querySelector('#f');
    el.querySelector('[data-voltar]').onclick = () => { if (passo === 1) go('#/login'); else { salvar(f); passo--; render(); } };
    el.querySelectorAll('[data-plano]').forEach((b) => b.addEventListener('click', () => { dados.plan = b.dataset.plano; salvar(f); render(); }));
    f.addEventListener('submit', async (e) => {
      e.preventDefault();
      salvar(f);
      if (passo < 4) { passo++; render(); return; }
      await busy(f.querySelector('[type=submit]'), async () => {
        const r = await api('/onboarding', { method: 'POST', body: dados });
        localStorage.setItem('edu_inst', r.slug);
        toast(`Instituição criada! Código de acesso: ${r.slug}`);
        entrar(r);
      });
    });
  };
  const salvar = (f) => {
    const d = formData(f);
    if (passo === 1) Object.assign(dados, { name: d.name, cnpj: d.cnpj, type: d.type, color: d.color });
    if (passo === 2) { dados.units = d.units.split('\n').map((s) => s.trim()).filter(Boolean); dados.courses = d.courses.split('\n').map((s) => s.trim()).filter(Boolean); }
    if (passo === 3) {
      Object.assign(dados, { admin_name: d.admin_name, admin_email: d.admin_email, admin_password: d.admin_password });
      dados.invites = d.invites.split(/[\n,;]+/).map((s) => s.trim()).filter(Boolean).map((email) => ({ email, role: 'professor' }));
    }
  };
  const corpo = () => {
    if (passo === 1) return html`<h2 class="cartao__titulo" style="font-size:22px">Conte sobre a sua instituição</h2><p class="texto-suave">Essas informações personalizam a plataforma para professores e alunos.</p>
      <label class="campo"><span>Nome da instituição</span><input class="entrada" name="name" required value="${dados.name || ''}" placeholder="Ex.: Colégio Exemplo"></label>
      <div class="campos-2"><label class="campo"><span>CNPJ</span><input class="entrada" name="cnpj" value="${dados.cnpj || ''}" placeholder="00.000.000/0001-00"></label>
      <label class="campo"><span>Tipo de instituição</span><select class="entrada" name="type">${['Escola', 'Curso profissionalizante', 'Preparatório', 'Faculdade'].map((t) => html`<option ${t === dados.type ? 'selected' : ''}>${t}</option>`)}</select></label></div>
      <label class="campo"><span>Cor principal</span><input class="entrada" type="color" name="color" value="${dados.color}" style="height:44px;padding:4px"></label>`;
    if (passo === 2) return html`<h2 class="cartao__titulo" style="font-size:22px">Unidades e cursos</h2>
      <label class="campo"><span>Unidades (uma por linha)</span><textarea class="entrada" name="units" placeholder="Unidade Centro">${dados.units.join('\n')}</textarea></label>
      <label class="campo"><span>Cursos ou segmentos (um por linha)</span><textarea class="entrada" name="courses" placeholder="Ensino Fundamental II&#10;Ensino Médio">${dados.courses.join('\n')}</textarea></label>`;
    if (passo === 3) return html`<h2 class="cartao__titulo" style="font-size:22px">Sua conta e a equipe</h2>
      <div class="campos-2"><label class="campo"><span>Seu nome</span><input class="entrada" name="admin_name" required value="${dados.admin_name || ''}"></label>
      <label class="campo"><span>Seu e-mail</span><input class="entrada" type="email" name="admin_email" required value="${dados.admin_email || ''}"></label></div>
      <label class="campo"><span>Crie uma senha (mín. 8 caracteres)</span><input class="entrada" type="password" name="admin_password" minlength="8" required value="${dados.admin_password || ''}"></label>
      <label class="campo"><span>Convidar professores (e-mails separados por vírgula ou linha) — opcional</span><textarea class="entrada" name="invites">${dados.invites.map((i) => i.email).join('\n')}</textarea></label>`;
    return html`<h2 class="cartao__titulo" style="font-size:22px">Plano inicial</h2>
      <div class="grade grade-3">${[['Essencial', 'R$ 490/mês', 'até 300 alunos · 300 gerações de IA/mês'], ['Escola Pro', 'R$ 1.290/mês', 'até 1.500 alunos · 3.000 gerações/mês'], ['Rede', 'R$ 3.900/mês', 'até 15.000 alunos · 30.000 gerações/mês']].map(([n, p, d]) => html`
      <div class="opcao" style="${n === 'Essencial' ? 'border:2px solid var(--amarelo)' : ''}"><strong>${n}</strong><span style="font-size:18px;font-weight:800">${p}</span><small>${d}</small>${n === 'Essencial' ? html`<span class="tag tag--amarelo">Começa aqui</span>` : ''}</div>`)}</div>
      ${aviso('Toda instituição começa no plano Essencial. Para mudar de plano, peça em Planos e uso: a equipe da plataforma confirma a contratação e libera o novo limite.')}`;
  };
  render();
}, { public: true });

/* ---------------------------------------------------------------- L03 primeiro acesso por convite */
route('convite/:token', async ({ token }) => {
  let inv;
  try { inv = await api('/invites/' + token); } catch (e) {
    page(html`<div class="centralizado">${logo('../index.html')}<div class="cartao" style="width:min(480px,100%)">${aviso(e.message, 'vermelho')}<a class="btn btn--contorno" href="#/login">Ir para o login</a></div></div>`, { bare: true });
    return;
  }
  const papel = { professor: 'Professor', aluno: 'Aluno', gestor: 'Gestor', secretaria: 'Secretaria' }[inv.role];
  const el = page(html`<div class="centralizado">${logo('../index.html')}
    <form class="cartao" style="width:min(480px,100%)" id="f">
      <h1 style="font-size:24px;font-weight:800">Convite de ${inv.institution}</h1>
      <p>Você foi convidado como <strong>${papel}</strong></p>
      <p class="texto-suave">Crie sua senha para ativar a conta e acessar suas turmas.</p>
      <label class="campo"><span>Nome completo</span><input class="entrada" name="name" required value="${inv.name || ''}"></label>
      <label class="campo"><span>E-mail</span><input class="entrada" value="${inv.email}" disabled></label>
      <label class="campo"><span>Criar senha</span><input class="entrada" type="password" name="password" minlength="8" required></label>
      <label class="campo"><span>Confirmar senha</span><input class="entrada" type="password" name="confirm" minlength="8" required></label>
      <label class="check"><input type="checkbox" name="accept_terms" required> Li e aceito os Termos de Uso e a Política de Privacidade</label>
      <button class="btn btn--primario btn--bloco" type="submit">Ativar conta</button>
      <p class="texto-fraco centro">Instituição: <code>${inv.slug}</code> — use este código para entrar depois.</p>
    </form></div>`, { bare: true });
  const f = el.querySelector('#f');
  f.addEventListener('submit', async (e) => {
    e.preventDefault();
    const d = formData(f);
    if (d.password !== d.confirm) return fail(new Error('As senhas não conferem'));
    await busy(f.querySelector('[type=submit]'), async () => {
      localStorage.setItem('edu_inst', inv.slug);
      entrar(await api(`/invites/${token}/accept`, { method: 'POST', body: d }));
    });
  });
}, { public: true });

/* ---------------------------------------------------------------- aluno entra com código da turma */
route('entrar-turma', async () => {
  const el = page(html`<div class="centralizado">${logo('../index.html')}
    <form class="cartao" style="width:min(480px,100%)" id="f">
      <h1 style="font-size:24px;font-weight:800">Criar conta de aluno</h1>
      <p class="texto-suave">Use o código da turma informado pelo seu professor.</p>
      <div class="campos-2"><label class="campo"><span>Código da instituição</span><input class="entrada" name="institution" required value="${localStorage.getItem('edu_inst') || ''}"></label>
      <label class="campo"><span>Código da turma</span><input class="entrada" name="class_code" required placeholder="Ex.: MAT9B1" style="text-transform:uppercase"></label></div>
      <label class="campo"><span>Nome completo</span><input class="entrada" name="name" required></label>
      <label class="campo"><span>E-mail</span><input class="entrada" type="email" name="email" required></label>
      <label class="campo"><span>Senha (mín. 8 caracteres)</span><input class="entrada" type="password" name="password" minlength="8" required></label>
      <label class="check"><input type="checkbox" name="accept_terms" required> Li e aceito os Termos de Uso e a Política de Privacidade</label>
      <button class="btn btn--primario btn--bloco" type="submit">Criar conta</button>
      <p class="link-sutil centro"><a href="#/login">Já tenho conta</a></p>
    </form></div>`, { bare: true });
  const f = el.querySelector('#f');
  f.addEventListener('submit', async (e) => {
    e.preventDefault();
    await busy(f.querySelector('[type=submit]'), async () => entrar(await api('/auth/join-class', { method: 'POST', body: formData(f) })));
  });
}, { public: true });

/* ---------------------------------------------------------------- L05 perfil */
route('perfil', async () => {
  const u = await api('/me');
  const el = page(html`${header('Perfil e conta', 'Seus dados, segurança e privacidade')}
    <div class="grade grade-2">
      <form class="cartao" id="f-perfil">
        <div class="linha"><span class="avatar avatar--g">${initials(u.name)}</span><div><strong>${u.name}</strong><p class="texto-fraco">${u.institution.name} · código <code>${u.institution.slug}</code></p></div></div>
        <label class="campo"><span>Nome</span><input class="entrada" name="name" value="${u.name}" required></label>
        <label class="campo"><span>E-mail</span><input class="entrada" name="email" type="email" value="${u.email}" required></label>
        <label class="check"><input type="checkbox" name="weekly_email" ${u.weekly_email ? 'checked' : ''}> Receber resumo semanal por e-mail</label>
        <button class="btn btn--escuro" type="submit">Salvar</button>
      </form>
      <div class="pilha">
        <section class="cartao" id="pref-ia"><h2 class="cartao__titulo">${icon('robo', 16)} Inteligência artificial</h2><p class="texto-fraco">Carregando…</p></section>
        <section class="cartao"><div class="cartao__topo"><h2 class="cartao__titulo">Verificação em duas etapas</h2>${u.two_factor ? tag('ativo', 'Ativada') : tag('inativo', 'Desativada')}</div>
          <p class="texto-suave">Além da senha, o login pede um código do app autenticador do seu celular (Google Authenticator, Microsoft Authenticator, Authy…).</p>
          ${u.impersonated_by ? '' : u.two_factor ? html`<button class="btn btn--perigo btn--p" data-2fa-off>Desativar</button>` : html`<button class="btn btn--escuro btn--p" data-2fa-on>Ativar</button>`}</section>
        <form class="cartao" id="f-senha"><h2 class="cartao__titulo">Alterar senha</h2>
          <label class="campo"><span>Senha atual</span><input class="entrada" type="password" name="current" required></label>
          <label class="campo"><span>Nova senha</span><input class="entrada" type="password" name="new" minlength="8" required></label>
          <button class="btn btn--contorno" type="submit">Alterar senha</button></form>
        <section class="cartao"><h2 class="cartao__titulo">Privacidade (LGPD)</h2>
          <p class="texto-suave">Você pode pedir uma cópia, a correção ou a exclusão dos seus dados. A solicitação é analisada pelo responsável de privacidade da instituição.</p>
          <div class="linha"><button class="btn btn--contorno btn--p" data-lgpd="exportacao">Solicitar cópia</button><button class="btn btn--contorno btn--p" data-lgpd="correcao">Pedir correção</button><button class="btn btn--perigo btn--p" data-lgpd="exclusao">Pedir exclusão</button></div></section>
        <button class="btn btn--perigo" data-sair>Sair da conta</button>
      </div>
    </div>`);
  const fp = el.querySelector('#f-perfil');
  fp.addEventListener('submit', async (e) => {
    e.preventDefault();
    await busy(fp.querySelector('[type=submit]'), async () => { S.user = await api('/me', { method: 'PUT', body: formData(fp) }); resetShell(); toast('Perfil atualizado'); go('#/perfil'); });
  });
  const fs = el.querySelector('#f-senha');
  fs.addEventListener('submit', async (e) => {
    e.preventDefault();
    await busy(fs.querySelector('[type=submit]'), async () => {
      const r = await api('/me/password', { method: 'POST', body: formData(fs) });
      setSession(r.token, S.user || u); fs.reset(); toast('Senha alterada. Os outros aparelhos conectados foram desconectados.');
    });
  });
  el.querySelector('[data-2fa-on]')?.addEventListener('click', (e) => busy(e.currentTarget, async () => {
    const s = await api('/me/2fa/setup', { method: 'POST' });
    modal('Ativar verificação em duas etapas', html`<form id="f2">
      <ol class="pilha" style="padding-left:18px">
        <li>Instale um app autenticador no celular (Google Authenticator, Microsoft Authenticator ou Authy).</li>
        <li>No app, escolha <strong>“Inserir chave de configuração”</strong> e digite a chave abaixo (tipo: baseado em tempo).</li>
        <li>Digite o código de 6 dígitos que o app mostrar.</li></ol>
      <p class="codigo" style="font-size:18px;text-align:center;word-break:break-all;letter-spacing:2px">${s.secret.match(/.{1,4}/g).join(' ')}</p>
      <label class="campo"><span>Código do app</span><input class="entrada" name="code" inputmode="numeric" maxlength="7" required style="font-size:22px;letter-spacing:6px;text-align:center"></label>
      <button class="btn btn--primario btn--bloco">Confirmar e ativar</button></form>`, {
      onMount: (m, close) => m.querySelector('#f2').addEventListener('submit', (ev) => {
        ev.preventDefault();
        busy(m.querySelector('.btn--primario'), async () => {
          await api('/me/2fa/enable', { method: 'POST', body: { code: ev.target.code.value } });
          close(); toast('Verificação em duas etapas ativada'); go('#/perfil');
        });
      }),
    });
  }));
  el.querySelector('[data-2fa-off]')?.addEventListener('click', () => {
    modal('Desativar verificação em duas etapas', html`<form id="f3"><label class="campo"><span>Confirme a sua senha</span><input class="entrada" type="password" name="password" required></label>
      <button class="btn btn--perigo btn--bloco">Desativar</button></form>`, {
      onMount: (m, close) => m.querySelector('#f3').addEventListener('submit', (ev) => {
        ev.preventDefault();
        busy(m.querySelector('.btn--perigo'), async () => {
          await api('/me/2fa/disable', { method: 'POST', body: { password: ev.target.password.value } });
          close(); toast('Verificação em duas etapas desativada'); go('#/perfil');
        });
      }),
    });
  });
  el.querySelectorAll('[data-lgpd]').forEach((b) => b.addEventListener('click', () => busy(b, async () => {
    await api('/me/data-request', { method: 'POST', body: { kind: b.dataset.lgpd } });
    toast('Solicitação registrada. Você será notificado.');
  })));
  el.querySelector('[data-sair]').onclick = logout;
  if (!u.impersonated_by) prefIa(el.querySelector('#pref-ia'));
});

/** Preferência de IA do usuário: nuvem (API da instituição) ou local (Ollama). Também dá para trocar no chat. */
async function prefIa(box) {
  const p = await api('/me/ia');
  const admin = p.is_superadmin;
  box.innerHTML = html`<h2 class="cartao__titulo">${icon('robo', 16)} Inteligência artificial</h2>
    <p class="texto-suave">${admin ? 'Escolha entre a IA em nuvem (com a sua chave, em Minha IA) e a IA local (Ollama).'
    : 'A sua instituição define a IA em nuvem (link e chave da API). Você escolhe qual usar no chat, nos jogos e nas gerações:'}</p>
    ${segmented('modo', [['', 'Padrão'], ['nuvem', 'IA em nuvem'], ['local', 'IA local (Ollama)']], p.mode)}
    <p class="texto-fraco" data-ativa>Em uso agora: <strong>${p.active === 'nuvem' ? 'IA em nuvem' : 'IA local (Ollama)'}</strong>${p.cloud_ready ? '' : ' · a IA em nuvem ainda não foi configurada' + (admin ? ' (cadastre em Minha IA)' : ' pela instituição')}</p>`.s;
  bindSeg(box, 'modo', async (v) => {
    try {
      const r = await api('/me/ia', { method: 'PUT', body: { mode: v } });
      box.querySelector('[data-ativa]').innerHTML = html`Em uso agora: <strong>${r.active === 'nuvem' ? 'IA em nuvem' : 'IA local (Ollama)'}</strong>${!r.cloud_ready && v === 'nuvem' ? ' · a IA em nuvem não está configurada: usando a local' : ''}`.s;
      toast('Preferência de IA salva'); refreshIaStatus();
    } catch (e) { fail(e); }
  });
}

/* ---------------------------------------------------------------- L07 notificações */
route('notificacoes', async () => {
  const n = await api('/notifications?limit=100');
  const el = page(html`${header('Notificações', 'Avisos de processamento, publicações, prazos e jogos', html`<button class="btn btn--contorno" data-ler>Marcar todas como lidas</button>`)}
    <div class="lista-itens">${n.items.length ? n.items.map((x) => html`<a class="item" href="${x.link || '#/notificacoes'}" style="color:inherit;text-decoration:none">
      <div class="item__info"><span class="notificacao__icone" style="width:36px;height:36px">${icon('sino', 16)}</span><div><strong>${x.text}</strong><small>${ago(x.created_at)} · ${x.kind || ''}</small></div></div>
      ${x.read ? '' : tag('pendente', 'Novo')}</a>`) : html`<div class="vazio">Nenhuma notificação.</div>`}</div>`);
  el.querySelector('[data-ler]').onclick = async () => { await api('/notifications/read-all', { method: 'POST' }); resetShell(); go('#/notificacoes'); };
});

/* ---------------------------------------------------------------- L06 ajuda */
const FAQ = [
  ['Como a IA usa meus documentos?', 'Privacidade', 'O texto do documento é enviado ao modelo de IA configurado pela instituição (por padrão um modelo local via Ollama, que roda no próprio servidor da escola). O conteúdo não é usado para treinar modelos, e tudo o que a IA gera fica em rascunho até você revisar e publicar.'],
  ['Posso editar um material gerado?', 'Editor', 'Sim. Abra o material em Editor de materiais: dá para editar seções, cartões, questões e ramos do mapa, pedir para a IA reescrever só uma parte, voltar a versões anteriores e só então publicar.'],
  ['Como entrar em um jogo ao vivo?', 'Jogos', 'O professor abre a sala e mostra um código de 6 dígitos. No menu Jogos e desafios, digite o código e aguarde o início.'],
  ['Por que meu PDF ficou com erro?', 'Biblioteca', 'PDFs escaneados (imagem) não têm texto extraível. Envie a versão digital do arquivo, um DOCX, ou cole o texto diretamente no envio.'],
  ['Quem vê meus rascunhos?', 'Publicação', 'Só você. Os alunos veem apenas materiais publicados para as turmas que você escolher.'],
  ['Como funciona a correção das discursivas?', 'Atividades', 'As objetivas são corrigidas automaticamente. Para as discursivas, a IA sugere nota e comentário, mas a nota só é publicada depois que você valida.'],
  ['Como peço uma declaração ou o histórico escolar?', 'Atendimento', 'Em Atendimento, clique em “Novo chamado”, escolha “Solicitação de documento” e o tipo de documento. A escola responde pela plataforma e pode anexar o documento pronto. Você acompanha tudo pelo número de protocolo.'],
  ['Onde vejo os dias de aula e os feriados?', 'Calendário', 'No Calendário escolar: os dias com aula ficam destacados, e feriados, recessos, provas e eventos aparecem em cada dia, junto com os prazos das suas atividades.'],
  ['Esqueci a minha senha', 'Acesso', 'Na tela de login, clique em “Esqueci minha senha” e informe o código da instituição e o seu e-mail. Você recebe um link válido por 1 hora.'],
  ['Como instalar a IA (Ollama)?', 'Instalação', 'Instale o Ollama (ollama.com), rode "ollama pull llama3.2" e reinicie o servidor. O indicador "IA" no topo fica verde quando a conexão funciona.'],
  ['Como uso a IA em nuvem da escola?', 'IA', 'O gestor cadastra o link e a chave da API em Configurações → Inteligência artificial. Depois disso, todos da instituição podem alternar entre a IA em nuvem e a IA local (Ollama) no Chat com IA ou em Configurações → Perfil.'],
  ['O que é o Aprendizado gamificado?', 'Jogos', 'O aluno escolhe um material, cola um texto ou escreve um tema, e a IA monta jogos: memória, quiz relâmpago, verdadeiro ou falso, completar frases, adivinhar o conceito e desafios de programação. O professor acompanha as partidas e onde cada aluno errou.'],
  ['Como recebo uma declaração da secretaria?', 'Documentos', 'Peça em Atendimento → Solicitar documento. Quando a secretaria emitir, o documento aparece em Meus documentos, pronto para imprimir ou salvar em PDF, com um código de verificação.'],
];
route('ajuda', async () => {
  const el = page(html`${header('Central de ajuda', 'Guias, perguntas frequentes e contato com o suporte')}
    <input class="entrada" id="q" type="search" placeholder="Buscar na ajuda..." style="max-width:420px">
    <div class="grade grade-4">${[['Primeiros passos', 'casa'], ['Enviar conteúdos', 'upload'], ['Usar o Estúdio de IA', 'ia'], ['Jogos ao vivo', 'jogo']].map(([t, i]) => html`<div class="cartao"><span class="tipo-icone">${icon(i)}</span><h3>${t}</h3></div>`)}</div>
    <div class="tabela-caixa"><table class="tabela"><thead><tr><th>Pergunta</th><th>Tema</th></tr></thead><tbody id="faq">${FAQ.map(([p, t, r]) => html`<tr><td><details><summary style="cursor:pointer;font-weight:600">${p}</summary><p class="texto-suave" style="margin-top:8px">${r}</p></details></td><td><span class="tag tag--cinza">${t}</span></td></tr>`)}</tbody></table></div>
    ${['aluno', 'professor'].includes(S.user?.role) ? html`<section class="cartao"><h2 class="cartao__titulo">Precisa falar com a escola?</h2>
      <p class="texto-suave">Peça documentos (declarações, histórico, boletim), tire dúvidas com a secretaria ou a coordenação, faça reclamações, sugestões ou denúncias (que podem ser anônimas) pelo Atendimento.</p>
      <a class="btn btn--escuro" href="#/atendimento/novo">Abrir um chamado</a></section>` : ''}
    <section class="cartao"><h2 class="cartao__titulo">Falar com o suporte</h2><p class="texto-suave">E-mail: suporte@eduai.com.br · Atendimento em dias úteis, das 8h às 18h.</p></section>`);
  el.querySelector('#q').addEventListener('input', (e) => {
    const q = e.target.value.toLowerCase();
    el.querySelectorAll('#faq tr').forEach((tr) => { tr.hidden = q && !tr.textContent.toLowerCase().includes(q); });
  });
});

/* ---------------------------------------------------------------- busca global */
route('busca', async () => {
  const q = query().q || '';
  const r = q.length >= 2 ? await api('/search?q=' + encodeURIComponent(q)) : [];
  page(html`${header(`Resultados para “${q}”`, `${r.length} resultado(s)`)}
    <div class="lista-itens">${r.length ? r.map((x) => html`<a class="item" href="${x.link}" style="color:inherit;text-decoration:none"><div class="item__info"><span class="tag tag--cinza">${x.kind}</span><strong>${x.title}</strong></div></a>`) : html`<div class="vazio">Nada encontrado.</div>`}</div>`);
});
