/* EDU.AI – ponto de entrada da plataforma */
import { dispatch } from './core.js';
import './acesso.js';
import './professor.js';
import './estudio.js';
import './avaliacoes.js';
import './jogos.js';
import './aluno.js';
import './gestor.js';
import './admin.js';
import './suporte.js';
import './chat.js';
import './secretaria.js';
import './aprendizado.js';

window.addEventListener('hashchange', dispatch);
dispatch();
