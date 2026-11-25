/* EDU.AI – núcleo da plataforma: API, sessão, roteador, layout e componentes */

export const S = { token: localStorage.getItem('edu_token'), user: null, cleanup: [] };

/* ---------------------------------------------------------------- HTML seguro */
class Raw { constructor(s) { this.s = s; } toString() { return this.s; } }
export const raw = (s) => new Raw(String(s ?? ''));
export const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
const fmt = (v) => (v == null || v === false ? '' : v instanceof Raw ? v.s : Array.isArray(v) ? v.map(fmt).join('') : esc(v));
/** Template com escape automático: html`<p>${texto}</p>` */
export function html(str, ...vals) {
  let out = str[0];
  vals.forEach((v, i) => { out += fmt(v) + str[i + 1]; });
  return new Raw(out);
}

/* ---------------------------------------------------------------- API */
export async function api(path, { method = 'GET', body, form } = {}) {
  const headers = {};
  if (S.token) headers.Authorization = 'Bearer ' + S.token;
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  const res = await fetch('/api' + path, { method, headers, body: form || (body !== undefined ? JSON.stringify(body) : undefined) });
  if (res.status === 401 && S.token) { logout(); throw new Error('Sessão expirada. Entre novamente.'); }
  const ct = res.headers.get('content-type') || '';
  const data = ct.includes('json') ? await res.json() : await res.blob();
  if (!res.ok) {
    const d = data && data.detail;
    throw new Error(Array.isArray(d) ? d.map((x) => x.msg).join('; ') : d || 'Erro ' + res.status);
  }
  return data;
}

export async function download(path, filename) {
  const blob = await api(path);
  const a = Object.assign(document.createElement('a'), { href: URL.createObjectURL(blob), download: filename });
  document.body.append(a); a.click(); a.remove();
}

export function setSession(token, user) {
  S.token = token; S.user = user;
  localStorage.setItem('edu_token', token);
}

export function logout() {
  const admin = S.user?.is_superadmin && !S.user?.impersonated_by;
  S.token = null; S.user = null;
  localStorage.removeItem('edu_token');
  go(admin ? '#/admin/login' : '#/login');
}

/* ---------------------------------------------------------------- formatação */
export const fmtDate = (s) => {
  if (!s) return '—';
  const d = new Date(s.length <= 10 ? s + 'T12:00:00' : s.replace(' ', 'T') + (s.includes('T') || s.includes('Z') ? '' : 'Z'));
  return isNaN(d) ? s : d.toLocaleDateString('pt-BR');
};
export const fmtDateTime = (s) => {
  if (!s) return '—';
  const d = new Date(s.replace(' ', 'T') + (s.includes('T') || s.includes('Z') ? '' : 'Z'));
  return isNaN(d) ? s : d.toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' });
};
export function ago(s) {
  if (!s) return '';
  const d = new Date(s.replace(' ', 'T') + (s.includes('Z') ? '' : 'Z'));
  const m = Math.round((Date.now() - d) / 60000);
  if (m < 1) return 'agora';
  if (m < 60) return `há ${m} min`;
  if (m < 1440) return `há ${Math.round(m / 60)} h`;
  if (m < 2880) return 'ontem';
  return fmtDate(s);
}
export function dueTag(s) {
  if (!s) return html`<span class="tag tag--cinza">Sem prazo</span>`;
  const days = Math.round((new Date(s + 'T23:59:59') - Date.now()) / 86400000);
  if (days < 0) return html`<span class="tag tag--cinza">Encerrou ${fmtDate(s)}</span>`;
  if (days === 0) return html`<span class="tag tag--vermelho">Hoje</span>`;
  if (days === 1) return html`<span class="tag tag--amarelo">Amanhã</span>`;
  return html`<span class="tag tag--azul">${fmtDate(s)}</span>`;
}
export const initials = (n) => (n || '?').split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0].toUpperCase()).join('');
export const pad2 = (n) => String(n ?? 0).padStart(2, '0');
export const nota = (v) => (v == null ? '—' : Number(v).toLocaleString('pt-BR', { maximumFractionDigits: 1 }));

export const TYPE_LABEL = { resumo: 'Resumo', mapa: 'Mapa mental', flashcards: 'Flashcards', exercicios: 'Exercícios', roteiro: 'Roteiro de revisão', glossario: 'Glossário' };
const STATUS = {
  rascunho: ['amarelo', 'Rascunho'], revisao: ['azul', 'Em revisão'], publicado: ['verde', 'Publicado'], arquivado: ['cinza', 'Arquivado'],
  enviado: ['cinza', 'Na fila'], processando: ['azul', 'Processando'], concluido: ['verde', 'Pronto'], erro: ['vermelho', 'Erro'],
  publicada: ['verde', 'Publicada'], encerrada: ['cinza', 'Encerrada'], pendente: ['amarelo', 'Pendente'],
  entregue: ['azul', 'Aguardando correção'], corrigida: ['verde', 'Corrigida'],
  ativo: ['verde', 'Ativo'], inativo: ['cinza', 'Inativo'], convidado: ['amarelo', 'Convidado'],
  sala: ['azul', 'Sala aberta'], pergunta: ['vermelho', 'Ao vivo'], discussao: ['vermelho', 'Ao vivo'], revelacao: ['vermelho', 'Ao vivo'], finalizado: ['cinza', 'Finalizado'],
  aberta: ['amarelo', 'Aberta'], concluida: ['verde', 'Concluída'], recusada: ['cinza', 'Recusada'],
};
export const tag = (status, label) => {
  const [cor, txt] = STATUS[status] || ['cinza', status];
  return html`<span class="tag tag--${cor}">${label || txt}</span>`;
};

/* ---------------------------------------------------------------- ícones (traço 2px, estilo do protótipo) */
const P = {
  casa: 'M3 10.5 12 3l9 7.5V21h-6v-6H9v6H3z', livro: 'M2 5h6a4 4 0 0 1 4 4v11a3 3 0 0 0-3-3H2zM22 5h-6a4 4 0 0 0-4 4v11a3 3 0 0 1 3-3h7z',
  turma: 'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75',
  pasta: 'M3 6a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z',
  baixar: 'M12 3v12M7 10l5 5 5-5M5 21h14',
  ia: 'M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9zM19 15l.9 2.1L22 18l-2.1.9L19 21l-.9-2.1L16 18l2.1-.9zM5 2l.6 1.4L7 4l-1.4.6L5 6l-.6-1.4L3 4l1.4-.6z',
  editar: 'M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z', questao: 'M9.1 9a3 3 0 0 1 5.8 1c0 2-3 3-3 3M12 17h.01M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20',
  tarefa: 'M9 11l3 3L22 4M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11', jogo: 'M6 12h4M8 10v4M15 13h.01M18 11h.01M17.3 5H6.7a4 4 0 0 0-4 3.6L2 15a3 3 0 0 0 5.1 2.2L9 15h6l1.9 2.2A3 3 0 0 0 22 15l-.7-6.4A4 4 0 0 0 17.3 5',
  grafico: 'M3 3v18h18M7 16v-5M12 16V8M17 16v-8', config: 'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1',
  cartas: 'M2 7a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2zM6 2h14a2 2 0 0 1 2 2v14',
  progresso: 'M22 12h-4l-3 9L9 3l-3 9H2', predio: 'M3 21h18M5 21V7l7-4 7 4v14M9 9h1M14 9h1M9 13h1M14 13h1M9 17h1M14 17h1',
  usuarios: 'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8M19 8v6M22 11h-6',
  conteudo: 'M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6M16 13H8M16 17H8M10 9H8',
  plano: 'M2 7h20v12H2zM2 11h20M6 15h4', escudo: 'M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10',
  sino: 'M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9M10.3 21a1.94 1.94 0 0 0 3.4 0', ajuda: 'M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20M9.1 9a3 3 0 0 1 5.8 1c0 2-3 3-3 3M12 17h.01',
  menu: 'M4 6h16M4 12h16M4 18h16', x: 'M18 6 6 18M6 6l12 12', mais: 'M12 5v14M5 12h14', upload: 'M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12',
  mapa: 'M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6M4 4h4v4H4zM16 4h4v4h-4zM4 16h4v4H4zM16 16h4v4h-4zM8 8l1.8 1.8M16 8l-1.8 1.8M8 16l1.8-1.8M16 16l-1.8-1.8',
  info: 'M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20M12 16v-4M12 8h.01', check: 'M20 6 9 17l-5-5', alerta: 'M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0M12 9v4M12 17h.01',
  lua: 'M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8', sol: 'M12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10M12 1v2M12 21v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M1 12h2M21 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4',
  chat: 'M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z', olho: 'M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6',
  glossario: 'M4 19.5A2.5 2.5 0 0 1 6.5 17H20V2H6.5A2.5 2.5 0 0 0 4 4.5zM4 19.5A2.5 2.5 0 0 0 6.5 22H20v-5M9 7h7M9 11h5',
  duplas: 'M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75M15 8h2',
  calendario: 'M5 4h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2zM16 2v4M8 2v4M3 10h18M8 14h.01M12 14h.01M16 14h.01M8 18h.01M12 18h.01',
  anexo: 'M21.4 11.1l-9.2 9.2a6 6 0 0 1-8.5-8.5l9.2-9.2a4 4 0 0 1 5.7 5.7l-9.2 9.2a2 2 0 0 1-2.8-2.8l8.5-8.5',
  trofeu: 'M8 21h8M12 17v4M7 4h10v5a5 5 0 0 1-10 0zM7 6H4a3 3 0 0 0 3 4M17 6h3a3 3 0 0 1-3 4',
  robo: 'M12 8V4M8 4h8M5 8h14a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2zM9 13h.01M15 13h.01M9 17h6',
  cracha: 'M3 5h18a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1zM8 13a2 2 0 1 0 0-4 2 2 0 0 0 0 4M5 17c.5-1.7 1.6-2.5 3-2.5s2.5.8 3 2.5M14 10h5M14 14h4',
  fatura: 'M6 2h12v20l-3-2-3 2-3-2-3 2zM9 7h6M9 11h6M9 15h4',
  carimbo: 'M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9zM14 3v6h6M9 15l2 2 4-4',
  chave: 'M21 2l-2 2m-7.6 7.6a5.5 5.5 0 1 1-7.8 7.8 5.5 5.5 0 0 1 7.8-7.8zm0 0L15.5 7.5m0 0 3 3L22 7l-3-3m-3.5 3.5L19 4',
  link: 'M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.7 1.7M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.7-1.7',
  admin: 'M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10zM9 12l2 2 4-4',
};
export const icon = (name, size = 18) => raw(`<svg aria-hidden="true" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="${P[name] || P.info}"/></svg>`);
const TYPE_ICON = { resumo: 'conteudo', mapa: 'mapa', flashcards: 'cartas', exercicios: 'tarefa', roteiro: 'progresso', glossario: 'glossario' };
export const typeIcon = (t) => html`<span class="tipo-icone tipo-icone--${t}" title="${TYPE_LABEL[t] || t}">${icon(TYPE_ICON[t] || 'conteudo')}</span>`;
export const logoSvg = raw('<svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#172033" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 5h6a4 4 0 0 1 4 4v11a3 3 0 0 0-3-3H2z"/><path d="M22 5h-6a4 4 0 0 0-4 4v11a3 3 0 0 1 3-3h7z"/></svg>');
export const logo = (href = '#/') => html`<a class="logo" href="${href}"><span class="logo__marca">${logoSvg}</span><span class="logo__textos"><span class="logo__nome">EDU.AI</span><span class="logo__sub">Plataforma de aprendizagem</span></span></a>`;

/* ---------------------------------------------------------------- menus por papel */
export const MENUS = {
  professor: ['Menu do professor', [
    ['#/p/inicio', 'Visão geral', 'casa'], ['#/p/disciplinas', 'Minhas disciplinas', 'livro'], ['#/p/turmas', 'Turmas e alunos', 'turma'],
    ['#/p/biblioteca', 'Biblioteca de conteúdos', 'pasta'], ['#/p/estudio', 'Estúdio de IA', 'ia'], ['#/p/materiais', 'Editor de materiais', 'editar'],
    ['#/p/questoes', 'Banco de questões', 'questao'], ['#/p/atividades', 'Atividades e avaliações', 'tarefa'], ['#/p/jogos', 'Jogos ao vivo', 'jogo'],
    ['#/aprender', 'Aprendizado gamificado', 'trofeu'], ['#/p/desempenho', 'Desempenho', 'grafico'], ['#/calendario', 'Calendário escolar', 'calendario'],
    ['#/chat', 'Chat com IA', 'robo'], ['#/atendimento', 'Atendimento', 'chat'], ['#/perfil', 'Configurações', 'config']]],
  aluno: ['Menu do aluno', [
    ['#/a/inicio', 'Início', 'casa'], ['#/a/materias', 'Minhas matérias', 'livro'], ['#/a/materiais', 'Materiais de estudo', 'conteudo'],
    ['#/a/flashcards', 'Flashcards e revisão', 'cartas'], ['#/a/atividades', 'Atividades', 'tarefa'], ['#/a/jogos', 'Jogos ao vivo', 'jogo'],
    ['#/aprender', 'Aprendizado gamificado', 'trofeu'], ['#/a/progresso', 'Meu progresso', 'progresso'], ['#/calendario', 'Calendário escolar', 'calendario'],
    ['#/chat', 'Chat com IA', 'robo'], ['#/documentos', 'Meus documentos', 'carimbo'],
    ['#/atendimento', 'Atendimento e secretaria', 'chat'], ['#/perfil', 'Configurações', 'config']]],
  secretaria: ['Secretaria escolar', [
    ['#/s/painel', 'Início', 'casa'], ['#/s/atendimento', 'Atendimento', 'chat'], ['#/s/alunos', 'Alunos', 'turma'],
    ['#/s/carteirinhas', 'Carteirinhas', 'cracha'], ['#/s/declaracoes', 'Declarações', 'carimbo'],
    ['#/atendimento', 'Chamados à gestão', 'ajuda'], ['#/calendario', 'Calendário escolar', 'calendario'],
    ['#/chat', 'Chat com IA', 'robo'], ['#/perfil', 'Configurações', 'config']]],
  gestor: ['Gestão da instituição', [
    ['#/g/dashboard', 'Dashboard', 'casa'], ['#/g/instituicao', 'Instituição', 'predio'], ['#/g/usuarios', 'Usuários', 'usuarios'],
    ['#/g/turmas', 'Cursos e turmas', 'turma'], ['#/g/disciplinas', 'Disciplinas e professores', 'livro'],
    ['#/g/calendario', 'Calendário escolar', 'calendario'], ['#/g/atendimento', 'Atendimento e ouvidoria', 'chat'],
    ['#/s/painel', 'Secretaria e documentos', 'carimbo'], ['#/g/conteudos', 'Conteúdos', 'conteudo'], ['#/g/relatorios', 'Relatórios', 'grafico'],
    ['#/g/planos', 'Planos, uso e faturas', 'plano'], ['#/g/configuracoes?aba=ia', 'Inteligência artificial', 'ia'],
    ['#/g/configuracoes', 'Configurações', 'config'], ['#/g/privacidade', 'Auditoria e privacidade', 'escudo'],
    ['#/chat', 'Chat com IA', 'robo'], ['#/g/suporte', 'Suporte da plataforma', 'ajuda']]],
  admin: ['Administração da plataforma', [
    ['#/admin/painel', 'Painel', 'casa'], ['#/admin/instituicoes', 'Instituições', 'predio'], ['#/admin/faturas', 'Faturas', 'fatura'],
    ['#/admin/chamados', 'Chamados das instituições', 'chat'], ['#/admin/administradores', 'Administradores', 'admin'],
    ['#/admin/usuarios', 'Todos os usuários', 'usuarios'], ['#/chat', 'Chat com IA', 'robo'], ['#/admin/ia', 'Minha IA (API)', 'chave'],
    ['#/perfil', 'Meu perfil', 'config']]],
};
const ROLE_LABEL = { professor: 'Professor', aluno: 'Aluno', gestor: 'Gestor', secretaria: 'Secretaria', admin: 'Administrador geral' };
/** Papel efetivo: o administrador geral (fora do "acessar como") tem um painel próprio. */
export const effRole = (u = S.user) => (u && u.is_superadmin && !u.impersonated_by ? 'admin' : u?.role);
export const homeOf = (role) => {
  if (role === 'gestor' && S.user?.is_superadmin && !S.user?.impersonated_by) return '#/admin/painel';
  return ({ professor: '#/p/inicio', aluno: '#/a/inicio', gestor: '#/g/dashboard', secretaria: '#/s/painel', admin: '#/admin/painel' })[role] || '#/login';
};
/* barra inferior do aluno no celular: os destinos mais usados ao alcance do polegar */
const NAV_INFERIOR = [['#/a/inicio', 'Início', 'casa'], ['#/a/materias', 'Matérias', 'livro'], ['#/a/flashcards', 'Revisar', 'cartas'],
  ['#/a/atividades', 'Atividades', 'tarefa'], ['#/a/jogos', 'Jogos', 'jogo']];

/* ---------------------------------------------------------------- tema claro/escuro */
/** Tema efetivo: o escolhido pelo usuário ou, sem escolha, o do sistema. */
export const temaAtual = () => document.documentElement.dataset.tema
  || (matchMedia('(prefers-color-scheme: dark)').matches ? 'escuro' : 'claro');
function alternarTema() {
  const novo = temaAtual() === 'escuro' ? 'claro' : 'escuro';
  document.documentElement.dataset.tema = novo;
  try { localStorage.setItem('edu_tema', novo); } catch { /* armazenamento bloqueado: vale só nesta visita */ }
  const b = document.querySelector('[data-acao="tema"]');
  if (b) { b.innerHTML = icon(novo === 'escuro' ? 'sol' : 'lua').s; b.setAttribute('aria-label', novo === 'escuro' ? 'Usar tema claro' : 'Usar tema escuro'); }
}

/* ---------------------------------------------------------------- cor do texto do menu */
/** Texto do menu sobre a cor da instituição: a escolha do gestor ou, no automático, o que contrasta mais. */
export function corTextoMenu(cor, escolha = 'auto') {
  if (escolha === 'branco' || escolha === 'preto') return escolha;
  const m = /^#?([0-9a-f]{6})$/i.exec(cor || '');
  if (!m) return 'branco';
  const [r, g, b] = [0, 2, 4].map((i) => {
    const c = parseInt(m[1].slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  const lum = 0.2126 * r + 0.7152 * g + 0.0722 * b;
  return (1.05 / (lum + 0.05)) >= ((lum + 0.05) / 0.05) ? 'branco' : 'preto';   // maior contraste WCAG
}

/* ---------------------------------------------------------------- layout do app */
const app = () => document.getElementById('app');

function shell() {
  const u = S.user;
  const papel = effRole(u);
  const [titulo, itens] = MENUS[papel];
  const corPropria = papel !== 'admin' && u.institution.color && u.institution.color !== '#172033';
  const inst = u.institution;
  const marca = inst.logo ? html`<img src="${inst.logo}" alt="" style="width:36px;height:36px;border-radius:10px;object-fit:cover">` : html`<span class="logo__marca">${logoSvg}</span>`;
  app().innerHTML = html`
  <div class="app">
    <aside class="lateral ${corPropria ? 'lateral--cor lateral--texto-' + corTextoMenu(inst.color, inst.settings?.menu_text) : ''}" style="${corPropria ? `background:${inst.color}` : ''}">
      <a class="logo" href="${homeOf(papel)}">${marca}<span class="logo__textos"><span class="logo__nome">EDU.AI</span><span class="logo__sub">${papel === 'admin' ? 'Administração' : inst.name}</span></span></a>
      <p class="menu__titulo">${titulo}</p>
      <nav class="menu" aria-label="${titulo}">${itens.map(([href, label, ic]) => html`<a href="${href}" data-rota="${href}">${icon(ic, 16)}<span>${label}</span></a>`)}</nav>
    </aside>
    <div class="principal">
      <header class="topo">
        <button type="button" class="icone-botao menu-mobile" data-acao="menu" aria-label="Abrir menu">${icon('menu')}</button>
        <form class="busca-global" role="search"><input class="topo__busca" type="search" name="q" placeholder="Buscar disciplinas, materiais, atividades..." aria-label="Buscar" autocomplete="off"><div class="busca-resultados popover" hidden></div></form>
        <div class="topo__acoes">
          <span class="ia-status" id="ia-status" hidden></span>
          <button type="button" class="icone-botao" data-acao="tema" aria-label="${temaAtual() === 'escuro' ? 'Usar tema claro' : 'Usar tema escuro'}">${icon(temaAtual() === 'escuro' ? 'sol' : 'lua')}</button>
          <button type="button" class="icone-botao" data-pop="pop-notif" aria-label="Notificações">${icon('sino')}<span class="icone-botao__ponto" id="notif-ponto" hidden></span></button>
          <a class="icone-botao" href="#/ajuda" aria-label="Ajuda">${icon('ajuda')}</a>
          <button type="button" class="usuario" data-pop="pop-usuario" aria-label="Menu do usuário"><span class="avatar">${initials(u.name)}</span><span class="usuario__textos"><span class="usuario__nome">${u.role === 'professor' ? 'Prof. ' : ''}${u.name}</span><span class="usuario__papel">${ROLE_LABEL[papel]}</span></span></button>
          <div class="popover popover--notificacoes" id="pop-notif" hidden></div>
          <div class="popover popover--usuario" id="pop-usuario" hidden>
            <div class="usuario"><span class="avatar">${initials(u.name)}</span><span><span class="usuario__nome">${u.name}</span><span class="usuario__papel">${inst.name}</span></span></div>
            <a href="#/perfil">Meu perfil</a><a href="#/notificacoes">Notificações</a><a href="#/ajuda">Ajuda e suporte</a>
            <a href="#" class="sair" data-acao="sair">Sair</a>
          </div>
        </div>
      </header>
      ${u.impersonated_by ? html`<div class="faixa-suporte nao-imprimir">${icon('escudo', 16)}<span>Você está acessando como <strong>${u.name}</strong> (${ROLE_LABEL[u.role]} · ${inst.name}).</span><button type="button" class="btn btn--primario btn--p" data-voltar>Voltar ao administrador geral</button></div>` : ''}
      <main class="conteudo" id="conteudo"></main>
    </div>
    ${u.role === 'aluno' ? html`<nav class="nav-inferior" aria-label="Atalhos">${NAV_INFERIOR.map(([href, label, ic]) => html`<a href="${href}" data-rota="${href}">${icon(ic, 20)}<span>${label}</span></a>`)}</nav>` : ''}
  </div>`;
  const root = app();
  root.querySelector('[data-acao="menu"]').onclick = (e) => { e.stopPropagation(); root.querySelector('.app').classList.toggle('menu-aberto'); };
  root.querySelector('[data-acao="tema"]').onclick = alternarTema;
  root.querySelector('[data-acao="sair"]').onclick = (e) => { e.preventDefault(); logout(); };
  root.querySelector('[data-voltar]')?.addEventListener('click', async (e) => {
    e.currentTarget.disabled = true;
    try {
      const r = await api('/plataforma/voltar', { method: 'POST' });
      setSession(r.token, r.user); resetShell(); go('#/admin/instituicoes');
    } catch (err) { fail(err); }
  });
  root.querySelectorAll('[data-pop]').forEach((b) => b.addEventListener('click', (e) => {
    e.stopPropagation();
    const alvo = document.getElementById(b.dataset.pop);
    const abrir = alvo.hidden;
    root.querySelectorAll('.popover').forEach((p) => { p.hidden = true; });
    alvo.hidden = !abrir;
    if (abrir && b.dataset.pop === 'pop-notif') loadNotifPopover();
  }));
  setupSearch(root.querySelector('.busca-global'));
  refreshNotifDot();
  if (!u.impersonated_by) refreshIaStatus();
}

/** Indicador "IA" no topo: nuvem (API da instituição) ou local (Ollama). Clicar abre o chat. */
export function refreshIaStatus() {
  api('/ia/status').then((s) => {
    const el = document.getElementById('ia-status');
    if (!el) return;
    const on = s.provider !== 'simulada';
    el.hidden = false;
    el.className = 'ia-status ' + (on ? 'ia-status--on' : 'ia-status--off');
    el.title = (on ? `${s.provider_label} conectada (${s.model || 'modelo padrão'})`
      : s.online ? (s.provider_name === 'ollama' ? `Ollama ativo, mas o modelo "${s.model}" não está instalado. Rode: ollama pull ${s.model}` : `${s.provider_label}: modelo "${s.model}" indisponível.`)
        : `${s.provider_label} não encontrada (${s.url}). Usando IA local simplificada.`) + ' — clique para abrir o chat com IA';
    el.textContent = on ? (s.mode === 'nuvem' ? 'IA: nuvem' : `IA local: ${s.model}`) : 'IA: modo simplificado';
    el.onclick = () => go('#/chat');
    el.style.cursor = 'pointer';
  }).catch(() => {});
}

document.addEventListener('click', (e) => {
  if (!e.target.closest('.popover') && !e.target.closest('[data-pop]')) document.querySelectorAll('.topo .popover').forEach((p) => { p.hidden = true; });
  const a = document.querySelector('.app.menu-aberto');
  if (a && !e.target.closest('.lateral')) a.classList.remove('menu-aberto');
});

async function refreshNotifDot() {
  try {
    const n = await api('/notifications?limit=1');
    const dot = document.getElementById('notif-ponto');
    if (dot) dot.hidden = !n.unread;
  } catch { /* silencioso */ }
}

async function loadNotifPopover() {
  const pop = document.getElementById('pop-notif');
  pop.innerHTML = '<p style="padding:16px" class="texto-fraco">Carregando…</p>';
  const n = await api('/notifications?limit=6');
  pop.innerHTML = html`<div class="popover__topo"><strong>Notificações</strong><a href="#" data-ler>Marcar todas como lidas</a></div>
    ${n.items.length ? n.items.map((x) => html`<a class="notificacao ${x.read ? '' : 'notificacao--nova'}" href="${x.link || '#/notificacoes'}" data-nid="${x.id}"><span class="notificacao__icone">${icon('sino', 14)}</span><div><strong>${x.text}</strong><span>${ago(x.created_at)} · ${x.kind || ''}</span></div></a>`) : html`<p style="padding:16px" class="texto-fraco">Nenhuma notificação.</p>`}
    <div class="popover__topo" style="border-top:1px solid var(--borda);border-bottom:0"><a href="#/notificacoes">Ver todas as notificações</a></div>`;
  pop.querySelector('[data-ler]').onclick = async (e) => { e.preventDefault(); await api('/notifications/read-all', { method: 'POST' }); loadNotifPopover(); refreshNotifDot(); };
  pop.querySelectorAll('[data-nid]').forEach((a) => a.addEventListener('click', () => { api(`/notifications/${a.dataset.nid}/read`, { method: 'POST' }); pop.hidden = true; setTimeout(refreshNotifDot, 300); }));
}

function setupSearch(form) {
  const input = form.querySelector('input');
  const box = form.querySelector('.busca-resultados');
  let t;
  input.addEventListener('input', () => {
    clearTimeout(t);
    t = setTimeout(async () => {
      const q = input.value.trim();
      if (q.length < 2) { box.hidden = true; return; }
      const r = await api('/search?q=' + encodeURIComponent(q));
      box.innerHTML = r.length
        ? html`${r.map((x) => html`<a href="${x.link}"><span class="tag tag--cinza">${x.kind}</span> ${x.title}</a>`)}`.s
        : '<p class="texto-fraco" style="padding:12px 14px">Nada encontrado.</p>';
      box.hidden = false;
    }, 250);
  });
  form.addEventListener('submit', (e) => { e.preventDefault(); go('#/busca?q=' + encodeURIComponent(input.value)); box.hidden = true; });
  box.addEventListener('click', () => { box.hidden = true; input.value = ''; });
}

/* ---------------------------------------------------------------- render */
let shellFor = null;
export function page(content, { bare = false } = {}) {
  if (bare) { shellFor = null; app().innerHTML = fmt(content); return app(); }
  if (shellFor !== S.user?.id + effRole()) { shell(); shellFor = S.user.id + effRole(); }
  const main = document.getElementById('conteudo');
  main.innerHTML = fmt(content);
  const rota = location.hash.split('?')[0];
  const rotaQ = location.hash;
  const exata = [...document.querySelectorAll('.menu a')].some((a) => a.dataset.rota.includes('?') && rotaQ === a.dataset.rota);
  document.querySelectorAll('.menu a, .nav-inferior a').forEach((a) => {
    const r = a.dataset.rota;
    const on = r.includes('?') ? rotaQ === r : !exata && (rota === r || rota.startsWith(r + '/') || ACTIVE_ALIAS[rota.split('/').slice(0, 3).join('/')] === r);
    a.classList.toggle('ativo', on);
    if (on) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
  });
  window.scrollTo(0, 0);
  return main;
}
export const resetShell = () => { shellFor = null; };
const ACTIVE_ALIAS = {
  '#/p/disciplina': '#/p/disciplinas', '#/p/turma': '#/p/turmas', '#/p/aluno': '#/p/turmas', '#/p/documento': '#/p/biblioteca',
  '#/p/upload': '#/p/biblioteca', '#/p/material': '#/p/materiais', '#/p/atividade': '#/p/atividades', '#/p/correcao': '#/p/atividades',
  '#/p/jogo': '#/p/jogos', '#/a/materia': '#/a/materias', '#/a/estudar': '#/a/materiais', '#/a/atividade': '#/a/atividades',
  '#/a/resultado': '#/a/atividades', '#/a/jogar': '#/a/jogos', '#/admin/instituicao': '#/admin/instituicoes',
  '#/g/chamado': '#/g/atendimento', '#/s/chamado': '#/s/atendimento', '#/s/aluno': '#/s/alunos', '#/s/documento': '#/s/declaracoes',
  '#/admin/chamado': '#/admin/chamados', '#/admin/fatura': '#/admin/faturas', '#/admin/nova-instituicao': '#/admin/instituicoes',
  '#/aprender/jogo': '#/aprender', '#/aprender/aluno': '#/aprender',
};

export const loading = () => html`<div class="carregando"><span class="spinner"></span> Carregando…</div>`;
export const empty = (titulo, texto = '', acao = '') => html`<div class="vazio">${icon('info', 28)}<strong>${titulo}</strong>${texto ? html`<p>${texto}</p>` : ''}${acao}</div>`;
export const header = (titulo, sub = '', acoes = '') => html`<div class="cabecalho"><div><h1>${titulo}</h1>${sub ? html`<p>${sub}</p>` : ''}</div>${acoes ? html`<div class="cabecalho__acoes">${acoes}</div>` : ''}</div>`;
export const kpi = (rotulo, valor, nota = '', cor = '') => html`<div class="kpi"><span class="kpi__rotulo">${rotulo}</span><span class="kpi__valor">${valor}</span><span class="kpi__nota ${cor ? 'kpi__nota--' + cor : ''}">${nota}</span></div>`;
export const progress = (pct, cor = '') => html`<div class="progresso ${cor ? 'progresso--' + cor : ''}" role="progressbar" aria-valuenow="${pct}" aria-valuemin="0" aria-valuemax="100"><span style="width:${Math.max(0, Math.min(100, pct || 0))}%"></span></div>`;
export const aviso = (texto, cor = 'azul') => html`<div class="aviso aviso--${cor}">${icon(cor === 'vermelho' ? 'alerta' : 'info')}<p>${texto}</p></div>`;
export const tabs = (items, ativa) => html`<nav class="abas" role="tablist">${items.map(([id, label]) => html`<button type="button" role="tab" data-aba="${id}" class="${id === ativa ? 'ativa' : ''}" aria-selected="${id === ativa}">${label}</button>`)}</nav>`;
export const segmented = (name, items, ativo) => html`<div class="segmentado" role="group" data-seg="${name}">${items.map(([v, l]) => html`<button type="button" data-valor="${v}" class="${v === ativo ? 'ativo' : ''}">${l}</button>`)}</div>`;

/** Liga controles segmentados: devolve getter do valor atual */
export function bindSeg(root, name, onChange) {
  const g = root.querySelector(`[data-seg="${name}"]`);
  if (!g) return () => null;
  g.addEventListener('click', (e) => {
    const b = e.target.closest('button');
    if (!b) return;
    g.querySelectorAll('button').forEach((x) => x.classList.toggle('ativo', x === b));
    onChange && onChange(b.dataset.valor);
  });
  return () => g.querySelector('.ativo')?.dataset.valor;
}

export function bindTabs(root, onChange) {
  root.querySelectorAll('[data-aba]').forEach((b) => b.addEventListener('click', () => {
    root.querySelectorAll('[data-aba]').forEach((x) => { x.classList.toggle('ativa', x === b); x.setAttribute('aria-selected', x === b); });
    onChange(b.dataset.aba);
  }));
}

/* ---------------------------------------------------------------- gráficos */
export function bars(items, { max = 10, height = 170, fmtV = nota } = {}) {
  if (!items.length) return empty('Sem dados ainda');
  const top = Math.max(max, ...items.map((i) => i.value || 0));
  const best = Math.max(...items.map((i) => i.value || 0));
  return html`<div class="barras" style="height:${height}px" role="img" aria-label="Gráfico de barras">${items.map((i) => html`
    <div class="barras__item ${i.value === best && best > 0 ? 'barras__item--destaque' : ''}" title="${i.label}: ${fmtV(i.value)}">
      <span class="barras__valor">${i.value == null ? '' : fmtV(i.value)}</span>
      <div class="barras__barra" style="height:${i.value ? Math.max(3, (100 * i.value) / top) : 2}%"></div>
      <span class="barras__rotulo">${i.label}</span></div>`)}</div>`;
}

export function hbars(items, { max = 100, suffix = '%', cor = (v) => (v < 50 ? 'vermelho' : v < 70 ? 'amarelo' : 'verde') } = {}) {
  if (!items.length) return empty('Sem dados ainda');
  return html`<div class="barras-h">${items.map((i) => html`<div class="barras-h__linha"><span>${i.label}</span>${progress((100 * (i.value || 0)) / max, cor(i.value))}<strong>${i.value == null ? '—' : nota(i.value) + suffix}</strong></div>`)}</div>`;
}

export function lineChart(points, { max = 10, height = 160 } = {}) {
  if (points.length < 2) return empty('Poucos dados para a evolução', 'Aparece após duas ou mais atividades corrigidas.');
  const w = 600, pad = 14;
  const xs = (i) => pad + (i * (w - 2 * pad)) / (points.length - 1);
  const ys = (v) => height - pad - ((v || 0) / max) * (height - 2 * pad);
  const d = points.map((p, i) => `${i ? 'L' : 'M'}${xs(i).toFixed(1)},${ys(p.value).toFixed(1)}`).join(' ');
  const grid = [0.25, 0.5, 0.75].map((f) => `<line x1="${pad}" x2="${w - pad}" y1="${ys(max * f)}" y2="${ys(max * f)}" stroke="var(--borda)"/>`).join('');
  const dots = points.map((p, i) => `<circle cx="${xs(i)}" cy="${ys(p.value)}" r="4.5" fill="#FACC15" stroke="var(--texto)" stroke-width="2"><title>${esc(p.label)}: ${nota(p.value)}</title></circle>`).join('');
  return html`<svg class="linha-grafico" viewBox="0 0 ${w} ${height}" role="img" aria-label="Gráfico de evolução">${raw(grid)}<path d="${d}" fill="none" stroke="var(--texto)" stroke-width="2.5" stroke-linejoin="round"/>${raw(dots)}</svg>
    <div class="linha-grafico__rotulos">${points.map((p) => html`<span title="${p.label}">${p.label.length > 14 ? p.label.slice(0, 13) + '…' : p.label}</span>`)}</div>`;
}

/* ---------------------------------------------------------------- toast e modal */
export function toast(msg, tipo = 'ok') {
  let box = document.querySelector('.toasts');
  if (!box) { box = document.createElement('div'); box.className = 'toasts'; box.setAttribute('role', 'status'); document.body.append(box); }
  const t = document.createElement('div');
  t.className = 'toast toast--' + tipo;
  t.textContent = msg;
  box.append(t);
  setTimeout(() => t.classList.add('toast--sai'), 3800);
  setTimeout(() => t.remove(), 4200);
}
export const fail = (e) => toast(e.message || String(e), 'erro');

/** Abre um modal. `body` é html; `onMount(el, close)` liga eventos. Devolve close(). */
export function modal(titulo, body, { onMount, onClose, largo = false } = {}) {
  const wrap = document.createElement('div');
  wrap.className = 'modal-fundo';
  wrap.innerHTML = html`<div class="modal ${largo ? 'modal--largo' : ''}" role="dialog" aria-modal="true" aria-label="${titulo}">
    <div class="modal__topo"><h2>${titulo}</h2><button type="button" class="icone-botao" data-fechar aria-label="Fechar">${icon('x')}</button></div>
    <div class="modal__corpo">${body}</div></div>`.s;
  document.body.append(wrap);
  const close = () => { wrap.remove(); document.removeEventListener('keydown', onKey); onClose && onClose(); };
  const onKey = (e) => { if (e.key === 'Escape') close(); };
  document.addEventListener('keydown', onKey);
  wrap.addEventListener('mousedown', (e) => { if (e.target === wrap) close(); });
  wrap.querySelectorAll('[data-fechar]').forEach((b) => b.addEventListener('click', close));
  onMount && onMount(wrap.querySelector('.modal'), close);
  wrap.querySelector('input, select, textarea')?.focus();
  return close;
}

/** Confirmação dentro da página (o navegador pode bloquear confirm()). */
export function confirmar(texto, { ok = 'Confirmar', perigo = false } = {}) {
  return new Promise((resolve) => {
    let result = false;
    modal('Confirmar', html`<p>${texto}</p><div class="linha linha--fim" style="margin-top:20px"><button class="btn btn--contorno" data-fechar>Cancelar</button><button class="btn ${perigo ? 'btn--vermelho' : 'btn--escuro'}" data-ok>${ok}</button></div>`, {
      onMount: (el, close) => { el.querySelector('[data-ok]').onclick = () => { result = true; close(); }; },
      onClose: () => resolve(result),
    });
  });
}

/** Lê os campos [name] de um form como objeto. */
export function formData(form) {
  const o = {};
  form.querySelectorAll('[name]').forEach((el) => {
    if (el.type === 'checkbox') o[el.name] = el.checked;
    else if (el.type === 'number') o[el.name] = el.value === '' ? null : Number(el.value);
    else o[el.name] = el.value;
  });
  return o;
}

/** Botão com estado de carregamento durante uma ação assíncrona. */
export async function busy(btn, fn) {
  const txt = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner spinner--p"></span> ' + txt;
  try { return await fn(); } catch (e) { fail(e); } finally { btn.disabled = false; btn.innerHTML = txt; }
}

/* ---------------------------------------------------------------- roteador */
const routes = [];
export function route(pattern, handler, { role = null, public: pub = false } = {}) {
  const keys = [];
  const re = new RegExp('^' + pattern.replace(/:(\w+)/g, (_, k) => { keys.push(k); return '([^/]+)'; }) + '$');
  routes.push({ re, keys, handler, role, pub });
}
export const go = (hash) => { if (location.hash === hash) dispatch(); else location.hash = hash; };
export const query = () => Object.fromEntries(new URLSearchParams(location.hash.split('?')[1] || ''));
/** Agenda limpeza (timers de polling) para quando a rota mudar. */
export const onLeave = (fn) => S.cleanup.push(fn);

export async function dispatch() {
  S.cleanup.splice(0).forEach((fn) => { try { fn(); } catch { /* */ } });
  document.querySelectorAll('.modal-fundo').forEach((m) => m.remove());
  const path = (location.hash.replace(/^#\/?/, '').split('?')[0]) || '';
  if (S.token && !S.user) {
    try { S.user = await api('/me'); } catch { S.token = null; localStorage.removeItem('edu_token'); }
  }
  if (!path) return go(S.user ? homeOf(effRole()) : '#/login');
  for (const r of routes) {
    const m = path.match(r.re);
    if (!m) continue;
    if (!r.pub && !S.user) return go(path.startsWith('admin') ? '#/admin/login' : '#/login');
    const roles = Array.isArray(r.role) ? r.role : r.role ? [r.role] : null;
    const permitido = !roles || roles.some((x) => (x === 'superadmin' ? effRole() === 'admin' : S.user.role === x));
    if (!r.pub && !permitido) return go(homeOf(effRole()));
    const params = Object.fromEntries(r.keys.map((k, i) => [k, decodeURIComponent(m[i + 1])]));
    try { await r.handler(params, query()); } catch (e) {
      console.error(e);
      if (S.user) page(html`${header('Algo deu errado')}${aviso(e.message, 'vermelho')}<a class="btn btn--contorno" href="${homeOf(effRole())}">Voltar ao início</a>`);
      else fail(e);
    }
    return;
  }
  if (S.user) page(html`${header('Página não encontrada')}<a class="btn btn--contorno" href="${homeOf(effRole())}">Voltar ao início</a>`);
  else go('#/login');
}
