# EDU.AI — plataforma educacional com IA

Plataforma SaaS para escolas com quatro perfis na instituição (gestor, secretaria, professor e aluno) e um painel
próprio para o administrador geral da plataforma. O professor envia um material, a IA gera resumos, mapas mentais, flashcards, exercícios e roteiros de revisão, o professor revisa e publica, o aluno estuda e responde, e a plataforma registra os resultados.

## Como rodar

1. Instale o **Python 3.11+**.
2. (Recomendado) Instale o **Ollama** (https://ollama.com) e baixe um modelo:
   ```
   ollama pull llama3.2
   ```
3. Dê dois cliques em `server/iniciar.bat` (ou, dentro de `server/`: `python -m uvicorn app.main:app --port 8000`).
4. Abra http://localhost:8000 (landing page) ou http://localhost:8000/app/ (plataforma).

Contas de teste — senha de todas: `Teste@2026`.
Login automático: `/app/#/demo/professor`, `/app/#/demo/aluno`, `/app/#/demo/gestor` e `/app/#/demo/secretaria`
(também há botões na tela de login). O administrador geral entra pela página exclusiva **`/app/#/admin/login`**
(só e-mail e senha, sem código de instituição; ele não entra pelo login das escolas).

| Perfil              | Instituição    | E-mail                                                   |
|---------------------|----------------|----------------------------------------------------------|
| Administrador geral | (login próprio)| admin@plataforma.edu.br, admin2@plataforma.edu.br        |
| Gestor              | `escola-teste` | gestor@escolateste.edu.br, gestor2@escolateste.edu.br    |
| Secretaria          | `escola-teste` | secretaria@escolateste.edu.br                            |
| Professor           | `escola-teste` | professor@escolateste.edu.br (com turmas e materiais), professor2@…, professor3@… (sem dados) |
| Aluno               | `escola-teste` | aluno@escolateste.edu.br, aluno02@… até aluno18@escolateste.edu.br |

O banco (`server/edu.db`) e os arquivos enviados (`server/uploads/`) são criados na primeira execução; as contas de teste são criadas quando o banco não tem nenhum usuário.
Bancos antigos são atualizados sozinhos na inicialização (novas tabelas e o papel "secretaria"); a conta da secretaria,
os dados cadastrais dos alunos e faturas de exemplo também são adicionados à escola de teste.

Para **zerar o banco** e recriar as contas de teste (com o servidor parado; faz backup em `server/backups/`):
```
cd server
.venv\Scripts\python.exe resetar_banco.py --confirmar
```

## Testes automáticos

Com o servidor parado ou não (o teste sobe o próprio servidor na porta 8799, com um banco temporário):
```
cd server
python testes_api.py
```
Cobre isolamento entre escolas, prazos e gabaritos, sessões, verificação em duas etapas, limite de tentativas,
atendimento (secretaria, gestão e plataforma, com anexos), calendário, faturas, administradores, carteirinhas e
declarações, a IA em nuvem da instituição (com uma API falsa local), o chat com IA, os jogos de aprendizado e todas as
telas de cada perfil. Rode antes de publicar qualquer mudança.

## Quem faz o quê

- **Administrador geral da plataforma** (login em `#/admin/login`): painel com receita, faturas vencidas e chamados;
  cadastra instituições (além do cadastro público na tela de login); emite e dá baixa nas **faturas das mensalidades**
  (uma a uma ou "gerar mensalidades do mês" para todas as instituições ativas, com o preço do plano); cadastra e
  desativa **outros administradores gerais**; responde os chamados que os gestores abrem para o suporte; usa o chat com
  IA com a **própria chave de API** (menu *Minha IA*) ou a IA local; pode "acessar como" qualquer usuário para suporte.
- **Gestão:** cria turmas e disciplinas, define o calendário, responde o atendimento, cadastra o **link e a chave da
  API da IA em nuvem** da instituição (Configurações → Inteligência artificial), vê as **faturas** em *Planos, uso e
  faturas* e abre chamados para o **suporte da plataforma**. Também acessa as telas da secretaria.
- **Secretaria:** responde os chamados de alunos e professores (com anexos), mantém foto, matrícula, nascimento e
  documento dos alunos, gera **carteirinhas de estudante** por turma (prontas para imprimir, 10 por folha A4) e
  **declarações automáticas** (matrícula, frequência, conclusão, transferência, vínculo ou texto livre, com a opção de
  a IA redigir). Abre chamados para a gestão.
- **Professor:** organiza os conteúdos, cria materiais com IA, atividades e jogos ao vivo, cria jogos de aprendizado
  para as turmas e acompanha o **aprendizado gamificado** de cada aluno (partidas, acertos e onde errou).
- **Aluno:** estuda, entrega atividades, usa o **estúdio de aprendizado gamificado**, conversa com a IA, vê os
  documentos emitidos pela secretaria (*Meus documentos*) e abre chamados para a secretaria ou para a gestão.

Todos os perfis têm a aba **Chat com IA**.

## Aprendizado gamificado

Menu *Aprendizado gamificado* (aluno e professor). O aluno escolhe um material publicado, cola um texto ou escreve um
tema, marca os jogos e a IA monta cada um com aquele conteúdo:

| Jogo                    | Como funciona                                                                        |
|-------------------------|--------------------------------------------------------------------------------------|
| Jogo da memória         | Pares de conceito e definição; menos jogadas, mais pontos                            |
| Quiz relâmpago          | Estilo Kahoot: 4 alternativas coloridas, 20 s, quanto mais rápido mais pontos       |
| Verdadeiro ou falso     | Afirmações com tempo e explicação depois de cada resposta                            |
| Complete a frase        | Escolha a palavra que falta                                                          |
| Adivinhe o conceito     | Dicas da mais difícil para a mais fácil; cada dica extra vale menos                  |
| Desafio de programação  | Completar a lacuna no código, prever a saída ou achar o erro                         |

Cada partida é registrada. O professor cria jogos a partir dos documentos e materiais dele e publica para uma turma
(com ranking), e na aba *Aprendizado dos alunos* vê o que cada aluno estudou, os acertos por tipo de jogo e as
perguntas em que mais errou. Sem IA disponível, os jogos são montados pelo modo local (mais simples).

## Atendimento e ouvidoria

Cada chamado tem um **destino**, que define quem responde:

| Quem abre                    | Destino                      | Quem responde                                  |
|------------------------------|------------------------------|------------------------------------------------|
| Aluno, professor             | Secretaria escolar           | Secretaria (o gestor também vê e responde)     |
| Aluno, professor, secretaria | Gestão da instituição        | Gestor(es)                                     |
| Gestor                       | Suporte da plataforma        | Administradores gerais                         |

Assuntos: documentos (declarações, histórico, boletim, carteirinha…), secretaria, coordenação, financeiro, reclamações,
sugestões e denúncias (estas podem ser anônimas). Todos podem anexar arquivos (PDF, imagens, documentos, planilhas,
TXT ou ZIP, até 10 MB) ao abrir e em cada resposta. A secretaria pode encaminhar um chamado para a gestão e, num pedido
de documento, **emitir a declaração direto do chamado** (o chamado é resolvido e o aluno recebe o documento em
*Meus documentos*). Cada documento tem um código de verificação público (`#/verificar/<código>`).

## Calendário escolar

A gestão cadastra os períodos letivos (datas e dias da semana com aula) e os eventos: feriados, recessos, dias sem
aula, aulas extras/reposições, provas, eventos e reuniões, para a escola toda ou para uma turma. Alunos e
professores veem o mês com os dias de aula destacados e os prazos das atividades.

## E-mail

| Variável            | Padrão                                | Uso                                              |
|---------------------|---------------------------------------|--------------------------------------------------|
| `EDU_SMTP_HOST`     | (vazio)                               | Servidor SMTP. Sem ele, os e-mails só aparecem no console do servidor e na tabela `outbox` |
| `EDU_SMTP_PORT`     | `587`                                 | Porta (STARTTLS); use `465` com `EDU_SMTP_SSL=1` |
| `EDU_SMTP_USER` / `EDU_SMTP_PASSWORD` | (vazio)             | Credenciais SMTP                                 |
| `EDU_SMTP_FROM`     | `EDU.AI <nao-responda@eduai.local>`   | Remetente                                        |
| `EDU_BASE_URL`      | `http://localhost:8000`               | Endereço público usado nos links dos e-mails     |

Usado em: convites, "Esqueci minha senha", aviso de troca de e-mail, respostas do atendimento e resumos semanais
(segunda-feira) para gestores e para quem marcou "resumo semanal" no perfil.

## Segurança

- Limite de tentativas no login (8 por conta a cada 15 min; 30 por IP a cada 10 min), no código de turma, no
  cadastro de escolas e na recuperação de senha.
- Verificação em duas etapas por app autenticador (Perfil → Verificação em duas etapas).
- Trocar ou redefinir a senha encerra as sessões abertas em outros aparelhos.
- Instituições criadas pelo cadastro público começam no plano Essencial; a troca de plano é pedida pelo gestor e
  aprovada pelo administrador geral (tela *Instituições*).

## IA

**IA em nuvem da instituição:** o gestor cadastra em *Configurações → Inteligência artificial* o **link da API** e a
**chave da API** da IA contratada (qualquer API no formato "chat completions": OpenAI, OpenRouter, Groq, DeepSeek,
Mistral, Gemini compatível…), o modelo e a IA padrão. A configuração vale para todos da instituição, e cada pessoa
(professor, aluno, secretaria, gestor) **alterna entre a IA em nuvem e a IA local (Ollama)** no próprio chat ou em
*Configurações → Perfil*. Há um botão para testar a conexão. A chave fica no servidor e nunca volta para o navegador
(só os 4 últimos caracteres). O administrador geral tem link e chave **próprios** (*Minha IA*), independentes dos
outros administradores; sem chave, usa a IA local. Sem link/chave, o modo nuvem cai na IA local.

> A chave é guardada em texto no banco (`institutions.settings` / `users.ai_prefs`): proteja o arquivo `edu.db` e os
> backups. O link da API é chamado pelo servidor, por isso só gestores e administradores podem cadastrá-lo.

A IA fica atrás de uma interface de provedores em `server/app/ia_providers/`:

| Variável           | Padrão     | Uso                                                     |
|--------------------|------------|---------------------------------------------------------|
| `EDU_IA_PROVIDER`  | `ollama`   | `ollama` (local) ou `nuvem` (modelo pronto para uma IA em nuvem) |
| `EDU_IA_MODEL`     | `llama3.2` | Modelo padrão (`OLLAMA_MODEL` também é aceito)          |

**Configuração por variáveis de ambiente (opcional):** sem nada cadastrado no painel, ainda vale
`EDU_IA_PROVIDER=nuvem` com `EDU_NUVEM_URL`, `EDU_NUVEM_API_KEY` e `EDU_NUVEM_MODELO`. Se a sua IA não usar o formato
"chat completions", ajuste `_montar_pedido` e `_ler_resposta` em `server/app/ia_providers/nuvem.py`.
Prompts, validação das respostas, limites do plano e o modo local de reserva continuam iguais. Para qualquer outro
provedor, crie uma classe que herde de `ProvedorIA` (`base.py`) e registre-a em `ia_providers/__init__.py`.
Com IA externa, os textos dos documentos e as dúvidas dos alunos saem do servidor da escola: exija contrato de
tratamento de dados (LGPD).

### Ollama

| Variável           | Padrão                    | Uso                                          |
|--------------------|---------------------------|----------------------------------------------|
| `OLLAMA_URL`       | `http://127.0.0.1:11434`  | Endereço do Ollama                           |
| `OLLAMA_MODEL`     | `llama3.2`                | Modelo padrão (o gestor pode trocar no painel) |
| `OLLAMA_TIMEOUT`   | `300`                     | Segundos por geração                         |
| `EDU_IA_MAX_CHARS` | `20000`                   | Quanto do documento entra no prompt (por geração; escolha o intervalo de páginas no Estúdio para documentos maiores) |
| `EDU_IA_MAX_CHUNKS`| `12`                      | Em quantas partes, no máximo, um documento longo é lido. Documentos maiores que `EDU_IA_MAX_CHARS` são lidos em partes e condensados em notas de estudo (guardadas para as próximas gerações) |
| `OLLAMA_NUM_CTX`   | `16384`                   | Janela de contexto do modelo (tokens)        |
| `EDU_SECRET`       | (valor de desenvolvimento)| Chave dos tokens de login — **troque em produção** |

A IA é usada para: identificar tópicos dos documentos, gerar os 5 formatos de material, reescrever uma parte específica, gerar questões para o banco e para jogos, sugerir correção de questões discursivas e montar o plano de revisão do aluno. Sem Ollama, a plataforma continua funcionando com um gerador local simplificado (o indicador "IA" no topo da tela do professor mostra qual está ativo). Para português, modelos como `qwen2.5:7b` ou `llama3.1:8b` dão resultados melhores que o `llama3.2` (3B), se a máquina aguentar.

## Jogos ao vivo

- **Pontuação por confiança** (padrão): o aluno responde e diz se tem certeza, acha que sabe ou está chutando. Acertar com certeza vale mais; errar com certeza custa pontos. A pontuação por velocidade continua disponível.
- **Discussão em duplas**: se entre 30% e 70% da turma acertar, a resposta não é revelada: os alunos discutem com um colega e votam de novo. O professor também pode pedir a discussão a qualquer momento.
- **Painel do professor**: resposta certa, explicação, quem votou em cada alternativa e quem ainda não respondeu. No telão, esconda com a tecla `G` ou abra `#/p/jogo/<id>/painel` em outro aparelho.
- No fim, cada aluno recebe a lista do que errou com a resposta certa e o porquê; o relatório do professor mostra o acerto antes/depois da discussão e a alternativa errada mais escolhida.

## Estrutura

```
server/app/
  main.py        app FastAPI + site estático
  db.py          esquema SQLite
  ia.py          prompts, validação das respostas e gerador local de reserva
  ia_providers/  provedores de IA: ollama.py (padrão) e nuvem.py (modelo para IA em nuvem)
  jobs.py        processamento de documentos e gerações em segundo plano
  manutencao.py  retoma processamentos interrompidos, retenção de dados e resumos semanais
  correio.py     envio de e-mails (SMTP)
  seguranca.py   limite de tentativas e verificação em duas etapas
  scoring.py     correção automática e estatísticas
  seed.py        dados de demonstração
  routes/        common · professor · aluno · jogos · gestor · plataforma · atendimento · calendario
                 chat (chat com IA) · secretaria (carteirinhas e declarações) · aprendizado (jogos gamificados)
server/testes_api.py   testes automáticos da API
web/
  index.html     landing page
  app/           plataforma (SPA em JavaScript puro, sem build)
  professor/ aluno/ gestor/ jogos/ ...   protótipos estáticos dos wireframes (referência)
```

Documentação interativa da API: http://localhost:8000/docs
