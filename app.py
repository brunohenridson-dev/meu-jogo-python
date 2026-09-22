from gevent import monkey
monkey.patch_all()

from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit, join_room
import random

app = Flask(__name__)
app.config['SECRET_KEY'] = 'segredo!'

socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode='gevent',
    transports=['polling']
)

jogos_cpu = {}

salas = {}
espera = None


@app.route('/')
def index():
    return render_template('index.html')


# ===============================================
# LÓGICA DE COMBATE CONTRA A CPU
# ===============================================

@socketio.on('reiniciar_jogo')
def reiniciar_jogo():
    sid = request.sid

    jogos_cpu[sid] = {
        'vida': 10,
        'ataque': 2,
        'life': 12,
        'ataque2': 2
    }

    emit('atualizar_tela', {
        'vida': jogos_cpu[sid]['vida'],
        'ataque': jogos_cpu[sid]['ataque'],
        'life': jogos_cpu[sid]['life'],
        'ataque2': jogos_cpu[sid]['ataque2'],
        'mensagem': 'Jogo iniciado contra a CPU!'
    })


@socketio.on('jogar_turno')
def jogar_turno(data):
    sid = request.sid

    if sid not in jogos_cpu:
        jogos_cpu[sid] = {
            'vida': 10,
            'ataque': 2,
            'life': 12,
            'ataque2': 2
        }

    estado_cpu = jogos_cpu[sid]

    acao_jogador = data.get('acao')

    opcoes_cpu = ['a', 'd', 'g']
    acao_cpu = random.choice(opcoes_cpu)

    msg = resolver_combate(
        estado_cpu,
        acao_jogador,
        acao_cpu,
        "Você",
        "CPU"
    )

    emit('atualizar_tela', {
        'vida': estado_cpu['vida'],
        'ataque': estado_cpu['ataque'],
        'life': estado_cpu['life'],
        'ataque2': estado_cpu['ataque2'],
        'mensagem': msg
    })


# ===============================================
# REGRAS DE COMBATE
# ===============================================

def resolver_combate(estado, a1, a2, nome1, nome2):

    # Ataque vs Ataque
    if a1 == 'a' and a2 == 'a':
        estado['life'] -= estado['ataque']
        estado['vida'] -= estado['ataque2']

        return f"{nome1} e {nome2} atacaram! Ambos sofreram dano."

    # Ataque vs Defesa
    elif a1 == 'a' and a2 == 'd':
        estado['ataque2'] += 1

        return (
            f"{nome1} atacou, mas {nome2} defendeu! "
            f"{nome2} não tomou dano e aumentou o ataque "
            f"para {estado['ataque2']}."
        )

    # Ataque vs Granada
    elif a1 == 'a' and a2 == 'g':
        estado['life'] -= estado['ataque']

        return (
            f"{nome1} atacou enquanto {nome2} jogou uma granada! "
            f"{nome1} causou {estado['ataque']} de dano."
        )

    # Defesa vs Ataque
    elif a1 == 'd' and a2 == 'a':
        estado['ataque'] += 1

        return (
            f"{nome1} defendeu o ataque de {nome2}! "
            f"{nome1} não tomou dano e aumentou o ataque "
            f"para {estado['ataque']}."
        )

    # Defesa vs Defesa
    elif a1 == 'd' and a2 == 'd':
        return "Ambos defenderam! Nenhum dano causado."

    # Defesa vs Granada
    elif a1 == 'd' and a2 == 'g':
        estado['vida'] -= 3

        return (
            f"{nome1} defendeu, mas {nome2} jogou uma granada! "
            f"{nome1} tomou 3 de dano de granada."
        )

    # Granada vs Ataque
    elif a1 == 'g' and a2 == 'a':
        estado['vida'] -= estado['ataque2']

        return (
            f"{nome1} jogou granada enquanto {nome2} atacou! "
            f"{nome2} causou {estado['ataque2']} de dano."
        )

    # Granada vs Defesa
    elif a1 == 'g' and a2 == 'd':
        estado['life'] -= 3

        return (
            f"{nome1} jogou uma granada na defesa de {nome2}! "
            f"{nome2} tomou 3 de dano de granada."
        )

    # Granada vs Granada
    elif a1 == 'g' and a2 == 'g':
        estado['vida'] -= 3
        estado['life'] -= 3

        return "Ambos jogaram granadas! Cada um tomou 3 de dano de explosão."

    return "Turno concluído."


# ===============================================
# MULTIPLAYER ONLINE
# ===============================================

@socketio.on('buscar_partida_online')
def buscar_partida_online(data):
    global espera

    sid = request.sid
    nome_jogador = data.get('nome', 'Jogador')

    # Criar espera
    if espera is None or espera.get('id') == sid:

        nome_sala = f"sala_{sid}"

        espera = {
            'sala': nome_sala,
            'id': sid,
            'nome': nome_jogador
        }

        join_room(nome_sala)

        salas[nome_sala] = {
            'p1': {
                'id': sid,
                'nome': nome_jogador,
                'vida': 10,
                'ataque': 2
            },
            'p2': None,
            'jogadas': {}
        }

        emit(
            'status_conexao',
            {'msg': 'Procurando um oponente...'},
            room=sid
        )

    # Encontrou oponente
    else:

        nome_sala = espera['sala']

        join_room(nome_sala)

        salas[nome_sala]['p2'] = {
            'id': sid,
            'nome': nome_jogador,
            'vida': 10,
            'ataque': 2
        }

        p1_data = salas[nome_sala]['p1']

        espera = None

        emit(
            'partida_iniciada',
            {
                'sala': nome_sala,
                'oponente': nome_jogador
            },
            room=p1_data['id']
        )

        emit(
            'partida_iniciada',
            {
                'sala': nome_sala,
                'oponente': p1_data['nome']
            },
            room=sid
        )


@socketio.on('jogar_turno_online')
def jogar_turno_online(data):

    sid = request.sid

    nome_sala = data.get('sala')
    acao = data.get('acao')

    if nome_sala not in salas:
        return

    sala = salas[nome_sala]

    sala['jogadas'][sid] = acao

    # Espera os dois jogadores
    if len(sala['jogadas']) == 2:

        p1 = sala['p1']
        p2 = sala['p2']

        a1 = sala['jogadas'][p1['id']]
        a2 = sala['jogadas'][p2['id']]

        estado_temp = {
            'vida': p1['vida'],
            'ataque': p1['ataque'],
            'life': p2['vida'],
            'ataque2': p2['ataque']
        }

        msg = resolver_combate(
            estado_temp,
            a1,
            a2,
            p1['nome'],
            p2['nome']
        )

        p1['vida'] = estado_temp['vida']
        p1['ataque'] = estado_temp['ataque']

        p2['vida'] = estado_temp['life']
        p2['ataque'] = estado_temp['ataque2']

        # Jogador 1
        emit(
            'atualizar_tela',
            {
                'vida': p1['vida'],
                'ataque': p1['ataque'],
                'life': p2['vida'],
                'ataque2': p2['ataque'],
                'mensagem': msg
            },
            room=p1['id']
        )

        # Jogador 2
        emit(
            'atualizar_tela',
            {
                'vida': p2['vida'],
                'ataque': p2['ataque'],
                'life': p1['vida'],
                'ataque2': p1['ataque'],
                'mensagem': msg
            },
            room=p2['id']
        )

        sala['jogadas'] = {}


# ===============================================
# CHAT
# ===============================================

@socketio.on('enviar_chat')
def enviar_chat(data):

    nome_sala = data.get('sala')

    emit(
        'receber_chat',
        {
            'autor': data.get('autor'),
            'mensagem': data.get('mensagem')
        },
        room=nome_sala
    )


if __name__ == '__main__':
    socketio.run(app, debug=True)
