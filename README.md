# Furiosa Bot - Telegram 🐾🔥

Bot de Telegram desenvolvido como parte do Challenge #1 (Experiência Conversacional FURIA) do processo seletivo para Assistente de Engenharia de Software.

## Descrição

Este bot fornece informações atualizadas sobre o time de CS da FURIA, notícias, agenda de jogos (FURIA e geral) e mais, diretamente no Telegram. Ele responde a comandos específicos e também entende algumas perguntas em linguagem natural através da integração com o Google Dialogflow ES.

## Funcionalidades Principais

O bot consegue:

- **Saudação e Ajuda:** Cumprimentar usuários (`oi`, `bom dia`) e explicar suas funções (`/help`, `/ajuda`, "o que você faz?").
- **Próximo Jogo (FURIA):** Informar sobre a próxima partida agendada (`/proximojogo`, "próximo jogo?").
- **Último Jogo (FURIA):** Mostrar o resultado da última partida finalizada (`/ultimojogo`, "último resultado?"). _(Nota: Pode não encontrar jogos mais antigos devido à forma como a busca é feita - veja Limitações)._
- **Line-up (FURIA):** Listar os jogadores e membros ativos da equipe (`/line_up`, "qual a line?").
- **Campeonatos (FURIA):** Listar torneios em andamento ou próximos que a FURIA participa. Se não encontrar específicos, mostra um panorama geral (`/campeonatos`, "campeonatos da furia?").
- **Estatísticas Anuais (FURIA):** Mostrar um resumo e resultados principais de um ano específico (Dados estáticos de 2017-2024) (`/stats ANO`, "stats furia 2022?").
- **Jogos de Hoje (Geral):** Apresentar a agenda geral de jogos de CS (ao vivo e agendados) para o dia atual (`/jogos_hoje`, "jogos hoje?").
- **Notícias (FURIA):** Buscar as últimas notícias sobre a FURIA em feeds RSS de portais de e-sports (`/noticias`, "notícias da furia?").
- **Links Sociais:** Fornecer links oficiais da organização (`/social`, `/links`, `/redes`).

## Tecnologias Utilizadas

- **Linguagem:** Python 3
- **Biblioteca Telegram:** `python-telegram-bot`
- **Requisições API:** `httpx`
- **NLU (Natural Language Understanding):** Google Dialogflow ES
- **Bibliotecas Auxiliares:** `python-dotenv`, `feedparser`, `google-cloud-dialogflow`, `pytz`
- **Gerenciador de Ambiente:** `pipenv`
- **APIs Externas:** PandaScore API (Jogos, Times, Torneios), Feeds RSS ([HLTV]), Dados Estáticos (para `/stats`).

## Configuração e Instalação

**Pré-requisitos:**

- Python 3.11.4+ (ou a versão que você usou)
- `pipenv` instalado globalmente (`pip install pipenv`)

**Passos:**

1.  **Clone o Repositório:**

    ```bash
    git clone [https://github.com/lilkirito22/Furiosa_Bot.git](https://github.com/lilkirito22/Furiosa_Bot.git)
    cd [Furiosa-Bot]
    ```

2.  **Instale as Dependências:**

    ```bash
    pipenv install
    ```

3.  **Configure as Variáveis de Ambiente:**

    - Crie um arquivo chamado `.env` na raiz do projeto.
    - Use o arquivo `.env.example` como modelo (crie este arquivo com a estrutura abaixo, mas sem suas chaves reais!).
    - Preencha os valores das seguintes variáveis no arquivo `.env`:
      - `TELEGRAM_BOT_TOKEN`: Token do seu bot obtido via @BotFather no Telegram.
      - `PANDASCORE_API_KEY`: Sua chave de API obtida no site da PandaScore.
      - `GOOGLE_APPLICATION_CREDENTIALS`: O caminho **completo e entre aspas** para o arquivo JSON da chave da sua Conta de Serviço do Google Cloud (ex: `"C:/Users/SeuUser/Keys/meu-bot-dialogflow.json"` ou `"/home/user/keys/meu-bot-dialogflow.json"`). **NÃO adicione o arquivo JSON ao Git! Adicione o nome dele ao `.gitignore`.**
      - `GOOGLE_PROJECT_ID`: O ID do seu projeto no Google Cloud onde o agente Dialogflow está hospedado (ex: `furiabotnlu-9wag`).

    **Estrutura do `.env.example`:**

    ```dotenv
    # Telegram Bot Token from BotFather
    TELEGRAM_BOT_TOKEN=COLOQUE_SEU_TOKEN_AQUI

    # PandaScore API Key
    PANDASCORE_API_KEY=COLOQUE_SUA_CHAVE_PANDASCORE_AQUI

    # Google Cloud Service Account Key File Path (for Dialogflow)
    # Example: "/path/to/your/service-account-key.json" or "C:/path/to/your/key.json"
    GOOGLE_APPLICATION_CREDENTIALS="COLOQUE_O_CAMINHO_COMPLETO_PARA_SUA_CHAVE_JSON_AQUI"

    # Google Cloud Project ID hosting Dialogflow Agent
    GOOGLE_PROJECT_ID=COLOQUE_O_ID_DO_SEU_PROJETO_GOOGLE_CLOUD_AQUI
    ```

4.  **Configure o Agente Dialogflow ES:**
    - É necessário ter um agente Dialogflow ES criado no Google Cloud Project (`GOOGLE_PROJECT_ID`).
    - Idioma do agente: `pt-br`.
    - Crie/verifique as seguintes **Intenções** (com frases de treinamento apropriadas): `Greeting`, `GetBotCapabilities`, `BuscarJogosHoje`, `GetNextMatch`, `GetLastMatchResult`, `FuriaTourments`, `GetTeamStatsByYear` (com parâmetro `year` [@sys.number], obrigatório, com prompts), `GetNews`, `GetSocialLinks`. [Ajuste esta lista se criou intenções com nomes diferentes].
    - Crie uma **Conta de Serviço** no Google Cloud IAM com o papel "Cliente da API do Dialogflow" (Dialogflow API Client) e gere a chave JSON referenciada em `GOOGLE_APPLICATION_CREDENTIALS`.

## Executando o Bot

1.  **Ative o Ambiente Virtual (opcional, mas recomendado):**
    ```bash
    pipenv shell
    ```
2.  **Inicie o Bot:**
    ```bash
    python furia_bot.py
    ```
    (Se não ativou o shell no passo anterior, use `pipenv run python furia_bot.py`)

O bot começará a escutar por mensagens no Telegram.

## Limitações Conhecidas e Melhorias Futuras

- **`/ultimojogo`:** A busca pelo último jogo consulta apenas os ~50 jogos mais recentes finalizados globalmente na API PandaScore e filtra pela FURIA no lado do cliente. Jogos mais antigos que isso (ex: >20 dias, dependendo da atividade global) podem não ser encontrados. Melhorias: Implementar paginação na busca ou investigar filtros de API mais específicos para o endpoint `/past`, se existirem.
- **`/stats <ano>`:** Os dados de estatísticas anuais são atualmente estáticos (2017-2024). Melhoria: Integrar com o endpoint de estatísticas por time da PandaScore API (`/csgo/teams/{id}/stats`).
- **Notícias:** A busca de notícias depende da disponibilidade e formato correto dos Feeds RSS configurados. Se um feed estiver offline ou mal formatado, as notícias daquela fonte não aparecerão.
- **NLU:** O entendimento de linguagem natural está focado nas intenções implementadas. Poderia ser expandido para cobrir mais perguntas (ex: stats de jogadores, H2H) e usar contextos do Dialogflow para conversas mais profundas.
- **Outras Ideias:** Adicionar placares ao vivo, ranking da equipe, informações detalhadas de jogadores, etc.

## Autor

[Daniel Chaves Castro]
[Link para seu GitHub: https://github.com/lilkirito22]
[https://www.linkedin.com/in/daniel-chaves-castro/]
