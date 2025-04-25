import os
import logging
import httpx
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from dotenv import load_dotenv
import datetime
import pytz

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
#id da fnatic para testes 3217 
#FURIA_TEAM_ID = 124530
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

# --- Funções Auxiliares para API PandaScore ---


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
        "Accept": "application/json"
    }

    # Parâmetros: Ordenar por data e pegar um lote maior (ex: 50)
    # REMOVEMOS o filtro de time daqui!
    params = {
        "sort": "begin_at",
        "page[size]": 50 # Pega os próximos 50 jogos para procurar a FURIA
    }

    try:
        async with httpx.AsyncClient() as client:
            logger.info(f"Chamando API PandaScore (sem filtro de time): {endpoint_proximos_jogos} com params: {params}")
            response = await client.get(endpoint_proximos_jogos, headers=headers, params=params)
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
                        break # Achou a FURIA neste jogo, pode parar de verificar oponentes
                
                if encontrou_furia:
                    proximo_jogo_furia = jogo # Guarda o objeto do jogo encontrado
                    logger.info(f"Próximo jogo da FURIA encontrado: ID {jogo.get('id')}")
                    break # Para o loop principal, já achamos o primeiro jogo da FURIA

            # Verifica se encontramos um jogo da FURIA na lista
            if proximo_jogo_furia is None:
                logger.info(f"FURIA não encontrada nos próximos {len(lista_jogos)} jogos retornados pela API.")
                return "⚫ Não encontrei jogos da FURIA agendados proximamente."

            # --- Processamento do Jogo Encontrado (igual a antes) ---
            # Extrai as informações do proximo_jogo_furia
            nome_jogo = proximo_jogo_furia.get("name", "Jogo sem nome")
            torneio = proximo_jogo_furia.get("league", {}).get("name", "Torneio desconhecido")
            serie = proximo_jogo_furia.get("serie", {}).get("full_name", "")
            data_inicio_str = proximo_jogo_furia.get("begin_at")
            oponentes_furia = proximo_jogo_furia.get("opponents", []) # Oponentes do jogo encontrado
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
                    data_inicio_dt_utc = datetime.datetime.fromisoformat(data_inicio_str.replace("Z", "+00:00"))
                    fuso_fortaleza = pytz.timezone("America/Fortaleza")
                    data_local = data_inicio_dt_utc.astimezone(fuso_fortaleza)
                    data_formatada = data_local.strftime("%d/%m/%Y às %H:%M")
                except (ValueError, TypeError, pytz.UnknownTimeZoneError) as e:
                    logger.error(f"Erro ao formatar data '{data_inicio_str}': {e}")
                    data_formatada = data_inicio_str

            status_emoji = "⏳" if status == "not_started" else "🔴" if status == "running" else "✅" if status == "finished" else ""

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
        logger.error(f"Erro HTTP ao buscar lista de jogos ({exc.response.status_code}): {exc.request.url} - Resposta: {exc.response.text}")
        return "❌ Erro ao buscar lista de jogos na API (HTTP)."
    except httpx.RequestError as exc:
        logger.error(f"Erro de Conexão/Requisição ao buscar lista de jogos: {exc.request.url} - {exc}")
        return "❌ Erro de conexão ao tentar buscar lista de jogos."
    except Exception as exc:
        logger.error(f"Erro inesperado ao processar lista de jogos: {exc}", exc_info=True)
        return "😵 Ocorreu um erro inesperado ao processar a lista de jogos."


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
    """Envia uma mensagem com o line up."""
    # Aqui você pode adicionar a lógica para obter o line up da Furia
    # Por enquanto, vamos apenas enviar uma mensagem de exemplo
    await update.message.reply_text(
        "O line up da Furia é: fallen, yekindar, kserato, yurih, molodoy."
    )


async def jogos_hoje(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Envia uma mensagem com os jogos de hoje."""
    # Aqui você pode adicionar a lógica para obter os jogos de hoje da Furia
    # Por enquanto, vamos apenas enviar uma mensagem de exemplo
    await update.message.reply_text(
        "Hoje a Furia não tem jogos agendados. Mas temos alguns times jogando no momento! Faze X Vitaly e G2 X Heroic."
    )


async def campeonatos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Envia uma mensagem com os campeonatos."""
    # Aqui você pode adicionar a lógica para obter os campeonatos da Furia
    # Por enquanto, vamos apenas enviar uma mensagem de exemplo
    await update.message.reply_text(
        "Os campeonatos da Furia são: ESL Pro League, Blast Premier, IEM."
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

    # Registra o handler de erro
    application.add_error_handler(error_handler)

    # Inicia o Bot (fica escutando por comandos)
    print("Bot iniciado...")
    application.run_polling()


if __name__ == "__main__":
    main()
