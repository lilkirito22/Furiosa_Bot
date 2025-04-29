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
from typing import Tuple, Dict, Any

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
FURIA_STATS_DB = {
    2024: {  # Dados de 2024 (parcial, verificar/atualizar)
        "resumo": "Início de ano com mudanças na line-up, Major e foco na reconstrução.",
        "principais_resultados": [
            "PGL Major Copenhagen: Eliminado (0-3)",
            "IEM Katowice: Play-in",
            "GET Rio: Top 8",
            "IEM Chengdu: Top 12",
        ],
        "titulos": 0,
    },
    2023: {  # Dados de 2023 (verificar)
        "resumo": "Ano de participação nos dois Majors e título do Elisa Masters Espoo.",
        "principais_resultados": [
            "BLAST.tv Paris Major: Challengers Stage",  # Corrigido nome do Major
            "IEM Rio Major: Legends Stage",  # Este foi em 2022, remover daqui? Ou era IEM Rio 2023? Verificar! -> Provavelmente BLAST Spring Final / IEM Cologne / Gamers8 foram mais relevantes. Precisa confirmar.
            "Elisa Masters Espoo: Campeão",
            "Pinnacle Cup V: Vice",
        ],
        "titulos": 1,  # Elisa Masters
    },
    2022: {  # Dados de 2022 (verificar)
        "resumo": "Grande ano com semifinal no Major do Rio e boa performance geral.",
        "principais_resultados": [
            "IEM Rio Major: Semifinalista (Top 4)",
            "PGL Major Antwerp: Legends Stage (Top 8)",
            "ESL Challenger Valencia: Vice",
            "PGL RMR Americas: Campeão",  # Qualificatório para o Major
        ],
        "titulos": 1,  # RMR
    },
    # --- Dados Adicionados (VERIFICAR NA LIQUIPEDIA) ---
    2021: {  # Simulado/Baseado em conhecimento geral
        "resumo": "Consistência em Majors, domínio regional e adaptação entre online/LAN.",
        "principais_resultados": [
            "PGL Major Stockholm: Legends Stage (Top 8)",
            "IEM Fall North America: Campeão",
            "ESL Pro League S14: Top 8",
            "IEM Cologne (LAN): Top 12",  # Primeiro grande evento LAN pós-pandemia
        ],
        "titulos": 1,  # IEM Fall NA
    },
    2020: {  # Simulado/Baseado em conhecimento geral
        "resumo": "Forte domínio na América do Norte durante a era online da pandemia.",
        "principais_resultados": [
            "IEM New York NA: Campeão",
            "ESL Pro League S12 Americas: Campeão",
            "DreamHack Masters Spring NA: Campeão",
            "DreamHack Open Summer NA: Campeão",
            "BLAST Premier Spring Americas Finals: Vice",
        ],
        "titulos": 4,  # Muitos títulos regionais NA online
    },
    2019: {  # Simulado/Baseado em conhecimento geral
        "resumo": "Ano de afirmação internacional com boas campanhas em grandes eventos.",
        "principais_resultados": [
            "StarLadder Major Berlin: Legends Stage (Top 16)",  # Confirmar Top 16 ou Top 8
            "ECS Season 7 Finals: Semifinalista (Top 4)",
            "DreamHack Masters Dallas: Semifinalista (Top 4)",
            "Arctic Invitational: Campeão",  # Verificar se foi este ou outro título menor
        ],
        "titulos": 1,  # Arctic Inv. (Verificar)
    },
    2018: {  # Simulado/Baseado em conhecimento geral
        "resumo": "Primeiras experiências internacionais e título da ESEA Premier NA.",
        "principais_resultados": [
            "Qualificação para o FACEIT Major London (via Americas Minor)",
            "ESEA Season 27 NA Premier: Campeão",  # Título importante para subir
            "ZOTAC Cup Masters Americas Finals: Campeão",  # Verificar
        ],
        "titulos": 2,  # Verificar títulos exatos
    },
    2017: {  # Simulado/Baseado em conhecimento geral
        "resumo": "Formação da equipe e foco total no cenário brasileiro.",
        "principais_resultados": [
            "Vitórias e boas colocações em ligas e qualificatórias no Brasil.",
            "(Resultados específicos de 2017 precisam ser pesquisados na Liquipedia)",
            # Exemplos (fictícios, precisam checar): Campeão Liga Pró GamersClub, Top 4 GC Masters...
        ],
        "titulos": 0,  # Assumindo nenhum título internacional/Tier 1 nesse ano
    },
    # Adicione mais anos se desejar
}

# --- Dialogflow Helper ---


async def detect_intent_text(
    project_id: str, session_id: str, text: str, language_code: str = "pt-br"
) -> Tuple[
    str | None, Dict[str, Any] | None
]:  # <<< MODIFICADO: Tipo de retorno agora é uma Tupla
    """
    Envia o texto do usuário para a API do Dialogflow e retorna o nome da intenção
    e um dicionário com os parâmetros detectados.

    Args:
        project_id: O ID do seu projeto no Google Cloud.
        session_id: Um ID único para esta conversa/usuário (ex: ID do usuário Telegram).
        text: O texto da mensagem do usuário.
        language_code: O código do idioma do agente Dialogflow.

    Returns:
        Uma tupla contendo:
        - O nome de exibição da intenção detectada (str) ou None se ocorrer erro.
        - Um dicionário com os parâmetros extraídos (Dict[str, Any]) ou None se ocorrer erro.
    """

    # 1. Criar o Cliente de Sessão (igual antes)
    try:
        session_client = dialogflow.SessionsAsyncClient()
    except Exception as e:
        logger.exception(
            "ERRO DIALOGFLOW: Falha ao criar o SessionsAsyncClient. Verifique as credenciais."
        )
        return None, None  # <<< MODIFICADO: Retorna tupla com Nones

    # 2. Definir o Caminho da Sessão (igual antes)
    session_path = session_client.session_path(project_id, session_id)
    logger.debug(f"Dialogflow session path: {session_path}")

    if not text:
        return None, None  # <<< MODIFICADO: Retorna tupla com Nones

    # 3. Preparar a Entrada de Texto (igual antes)
    text_input = dialogflow.TextInput(text=text, language_code=language_code)
    query_input = dialogflow.QueryInput(text=text_input)

    # 4. Chamar a API detect_intent (igual antes)
    try:
        logger.info(f"Enviando para Dialogflow (Projeto: {project_id}): '{text}'")
        response = await session_client.detect_intent(
            request={"session": session_path, "query_input": query_input}
        )

        # 5. Processar a Resposta (Modificado para pegar parâmetros)
        query_result = response.query_result
        intent_name = query_result.intent.display_name
        confidence = query_result.intent_detection_confidence

        # <<< NOVO: Extrai os parâmetros e converte para um dict Python >>>
        parameters = dict(query_result.parameters.items())

        logger.info(
            f"Dialogflow detectou: Intenção='{intent_name}', Confiança={confidence:.2f}, Parâmetros={parameters}"
        )

        # <<< MODIFICADO: Retorna a tupla com nome da intenção e parâmetros >>>
        return intent_name, parameters

    except Exception as e:
        logger.exception(
            f"ERRO DIALOGFLOW: Falha na chamada detect_intent para o texto '{text}'"
        )
        # <<< MODIFICADO: Retorna tupla com Nones em caso de erro >>>
        return None, None


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

async def buscar_torneios_gerais_api(limit_each: int = 10) -> list[dict]:
    """
    Busca torneios 'running' e 'upcoming' GERAIS de CS na API PandaScore.
    Retorna uma lista combinada de dicionários de torneios.
    """
    endpoint_running = f"{PANDASCORE_BASE_URL}/csgo/tournaments/running"
    endpoint_upcoming = f"{PANDASCORE_BASE_URL}/csgo/tournaments/upcoming"
    headers = {"Authorization": f"Bearer {PANDASCORE_API_KEY}", "Accept": "application/json"}

    # Parâmetros SEM filtro de time
    # Ordenar por data é uma opção segura. Ordenar por tier (-tier) pode ser melhor se suportado.
    params_running = {"page[size]": limit_each, "sort": "-begin_at"}
    params_upcoming = {"page[size]": limit_each, "sort": "begin_at"}

    lista_combinada = []
    ids_adicionados = set()

    try:
        async with httpx.AsyncClient() as client:
            logger.info("Buscando torneios GERAIS running e upcoming...")
            responses = await asyncio.gather(
                client.get(endpoint_running, headers=headers, params=params_running),
                client.get(endpoint_upcoming, headers=headers, params=params_upcoming),
                return_exceptions=True
            )

            # Processa resposta dos 'running'
            if isinstance(responses[0], httpx.Response) and responses[0].status_code == 200:
                torneios_running = responses[0].json()
                for torneio in torneios_running:
                    if torneio and torneio.get('id') not in ids_adicionados:
                        torneio['_list_status'] = 'running'
                        lista_combinada.append(torneio)
                        ids_adicionados.add(torneio.get('id'))
                logger.info(f"Encontrados {len(torneios_running)} torneios running (geral).")
            elif isinstance(responses[0], Exception):
                 logger.error(f"Erro ao buscar torneios running (geral): {responses[0]}")
            elif isinstance(responses[0], httpx.Response):
                 logger.error(f"Erro HTTP {responses[0].status_code} ao buscar torneios running (geral): {responses[0].text}")

            # Processa resposta dos 'upcoming'
            if isinstance(responses[1], httpx.Response) and responses[1].status_code == 200:
                torneios_upcoming = responses[1].json()
                for torneio in torneios_upcoming:
                    if torneio and torneio.get('id') not in ids_adicionados:
                        torneio['_list_status'] = 'upcoming'
                        lista_combinada.append(torneio)
                        ids_adicionados.add(torneio.get('id'))
                logger.info(f"Encontrados {len(torneios_upcoming)} torneios upcoming (geral).")
            elif isinstance(responses[1], Exception):
                 logger.error(f"Erro ao buscar torneios upcoming (geral): {responses[1]}")
            elif isinstance(responses[1], httpx.Response):
                 logger.error(f"Erro HTTP {responses[1].status_code} ao buscar torneios upcoming (geral): {responses[1].text}")

            # Reordena a lista combinada pela data de início para consistência
            lista_combinada.sort(key=lambda t: t.get('begin_at', ''))
            return lista_combinada

    except Exception as exc:
        logger.error(f"Erro geral ao buscar torneios gerais: {exc}", exc_info=True)
        return []


async def obter_e_formatar_campeonatos() -> str:
    """
    Busca e formata a lista de campeonatos.
    Tenta primeiro os da FURIA, se vazio, busca os gerais.
    Retorna a string HTML formatada para o Telegram ou mensagem de 'não encontrado'.
    """
    mensagem_final = ""
    lista_vazia = True
    titulo = "" # Título da seção (Furia ou Geral)
    nota = "" # Nota adicional (ex: fallback para geral)

    try:
        # 1. Tenta buscar torneios específicos da FURIA
        logger.info("obtendo_formatando_campeonatos: Tentando buscar torneios da FURIA...")
        lista_torneios_furia = await buscar_torneios_furia_api(limit_each=15)

        # 2. Verifica se encontrou torneios da FURIA
        if lista_torneios_furia:
            logger.info(f"obtendo_formatando_campeonatos: Encontrados {len(lista_torneios_furia)} torneios da FURIA.")
            lista_vazia = False
            titulo = "📅 **Campeonatos da FURIA** 📅"
            # Formata a lista da Furia
            torneios_running_fmt = []
            torneios_upcoming_fmt = []
            for torneio in lista_torneios_furia:
                info_formatada = format_tournament_data(torneio) # Usa a função que já tínhamos
                if torneio.get('_list_status') == 'running':
                    torneios_running_fmt.append(info_formatada)
                else:
                    torneios_upcoming_fmt.append(info_formatada)

            mensagem_final += f"{titulo}\n" # Adiciona título
            if torneios_running_fmt:
                mensagem_final += "\n🔴 **Em Andamento:**\n" + "\n\n".join(torneios_running_fmt) + "\n"
            if torneios_upcoming_fmt:
                mensagem_final += "\n⏳ **Próximos:**\n" + "\n\n".join(torneios_upcoming_fmt)

        else:
            # 3. Se não achou da FURIA, busca os gerais (Fallback)
            logger.info("obtendo_formatando_campeonatos: Não achou da FURIA, buscando gerais...")
            lista_torneios_gerais = await buscar_torneios_gerais_api(limit_each=10)

            if lista_torneios_gerais:
                logger.info(f"obtendo_formatando_campeonatos: Encontrados {len(lista_torneios_gerais)} torneios gerais.")
                lista_vazia = False
                titulo = "📅 **Principais Campeonatos de CS** 📅"
                nota = "\n_(Não encontrei torneios específicos da FURIA no momento)_" # Nota de fallback
                # Formata a lista geral
                torneios_running_fmt = []
                torneios_upcoming_fmt = []
                for torneio in lista_torneios_gerais:
                    info_formatada = format_tournament_data(torneio) # Usa a função que já tínhamos
                    if torneio.get('_list_status') == 'running':
                        torneios_running_fmt.append(info_formatada)
                    else:
                        torneios_upcoming_fmt.append(info_formatada)

                mensagem_final += f"{titulo}{nota}\n" # Adiciona título e nota
                if torneios_running_fmt:
                    mensagem_final += "\n🔴 **Em Andamento:**\n" + "\n\n".join(torneios_running_fmt) + "\n"
                if torneios_upcoming_fmt:
                    mensagem_final += "\n⏳ **Próximos:**\n" + "\n\n".join(torneios_upcoming_fmt)
            # else: Se nem geral achou, lista_vazia continua True

        # 4. Retorna a mensagem apropriada
        if lista_vazia:
            logger.info("obtendo_formatando_campeonatos: Nenhuma lista retornou resultados.")
            return "⚫ Não encontrei campeonatos relevantes (nem da FURIA, nem gerais) em andamento ou próximos na API no momento."
        else:
            return mensagem_final.strip()

    except Exception as e:
        logger.error(f"Erro em obter_e_formatar_campeonatos: {e}", exc_info=True)
        return "❌ Ocorreu um erro ao buscar os campeonatos."



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


def get_furia_stats_for_year(year_to_check: int) -> str:
    """Busca stats (estáticos) e formata a resposta para um ano."""
    logger.info(f"Buscando stats no DB estático para o ano {year_to_check}")
    stats_do_ano = FURIA_STATS_DB.get(year_to_check)

    if stats_do_ano:
        # ... (código de formatação da resposta que você já tinha) ...
        resultados_str = "\n".join(
            [f"  - {res}" for res in stats_do_ano["principais_resultados"]]
        )
        resposta = (
            f"📊 <b>Estatísticas da FURIA em {year_to_check}</b> 📊\n\n"
            f"<b>Resumo:</b> {stats_do_ano['resumo']}\n\n"
            f"<b>Principais Resultados:</b>\n{resultados_str}\n\n"
            f"<b>Títulos importantes conquistados:</b> {stats_do_ano['titulos']}"
        )
        return resposta
    else:
        # ... (código para mensagem de ano não encontrado que você já tinha) ...
        anos_disponiveis = ", ".join(map(str, sorted(FURIA_STATS_DB.keys())))
        return (
            f"Desculpe, não tenho informações detalhadas para o ano {year_to_check}.\n"
            f"Anos disponíveis no meu DB: {anos_disponiveis}"
        )


# Atualiza o handler do comando /jogos_hoje para usar a nova função
async def jogos_hoje(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler para o comando /jogos_hoje."""
    await update.message.reply_text("Verificando a agenda geral de CS para hoje...")
    resultado_formatado = await obter_e_formatar_jogos_hoje()
    await update.message.reply_html(resultado_formatado)


# --- Fim das Funções Auxiliares ---


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

    # Detecta a intenção e o parametro via Dialogflow
    intent_name, parameters = await detect_intent_text(
        GOOGLE_PROJECT_ID, user_id, message_text
    )
    logger.info(f"handle_message: Intenção='{intent_name}', Parâmetros='{parameters}'")

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
            f"Olá, {user_first_name}! 👋 Pronto para saber as novidades da FURIA? Você pode começar me perguntando oque eu sei fazer para conferir todas minhas funcionalidades!"
        )
        await update.message.reply_text(resposta_greeting)

    elif intent_name == "NextGame":  # Intenção que já tínhamos
        logger.info("handle_message: Intenção 'NextGame' reconhecida.")
        await update.message.reply_text(
            "Entendi! vou da uma conferida para você! Buscando..."
        )
        resultado_proximo_jogo = (
            await buscar_proximo_jogo_furia_api()
        )  # Ou uma função refatorada
        await update.message.reply_html(resultado_proximo_jogo)

    elif intent_name == "LineUp":  # intenção que já tínhamos
        logger.info("handle_message: Intenção 'LineUp' reconhecida.")
        await update.message.reply_text(
            "Entendi! vou da uma conferida para você! Buscando..."
        )
        resultado_lineup = await buscar_lineup_furia_api()  # Ou uma função refatorada
        await update.message.reply_html(resultado_lineup)

    elif intent_name == "FuriaTourments": # Use o nome exato da sua intenção
        logger.info("handle_message: Intenção 'FuriaTourments' reconhecida.")
        await update.message.reply_text(
            "Entendi! Vou dar uma conferida nos campeonatos para você! Buscando..."
        )
        # <<< CHAMA A FUNÇÃO REUTILIZÁVEL >>>
        resultado_formatado = await obter_e_formatar_campeonatos()
        await update.message.reply_html(resultado_formatado)

    elif intent_name == "GetBotCapabilities":  # <<< NOVA INTENÇÃO: O que o bot faz >>>
        logger.info("handle_message: Intenção 'GetBotCapabilities' reconhecida.")
        # Monta a mensagem explicando as funções
        resposta_capabilities = """
Eu sou o Furia Fan Bot! 🔥 Posso te ajudar com:

📅 **Agenda de Hoje:** Me pergunte "quais os jogos de hoje?" para ver as partidas de CS rolando.
🐾 **Próximo Jogo da FURIA:** Só me perguntar quando é o proximo jogo que eu ti respondo
👥 **Line-up Atual da FURIA:** só me perguntar!
🏆 **Campeonatos:** Só me perguntar quais campeonatos a furia esta jogando
📊 **Stats Anuais:** Você pode me perguntar as estatisticas da furia em algum ano especifico.

É só pedir! #DIADEFURIA
        """
        # Usamos reply_html para garantir que a formatação funcione, mesmo sem tags HTML explícitas aqui
        await update.message.reply_html(resposta_capabilities)
        pass

    # <<< NOVO Bloco para Stats por Ano >>>
    elif intent_name == "GetTeamStatsByYear":  # Use o nome exato da sua intenção
        logger.info("handle_message: Intenção 'GetTeamStatsByYear' reconhecida.")
        # Verifica se o dicionário de parâmetros existe e contém a chave 'year'

        if parameters and "year" in parameters and parameters["year"] != "":
            try:
                # Tenta converter o parâmetro para inteiro (@sys.number pode vir como float)
                year_param = int(parameters["year"])
                logger.info(f"Ano extraído do parâmetro 'year': {year_param}")

                # Valida o intervalo do ano (exemplo)
                current_year = datetime.datetime.now().year
                min_year = (
                    min(FURIA_STATS_DB.keys()) if FURIA_STATS_DB else 2017
                )  # Pega o menor ano do seu DB

                if min_year <= year_param <= current_year:
                    # Ano é válido, busca as stats
                    await update.message.reply_text(
                        f"Entendi! Buscando estatísticas da FURIA para {year_param}..."
                    )
                    # Chama a função reutilizável que usa o DB estático
                    response_text = get_furia_stats_for_year(year_param)
                    await update.message.reply_html(response_text)
                else:
                    # Ano fora do intervalo esperado
                    logger.warning(f"Ano inválido recebido do Dialogflow: {year_param}")
                    await update.message.reply_text(
                        f"Hmm, {year_param} parece um ano um pouco estranho. Pode me dar um ano entre {min_year} e {current_year}?"
                    )

            except (ValueError, TypeError):
                # Erro ao converter o parâmetro para número
                logger.error(
                    f"Não foi possível converter o parâmetro 'year' ({parameters.get('year')}) para int."
                )
                await update.message.reply_text(
                    "Não consegui entender o ano que você mencionou. Pode tentar de novo?"
                )
        else:
            # Se Dialogflow não extraiu o ano, ele deveria ter usado os prompts que você definiu na intenção.
            # Mas caso algo falhe, podemos ter um fallback aqui.
            logger.warning(
                "Intenção GetTeamStatsByYear detectada, mas parâmetro 'year' ausente ou vazio."
            )
            # Idealmente, o prompt do Dialogflow já teria perguntado o ano.
            # Você pode adicionar uma resposta aqui se quiser, mas pode ser redundante.
            await update.message.reply_text(
                "Para qual ano você gostaria de ver as estatísticas?"
            )

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
    """Handler para o comando /campeonatos."""
    await update.message.reply_text("Buscando campeonatos...")
    # Chama a função reutilizável que contém toda a lógica (Furia -> Geral -> Formatação)
    resultado_formatado = await obter_e_formatar_campeonatos()
    await update.message.reply_html(resultado_formatado)


async def stats_ano(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler para o comando /stats <ano>."""
    args = context.args
    if not args or len(args) > 1:
        await update.message.reply_text("Uso: `/stats ANO` (ex: `/stats 2023`)")
        return
    try:
        year_int = int(args[0])
        current_year = datetime.datetime.now().year
        min_year = 2017
        # Adiciona validação de intervalo
        if not (min_year <= year_int <= current_year):  # Ajuste o 2018 se necessário
            raise ValueError("Ano fora do intervalo válido.")
        # Chama a função reutilizável
        response_text = get_furia_stats_for_year(year_int)
        await update.message.reply_html(response_text)
    except ValueError:
        await update.message.reply_text(
            f"Hmm, '{args[0]}' não parece um ano válido. Tente um ano entre 2018 e {datetime.datetime.now().year}."
        )
    except Exception as e:
        logger.error(f"Erro no comando /stats: {e}", exc_info=True)
        await update.message.reply_text("Ocorreu um erro ao buscar as estatísticas.")


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
