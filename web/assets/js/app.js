/* EDU.AI – interações compartilhadas das telas da plataforma */
(function () {
  // Menu lateral no celular
  document.querySelectorAll('[data-acao="menu"]').forEach(function (botao) {
    botao.addEventListener('click', function () {
      document.querySelector('.app').classList.toggle('menu-aberto');
    });
  });
  document.addEventListener('click', function (e) {
    var app = document.querySelector('.app.menu-aberto');
    if (app && !e.target.closest('.lateral') && !e.target.closest('[data-acao="menu"]')) {
      app.classList.remove('menu-aberto');
    }
  });

  // Popovers do topo (notificações e menu do usuário)
  document.querySelectorAll('[data-popover]').forEach(function (botao) {
    botao.addEventListener('click', function (e) {
      e.stopPropagation();
      var alvo = document.getElementById(botao.dataset.popover);
      var abrir = alvo.hidden;
      document.querySelectorAll('.popover').forEach(function (p) { p.hidden = true; });
      alvo.hidden = !abrir;
      botao.setAttribute('aria-expanded', String(abrir));
    });
  });
  document.addEventListener('click', function (e) {
    if (e.target.closest('.popover')) return;
    document.querySelectorAll('.popover[data-fechavel]').forEach(function (p) { p.hidden = true; });
  });

  // Controles segmentados e chips: um ativo por grupo
  document.querySelectorAll('.segmentado, .chips[data-unico]').forEach(function (grupo) {
    grupo.addEventListener('click', function (e) {
      var item = e.target.closest('button');
      if (!item || !grupo.contains(item)) return;
      grupo.querySelectorAll('button').forEach(function (b) { b.classList.remove('ativo'); });
      item.classList.add('ativo');
    });
  });

  // Interruptores
  document.querySelectorAll('.switch:not([disabled])').forEach(function (s) {
    s.addEventListener('click', function () {
      s.setAttribute('aria-checked', s.getAttribute('aria-checked') === 'true' ? 'false' : 'true');
    });
  });

  // Flashcards: virar ao clicar
  document.querySelectorAll('.flashcard').forEach(function (c) {
    c.addEventListener('click', function () { c.classList.toggle('virado'); });
  });

  // Estúdio de IA: contador de recursos selecionados
  var contador = document.querySelector('[data-contador-opcoes]');
  if (contador) {
    var atualizar = function () {
      var n = document.querySelectorAll('.opcao input:checked').length;
      contador.textContent = n + (n === 1 ? ' recurso selecionado' : ' recursos selecionados');
    };
    document.querySelectorAll('.opcao input').forEach(function (i) { i.addEventListener('change', atualizar); });
    atualizar();
  }

  // Mapa mental: selecionar nó e mostrar no painel
  var campoNo = document.querySelector('[data-texto-no]');
  document.querySelectorAll('.no').forEach(function (no) {
    no.addEventListener('click', function () {
      document.querySelectorAll('.no').forEach(function (n) { n.classList.remove('selecionado'); });
      no.classList.add('selecionado');
      if (campoNo) campoNo.value = no.textContent.trim();
    });
  });

  // Formulários de demonstração não enviam para lugar nenhum
  document.querySelectorAll('form[data-demo]').forEach(function (f) {
    f.addEventListener('submit', function (e) {
      e.preventDefault();
      if (f.dataset.demo) window.location.href = f.dataset.demo;
    });
  });
})();
