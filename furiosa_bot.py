import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from dotenv import load_dotenv

# Carregue as variáveis do arquivo .env (opcional, veja abaixo)
load_dotenv()


# Configure o logging para ver erros
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Substitua 'SEU_TOKEN_AQUI' pelo token que você recebeu do BotFather
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if BOT_TOKEN is None:
    logger.error("Erro: Variável de ambiente TELEGRAM_BOT_TOKEN não definida!")
    # Você pode querer sair do script aqui ou lançar uma exceção mais específica
    exit("Por favor, defina a variável de ambiente TELEGRAM_BOT_TOKEN.")

# Dicionário para armazenar estatísticas (por enquanto, estático)
# A chave é o ano (inteiro)
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
    await update.message.reply_text("O próximo jogo da Furia será contra o time XYZ!")


async def line_up(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Envia uma mensagem com o line up."""
    # Aqui você pode adicionar a lógica para obter o line up da Furia
    # Por enquanto, vamos apenas enviar uma mensagem de exemplo
    await update.message.reply_text(
        "O line up da Furia é: fallen, yekindar, kserato, yurih, molodoy."
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
    application.add_handler(CommandHandler("stats", stats_ano))

    # Registra o handler de erro
    application.add_error_handler(error_handler)

    # Inicia o Bot (fica escutando por comandos)
    print("Bot iniciado...")
    application.run_polling()


if __name__ == "__main__":
    main()
