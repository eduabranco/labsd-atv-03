"""
Nó P2P 

Gerencia conexões TCP com outros nós, processa mensagens do protocolo
e mantém a blockchain local sincronizada.
"""

import socket
import threading
import logging

from core import (
    Blockchain, Block, Transaction, Miner,
    Protocol, Message, MessageType,
)

BUFFER_SIZE = 65536  # 64 KB


def _recv_message(sock: socket.socket) -> "Message | None":
    """Lê uma mensagem length-prefixed do socket."""
    try:
        length_data = sock.recv(4)
        if not length_data:
            return None
        length = int.from_bytes(length_data, "big")
        data = b""
        while len(data) < length:
            chunk = sock.recv(min(BUFFER_SIZE, length - len(data)))
            if not chunk:
                break
            data += chunk
        return Message.from_bytes(data) if data else None
    except Exception:
        return None


def _send_message_raw(sock: socket.socket, message: Message):
    sock.sendall(message.to_bytes())


class Node:
    """Nó da rede P2P."""

    def __init__(self, host: str = "localhost", port: int = 5000):
        self.host = host
        self.port = port
        self.address = f"{host}:{port}"

        self.blockchain = Blockchain()
        self.miner = Miner(self.blockchain, self.address)
        self.peers: set[str] = set()

        self._server: socket.socket | None = None
        self.running = False

        self.logger = logging.getLogger(f"Node:{port}")

        # Callbacks opcionais
        self.on_new_block = None
        self.on_new_transaction = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self):
        """Inicia o servidor TCP em background."""
        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server.bind(("0.0.0.0", self.port))
        self._server.listen(10)
        self.running = True
        self.logger.info(f"Nó iniciado em {self.address}")
        t = threading.Thread(target=self._accept_loop, daemon=True)
        t.start()

    def stop(self):
        self.running = False
        self.miner.stop_mining()
        if self._server:
            self._server.close()
        self.logger.info("Nó encerrado")

    # ------------------------------------------------------------------
    # Server loop
    # ------------------------------------------------------------------

    def _accept_loop(self):
        while self.running:
            try:
                client_sock, addr = self._server.accept()
                t = threading.Thread(target=self._handle_client, args=(client_sock, addr), daemon=True)
                t.start()
            except Exception as e:
                if self.running:
                    self.logger.error(f"Erro ao aceitar conexão: {e}")

    def _handle_client(self, sock: socket.socket, addr):
        try:
            msg = _recv_message(sock)
            if msg:
                response = self._process(msg)
                if response:
                    _send_message_raw(sock, response)
        except Exception as e:
            self.logger.error(f"Erro com cliente {addr}: {e}")
        finally:
            sock.close()

    # ------------------------------------------------------------------
    # Message processing
    # ------------------------------------------------------------------

    def _process(self, msg: Message) -> "Message | None":
        self.logger.debug(f"Mensagem: {msg.type.value} de {msg.sender}")

        match msg.type:

            case MessageType.NEW_TRANSACTION:
                tx = Transaction.from_dict(msg.payload["transaction"])
                if self.blockchain.add_transaction(tx):
                    self.logger.info(f"Transação adicionada: {tx.id[:8]}...")
                    self._broadcast(msg, exclude=msg.sender)
                    if self.on_new_transaction:
                        self.on_new_transaction(tx)

            case MessageType.NEW_BLOCK:
                block = Block.from_dict(msg.payload["block"])
                if self.blockchain.add_block(block):
                    self.logger.info(f"Bloco adicionado: #{block.index}")
                    self.miner.stop_mining()
                    self._broadcast(msg, exclude=msg.sender)
                    if self.on_new_block:
                        self.on_new_block(block)
                else:
                    # Tenta sincronizar com o remetente
                    if msg.sender:
                        self._try_sync_from(msg.sender)

            case MessageType.REQUEST_CHAIN:
                if msg.sender and msg.sender != self.address:
                    self.peers.add(msg.sender)
                return Protocol.response_chain(self.blockchain.to_dict())

            case MessageType.REQUEST_MEMPOOL:
                txs = [tx.to_dict() for tx in self.blockchain.pending_transactions]
                return Protocol.response_mempool(txs)

            case MessageType.RESPONSE_CHAIN:
                chain_data = msg.payload["blockchain"]
                new_chain = [Block.from_dict(b) for b in chain_data["chain"]]
                if self.blockchain.replace_chain(new_chain):
                    self.logger.info(f"Chain atualizada: {len(new_chain)} blocos")
                if msg.sender and msg.sender != self.address:
                    self.peers.add(msg.sender)

            case MessageType.PING:
                if msg.sender and msg.sender != self.address:
                    self.peers.add(msg.sender)
                return Protocol.pong()

            case MessageType.DISCOVER_PEERS:
                return Protocol.peers_list(list(self.peers))

            case MessageType.PEERS_LIST:
                new_peers = set(msg.payload.get("peers", [])) - {self.address}
                self.peers.update(new_peers)

        return None

    # ------------------------------------------------------------------
    # Peer management
    # ------------------------------------------------------------------

    def connect_to_peer(self, peer_address: str) -> bool:
        """
        Conecta a um peer via REQUEST_CHAIN (handshake obrigatório pelo protocolo).
        Compatível com nós que respondem no mesmo socket ou via callback.
        """
        if peer_address == self.address:
            return False
        try:
            host, port = peer_address.split(":")
            connected = False
            response = None

            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(10)
                sock.connect((host, int(port)))
                connected = True

                req = Protocol.request_chain()
                req.sender = self.address
                _send_message_raw(sock, req)

                try:
                    response = _recv_message(sock)
                except Exception:
                    pass  # peer usa estilo callback

            if not connected:
                return False

            self.peers.add(peer_address)
            self.logger.info(f"Peer conectado: {peer_address}")

            if response and response.type == MessageType.RESPONSE_CHAIN:
                chain_data = response.payload["blockchain"]
                new_chain = [Block.from_dict(b) for b in chain_data["chain"]]
                if self.blockchain.replace_chain(new_chain):
                    self.logger.info(f"Chain sincronizada no handshake: {len(new_chain)} blocos")

            return True

        except Exception as e:
            self.logger.error(f"Erro ao conectar a {peer_address}: {e}")
            return False

    def sync_blockchain(self):
        """Obtém a cadeia mais longa de todos os peers conhecidos."""
        for peer in list(self.peers):
            response = self._send(peer, Protocol.request_chain())
            if response and response.type == MessageType.RESPONSE_CHAIN:
                chain_data = response.payload["blockchain"]
                new_chain = [Block.from_dict(b) for b in chain_data["chain"]]
                if self.blockchain.replace_chain(new_chain):
                    self.logger.info(f"Chain sincronizada de {peer}: {len(new_chain)} blocos")
                    break

    def sync_mempool(self) -> dict:
        """Obtém transações pendentes de cada peer."""
        added = 0
        unreachable = []
        for peer in list(self.peers):
            response = self._send(peer, Protocol.request_mempool())
            if response and response.type == MessageType.RESPONSE_MEMPOOL:
                for tx_data in response.payload["transactions"]:
                    tx = Transaction.from_dict(tx_data)
                    if self.blockchain.add_transaction(tx, trusted=True):
                        added += 1
            else:
                unreachable.append(peer)
        self.logger.info(f"Mempool: +{added} transação(ões)")
        return {"added": added, "unreachable": unreachable}

    # ------------------------------------------------------------------
    # Mining & broadcasting
    # ------------------------------------------------------------------

    def broadcast_transaction(self, tx: Transaction):
        """Adiciona a transação localmente e propaga aos peers."""
        if self.blockchain.add_transaction(tx):
            self._broadcast(Protocol.new_transaction(tx.to_dict()))

    def broadcast_block(self, block: Block):
        """Adiciona o bloco localmente e propaga aos peers."""
        if self.blockchain.add_block(block):
            self._broadcast(Protocol.new_block(block.to_dict()))
            self.logger.info(f"Bloco #{block.index} propagado para {len(self.peers)} peers")

    def mine(self) -> "Block | None":
        """Minera um novo bloco e o propaga se encontrado."""
        self.logger.info("Iniciando mineração...")
        block = self.miner.mine_block(
            on_progress=lambda n: self.logger.debug(f"nonce={n}")
        )
        if block:
            self.logger.info(f"Bloco #{block.index} minerado! hash={block.hash[:16]}...")
            self.broadcast_block(block)
        return block

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _send(self, peer_address: str, message: Message) -> "Message | None":
        """Envia uma mensagem e aguarda resposta (request/response)."""
        try:
            host, port = peer_address.split(":")
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(10)
                sock.connect((host, int(port)))
                message.sender = self.address
                _send_message_raw(sock, message)
                return _recv_message(sock)
        except Exception as e:
            self.logger.error(f"Erro ao enviar para {peer_address}: {e}")
            return None

    def _broadcast(self, message: Message, exclude: str = ""):
        """Envia para todos os peers em threads separadas (fire-and-forget)."""
        message.sender = self.address
        for peer in list(self.peers):
            if peer != exclude:
                threading.Thread(target=self._send, args=(peer, message), daemon=True).start()

    def _try_sync_from(self, peer: str):
        """Tenta substituir a chain local pela do peer."""
        response = self._send(peer, Protocol.request_chain())
        if response and response.type == MessageType.RESPONSE_CHAIN:
            chain_data = response.payload["blockchain"]
            new_chain = [Block.from_dict(b) for b in chain_data["chain"]]
            if self.blockchain.replace_chain(new_chain):
                self.logger.info(f"Chain substituída por {peer}: {len(new_chain)} blocos")
                self.miner.stop_mining()
            self.peers.add(peer)
