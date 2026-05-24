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
        acao = request.form.get('acao')

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

# EMBED V2: Interpretador de Cascata de Blocos Completo para o Bot Real
def rodar_motor_bot_v2(token, prefixo, blocos_config, nome_comando):
    asyncio.set_event_loop(asyncio.new_event_loop())
    
    # Ativa as intenções necessárias para gerenciar membros, cargos e mensagens
    intents = discord.Intents.all()
    bot = commands.Bot(command_prefix=prefixo, intents=intents)

    @bot.event
    async def on_ready():
        print(f"🔥 Bot {bot.user.name} conectado com sucesso via Hexaflow V2!")

    @bot.command(name=nome_comando)
    async def comando_customizado(ctx):
        # Variáveis base do ambiente do Discord
        contexto_vars = {
            "autor": ctx.author.mention,
            "canal": ctx.channel.name,
            "servidor": ctx.guild.name
        }

        # Executa cada bloco de cima para baixo na ordem exata da área de trabalho
        for bloco in blocos_config:
            tipo = bloco.get('tipo')

            # 📥 CAPTURA DE INPUTS E PROCESSAMENTO DE VARIÁVEIS
            if tipo == 'input_texto':
                nome_var = bloco.get('var_nome', 'texto_info')
                valor_var = bloco.get('v_text', '')
                contexto_vars[nome_var] = valor_var
                
            elif tipo == 'input_numero':
                nome_var = bloco.get('var_nome', 'num')
                valor_var = bloco.get('v_text', '0')
                contexto_vars[nome_var] = valor_var

            # 💬 GERENCIAMENTO DE MENSAGENS E EMBEDS
            elif tipo == 'enviar_mensagem':
                texto_final = bloco.get('txt', '')
                # Substitui as variáveis formatadas como {autor} ou personalizadas
                for var, val in contexto_vars.items():
                    texto_final = texto_final.replace(f"{{{var}}}", str(val))
                if texto_final:
                    await ctx.send(texto_final)

            elif tipo == 'enviar_embed_completa':
                titulo_final = bloco.get('tit', '')
                desc_final = bloco.get('desc', '')
                
                # Aplica o sistema de variáveis também dentro da embed premium
                for var, val in contexto_vars.items():
                    titulo_final = titulo_final.replace(f"{{{var}}}", str(val))
                    desc_final = desc_final.replace(f"{{{var}}}", str(val))
                
                cor = int(bloco.get('cor', '#ff007f').replace('#', ''), 16)
                embed = discord.Embed(title=titulo_final, description=desc_final, color=cor)
                
                if bloco.get('ban') and bloco.get('ban').startswith('http'):
                    embed.set_image(url=bloco['ban'])
                await ctx.send(embed=embed)

            # 🔑 GERENCIAMENTO DE CARGOS (INPUT DE CARGO)
            elif tipo == 'add_cargo_automatico':
                cargo_id_str = bloco.get('cargo_id')
                if cargo_id_str and cargo_id_str.isdigit():
                    cargo = ctx.guild.get_role(int(cargo_id_str))
                    if cargo:
                        try:
                            await ctx.author.add_roles(cargo)
                        except discord.Forbidden:
                            await ctx.send("❌ Erro: O Bot não tem permissão hierárquica para dar este cargo.")

            # 📁 GERENCIAMENTO DE CANAIS (INPUT DE CANAL / DELETAR)
            elif tipo == 'deletar_canal_atual':
                try:
                    await ctx.channel.delete()
                except discord.Forbidden:
                    print("Não foi possível deletar o canal: Permissão Insuficiente.")

    global bot_instancia
    bot_instancia = bot
    try:
        bot.run(token)
    except Exception as e:
        print(f"Erro ao iniciar o bot com o token fornecido: {e}")

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
        return jsonify({"status": "aviso", "message": "Um bot já está rodando nesta sessão do painel!"})

    # Cria uma Thread paralela dedicada para o bot rodar livremente sem travar o Flask
    bot_thread = threading.Thread(target=rodar_motor_bot_v2, args=(token, prefixo, blocos, nome_cmd))
    bot_thread.daemon = True
    bot_thread.start()

    return jsonify({"status": "sucesso", "message": "🔥 Bot Inicializado com sucesso! Digite seu comando no Discord."})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
