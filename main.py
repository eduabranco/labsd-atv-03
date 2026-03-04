#!/usr/bin/env python3
"""
Blockchain
Interface de linha de comando usando apenas stdin/stdout.

Uso:
    python main.py --port 5000
    python main.py --port 5001 --bootstrap localhost:5000
"""

import argparse
import logging
import sys
import time

from node import Node
from core import Transaction


# ---------------------------------------------------------------------------
# CLI helpers
# ---------------------------------------------------------------------------

def prompt(msg: str) -> str:
    """Lê uma linha do stdin."""
    try:
        return input(msg).strip()
    except (EOFError, KeyboardInterrupt):
        return ""


def hr():
    print("-" * 50)


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

def create_transaction(node: Node):
    hr()
    print("Nova Transação")
    print(f"Sua carteira (origem): {node.address}")
    destino = prompt("Destino (endereço host:port): ")
    if not destino:
        print("Cancelado.")
        return
    valor_str = prompt("Valor: ")
    if not valor_str:
        print("Cancelado.")
        return
    try:
        valor = float(valor_str)
        saldo = node.blockchain.get_balance(node.address)
        if node.address not in ("genesis", "coinbase") and saldo < valor:
            print(f"Saldo insuficiente! Saldo atual: {saldo}")
            return
        tx = Transaction(origem=node.address, destino=destino, valor=valor)
        node.broadcast_transaction(tx)
        print(f"Transação enviada: {tx.id[:8]}...")
    except ValueError as e:
        print(f"Erro: {e}")


def show_pending(node: Node):
    hr()
    txs = node.blockchain.pending_transactions
    if not txs:
        print("Nenhuma transação pendente.")
        return
    print(f"{'ID':10}  {'Origem':22}  {'Destino':22}  {'Valor':>8}")
    print("-" * 70)
    for tx in txs:
        print(f"{tx.id[:8]:10}  {tx.origem:22}  {tx.destino:22}  {tx.valor:>8}")


def mine_block(node: Node):
    hr()
    n = len(node.blockchain.pending_transactions)
    print(f"Minerando bloco com {n} transação(ões)... (Ctrl+C não interrompe a mineração)")
    start = time.time()
    block = node.mine()
    elapsed = time.time() - start
    if block:
        print(f"Bloco #{block.index} minerado em {elapsed:.2f}s")
        print(f"  Hash : {block.hash}")
        print(f"  Nonce: {block.nonce}")
    else:
        print("Mineração interrompida.")


def show_blockchain(node: Node):
    hr()
    for block in node.blockchain.chain:
        print(f"Bloco #{block.index}")
        print(f"  Hash:     {block.hash[:32]}...")
        print(f"  Anterior: {block.previous_hash[:32]}...")
        print(f"  Nonce:    {block.nonce}")
        print(f"  Transações ({len(block.transactions)}):")
        for tx in block.transactions:
            print(f"    {tx.origem} -> {tx.destino}: {tx.valor}")
        print()


def show_balance(node: Node):
    hr()
    print(f"1. Minha carteira ({node.address})")
    print("2. Digitar endereço")
    choice = prompt("Escolha: ")
    if choice == "1":
        address = node.address
    elif choice == "2":
        address = prompt("Endereço: ")
        if not address:
            print("Cancelado.")
            return
    else:
        print("Opção inválida.")
        return
    balance = node.blockchain.get_balance(address)
    print(f"Saldo de {address}: {balance}")


def show_peers(node: Node):
    hr()
    if not node.peers:
        print("Nenhum peer conectado.")
        return
    print("Peers conectados:")
    for peer in node.peers:
        print(f"  {peer}")


def connect_peer(node: Node):
    hr()
    peer = prompt("Endereço do peer (host:port): ")
    if not peer:
        print("Cancelado.")
        return
    print(f"Conectando a {peer}...")
    if node.connect_to_peer(peer):
        print(f"Conectado a {peer}")
    else:
        print(f"Falha ao conectar a {peer}")


def sync_chain(node: Node):
    hr()
    print("Sincronizando blockchain e mempool...")
    node.sync_blockchain()
    result = node.sync_mempool()
    print(f"Blockchain: {len(node.blockchain.chain)} bloco(s)")
    print(f"Mempool: {len(node.blockchain.pending_transactions)} transação(ões) pendente(s) (+{result['added']} nova(s))")
    if result["unreachable"]:
        for peer in result["unreachable"]:
            print(f"  Peer inalcançável: {peer}")


# ---------------------------------------------------------------------------
# Menu
# ---------------------------------------------------------------------------

MENU = """
1. Criar transação
2. Ver transações pendentes
3. Minerar bloco
4. Ver blockchain
5. Ver saldo
6. Ver peers
7. Conectar a peer
8. Sincronizar
0. Sair
"""


def main():
    parser = argparse.ArgumentParser(description="Nó blockchain (versão simplificada)")
    parser.add_argument("--host", default="localhost", help="Host do nó")
    parser.add_argument("--port", type=int, default=5555, help="Porta do nó")
    parser.add_argument("--bootstrap", nargs="*", default=[], help="Peers bootstrap")
    parser.add_argument("--log", choices=["DEBUG", "INFO", "WARNING", "ERROR"], default="INFO")
    args = parser.parse_args()

    log_file = f"node_{args.port}.log"
    logging.basicConfig(
        level=getattr(logging, args.log),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(log_file)],
    )

    print(f"=== Blockchain LSD (simplificado) ===")
    print(f"Nó: {args.host}:{args.port}  |  logs → {log_file}")
    print("=" * 38)

    node = Node(host=args.host, port=args.port)
    node.start()

    for bootstrap in args.bootstrap:
        if node.connect_to_peer(bootstrap):
            print(f"Conectado ao bootstrap: {bootstrap}")
        else:
            print(f"Falha ao conectar: {bootstrap}")

    if node.peers:
        node.sync_blockchain()

    actions = {
        "1": create_transaction,
        "2": show_pending,
        "3": mine_block,
        "4": show_blockchain,
        "5": show_balance,
        "6": show_peers,
        "7": connect_peer,
        "8": sync_chain,
    }

    try:
        while True:
            print(MENU, end="")
            choice = prompt("Escolha: ")
            if choice in ("0", ""):
                break
            action = actions.get(choice)
            if action:
                action(node)
            else:
                print("Opção inválida.")
    except KeyboardInterrupt:
        print("\nInterrompido pelo usuário.")
    finally:
        node.stop()
        print("Nó encerrado.")


if __name__ == "__main__":
    main()
