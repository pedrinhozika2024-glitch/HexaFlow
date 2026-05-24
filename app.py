import os
import sqlite3
import threading
import asyncio
import requests
import discord
from discord.ext import commands
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "chave_secreta_super_segura_hexaflow"

# Configuração do Sistema de Login por E-mail
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Instâncias globais do Bot para controle de linha
bot_instancia = None
bot_thread = None

# --- BANCO DE DADOS LOCAL (SQLite) ---
def init_db():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            senha TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

init_db()

class Usuario(UserMixin):
    def __init__(self, id, email):
        self.id = id
        self.email = email

@login_manager.user_loader
def load_user(user_id):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, email FROM usuarios WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()
    if user:
        return Usuario(user[0], user[1])
    return None

# --- ROTAS DE AUTENTICAÇÃO ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        senha = request.form.get('senha')
        acao = request.form.get('acao') # 'login' ou 'cadastro'

        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()

        if acao == 'cadastro':
            try:
                senha_hash = generate_password_hash(senha)
                cursor.execute("INSERT INTO usuarios (email, senha) VALUES (?, ?)", (email, senha_hash))
                conn.commit()
                flash("Conta criada com sucesso! Faça seu login.", "success")
            except sqlite3.IntegrityError:
                flash("Este e-mail já está cadastrado.", "danger")
            finally:
                conn.close()
            return redirect(url_for('login'))

        else:
            cursor.execute("SELECT id, email, senha FROM usuarios WHERE email = ?", (email,))
            user = cursor.fetchone()
            conn.close()

            if user and check_password_hash(user[2], senha):
                usuario_obj = Usuario(user[0], user[1])
                login_user(usuario_obj)
                return redirect(url_for('index'))
            else:
                flash("E-mail ou senha incorretos.", "danger")

    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# --- ROTA PRINCIPAL PROTEGIDA ---
@app.route('/')
@login_required
def index():
    return render_template('index.html', usuario=current_user.email)

# --- EXECUÇÃO DOS SISTEMAS (V1 E V2) ---

# EMBED V1: Envio rápido via Webhook
@app.route('/api/v1/webhook', methods=['POST'])
@login_required
def api_v1_webhook():
    try:
        data = request.json
        url = data.get('url')
        titulo = data.get('titulo')
        descricao = data.get('descricao')
        cor_hex = data.get('cor', '#ff007f')
        banner = data.get('banner')

        if not url:
            return jsonify({"status": "erro", "message": "A URL do Webhook é obrigatória."}), 400

        cor_num = int(cor_hex.replace("#", ""), 16)
        payload = {
            "embeds": [{
                "title": titulo if titulo else None,
                "description": descricao if descricao else None,
                "color": cor_num
            }]
        }
        if banner and banner.startswith("http"):
            payload["embeds"][0]["image"] = {"url": banner}

        res = requests.post(url, json=payload)
        if res.status_code in [200, 204]:
            return jsonify({"status": "sucesso", "message": "Embed V1 enviada via Webhook!"})
        return jsonify({"status": "erro", "message": f"Erro Discord: {res.text}"}), 400
    except Exception as e:
        return jsonify({"status": "erro", "message": str(e)}), 500

# EMBED V2: Interpretador de Cascata de Blocos para o Bot Real
def rodar_motor_bot_v2(token, prefixo, blocos_config, nome_comando):
    asyncio.set_event_loop(asyncio.new_event_loop())
    intents = discord.Intents.all()
    bot = commands.Bot(command_prefix=prefixo, intents=intents)

    @bot.command(name=nome_comando)
    async def comando_customizado(ctx):
        contexto_vars = {"autor": ctx.author.mention, "canal": ctx.channel.name}

        for bloco in blocos_config:
            tipo = bloco.get('tipo')

            # Inputs e variáveis
            if tipo == 'input_texto':
                contexto_vars[bloco.get('var_nome', 'texto')] = bloco.get('v_text', '')
            
            # Chat e mensagens
            elif tipo == 'enviar_mensagem':
                texto_final = bloco.get('txt', 'Mensagem No-Code')
                for var, val in contexto_vars.items():
                    texto_final = texto_final.replace(f"{{{var}}}", str(val))
                await ctx.send(texto_final)

            elif tipo == 'enviar_embed_completa':
                cor = int(bloco.get('cor', '#ff007f').replace('#', ''), 16)
                embed = discord.Embed(title=bloco.get('tit'), description=bloco.get('desc'), color=cor)
                if bloco.get('ban'):
                    embed.set_image(url=bloco['ban'])
                await ctx.send(embed=embed)

            # Cargos e Moderação
            elif tipo == 'add_cargo_automatico':
                cargo = ctx.guild.get_role(int(bloco.get('cargo_id')))
                if cargo: await ctx.author.add_roles(cargo)

            elif tipo == 'deletar_canal_atual':
                await ctx.channel.delete()

    global bot_instancia
    bot_instancia = bot
    bot.run(token)

@app.route('/api/v2/ligar-bot', methods=['POST'])
@login_required
def api_v2_ligar_bot():
    global bot_thread, bot_instancia
    data = request.json
    token = data.get('token')
    prefixo = data.get('prefixo', '!')
    nome_cmd = data.get('nome_comando', 'executar')
    blocos = data.get('blocos', [])

    if not token:
        return jsonify({"status": "erro", "message": "O Token do bot é obrigatório!"}), 400

    if bot_instancia:
        return jsonify({"status": "aviso", "message": "O Bot já está rodando em segundo plano!"})

    bot_thread = threading.Thread(target=rodar_motor_bot_v2, args=(token, prefixo, blocos, nome_cmd))
    bot_thread.daemon = True
    bot_thread.start()

    return jsonify({"status": "sucesso", "message": "🔥 Bot Inicializado com sucesso em segundo plano!"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
