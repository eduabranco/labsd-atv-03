"""
Blockchain
Compatível com a turma (mesmo protocolo de rede e estrutura de dados).
Usa apenas a biblioteca padrão do Python (sem dependências externas).
"""

import hashlib
import json
import time
import uuid
from enum import Enum
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Transaction
# ---------------------------------------------------------------------------

@dataclass
class Transaction:
    """Representa uma transação na blockchain."""
    origem: str
    destino: str
    valor: float
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)

    def __post_init__(self):
        if self.valor <= 0:
            raise ValueError("Valor da transação deve ser positivo")
        if not self.origem or not self.destino:
            raise ValueError("Origem e destino são obrigatórios")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "origem": self.origem,
            "destino": self.destino,
            "valor": self.valor,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Transaction":
        return cls(
            id=data["id"],
            origem=data["origem"],
            destino=data["destino"],
            valor=data["valor"],
            timestamp=data["timestamp"],
        )

    def __hash__(self):
        return hash(self.id)

    def __eq__(self, other):
        if isinstance(other, Transaction):
            return self.id == other.id
        return False


# ---------------------------------------------------------------------------
# Block
# ---------------------------------------------------------------------------

@dataclass
class Block:
    """Representa um bloco na blockchain."""
    index: int
    previous_hash: str
    transactions: list
    nonce: int = 0
    timestamp: float = field(default_factory=time.time)
    hash: str = ""

    def __post_init__(self):
        if not self.hash:
            self.hash = self.calculate_hash()

    def calculate_hash(self) -> str:
        """Calcula o hash SHA-256 do bloco (excluindo o campo hash)."""
        block_data = {
            "index": self.index,
            "previous_hash": self.previous_hash,
            "transactions": [tx.to_dict() for tx in self.transactions],
            "nonce": self.nonce,
            "timestamp": self.timestamp,
        }
        block_string = json.dumps(block_data, sort_keys=True)
        return hashlib.sha256(block_string.encode()).hexdigest()

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "previous_hash": self.previous_hash,
            "transactions": [tx.to_dict() for tx in self.transactions],
            "nonce": self.nonce,
            "timestamp": self.timestamp,
            "hash": self.hash,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Block":
        transactions = [Transaction.from_dict(tx) for tx in data["transactions"]]
        return cls(
            index=data["index"],
            previous_hash=data["previous_hash"],
            transactions=transactions,
            nonce=data["nonce"],
            timestamp=data["timestamp"],
            hash=data["hash"],
        )

    @classmethod
    def create_genesis(cls) -> "Block":
        """Cria o bloco gênesis com parâmetros fixos (mesmo da versão completa)."""
        genesis = cls(
            index=0,
            previous_hash="0" * 64,
            transactions=[],
            nonce=0,
            timestamp=0,
        )
        genesis.hash = genesis.calculate_hash()
        return genesis

    def is_valid_hash(self, difficulty: str = "000") -> bool:
        return self.hash.startswith(difficulty)


# ---------------------------------------------------------------------------
# Blockchain
# ---------------------------------------------------------------------------

class Blockchain:
    """Gerencia a cadeia de blocos e o pool de transações pendentes."""

    DIFFICULTY = "000"

    def __init__(self):
        self.chain: list[Block] = [Block.create_genesis()]
        self.pending_transactions: list[Transaction] = []

    @property
    def last_block(self) -> Block:
        return self.chain[-1]

    def get_balance(self, address: str) -> float:
        balance = 0.0
        for block in self.chain:
            for tx in block.transactions:
                if tx.destino == address:
                    balance += tx.valor
                if tx.origem == address:
                    balance -= tx.valor
        for tx in self.pending_transactions:
            if tx.origem == address:
                balance -= tx.valor
        return balance

    def add_transaction(self, transaction: Transaction, trusted: bool = False) -> bool:
        """Adiciona transação ao pool; trusted=True ignora verificação de saldo."""
        if transaction in self.pending_transactions:
            return False
        for block in self.chain:
            if transaction in block.transactions:
                return False
        if not trusted and transaction.origem not in ("genesis", "coinbase"):
            if self.get_balance(transaction.origem) < transaction.valor:
                return False
        self.pending_transactions.append(transaction)
        return True

    def add_block(self, block: Block) -> bool:
        if not self.is_valid_block(block):
            return False
        for tx in block.transactions:
            if tx in self.pending_transactions:
                self.pending_transactions.remove(tx)
        self.chain.append(block)
        return True

    def is_valid_block(self, block: Block) -> bool:
        if block.index != len(self.chain):
            return False
        if block.previous_hash != self.last_block.hash:
            return False
        if not block.hash.startswith(self.DIFFICULTY):
            return False
        if block.hash != block.calculate_hash():
            return False
        return True

    def is_valid_chain(self, chain: list[Block] = None) -> bool:
        if chain is None:
            chain = self.chain
        if not chain:
            return False
        if chain[0].hash != Block.create_genesis().hash:
            return False
        for i in range(1, len(chain)):
            cur, prev = chain[i], chain[i - 1]
            if cur.previous_hash != prev.hash:
                return False
            if cur.hash != cur.calculate_hash():
                return False
            if not cur.hash.startswith(self.DIFFICULTY):
                return False
        return True

    def replace_chain(self, new_chain: list[Block]) -> bool:
        """Substitui pela cadeia mais longa e válida (regra do consenso)."""
        if len(new_chain) <= len(self.chain):
            return False
        if not self.is_valid_chain(new_chain):
            return False
        self.chain = new_chain
        return True

    def to_dict(self) -> dict:
        return {
            "chain": [b.to_dict() for b in self.chain],
            "pending_transactions": [tx.to_dict() for tx in self.pending_transactions],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Blockchain":
        bc = cls()
        bc.chain = [Block.from_dict(b) for b in data["chain"]]
        bc.pending_transactions = [Transaction.from_dict(tx) for tx in data["pending_transactions"]]
        return bc


# ---------------------------------------------------------------------------
# Miner
# ---------------------------------------------------------------------------

class Miner:
    """Implementa Proof of Work."""

    REWARD = 50.0

    def __init__(self, blockchain: Blockchain, miner_address: str):
        self.blockchain = blockchain
        self.miner_address = miner_address
        self.mining = False

    def mine_block(self, transactions: list = None, on_progress=None) -> "Block | None":
        """
        Minera um novo bloco. Retorna o bloco ou None se interrompido.
        on_progress(nonce) é chamado a cada 10 000 tentativas.
        """
        if transactions is None:
            transactions = list(self.blockchain.pending_transactions)

        self.mining = True
        block_timestamp = time.time()

        reward_tx = Transaction(
            origem="coinbase",
            destino=self.miner_address,
            valor=self.REWARD,
            timestamp=block_timestamp,
        )
        transactions = [reward_tx] + transactions

        block = Block(
            index=len(self.blockchain.chain),
            previous_hash=self.blockchain.last_block.hash,
            transactions=transactions,
            nonce=0,
            timestamp=block_timestamp,
        )

        while self.mining:
            block.hash = block.calculate_hash()
            if block.is_valid_hash(Blockchain.DIFFICULTY):
                self.mining = False
                return block
            block.nonce += 1
            if on_progress and block.nonce % 10_000 == 0:
                on_progress(block.nonce)

        return None

    def stop_mining(self):
        self.mining = False


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------

class MessageType(Enum):
    NEW_TRANSACTION = "NEW_TRANSACTION"
    NEW_BLOCK = "NEW_BLOCK"
    REQUEST_CHAIN = "REQUEST_CHAIN"
    RESPONSE_CHAIN = "RESPONSE_CHAIN"
    REQUEST_MEMPOOL = "REQUEST_MEMPOOL"
    RESPONSE_MEMPOOL = "RESPONSE_MEMPOOL"
    PING = "PING"
    PONG = "PONG"
    DISCOVER_PEERS = "DISCOVER_PEERS"
    PEERS_LIST = "PEERS_LIST"


@dataclass
class Message:
    """Mensagem do protocolo de comunicação."""
    type: MessageType
    payload: dict
    sender: str = ""

    def to_json(self) -> str:
        return json.dumps({"type": self.type.value, "payload": self.payload, "sender": self.sender})

    @classmethod
    def from_json(cls, data: str) -> "Message":
        parsed = json.loads(data)
        return cls(type=MessageType(parsed["type"]), payload=parsed["payload"], sender=parsed.get("sender", ""))

    def to_bytes(self) -> bytes:
        """Serializa com prefixo de 4 bytes para o tamanho (big-endian)."""
        encoded = self.to_json().encode()
        return len(encoded).to_bytes(4, "big") + encoded

    @classmethod
    def from_bytes(cls, data: bytes) -> "Message":
        return cls.from_json(data.decode())


class Protocol:
    """Factory de mensagens."""

    @staticmethod
    def new_transaction(tx: dict) -> Message:
        return Message(MessageType.NEW_TRANSACTION, {"transaction": tx})

    @staticmethod
    def new_block(block: dict) -> Message:
        return Message(MessageType.NEW_BLOCK, {"block": block})

    @staticmethod
    def request_chain() -> Message:
        return Message(MessageType.REQUEST_CHAIN, {})

    @staticmethod
    def response_chain(bc: dict) -> Message:
        return Message(MessageType.RESPONSE_CHAIN, {"blockchain": bc})

    @staticmethod
    def request_mempool() -> Message:
        return Message(MessageType.REQUEST_MEMPOOL, {})

    @staticmethod
    def response_mempool(txs: list) -> Message:
        return Message(MessageType.RESPONSE_MEMPOOL, {"transactions": txs})

    @staticmethod
    def ping() -> Message:
        return Message(MessageType.PING, {})

    @staticmethod
    def pong() -> Message:
        return Message(MessageType.PONG, {})

    @staticmethod
    def discover_peers() -> Message:
        return Message(MessageType.DISCOVER_PEERS, {})

    @staticmethod
    def peers_list(peers: list) -> Message:
        return Message(MessageType.PEERS_LIST, {"peers": peers})
