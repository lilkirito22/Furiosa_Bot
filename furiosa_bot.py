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


def main() -> None:
    """Inicia o bot."""
    # Cria a Application e passa o token do seu bot.
    application = Application.builder().token(BOT_TOKEN).build()

    # Cria um 'handler' para o comando /start e registra ele no 'dispatcher'
    application.add_handler(CommandHandler("start", start))

    # Registra o handler de erro
    application.add_error_handler(error_handler)

    # Inicia o Bot (fica escutando por comandos)
    print("Bot iniciado...")
    application.run_polling()


if __name__ == "__main__":
    main()
