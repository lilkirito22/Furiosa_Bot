import os
import logging
import httpx
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from dotenv import load_dotenv
import datetime
import pytz
import asyncio
from google.cloud import dialogflow_v2 as dialogflow
import uuid

# Carregue as variáveis do arquivo .env (opcional, veja abaixo)
load_dotenv()


# Configure o logging para ver erros
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Aqui estao as keys devidamente protegidas
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
PANDASCORE_API_KEY = os.getenv("PANDASCORE_API_KEY")
GOOGLE_PROJECT_ID = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
GOOGLE_PROJECT_ID = os.getenv("GOOGLE_PROJECT_ID")
# id da fnatic para testes 3217
# FURIA_TEAM_ID = 124530
FURIA_TEAM_ID = 124530

# Verifica se o token do bot foi carregado corretamente

if BOT_TOKEN is None:
    logger.error("Erro: Variável de ambiente TELEGRAM_BOT_TOKEN não definida!")
    # Você pode querer sair do script aqui ou lançar uma exceção mais específica
    exit("Por favor, defina a variável de ambiente TELEGRAM_BOT_TOKEN.")

if PANDASCORE_API_KEY is None:
    logger.error("Erro: Variável de ambiente PANDASCORE_API_KEY não definida!")
    # Considere o que fazer aqui - talvez o bot funcione parcialmente?
    # Por enquanto, vamos sair se não tiver a chave da PandaScore.
    exit("Por favor, defina a variável de ambiente PANDASCORE_API_KEY.")

PANDASCORE_BASE_URL = "https://api.pandascore.co"

# Dicionário para armazenar estatísticas (por enquanto, estático)
# A chave é o ano (inteiro)

# (Coloque isso antes das suas funções de comando como start, proximo_jogo, etc.)


# --- Dialogflow Helper ---
async def detect_intent_text(
    project_id: str, session_id: str, text: str, language_code: str = "pt-br"
) -> str | None:
    """
    Envia o texto do usuário para a API do Dialogflow e retorna o nome da intenção detectada.

    Args:
        project_id: O ID do seu projeto no Google Cloud.
        session_id: Um ID único para esta conversa/usuário (ex: ID do usuário Telegram).
        text: O texto da mensagem do usuário.
        language_code: O código do idioma do agente Dialogflow.

    Returns:
        O nome de exibição da intenção detectada (ex: "BuscarJogosHoje") ou None se ocorrer erro.
    """

    # 1. Criar o Cliente de Sessão:
    #    A biblioteca usa automaticamente as credenciais encontradas via
    #    a variável de ambiente GOOGLE_APPLICATION_CREDENTIALS para se autenticar.
    try:
        session_client = dialogflow.SessionsAsyncClient()
    except Exception as e:
        logger.exception(
            "ERRO DIALOGFLOW: Falha ao criar o SessionsAsyncClient. Verifique as credenciais."
        )
        return None

    # 2. Definir o Caminho da Sessão:
    #    Identifica unicamente esta sessão de conversa dentro do seu projeto.
    session_path = session_client.session_path(project_id, session_id)
    logger.debug(f"Dialogflow session path: {session_path}")

    if not text:
        return None

    # 3. Preparar a Entrada de Texto:
    #    Empacota o texto do usuário no formato que a API espera.
    text_input = dialogflow.TextInput(text=text, language_code=language_code)
    query_input = dialogflow.QueryInput(text=text_input)

    # 4. Chamar a API detect_intent:
    #    Envia a consulta para o Dialogflow e espera a resposta.
    try:
        logger.info(f"Enviando para Dialogflow (Projeto: {project_id}): '{text}'")
        response = await session_client.detect_intent(
            request={"session": session_path, "query_input": query_input}
        )

        # 5. Processar a Resposta:
        query_result = response.query_result
        intent_name = query_result.intent.display_name
        confidence = query_result.intent_detection_confidence

        logger.info(
            f"Dialogflow detectou: Intenção='{intent_name}', Confiança={confidence:.2f}"
        )

        # Poderíamos adicionar um limite de confiança, mas por enquanto retornamos o que foi detectado.
        return intent_name

    except Exception as e:
        # Captura erros durante a chamada à API (rede, autenticação talvez?)
        logger.exception(
            f"ERRO DIALOGFLOW: Falha na chamada detect_intent para o texto '{text}'"
        )
        return None


# --- Fim Dialogflow Helper ---

# --- Funções Auxiliares para API PandaScore ---


def get_today_utc_date_str() -> str:
    """Retorna a data de hoje no formato YYYY-MM-DD (UTC)."""
    today_utc = datetime.datetime.now(pytz.utc)
    return today_utc.strftime("%Y-%m-%d")


def format_match_data_geral(
    match_data: dict, fuso_horario_local: str = "America/Fortaleza"
) -> str:
    """Formata os dados de uma única partida (geral) para exibição."""
    nome_jogo = match_data.get("name", "Jogo sem nome")
    torneio = match_data.get("league", {}).get("name", "Torneio desconhecido")
    status = match_data.get("status", "desconhecido")
    data_inicio_str = match_data.get("begin_at")
    oponentes = match_data.get("opponents", [])
    results = match_data.get("results", [])  # Para o placar

    # Extrai nomes dos oponentes
    time_a_nome = "Time A?"
    time_b_nome = "Time B?"
    time_a_id = None
    time_b_id = None
    if len(oponentes) >= 1:
        time_a_data = oponentes[0].get("opponent", {})
        time_a_nome = time_a_data.get("name", time_a_nome)
        time_a_id = time_a_data.get("id")
    if len(oponentes) >= 2:
        time_b_data = oponentes[1].get("opponent", {})
        time_b_nome = time_b_data.get("name", time_b_nome)
        time_b_id = time_b_data.get("id")

    # Formata hora local
    data_formatada = "Hora indefinida"
    if data_inicio_str:
        try:
            data_inicio_dt_utc = datetime.datetime.fromisoformat(
                data_inicio_str.replace("Z", "+00:00")
            )
            fuso_local = pytz.timezone(fuso_horario_local)
            data_local = data_inicio_dt_utc.astimezone(fuso_local)
            data_formatada = data_local.strftime("%H:%M")
        except Exception as e:
            logger.error(
                f"Erro ao formatar data '{data_inicio_str}' para {fuso_horario_local}: {e}"
            )
            data_formatada = "Hora?"

    status_emoji = (
        "⏳"
        if status == "not_started"
        else "🔴" if status == "running" else "✅" if status == "finished" else "❓"
    )
    status_texto = status.replace("_", " ").capitalize()

    # Pega placar - VERIFICAR SE A ORDEM DOS 'results' CORRESPONDE À ORDEM DOS 'opponents'
    placar_str = ""
    if (status == "running" or status == "finished") and len(results) == 2:
        # Assumindo que results[0] é do opponents[0] e results[1] do opponents[1]
        # A API PODE NÃO GARANTIR ISSO! Precisa testar.
        score_a = results[0].get("score", "?")
        score_b = results[1].get("score", "?")
        placar_str = f" ({score_a} x {score_b})"
        # Uma forma mais segura seria verificar o team_id dentro de results, se ele existir lá
        # Ex: score_a = next((r['score'] for r in results if r.get('team_id') == time_a_id), '?')

    return (
        f"🆚 **{time_a_nome} vs {time_b_nome}**{placar_str}\n"
        f"   🕒 {data_formatada} | {status_texto} {status_emoji}\n"
        f"   🏆 {torneio}"
    )


def format_tournament_data(
    tournament_data: dict, fuso_horario_local: str = "America/Fortaleza"
) -> str:
    """Formata os dados de um único torneio para exibição."""
    nome = tournament_data.get("name", "Nome Indefinido")
    serie = tournament_data.get("serie", {}).get(
        "full_name", ""
    )  # Nome completo da série (inclui ano/temporada)
    tier = tournament_data.get(
        "tier"
    )  # Tier pode indicar importância (S, A, B, C, D...)
    begin_at_str = tournament_data.get("begin_at")
    end_at_str = tournament_data.get("end_at")
    status = tournament_data.get(
        "status", "?"
    )  # A API pode ter um status para torneios também

    # Formata datas
    data_inicio_fmt = "?"
    data_fim_fmt = "?"
    try:
        if begin_at_str:
            dt_inicio = datetime.datetime.fromisoformat(
                begin_at_str.replace("Z", "+00:00")
            )
            data_inicio_fmt = dt_inicio.strftime("%d/%m/%Y")
        if end_at_str:
            dt_fim = datetime.datetime.fromisoformat(end_at_str.replace("Z", "+00:00"))
            data_fim_fmt = dt_fim.strftime("%d/%m/%Y")
    except Exception as e:
        logger.warning(f"Erro ao formatar datas do torneio {nome}: {e}")

    tier_str = f" (Tier: {tier.upper()})" if tier else ""  # Adiciona o Tier se existir

    return (
        f"🏆 **{serie or nome}**{tier_str}\n" f"   🗓️ {data_inicio_fmt} a {data_fim_fmt}"
    )


async def buscar_jogos_correndo_api() -> list[dict]:
    """
    Busca jogos que estão atualmente 'running' na API PandaScore.
    Retorna a lista de partidas encontradas.
    """
    endpoint_jogos_correndo = f"{PANDASCORE_BASE_URL}/csgo/matches/running"
    headers = {
        "Authorization": f"Bearer {PANDASCORE_API_KEY}",
        "Accept": "application/json",
    }
    # Ordenar pelos mais recentes ou por importância? Ordenar por início é padrão.
    params = {
        "page[size]": 30,
        "sort": "-begin_at",
    }  # Pega até 30 jogos correndo, mais recentes primeiro

    try:
        async with httpx.AsyncClient() as client:
            logger.info(
                f"Chamando API (Jogos Correndo - Geral): {endpoint_jogos_correndo}"
            )
            response = await client.get(
                endpoint_jogos_correndo, headers=headers, params=params
            )
            if response.status_code >= 400:
                logger.error(
                    f"Erro HTTP {response.status_code} ao buscar jogos correndo: {response.text}"
                )
                return []  # Retorna lista vazia em caso de erro
            lista_jogos = response.json()
            logger.info(f"API retornou {len(lista_jogos)} jogos 'running'.")
            return lista_jogos if lista_jogos else []
    except Exception as exc:
        logger.error(f"Erro ao buscar/processar jogos correndo: {exc}", exc_info=True)
        return []


async def buscar_jogos_proximos_hoje_api() -> list[dict]:
    """
    Busca jogos agendados para começar hoje (UTC) na API PandaScore.
    Usa filtro de data na API.
    Retorna a lista de partidas encontradas.
    """
    endpoint_proximos_jogos = f"{PANDASCORE_BASE_URL}/csgo/matches/upcoming"
    headers = {
        "Authorization": f"Bearer {PANDASCORE_API_KEY}",
        "Accept": "application/json",
    }
    today_utc_str = get_today_utc_date_str()
    params = {
        "sort": "begin_at",  # Ordena pelos mais próximos primeiro
        "filter[begin_at]": today_utc_str,
        "page[size]": 50,  # Pega até 50 jogos agendados para hoje
    }

    try:
        async with httpx.AsyncClient() as client:
            logger.info(
                f"Chamando API (Próximos de Hoje - Geral): {endpoint_proximos_jogos} com params: {params}"
            )
            response = await client.get(
                endpoint_proximos_jogos, headers=headers, params=params
            )
            if response.status_code >= 400:
                logger.error(
                    f"Erro HTTP {response.status_code} ao buscar próximos jogos de hoje: {response.text}"
                )
                return []
            lista_jogos = response.json()
            logger.info(
                f"API retornou {len(lista_jogos)} jogos 'upcoming' para hoje ({today_utc_str})."
            )
            return lista_jogos if lista_jogos else []
    except Exception as exc:
        logger.error(
            f"Erro ao buscar/processar próximos jogos de hoje: {exc}", exc_info=True
        )
        return []


async def buscar_proximo_jogo_furia_api() -> str:
    """
    Busca o próximo jogo da FURIA CS usando a API PandaScore.
    Como o filtro direto por time não funciona no endpoint /upcoming,
    busca uma lista de jogos futuros e filtra no lado do cliente.
    Retorna uma string formatada ou uma mensagem de erro/não encontrado.
    """
    endpoint_proximos_jogos = f"{PANDASCORE_BASE_URL}/csgo/matches/upcoming"

    headers = {
        "Authorization": f"Bearer {PANDASCORE_API_KEY}",
        "Accept": "application/json",
    }

    # Parâmetros: Ordenar por data e pegar um lote maior (ex: 50)
    # REMOVEMOS o filtro de time daqui!
    params = {
        "sort": "begin_at",
        "page[size]": 50,  # Pega os próximos 50 jogos para procurar a FURIA
    }

    try:
        async with httpx.AsyncClient() as client:
            logger.info(
                f"Chamando API PandaScore (sem filtro de time): {endpoint_proximos_jogos} com params: {params}"
            )
            response = await client.get(
                endpoint_proximos_jogos, headers=headers, params=params
            )
            response.raise_for_status()

            logger.info(f"Resposta da API recebida: Status {response.status_code}")
            lista_jogos = response.json()

            if not lista_jogos:
                logger.info("API não retornou nenhum jogo futuro.")
                return "⚫ Nenhum jogo futuro encontrado na API no momento."

            # --- Filtragem no Lado do Cliente ---
            proximo_jogo_furia = None
            for jogo in lista_jogos:
                oponentes = jogo.get("opponents", [])
                encontrou_furia = False
                for oponente_info in oponentes:
                    opponent_data = oponente_info.get("opponent", {})
                    if opponent_data.get("id") == FURIA_TEAM_ID:
                        encontrou_furia = True
                        break  # Achou a FURIA neste jogo, pode parar de verificar oponentes

                if encontrou_furia:
                    proximo_jogo_furia = jogo  # Guarda o objeto do jogo encontrado
                    logger.info(
                        f"Próximo jogo da FURIA encontrado: ID {jogo.get('id')}"
                    )
                    break  # Para o loop principal, já achamos o primeiro jogo da FURIA

            # Verifica se encontramos um jogo da FURIA na lista
            if proximo_jogo_furia is None:
                logger.info(
                    f"FURIA não encontrada nos próximos {len(lista_jogos)} jogos retornados pela API."
                )
                return "⚫ Não encontrei jogos da FURIA agendados proximamente."

            # --- Processamento do Jogo Encontrado (igual a antes) ---
            # Extrai as informações do proximo_jogo_furia
            nome_jogo = proximo_jogo_furia.get("name", "Jogo sem nome")
            torneio = proximo_jogo_furia.get("league", {}).get(
                "name", "Torneio desconhecido"
            )
            serie = proximo_jogo_furia.get("serie", {}).get("full_name", "")
            data_inicio_str = proximo_jogo_furia.get("begin_at")
            oponentes_furia = proximo_jogo_furia.get(
                "opponents", []
            )  # Oponentes do jogo encontrado
            status = proximo_jogo_furia.get("status", "desconhecido")

            adversario_nome = "Adversário indefinido"
            if len(oponentes_furia) == 2:
                for oponente in oponentes_furia:
                    opponent_data = oponente.get("opponent", {})
                    if opponent_data.get("id") != FURIA_TEAM_ID:
                        adversario_nome = opponent_data.get("name", adversario_nome)
                        break

            data_formatada = "Data indefinida"
            if data_inicio_str:
                try:
                    data_inicio_dt_utc = datetime.datetime.fromisoformat(
                        data_inicio_str.replace("Z", "+00:00")
                    )
                    fuso_fortaleza = pytz.timezone("America/Fortaleza")
                    data_local = data_inicio_dt_utc.astimezone(fuso_fortaleza)
                    data_formatada = data_local.strftime("%d/%m/%Y às %H:%M")
                except (ValueError, TypeError, pytz.UnknownTimeZoneError) as e:
                    logger.error(f"Erro ao formatar data '{data_inicio_str}': {e}")
                    data_formatada = data_inicio_str

            status_emoji = (
                "⏳"
                if status == "not_started"
                else (
                    "🔴"
                    if status == "running"
                    else "✅" if status == "finished" else ""
                )
            )

            resposta_formatada = (
                f"📅 **Próximo Jogo da FURIA** 📅\n\n"
                f"**Partida:** FURIA vs {adversario_nome}\n"
                f"({nome_jogo})\n"
                f"**Torneio:** {torneio}\n"
                f"**Data:** {data_formatada} (Horário de Fortaleza)\n"
                f"**Status:** {status.replace('_', ' ').capitalize()} {status_emoji}"
            )
            return resposta_formatada

    # ... (Blocos except continuam iguais) ...
    except httpx.HTTPStatusError as exc:
        logger.error(
            f"Erro HTTP ao buscar lista de jogos ({exc.response.status_code}): {exc.request.url} - Resposta: {exc.response.text}"
        )
        return "❌ Erro ao buscar lista de jogos na API (HTTP)."
    except httpx.RequestError as exc:
        logger.error(
            f"Erro de Conexão/Requisição ao buscar lista de jogos: {exc.request.url} - {exc}"
        )
        return "❌ Erro de conexão ao tentar buscar lista de jogos."
    except Exception as exc:
        logger.error(
            f"Erro inesperado ao processar lista de jogos: {exc}", exc_info=True
        )
        return "😵 Ocorreu um erro inesperado ao processar a lista de jogos."


async def buscar_lineup_furia_api() -> str:
    """
    Busca os detalhes da equipe FURIA na API PandaScore para extrair a line-up ativa.
    Retorna uma string formatada com a line-up ou uma mensagem de erro.
    """
    # Endpoint para buscar detalhes de um time específico de CSGO
    # Verifique se /csgo/teams/{id} é o correto ou apenas /teams/{id}
    # endpoint_detalhes_time = f"{PANDASCORE_BASE_URL}/csgo/teams/{FURIA_TEAM_ID}"
    endpoint_detalhes_time = f"{PANDASCORE_BASE_URL}/teams/{FURIA_TEAM_ID}"

    headers = {
        "Authorization": f"Bearer {PANDASCORE_API_KEY}",
        "Accept": "application/json",
    }

    # Geralmente não são necessários parâmetros para buscar por ID no path
    params = {}

    try:
        async with httpx.AsyncClient() as client:
            logger.info(f"Chamando API PandaScore: {endpoint_detalhes_time}")
            response = await client.get(
                endpoint_detalhes_time, headers=headers, params=params
            )
            response.raise_for_status()  # Verifica erros HTTP

            logger.info(f"Resposta da API recebida: Status {response.status_code}")
            dados_time = response.json()

            if not dados_time:
                logger.warning("API não retornou dados para o ID da FURIA.")
                return "Não foi possível obter os dados da equipe FURIA."

            # Extrai a lista de jogadores
            jogadores_lista = dados_time.get("players", [])

            if not jogadores_lista:
                logger.warning(
                    "Lista de jogadores vazia ou não encontrada nos dados da FURIA."
                )
                return "Não encontrei a lista de jogadores para a FURIA."

            # Filtra apenas jogadores ativos e pega seus nomes
            lineup_ativa_nomes = []
            for jogador in jogadores_lista:
                if jogador.get("active") is True:
                    nome_jogador = jogador.get("name", "Nome Desconhecido")
                    lineup_ativa_nomes.append(nome_jogador)

            if not lineup_ativa_nomes:
                return "Não encontrei jogadores ativos listados para a FURIA."

            # Formata a resposta
            # Opcional: Adicionar emoji ou formatação HTML
            resposta_formatada = (
                f"🐾 **Line-up Ativa da FURIA** 🐾\n\n"
                f"{' | '.join(lineup_ativa_nomes)}\n\n"
                f"_(Nota: Pode incluir técnico/outros membros ativos)_"
            )
            return resposta_formatada

    except httpx.HTTPStatusError as exc:
        logger.error(
            f"Erro HTTP ao buscar detalhes da FURIA ({exc.response.status_code}): {exc.request.url} - Resposta: {exc.response.text}"
        )
        return "❌ Erro ao buscar informações da line-up na API (HTTP)."
    except httpx.RequestError as exc:
        logger.error(
            f"Erro de Conexão/Requisição ao buscar detalhes da FURIA: {exc.request.url} - {exc}"
        )
        return "❌ Erro de conexão ao tentar buscar a line-up."
    except Exception as exc:
        logger.error(
            f"Erro inesperado ao processar detalhes da FURIA: {exc}", exc_info=True
        )
        return "😵 Ocorreu um erro inesperado ao processar a line-up."


async def buscar_torneios_furia_api(limit_each: int = 15) -> list[dict]:
    """
    TENTA buscar torneios 'running' e 'upcoming' de CS onde a FURIA participa,
    usando um filtro de servidor (filter[teams.id]).
    Retorna uma lista combinada de dicionários de torneios se o filtro funcionar.
    """
    # --- ATENÇÃO: Tentativa de filtro. VERIFICAR SE FUNCIONA! ---
    # Palpite: A API pode permitir filtrar por ID dentro de uma lista de times associada ao torneio.
    parametro_filtro_time = "filter[teams.id]"  # ISSO É UM PALPITE! Pode dar erro 400.
    # --- Fim da Atenção ---

    endpoint_running = f"{PANDASCORE_BASE_URL}/csgo/tournaments/running"
    endpoint_upcoming = f"{PANDASCORE_BASE_URL}/csgo/tournaments/upcoming"
    headers = {
        "Authorization": f"Bearer {PANDASCORE_API_KEY}",
        "Accept": "application/json",
    }

    # Adiciona o filtro de time aos parâmetros
    params_base = {parametro_filtro_time: FURIA_TEAM_ID, "page[size]": limit_each}
    params_running = {**params_base, "sort": "-begin_at"}  # Mais recentes primeiro
    params_upcoming = {**params_base, "sort": "begin_at"}  # Mais próximos primeiro

    lista_combinada = []
    ids_adicionados = set()

    try:
        async with httpx.AsyncClient() as client:
            logger.info(
                f"Tentando buscar torneios da FURIA (running): {endpoint_running} com params: {params_running}"
            )
            logger.info(
                f"Tentando buscar torneios da FURIA (upcoming): {endpoint_upcoming} com params: {params_upcoming}"
            )

            responses = await asyncio.gather(
                client.get(endpoint_running, headers=headers, params=params_running),
                client.get(endpoint_upcoming, headers=headers, params=params_upcoming),
                return_exceptions=True,
            )

            # Processa resposta dos 'running'
            if (
                isinstance(responses[0], httpx.Response)
                and responses[0].status_code == 200
            ):
                torneios_running = responses[0].json()
                for torneio in torneios_running:
                    if torneio and torneio.get("id") not in ids_adicionados:
                        torneio["_list_status"] = "running"
                        lista_combinada.append(torneio)
                        ids_adicionados.add(torneio.get("id"))
                logger.info(
                    f"Encontrados {len(torneios_running)} torneios running (com filtro da FURIA)."
                )
            elif (
                isinstance(responses[0], httpx.Response)
                and responses[0].status_code == 400
            ):
                logger.error(
                    f"Erro 400 ao buscar torneios running com filtro {parametro_filtro_time}. Filtro provavelmente inválido."
                )
                # Poderíamos já mudar para a estratégia de cliente aqui, mas vamos tratar no handler por enquanto.
            elif isinstance(responses[0], Exception):
                logger.error(f"Erro ao buscar torneios running (Furia): {responses[0]}")
            elif isinstance(responses[0], httpx.Response):
                logger.error(
                    f"Erro HTTP {responses[0].status_code} ao buscar torneios running (Furia): {responses[0].text}"
                )

            # Processa resposta dos 'upcoming'
            if (
                isinstance(responses[1], httpx.Response)
                and responses[1].status_code == 200
            ):
                torneios_upcoming = responses[1].json()
                for torneio in torneios_upcoming:
                    if torneio and torneio.get("id") not in ids_adicionados:
                        torneio["_list_status"] = "upcoming"
                        lista_combinada.append(torneio)
                        ids_adicionados.add(torneio.get("id"))
                logger.info(
                    f"Encontrados {len(torneios_upcoming)} torneios upcoming (com filtro da FURIA)."
                )
            elif (
                isinstance(responses[1], httpx.Response)
                and responses[1].status_code == 400
            ):
                logger.error(
                    f"Erro 400 ao buscar torneios upcoming com filtro {parametro_filtro_time}. Filtro provavelmente inválido."
                )
            elif isinstance(responses[1], Exception):
                logger.error(
                    f"Erro ao buscar torneios upcoming (Furia): {responses[1]}"
                )
            elif isinstance(responses[1], httpx.Response):
                logger.error(
                    f"Erro HTTP {responses[1].status_code} ao buscar torneios upcoming (Furia): {responses[1].text}"
                )

            # Ordena a lista final pela data de início
            lista_combinada.sort(key=lambda t: t.get("begin_at", ""))

            return lista_combinada

    except Exception as exc:
        logger.error(f"Erro geral ao buscar torneios da Furia: {exc}", exc_info=True)
        return []


async def obter_e_formatar_jogos_hoje() -> str:
    """Busca jogos correndo e próximos de hoje e retorna a string formatada."""
    try:
        resultados = await asyncio.gather(
            buscar_jogos_correndo_api(), buscar_jogos_proximos_hoje_api()
        )
        jogos_correndo = resultados[0]
        jogos_proximos = resultados[1]

        if not jogos_correndo and not jogos_proximos:
            return (
                "⚫ Não encontrei jogos de CS correndo ou agendados para hoje na API."
            )

        mensagem_final = f"📅 **Jogos de CS para Hoje ({datetime.date.today().strftime('%d/%m')})** 📅\n"
        max_jogos_mostrar = 10

        if jogos_correndo:
            mensagem_final += "\n🔴 **Ao Vivo Agora:**\n"
            count = 0
            for jogo in jogos_correndo:
                # ... (lógica de formatação e limite como antes) ...
                if count >= max_jogos_mostrar:
                    mensagem_final += "_... e mais!_\n"
                    break
                mensagem_final += format_match_data_geral(jogo) + "\n\n"
                count += 1

        if jogos_proximos:
            # ... (lógica de filtro de duplicatas, formatação e limite como antes) ...
            mensagem_final += "\n⏳ **Agendados para Hoje:**\n"
            count = 0
            ids_correndo = {j.get("id") for j in jogos_correndo}
            jogos_proximos_filtrados = [
                j for j in jogos_proximos if j.get("id") not in ids_correndo
            ]
            for jogo in jogos_proximos_filtrados:
                if count >= max_jogos_mostrar:
                    mensagem_final += "_... e mais!_\n"
                    break
                mensagem_final += format_match_data_geral(jogo) + "\n\n"
                count += 1

        mensagem_final = mensagem_final.strip()

        if len(mensagem_final) <= len(
            f"📅 **Jogos de CS para Hoje ({datetime.date.today().strftime('%d/%m')})** 📅\n"
        ):
            return "⚫ Não encontrei jogos relevantes de CS para exibir hoje."

        return mensagem_final

    except Exception as e:
        logger.error(f"Erro ao obter e formatar jogos de hoje: {e}", exc_info=True)
        return "❌ Ocorreu um erro ao buscar a agenda geral de hoje."


# Atualiza o handler do comando /jogos_hoje para usar a nova função
async def jogos_hoje(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler para o comando /jogos_hoje."""
    await update.message.reply_text("Verificando a agenda geral de CS para hoje...")
    resultado_formatado = await obter_e_formatar_jogos_hoje()
    await update.message.reply_html(resultado_formatado)


# --- Fim das Funções Auxiliares ---


FURIA_STATS_DB = {
    2024: {
        "resumo": "Início de ano com mudanças na line-up e foco na reconstrução.",
        "principais_resultados": [
            "Classificação para o PGL Major Copenhagen 2024",
            "Participação IEM Katowice 2024",
            "Top 8 - GET Rio 2024",
        ],
        "titulos": 0,
    },
    2023: {
        "resumo": "Ano de participação nos dois Majors e título do Elisa Masters Espoo.",
        "principais_resultados": [
            "PGL Major Paris 2023: Challengers Stage",
            "IEM Rio Major 2023: Legends Stage",
            "Campeão - Elisa Masters Espoo 2023",
            "Vice - Pinnacle Cup V",
        ],
        "titulos": 1,  # Elisa Masters
    },
    2022: {
        "resumo": "Grande ano com semifinal no Major do Rio e boa performance geral.",
        "principais_resultados": [
            "IEM Rio Major 2022: Semifinalista (Top 4)",
            "PGL Major Antwerp 2022: Legends Stage",
            "Vice - ESL Challenger Valencia 2022",
            "Campeão - PGL RMR Americas",
        ],
        "titulos": 1,  # RMR (Considerado título?)
    },
    # Adicione mais anos se desejar
}


# Função para o comando /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Envia uma mensagem quando o comando /start é emitido."""
    user = update.effective_user
    # Mensagem de boas vindas um pouco mais temática
    await update.message.reply_html(
        f"Fala, {user.mention_html()}! Bem-vindo ao Furia Fan Bot! 🔥\n"
        f"Use os comandos para saber tudo sobre a Furia. #DIADEFURIA"
    )


# Função para lidar com erros
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Loga os erros causados por Updates."""
    logger.error("Exception while handling an update:", exc_info=context.error)
    # Opcional: informar o usuário que algo deu errado
    # if update and isinstance(update, Update) and update.message:
    #     await update.message.reply_text("Ocorreu um erro ao processar sua solicitação.")


# --- Manipulador de Mensagens de Texto ---
# ... (imports, constantes, outras funções como detect_intent_text, etc.) ...


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Processa mensagens de texto que NÃO são comandos.
    Envia o texto para o Dialogflow para detectar a intenção e responde adequadamente.
    """
    message_text = update.message.text
    user_id = str(update.message.from_user.id)
    user_first_name = (
        update.effective_user.first_name
    )  # Pega o primeiro nome do usuário

    logger.info(
        f"handle_message: Recebido texto='{message_text}' do user={user_first_name} (id={user_id})"
    )

    if not GOOGLE_PROJECT_ID:
        logger.warning("GOOGLE_PROJECT_ID não definido em handle_message.")
        return

    # Detecta a intenção via Dialogflow
    intent_name = await detect_intent_text(GOOGLE_PROJECT_ID, user_id, message_text)
    logger.info(f"handle_message: Intenção retornada='{intent_name}'")

    # --- Respostas baseadas na Intenção ---

    if intent_name == "BuscarJogosHoje":  # Intenção que já tínhamos
        logger.info("handle_message: Intenção 'BuscarJogosHoje' reconhecida.")
        await update.message.reply_text(
            "Entendi que você quer os jogos de hoje! Buscando..."
        )
        resultado_formatado = await obter_e_formatar_jogos_hoje()
        await update.message.reply_html(resultado_formatado)

    elif intent_name == "Greeting":  # <<< NOVA INTENÇÃO: Cumprimento >>>
        logger.info("handle_message: Intenção 'Greeting' reconhecida.")
        # Responde de forma personalizada usando o nome do usuário
        resposta_greeting = (
            f"Olá, {user_first_name}! 👋 Pronto para saber as novidades da FURIA?"
        )
        await update.message.reply_text(resposta_greeting)

    elif intent_name == "GetBotCapabilities":  # <<< NOVA INTENÇÃO: O que o bot faz >>>
        logger.info("handle_message: Intenção 'GetBotCapabilities' reconhecida.")
        # Monta a mensagem explicando as funções
        resposta_capabilities = """
Eu sou o Furia Fan Bot! 🔥 Posso te ajudar com:

📅 **Agenda de Hoje:** Me pergunte "quais os jogos de hoje?" para ver as partidas de CS rolando.
🐾 **Próximo Jogo da FURIA:** Use /proximojogo
👥 **Line-up Atual da FURIA:** Use /line_up
🏆 **Campeonatos:** Use /campeonatos para ver os torneios da FURIA.
📊 **Stats Anuais:** Use /stats ANO (ex: /stats 2023) para ver um resumo da FURIA naquele ano.

É só pedir ou usar os comandos! #DIADEFURIA
        """
        # Usamos reply_html para garantir que a formatação funcione, mesmo sem tags HTML explícitas aqui
        await update.message.reply_html(resposta_capabilities)

    # elif intent_name == "OutraIntencao":
    # Adicione mais 'elif' para outras intenções que criar
    # pass

    else:
        # Nenhuma intenção conhecida foi detectada
        logger.info(
            f"handle_message: Nenhuma ação definida para a intenção '{intent_name}'. Ignorando."
        )
        # Opcional: Responder com "Não entendi" apenas se a confiança for muito baixa ou for Fallback Intent
        # if intent_name == "Default Fallback Intent":
        #     await update.message.reply_text("Desculpe, não entendi direito. Pode tentar perguntar de outra forma?")
        pass  # Melhor não responder nada para não ser chato


# --- Fim do handle_message ---


async def proximo_jogo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Envia uma mensagem com o próximo jogo."""
    # Aqui você pode adicionar a lógica para obter o próximo jogo da Furia
    # Por enquanto, vamos apenas enviar uma mensagem de exemplo
    await update.message.reply_text("Buscando informações do próximo jogo...")
    # Chama a função que busca na API
    resultado = await buscar_proximo_jogo_furia_api()
    # Edita a mensagem anterior ou envia uma nova com o resultado
    # (Editar pode ser melhor para não poluir o chat)
    # Para editar, você precisaria guardar a mensagem enviada:
    # msg = await update.message.reply_text("Buscando...")
    # await msg.edit_text(resultado, parse_mode='HTML') # Se for HTML

    # Ou simplesmente envia a resposta (mais fácil para começar):
    await update.message.reply_html(
        resultado
    )  # Usar reply_html se a string tiver tags HTML


async def line_up(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Envia uma mensagem com a line up atual buscada da API."""
    await update.message.reply_text("Buscando a line-up atual da FURIA...")  # Feedback

    resultado_lineup = await buscar_lineup_furia_api()  # Chama a nova função

    # Envia o resultado formatado (ou a mensagem de erro)
    await update.message.reply_html(
        resultado_lineup
    )  # Usar reply_html se tiver formatação HTML


async def jogos_hoje(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Envia uma mensagem com os jogos gerais de CS de hoje (correndo e agendados)."""
    await update.message.reply_text("Verificando a agenda geral de CS para hoje...")

    try:
        # Busca as duas listas em paralelo
        resultados = await asyncio.gather(
            buscar_jogos_correndo_api(),  # Chama a função geral
            buscar_jogos_proximos_hoje_api(),  # Chama a função geral
        )
        jogos_correndo = resultados[0]
        jogos_proximos = resultados[1]

        if not jogos_correndo and not jogos_proximos:
            await update.message.reply_text(
                "⚫ Não encontrei jogos de CS correndo ou agendados para hoje na API."
            )
            return

        # Monta a mensagem final
        mensagem_final = f"📅 **Jogos de CS para Hoje ({datetime.date.today().strftime('%d/%m')})** 📅\n"

        # Limitar a quantidade de jogos exibidos para não ficar gigante?
        max_jogos_mostrar = 10  # Exemplo

        if jogos_correndo:
            mensagem_final += "\n🔴 **Ao Vivo Agora:**\n"
            count = 0
            for jogo in jogos_correndo:
                if count >= max_jogos_mostrar:
                    mensagem_final += "_... e mais!_\n"
                    break
                mensagem_final += (
                    format_match_data_geral(jogo) + "\n\n"
                )  # Usa a formatação geral
                count += 1

        if jogos_proximos:
            mensagem_final += "\n⏳ **Agendados para Hoje:**\n"
            count = 0
            # Remove jogos próximos que já estão na lista de correndo (caso haja sobreposição de status)
            ids_correndo = {j.get("id") for j in jogos_correndo}
            jogos_proximos_filtrados = [
                j for j in jogos_proximos if j.get("id") not in ids_correndo
            ]

            for jogo in jogos_proximos_filtrados:
                if count >= max_jogos_mostrar:
                    mensagem_final += "_... e mais!_\n"
                    break
                mensagem_final += (
                    format_match_data_geral(jogo) + "\n\n"
                )  # Usa a formatação geral
                count += 1

        mensagem_final = mensagem_final.strip()

        # Verifica se após os limites, a mensagem ficou vazia (improvável, mas possível)
        if len(mensagem_final) <= len(
            f"📅 **Jogos de CS para Hoje ({datetime.date.today().strftime('%d/%m')})** 📅\n"
        ):
            await update.message.reply_text(
                "⚫ Não encontrei jogos relevantes de CS para exibir hoje."
            )
            return

        await update.message.reply_html(mensagem_final)

    except Exception as e:
        logger.error(f"Erro geral ao executar /jogos_hoje: {e}", exc_info=True)
        await update.message.reply_text(
            "❌ Ocorreu um erro ao buscar a agenda geral de hoje."
        )


async def campeonatos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Envia uma mensagem com os campeonatos de CS que a FURIA participa (running/upcoming)."""
    await update.message.reply_text("Buscando campeonatos da FURIA...")

    try:
        # Chama a função que TENTA filtrar pela FURIA
        lista_torneios_furia = await buscar_torneios_furia_api(limit_each=15)

        if not lista_torneios_furia:
            # Se a lista está vazia, pode ser que o filtro deu erro 400 ou que não há torneios mesmo.
            # Os logs devem indicar se o filtro falhou.
            await update.message.reply_text(
                "⚫ Não encontrei campeonatos em andamento ou próximos para a FURIA na API."
            )
            return

        # Separa as listas para exibição
        torneios_running_fmt = []
        torneios_upcoming_fmt = []

        for torneio in lista_torneios_furia:
            # Usa a mesma função de formatação de antes
            info_formatada = format_tournament_data(torneio)
            if torneio.get("_list_status") == "running":
                torneios_running_fmt.append(info_formatada)
            else:
                torneios_upcoming_fmt.append(info_formatada)

        # Monta a mensagem final
        mensagem_final = "📅 **Campeonatos da FURIA** 📅\n"

        if torneios_running_fmt:
            mensagem_final += "\n🔴 **Em Andamento:**\n"
            mensagem_final += "\n\n".join(torneios_running_fmt)
            mensagem_final += "\n"

        if torneios_upcoming_fmt:
            mensagem_final += "\n⏳ **Próximos:**\n"
            mensagem_final += "\n\n".join(torneios_upcoming_fmt)

        mensagem_final = mensagem_final.strip()

        # Se por acaso as listas ficaram vazias após processar (improvável)
        if len(mensagem_final) <= len("📅 **Campeonatos da FURIA** 📅\n"):
            await update.message.reply_text(
                "⚫ Não encontrei campeonatos em andamento ou próximos para a FURIA."
            )
            return

        await update.message.reply_html(mensagem_final)

    except Exception as e:
        logger.error(f"Erro geral ao executar /campeonatos: {e}", exc_info=True)
        await update.message.reply_text(
            "❌ Ocorreu um erro ao buscar os campeonatos da FURIA."
        )


async def stats_ano(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Fornece estatísticas da FURIA para um ano específico."""
    args = context.args  # Pega os argumentos passados após o comando /stats

    # Verifica se o usuário passou um argumento (o ano)
    if not args:
        await update.message.reply_text(
            "Por favor, informe o ano após o comando.\nExemplo: `/stats 2023`"
        )
        return

    # Verifica se passou mais de um argumento
    if len(args) > 1:
        await update.message.reply_text(
            "Por favor, informe apenas o ano.\nExemplo: `/stats 2023`"
        )
        return

    # Tenta converter o argumento para um número inteiro (ano)
    try:
        ano_solicitado = int(args[0])
    except ValueError:
        await update.message.reply_text(
            "O ano informado não é válido. Use um número.\nExemplo: `/stats 2023`"
        )
        return

    # Busca os dados no nosso "banco de dados" estático
    stats_do_ano = FURIA_STATS_DB.get(ano_solicitado)

    # Verifica se encontramos dados para o ano solicitado
    if stats_do_ano:
        # Formata a mensagem de resposta usando HTML para melhor visualização
        resultados_str = "\n".join(
            [f"  - {res}" for res in stats_do_ano["principais_resultados"]]
        )  # Formata a lista
        resposta = (
            f"📊 <b>Estatísticas da FURIA em {ano_solicitado}</b> 📊\n\n"
            f"<b>Resumo:</b> {stats_do_ano['resumo']}\n\n"
            f"<b>Principais Resultados:</b>\n{resultados_str}\n\n"
            f"<b>Títulos importantes conquistados:</b> {stats_do_ano['titulos']}"
        )
        await update.message.reply_html(resposta)
    else:
        # Informa ao usuário se não temos dados para aquele ano
        anos_disponiveis = ", ".join(
            map(str, sorted(FURIA_STATS_DB.keys()))
        )  # Mostra anos disponíveis
        await update.message.reply_text(
            f"Desculpe, não tenho informações detalhadas para o ano {ano_solicitado}.\n"
            f"Anos disponíveis: {anos_disponiveis}"
        )


def main() -> None:
    """Inicia o bot."""
    # Cria a Application e passa o token do seu bot.
    application = Application.builder().token(BOT_TOKEN).build()

    # Cria um 'handler' para o comando /start e registra ele no 'dispatcher'
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("proximo_jogo", proximo_jogo))
    application.add_handler(CommandHandler("line_up", line_up))
    application.add_handler(CommandHandler("campeonatos", campeonatos))
    # ATENÇÃO COM COMANDO STATS
    application.add_handler(CommandHandler("stats", stats_ano))
    application.add_handler(CommandHandler("jogos_hoje", jogos_hoje))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )

    # Registra o handler de erro
    application.add_error_handler(error_handler)

    # Inicia o Bot (fica escutando por comandos)
    print("Bot iniciado...")
    application.run_polling()


if __name__ == "__main__":
    main()
