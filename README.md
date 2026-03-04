# labsd-atv03
Por Aimeê, Eduardo &amp; Keanu

---

## Arquitetura

O projeto implementa uma rede blockchain peer-to-peer utilizando apenas a biblioteca padrão do Python. Está organizado em três módulos:

| Arquivo | Responsabilidade |
|---|---|
| `core.py` | Modelos de dados, lógica da blockchain, mineração (PoW) e protocolo de mensagens |
| `node.py` | Rede TCP, gerenciamento de peers, roteamento de mensagens e sincronização |
| `main.py` | Ponto de entrada da CLI — analisa argumentos e gerencia o menu interativo |

### Diagrama de classes

```mermaid
classDiagram
    class Transaction {
        +str id
        +str origem
        +str destino
        +float valor
        +float timestamp
        +to_dict() dict
        +from_dict(data) Transaction
    }

    class Block {
        +int index
        +str previous_hash
        +list transactions
        +int nonce
        +float timestamp
        +str hash
        +calculate_hash() str
        +is_valid_hash(difficulty) bool
        +create_genesis() Block
    }

    class Blockchain {
        +list~Block~ chain
        +list~Transaction~ pending_transactions
        +DIFFICULTY = "000"
        +add_transaction(tx, trusted) bool
        +add_block(block) bool
        +is_valid_block(block) bool
        +is_valid_chain(chain) bool
        +replace_chain(new_chain) bool
        +get_balance(address) float
        +to_dict() dict
    }

    class Miner {
        +Blockchain blockchain
        +str miner_address
        +REWARD = 50.0
        +mine_block(transactions, on_progress) Block
        +stop_mining()
    }

    class MessageType {
        <<enumeration>>
        NEW_TRANSACTION
        NEW_BLOCK
        REQUEST_CHAIN
        RESPONSE_CHAIN
        REQUEST_MEMPOOL
        RESPONSE_MEMPOOL
        PING
        PONG
        DISCOVER_PEERS
        PEERS_LIST
    }

    class Message {
        +MessageType type
        +dict payload
        +str sender
        +to_bytes() bytes
        +from_bytes(data) Message
        +to_json() str
        +from_json(data) Message
    }

    class Protocol {
        <<static>>
        +new_transaction(tx) Message
        +new_block(block) Message
        +request_chain() Message
        +response_chain(bc) Message
        +request_mempool() Message
        +response_mempool(txs) Message
        +ping() Message
        +pong() Message
        +discover_peers() Message
        +peers_list(peers) Message
    }

    class Node {
        +str host
        +str port
        +Blockchain blockchain
        +Miner miner
        +set~str~ peers
        +start()
        +stop()
        +connect_to_peer(addr) bool
        +broadcast_transaction(tx)
        +broadcast_block(block)
        +mine() Block
        +sync_blockchain()
        +sync_mempool() dict
    }

    Blockchain "1" *-- "1..*" Block
    Block "1" *-- "0..*" Transaction
    Miner --> Blockchain : uses
    Node *-- Blockchain
    Node *-- Miner
    Node ..> Protocol : creates messages
    Protocol ..> Message : returns
    Message *-- MessageType
```

### Estrutura de dados da blockchain

Cada bloco armazena um hash SHA-256 de seu próprio conteúdo e referencia o hash do bloco anterior, formando uma cadeia à prova de adulterações. A mineração exige encontrar um `nonce` tal que o hash resultante comece com `"000"` (Prova de Trabalho).

```mermaid
graph LR
    G["Block #0 — Genesis\nprev_hash: 000...0\nnonce: 0"]
    B1["Block #1\nprev_hash: hash(#0)\ntransactions: [...]"]
    B2["Block #2\nprev_hash: hash(#1)\ntransactions: [...]"]
    BN["Block #N\nprev_hash: hash(#N-1)\ntransactions: [...]"]

    G --> B1 --> B2 --> BN
```

### Fluxo de mineração por Prova de Trabalho

```mermaid
sequenceDiagram
    participant CLI as main.py (CLI)
    participant Node
    participant Miner

    CLI->>Node: mine()
    Node->>Miner: mine_block(pending_transactions)
    Note over Miner: inclui tx de recompensa coinbase (50 moedas)
    loop incrementa nonce até hash começar com "000"
        Miner->>Miner: block.nonce += 1
        Miner->>Miner: block.hash = SHA-256(block)
    end
    Miner-->>Node: Bloco (hash válido)
    Node->>Node: broadcast_block() para todos os peers
    Node-->>CLI: Bloco
```

### Fluxo de mensagens P2P

Toda a comunicação utiliza TCP com mensagens JSON prefixadas por tamanho (cabeçalho de 4 bytes big-endian).

```mermaid
sequenceDiagram
    participant A as Node A (new)
    participant B as Node B (bootstrap)
    participant C as Node C (peer of B)

    A->>B: REQUEST_CHAIN (handshake)
    B-->>A: RESPONSE_CHAIN (blockchain completa)
    Note over A: adota a cadeia se for maior e válida

    A->>B: NEW_TRANSACTION
    B->>C: NEW_TRANSACTION (broadcast, fire-and-forget)

    A->>B: NEW_BLOCK (após mineração)
    B->>C: NEW_BLOCK (broadcast)
    Note over B,C: interrompe mineração atual se bloco aceito

    A->>B: PING
    B-->>A: PONG

    A->>B: DISCOVER_PEERS
    B-->>A: PEERS_LIST
```

### Topologia de rede

Os nós se comunicam em uma sobreposição estilo gossip. Cada nó rastreia um conjunto simples de endereços de peers conhecidos (`host:port`). Não há topologia estruturada — qualquer nó pode se conectar a qualquer outro.

```mermaid
graph TB
    N1["Node :5000\n(bootstrap)"]
    N2["Node :5001"]
    N3["Node :5002"]
    N4["Node :5003"]

    N1 <--> N2
    N1 <--> N3
    N2 <--> N3
    N2 <--> N4
    N3 <--> N4
```

---

## Como usar

### Requisitos

- Python **3.10+** (utiliza `match`/`case` e anotações de tipo union)
- Sem dependências externas — apenas a biblioteca padrão

### Iniciando um nó

```bash
# Primeiro nó (bootstrap)
python main.py --port 5000

# Nós adicionais entrando na rede
python main.py --port 5001 --bootstrap localhost:5000
python main.py --port 5002 --bootstrap localhost:5000 localhost:5001
```

Todas as opções de linha de comando:

| Flag | Padrão | Descrição |
|---|---|---|
| `--host` | `localhost` | Endereço de bind do servidor TCP |
| `--port` | `5555` | Porta de escuta |
| `--bootstrap` | *(nenhum)* | Lista de endereços de peers separados por espaço para conectar na inicialização |
| `--log` | `INFO` | Nível de log (`DEBUG`, `INFO`, `WARNING`, `ERROR`). Escrito em `node_<port>.log` |

### Menu interativo

Após iniciar um nó, um menu interativo é apresentado:

```
1. Criar transação        — send coins to another node's address (host:port)
2. Ver transações pendentes — list transactions waiting to be mined
3. Minerar bloco          — run PoW, earn 50 coins reward, broadcast the new block
4. Ver blockchain         — print all blocks and their transactions
5. Ver saldo              — check balance of own wallet or any address
6. Ver peers              — list currently known peers
7. Conectar a peer        — manually add a peer by address
8. Sincronizar            — pull the longest chain and missing mempool txs from peers
0. Sair                   — gracefully shut down the node
```

### Sessão de exemplo (dois nós)

**Terminal 1 — nó bootstrap**
```bash
python main.py --port 5000
# Escolha: 3   →  minera o bloco de recompensa genesis
```

**Terminal 2 — segundo nó**
```bash
python main.py --port 5001 --bootstrap localhost:5000
# Escolha: 1   →  cria uma transação
#   Destino: localhost:5000
#   Valor: 10
# Escolha: 8   →  sincroniza para confirmar que a transação apareceu no Nó 1
```

**Terminal 1 — minera a transação**
```bash
# Escolha: 3   →  minera um bloco contendo a transação recebida
```

### Endereços de carteira

O endereço de carteira de cada nó é sua string `host:port` (ex.: `localhost:5001`). Use-o como destino ao criar transações a partir de outro nó.

### Logs

Cada nó grava logs estruturados em `node_<port>.log` no diretório de trabalho. Use `--log DEBUG` para ver o progresso de mineração por nonce e rastreamentos completos de mensagens.
