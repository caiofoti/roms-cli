# Roms Downloader

Busca e baixa ROMs por console de forma prática, confiável e objetiva:
digita o nome do jogo, escolhe, baixa — com verificação de integridade,
extração automática e capas prontas pro RetroArch/PCSX2, sem passo manual.

## Consoles suportados

GB, GBC, GBA, NES, SNES, N64, Nintendo DS, Master System, Game Gear,
Genesis/Mega Drive, PSX, PS2, Dreamcast, PSP. Lista atual:
`roms-downloader --list-consoles`.

## Instalação

**Recomendado — pipx** (isola o app, expõe o comando globalmente, sem
precisar ativar venv toda vez):

```bash
pipx install git+https://github.com/caiofoti/roms-cli.git
roms-downloader
```

**Alternativa — venv manual:**

```bash
git clone https://github.com/caiofoti/roms-cli.git
cd roms-cli
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\Activate.ps1
pip install -e .
```

### Dependência de sistema (só pra `.rar`)

`.zip` e `.7z` funcionam sem nada extra. Pra `.rar` (raro nesses acervos),
o sistema precisa ter `unrar` ou `7z` instalado:

```bash
# Linux
sudo apt install unrar
# macOS
brew install unrar
# Windows: 7-Zip já cobre, https://7-zip.org
```

## Configuração (.env)

Sem isso, busca/download funcionam normal, mas `/info`, `/top` e capa
automática não. Precisa de 1 chave gratuita da [RAWG](https://rawg.io/apidocs)
(cadastro simples, sem cartão).

**Se instalou via venv manual** (tem o repo clonado):

```bash
cp .env.example .env
# edite .env e coloque: RAWG_API_KEY=sua_chave_aqui
```

**Se instalou via pipx** (sem repo local): rode `roms-downloader --config` —
a tela mostra o caminho exato onde criar o `.env` (pasta de configuração
padrão do seu SO). Crie o arquivo lá com uma linha:

```
RAWG_API_KEY=sua_chave_aqui
```

O app avisa na tela inicial e em `/config` se a chave não estiver configurada.

## Uso

Sem argumentos abre o **chat interativo**:

```bash
roms-downloader
```

| Comando | O que faz |
|---|---|
| `/console <nome>` | escolhe o console |
| `<texto>` | busca no console atual |
| `/download <n>[,<n>...\|<n>-<n>]` | baixa por número, lista ou faixa (ex: `1-10`), em paralelo |
| `/delete <n>[,<n>...\|<n>-<n>]` | apaga rom(s) local(is) + capa, com confirmação |
| `/scan` | varre a pasta de ROMs e completa capa do que já existe sem uma |
| `/info <n>` | nota, gêneros, descrição (RAWG) |
| `/top` | melhores avaliados (RAWG) |
| `/config` | pasta de ROMs, limites, downloads simultâneos, auto-clear |
| `/clean` | apaga downloads incompletos |
| `/help` | lista completa |

Sessões longas viram scroll infinito rápido — configure auto-clear em
`/config` (limpa a tela sozinho a cada N ações) se preferir.

Modo direto, sem chat:

```bash
roms-downloader --console "PS2" --query "crash bandicoot"
roms-downloader --console "SNES" --query "zelda" --yes
```

## Depois do download

1. Hash (md5/sha1) confere contra o valor oficial do archive.org.
2. `.zip`/`.7z`/`.rar` extraem sozinhos — arquivo compactado some, jogo fica
   pronto pra abrir.
3. Capa baixa e salva automaticamente em `Documentos/PCSX2/covers` e/ou
   `thumbnails/<Sistema>/Named_Boxarts` do RetroArch (detecção automática).

A coluna "Downloads"/"★" vem de estatísticas do próprio archive.org (nível
do acervo, não por ROM) — sinal de quão usada/confiável é a fonte.

## Desenvolvimento

```bash
pip install -r requirements.txt
pytest
```

## Aviso legal

Este projeto só automatiza busca e download de arquivos publicamente
indexados no archive.org — não hospeda, distribui nem modifica ROMs. A
legalidade de baixar ROMs de jogos que você não possui varia por país; a
responsabilidade de verificar isso é de quem usa a ferramenta.

## Licença

MIT — ver [LICENSE](LICENSE).
