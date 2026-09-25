# ChatChannels

**Comunicação corporativa em tempo real integrada ao ecossistema ZeladorX.**

O ChatChannels é a ferramenta de mensagens da família ZeladorX. Ele conecta os mesmos usuários, empresas e regras de identidade do sistema de gestão de zeladoria a salas de conversa em tempo real, mantendo o contexto corporativo em uma aplicação especializada.

![Django](https://img.shields.io/badge/Django-5.2-092E20?logo=django)
![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python)
![Channels](https://img.shields.io/badge/Django-Channels-44B78B?logo=django)
![WebSockets](https://img.shields.io/badge/Tempo_real-WebSockets-010101)
![PostgreSQL](https://img.shields.io/badge/Banco-PostgreSQL-4169E1?logo=postgresql)
![Google Cloud](https://img.shields.io/badge/Storage-Google_Cloud-4285F4?logo=googlecloud)
![Heroku](https://img.shields.io/badge/Deploy-Heroku-430098?logo=heroku)

---

## Sumário

- [Visão geral](#visão-geral)
- [Família ZeladorX](#família-zeladorx)
- [Como funciona](#como-funciona)
- [Funcionalidades](#funcionalidades)
- [Módulos](#módulos)
- [Arquitetura em tempo real](#arquitetura-em-tempo-real)
- [Banco e migrações compartilhados](#banco-e-migrações-compartilhados)
- [Stack técnica](#stack-técnica)
- [Instalação local](#instalação-local)
- [Variáveis de ambiente](#variáveis-de-ambiente)
- [Deploy](#deploy)
- [Segurança](#segurança)

---

## Visão geral

O ChatChannels não é apenas um chat isolado. Ele é uma **ferramenta corporativa complementar ao [ZeladorX](https://github.com/Markosalves12/zeladorxV2)** e reutiliza parte da mesma base de domínio.

A aplicação mantém os colaboradores dentro do contexto de suas empresas e oferece comunicação instantânea por salas públicas ou privadas. Mensagens, anexos, presença, digitação e contadores de não lidas são atualizados sem recarregar a página.

```text
                         FAMÍLIA ZELADORX

                 ┌───────────────────────────┐
                 │ Banco de dados corporativo│
                 │ usuários • empresas • IDs │
                 └─────────────┬─────────────┘
                               │
                 ┌─────────────┴─────────────┐
                 │                           │
       ┌─────────▼─────────┐       ┌────────▼─────────┐
       │     ZeladorX      │       │   ChatChannels   │
       │ gestão operacional│       │ comunicação real │
       │ kanban e serviços │       │ salas e mensagens│
       └───────────────────┘       └──────────────────┘
```

---

## Família ZeladorX

Os dois repositórios são aplicações irmãs: possuem responsabilidades diferentes, mas compartilham a fundação corporativa.

| Camada | Compartilhada | Própria do ChatChannels |
|---|---|---|
| **Identidade** | Modelo de usuário `Gerente`, autenticação e vínculo empresarial | Presença e última atividade |
| **Organização** | Empresa primária, empresas secundárias e identificadores globais | Participação e gestão de membros das salas |
| **Dados** | Mesmo PostgreSQL e histórico compatível de migrações dos apps comuns | Tabelas de salas, mensagens e anexos |
| **Configuração** | Convenções de ambiente, e-mail, armazenamento e infraestrutura | ASGI, Channels e WebSockets |
| **Experiência** | Identidade visual e contexto ZeladorX | Interface especializada em conversas |

### Apps compartilhados

- `gerente`: usuário corporativo e vínculo com empresas secundárias;
- `empresaprimaria`: organização proprietária da operação;
- `empresasecundario`: empresas e unidades organizacionais atendidas;
- `zeladorx`: parâmetros globais e contexto comum da plataforma;
- `notifications`: infraestrutura de notificações e e-mails.

### Apps próprios do ChatChannels

- `chat`: salas, membros, mensagens, presença e comunicação em tempo real;
- `attachments`: arquivos vinculados às mensagens;
- `message`: camada auxiliar/legada de mensagens;
- `authenticate`: entrada, saída e recuperação de senha;
- `utils`: geração de identificadores e utilitários locais.

> O `manage.py` inicia o projeto por `mysite.settings`. O `settings.py` da raiz preserva grande parte da configuração da aplicação irmã, enquanto `mysite/settings.py` contém a configuração ativa e enxuta do ChatChannels.

---

## Como funciona

1. O colaborador entra com a mesma identidade corporativa usada no ecossistema ZeladorX.
2. A aplicação carrega as salas disponíveis e a contagem de mensagens não lidas.
3. O usuário cria uma sala pública ou privada e adiciona participantes.
4. Ao abrir uma sala, o navegador estabelece uma conexão WebSocket autenticada.
5. O servidor valida o acesso e envia as 50 mensagens mais recentes.
6. Novas mensagens e anexos são persistidos no PostgreSQL e distribuídos imediatamente aos participantes conectados.
7. Indicadores de digitação, leitura, entrada, saída e exclusão são propagados em tempo real.

---

## Funcionalidades

- autenticação corporativa por e-mail;
- recuperação de senha por token;
- criação e edição de salas públicas ou privadas;
- inclusão, remoção, saída e pesquisa de participantes;
- validação de acesso antes de aceitar a conexão em salas privadas;
- mensagens em tempo real com confirmação visual imediata;
- histórico das 50 mensagens mais recentes ao entrar na sala;
- indicador de usuário digitando e registro de última atividade;
- controle de mensagens lidas e contadores de não lidas;
- atualização automática e reordenação da lista de conversas;
- anexos de imagem, vídeo, áudio, PDF e outros documentos;
- até 5 anexos por mensagem e limite de 10 MB por arquivo;
- exclusão lógica de mensagens;
- identificação pública de salas por `id_random`, sem expor a chave numérica interna;
- estatísticas e consulta de membros por sala.

---

## Módulos

| Módulo | Responsabilidade |
|---|---|
| `chat/` | Núcleo do produto: salas, associações, mensagens, WebSockets e atividades |
| `attachments/` | Upload, validação, classificação e armazenamento de arquivos |
| `authenticate/` | Login, logout e redefinição de senha |
| `gerente/` | Modelo de usuário corporativo compartilhado |
| `empresaprimaria/` | Empresa principal da estrutura organizacional |
| `empresasecundario/` | Empresas vinculadas aos usuários |
| `zeladorx/` | Parâmetros e contexto global compartilhados |
| `notifications/` | Notificações e envio de e-mails |
| `mysite/` | Configuração ativa, rotas HTTP, ASGI e publicação |

---

## Arquitetura em tempo real

O acesso HTTP tradicional é atendido pelo Django. As conversas usam Django Channels sobre WebSockets e são iniciadas pelo Daphne.

```text
Navegador
   ├── HTTP/HTTPS ──▶ Django ──▶ autenticação, páginas e ações de sala
   └── WebSocket ──▶ Daphne/Channels ──▶ ChatConsumer
                                         ├── valida acesso
                                         ├── persiste mensagem/anexo
                                         ├── transmite à sala
                                         └── atualiza não lidas/presença
```

A conexão usa o endereço `ws/chat/<id_random>/`. Cada sala possui um grupo próprio (`chat_<id>`) e cada usuário conectado possui um canal pessoal (`user_<id>`) para notificações e contadores.

> O projeto está configurado atualmente com `InMemoryChannelLayer`. Essa opção funciona em uma única instância. Para múltiplas instâncias de produção, use uma camada compartilhada compatível com Channels, como Redis.

---

## Banco e migrações compartilhados

O ChatChannels e o ZeladorX apontam para a mesma base PostgreSQL e mantêm cópias dos apps e migrações comuns. Isso permite reconhecer os mesmos usuários e empresas, mas exige coordenação rigorosa.

### Regras de manutenção

1. **Não crie migrações concorrentes** para o mesmo app nos dois repositórios.
2. Antes de alterar um modelo compartilhado, compare os arquivos de `migrations/` dos dois projetos.
3. A mesma migração de um app comum deve manter o mesmo nome, dependências e conteúdo em ambos.
4. Teste a compatibilidade das duas aplicações antes de remover ou renomear campos.
5. Publique primeiro a alteração compatível com o esquema atual, aplique a migração e só depois remova dependências antigas.
6. Execute `migrate` por um fluxo de publicação controlado; não trate cada repositório como dono independente do esquema.
7. Mantenha `DATABASE_URL_DEV` e `DATABASE_URL_PROD` apontando apenas para os ambientes correspondentes.

Uma mudança nos apps `gerente`, `empresaprimaria`, `empresasecundario`, `zeladorx` ou `notifications` deve ser considerada uma mudança em **toda a família de aplicações**.

---

## Stack técnica

### Backend

- Python 3.11+
- Django 5.2
- Django Channels 4
- Daphne / ASGI
- Django REST Framework
- PostgreSQL (`psycopg2`)

### Frontend

- Templates Django
- JavaScript com WebSocket API nativa
- HTML5 e CSS3

### Infraestrutura

- Google Cloud Storage para mídia e arquivos estáticos
- Heroku para publicação
- SMTP para notificações e recuperação de senha

---

## Instalação local

### Pré-requisitos

- Python 3.11 ou superior;
- PostgreSQL;
- credenciais próprias de armazenamento;
- variáveis de ambiente de desenvolvimento.

```bash
git clone https://github.com/Markosalves12/CHATCHANNELS.git
cd CHATCHANNELS
python -m venv .venv
```

Ative o ambiente virtual:

```bash
# Linux/macOS
source .venv/bin/activate

# Windows
.venv\Scripts\activate
```

Instale e execute:

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Para validar o servidor ASGI localmente:

```bash
daphne mysite.asgi:application --port 8000 --bind 0.0.0.0
```

> Antes de executar migrações, confirme que elas estão sincronizadas com o ZeladorX e use uma base local/de desenvolvimento — nunca a base de produção.

---

## Variáveis de ambiente

Crie um `.env` local, sem adicioná-lo ao Git:

```env
DATABASE_URL_DEV=postgres://usuario:senha@host:5432/banco_dev
DATABASE_URL_PROD=postgres://usuario:senha@host:5432/banco_prod
EMAIL_HOST=smtp.exemplo.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_USE_SSL=False
EMAIL_HOST_USER=usuario
EMAIL_HOST_PASSWORD=senha
```

As credenciais do Google Cloud devem ser fornecidas pelo ambiente de publicação ou por um arquivo local ignorado pelo Git. Nunca versione chaves privadas.

---

## Deploy

O `Procfile` inicia a aplicação com Daphne:

```text
web: daphne mysite.asgi:application --port $PORT --bind 0.0.0.0 -v2
```

Antes de publicar:

1. confira as migrações compartilhadas;
2. configure banco, e-mail e armazenamento;
3. execute as verificações de segurança do Django;
4. aplique as migrações uma única vez;
5. valide login, sala privada, mensagem, anexo e reconexão WebSocket.

---

## Demonstração

O repositório inclui `demonstracao.mp4` e as capturas `P1.png`, `P2.png` e `P3.png` com o fluxo visual da aplicação.

---

## Segurança

- não publique `.env`, chaves de serviço ou senhas;
- mantenha `SECRET_KEY` exclusivamente em variável de ambiente;
- use `DEBUG=False` fora do desenvolvimento;
- restrinja `ALLOWED_HOSTS` aos domínios reais;
- valide origem, autenticação e participação em toda conexão WebSocket;
- rotacione imediatamente qualquer credencial que tenha sido versionada;
- remova segredos também do histórico Git, não apenas do commit mais recente.

> **Atenção:** este repositório contém atualmente um `.env` e um arquivo de chave de serviço do Google Cloud versionados. Considere essas credenciais comprometidas: revogue-as, gere novas credenciais, remova os arquivos do histórico e adicione-os ao `.gitignore`.

---

## Repositório relacionado

- [ZeladorX](https://github.com/Markosalves12/zeladorxV2) — gestão completa de zeladoria, jardinagem e limpeza predial, organizada por um Kanban operacional de seis estágios.

---

O ChatChannels transforma a base corporativa do ZeladorX em um canal de comunicação integrado, preservando usuários, empresas e contexto operacional enquanto adiciona colaboração instantânea em tempo real.
