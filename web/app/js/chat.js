/* EDU.AI – Chat com IA (aluno, professor, secretaria, gestor e administrador geral)
   A IA em nuvem é a da instituição (link e chave cadastrados pelo gestor) ou, para o administrador
   geral, a própria. Cada pessoa alterna entre nuvem e local (Ollama) aqui mesmo ou no perfil. */
import {
  S, api, busy, confirmar, effRole, esc, fail, go, html, icon, loading, page, raw, refreshIaStatus, route, toast,
} from './core.js';

const SUGESTOES = {
  aluno: ['Me explique frações com um exemplo do dia a dia', 'Monte um plano de estudo de 1 semana para a prova de história', 'Quais são as dicas para fazer uma boa redação?'],
  professor: ['Crie um plano de aula de 50 minutos sobre ecossistemas', 'Sugira uma rubrica para avaliar seminários', 'Dê 3 ideias de atividades práticas sobre frações'],
  secretaria: ['Redija um comunicado sobre a rematrícula', 'Escreva uma resposta cordial para um pedido de histórico escolar', 'Liste os documentos para transferência de aluno'],
  gestor: ['Sugira indicadores para acompanhar a evasão escolar', 'Escreva um comunicado às famílias sobre o calendário', 'Como organizar uma reunião pedagógica produtiva?'],
  admin: ['Escreva um e-mail de cobrança cordial para uma fatura vencida', 'Sugira métricas de sucesso para clientes da plataforma', 'Crie um roteiro de onboarding para uma nova escola'],
};

/** Markdown simples e seguro: escapa tudo e depois aplica negrito, itálico, código, listas e quebras. */
function md(texto) {
  const blocos = esc(texto).split(/```/);
  return blocos.map((b, i) => {
    if (i % 2) return `<pre class="chat-codigo"><code>${b.replace(/^[a-zA-Z0-9]*\n/, '')}</code></pre>`;
    return b.split(/\n{2,}/).map((p) => {
      const linhas = p.split('\n');
      if (linhas.every((l) => /^\s*([-*•]|\d+[.)])\s+/.test(l) || !l.trim())) {
        const ordenada = /^\s*\d/.test(linhas[0]);
        const itens = linhas.filter((l) => l.trim()).map((l) => `<li>${inline(l.replace(/^\s*([-*•]|\d+[.)])\s+/, ''))}</li>`).join('');
        return ordenada ? `<ol>${itens}</ol>` : `<ul>${itens}</ul>`;
      }
      if (/^#{1,4}\s/.test(p)) return `<p><strong>${inline(p.replace(/^#{1,4}\s/, ''))}</strong></p>`;
      return `<p>${linhas.map(inline).join('<br>')}</p>`;
    }).join('');
  }).join('');
}
const inline = (s) => s.replace(/`([^`]+)`/g, '<code>$1</code>').replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>').replace(/(^|[^*])\*([^*]+)\*/g, '$1<em>$2</em>');

const balao = (m) => html`<div class="chat-msg chat-msg--${m.role === 'user' ? 'eu' : 'ia'}">
  <div class="chat-msg__avatar">${m.role === 'user' ? icon('usuarios', 16) : icon('robo', 16)}</div>
  <div class="chat-msg__corpo">${m.role === 'user' ? html`<p>${m.content}</p>` : raw(md(m.content))}
  ${m.role !== 'user' && m.provider ? html`<span class="chat-msg__fonte">${m.provider.startsWith('nuvem') ? 'IA em nuvem' : m.provider.startsWith('ollama') ? 'IA local' : 'sem IA'}</span>` : ''}</div></div>`;

async function telaChat(id) {
  if (S.user.impersonated_by) {
    return page(html`<div class="cabecalho"><div><h1>Chat com IA</h1><p>O chat fica indisponível ao acessar como outro usuário.</p></div></div>`);
  }
  page(loading());
  const [lista, pref] = await Promise.all([api('/chat/conversas'), api('/me/ia')]);
  if (!id && lista.length && location.hash.split('?')[0] === '#/chat' && !location.hash.includes('nova')) {
    return go('#/chat/' + lista[0].id);
  }
  const conv = id ? await api('/chat/conversas/' + id) : null;
  const papel = effRole();
  const nuvemOk = pref.cloud_ready;
  const el = page(html`<div class="chat">
    <aside class="chat__lado">
      <button class="btn btn--primario btn--bloco" data-nova>${icon('mais', 16)} Nova conversa</button>
      <nav class="chat__lista" aria-label="Conversas">${lista.length ? lista.map((c) => html`<a href="#/chat/${c.id}" class="${conv && c.id === conv.id ? 'ativa' : ''}"><span>${c.title}</span><button class="icone-botao" data-apagar="${c.id}" aria-label="Apagar conversa">${icon('x', 14)}</button></a>`)
    : html`<p class="texto-fraco" style="padding:8px">Nenhuma conversa ainda.</p>`}</nav>
    </aside>
    <section class="chat__principal">
      <header class="chat__topo">
        <div><h1>${conv ? conv.title : 'Chat com IA'}</h1><p class="texto-fraco">Assistente para ${({ aluno: 'estudar', professor: 'planejar aulas e atividades', secretaria: 'rotinas da secretaria', gestor: 'a gestão da escola', admin: 'a administração da plataforma' })[papel]}</p></div>
        <div class="segmentado chat__modo" role="group" aria-label="Qual IA usar">
          <button type="button" data-modo="nuvem" class="${pref.active === 'nuvem' ? 'ativo' : ''}" ${nuvemOk ? '' : 'disabled'} title="${nuvemOk ? 'IA em nuvem (API)' : papel === 'admin' ? 'Cadastre a sua chave em Minha IA' : 'A instituição ainda não cadastrou o link e a chave da API'}">${icon('link', 14)} Nuvem</button>
          <button type="button" data-modo="local" class="${pref.active === 'local' ? 'ativo' : ''}" title="IA local (Ollama)">${icon('robo', 14)} Local</button>
        </div>
      </header>
      <div class="chat__mensagens" id="msgs">${conv && conv.messages.length ? conv.messages.map(balao)
    : html`<div class="chat__vazio">${icon('robo', 36)}<h2>Como posso ajudar?</h2><div class="chat__sugestoes">${SUGESTOES[papel].map((s) => html`<button class="chip" data-sugestao="${s}">${s}</button>`)}</div></div>`}</div>
      <form class="chat__entrada" id="f">
        <textarea class="entrada" name="text" rows="1" maxlength="6000" placeholder="Escreva sua mensagem… (Enter envia, Shift+Enter quebra a linha)" required></textarea>
        <button class="btn btn--primario" type="submit" aria-label="Enviar">Enviar</button>
      </form>
      ${!nuvemOk && papel !== 'admin' ? html`<p class="texto-fraco chat__nota">Usando a IA local. A IA em nuvem aparece aqui quando o gestor cadastrar o link e a chave da API.</p>` : ''}
    </section></div>`);
  const msgs = el.querySelector('#msgs');
  msgs.scrollTop = msgs.scrollHeight;
  const f = el.querySelector('#f');
  const ta = f.text;
  ta.focus();
  ta.addEventListener('input', () => { ta.style.height = 'auto'; ta.style.height = Math.min(200, ta.scrollHeight) + 'px'; });
  ta.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); f.requestSubmit(); } });
  let modo = pref.active;

  el.querySelectorAll('[data-modo]').forEach((b) => {
    b.onclick = async () => {
      if (b.disabled || b.dataset.modo === modo) return;
      try {
        const r = await api('/me/ia', { method: 'PUT', body: { mode: b.dataset.modo } });
        modo = r.active;
        el.querySelectorAll('[data-modo]').forEach((x) => x.classList.toggle('ativo', x.dataset.modo === modo));
        toast(modo === 'nuvem' ? 'Usando a IA em nuvem' : 'Usando a IA local (Ollama)');
        refreshIaStatus();
      } catch (e) { fail(e); }
    };
  });
  el.querySelectorAll('[data-sugestao]').forEach((b) => { b.onclick = () => { ta.value = b.dataset.sugestao; f.requestSubmit(); }; });
  el.querySelector('[data-nova]').onclick = () => go('#/chat?nova=1');
  el.querySelectorAll('[data-apagar]').forEach((b) => {
    b.onclick = async (e) => {
      e.preventDefault(); e.stopPropagation();
      if (!(await confirmar('Apagar esta conversa?', { ok: 'Apagar', perigo: true }))) return;
      await api('/chat/conversas/' + b.dataset.apagar, { method: 'DELETE' });
      go(conv && String(conv.id) === b.dataset.apagar ? '#/chat?nova=1' : location.hash);
    };
  });
  f.addEventListener('submit', (e) => {
    e.preventDefault();
    const text = ta.value.trim();
    if (!text) return;
    busy(f.querySelector('[type=submit]'), async () => {
      let cid = conv?.id;
      if (!cid) cid = (await api('/chat/conversas', { method: 'POST', body: {} })).id;
      msgs.querySelector('.chat__vazio')?.remove();
      msgs.insertAdjacentHTML('beforeend', balao({ role: 'user', content: text }).s);
      msgs.insertAdjacentHTML('beforeend', '<div class="chat-msg chat-msg--ia" data-digitando><div class="chat-msg__avatar">' + icon('robo', 16).s + '</div><div class="chat-msg__corpo"><span class="digitando"><i></i><i></i><i></i></span></div></div>');
      msgs.scrollTop = msgs.scrollHeight;
      ta.value = ''; ta.style.height = 'auto';
      try {
        const r = await api(`/chat/conversas/${cid}/mensagens`, { method: 'POST', body: { text, mode: modo } });
        msgs.querySelector('[data-digitando]')?.remove();
        msgs.insertAdjacentHTML('beforeend', balao(r).s);
        msgs.scrollTop = msgs.scrollHeight;
        if (!conv) { history.replaceState(null, '', '#/chat/' + cid); return telaChat(cid); }
        el.querySelector('.chat__topo h1').textContent = r.title;
      } catch (err) {
        msgs.querySelector('[data-digitando]')?.remove();
        ta.value = text;
        throw err;
      }
    });
  });
}

route('chat', () => telaChat(null));
route('chat/:id', ({ id }) => telaChat(Number(id)));
