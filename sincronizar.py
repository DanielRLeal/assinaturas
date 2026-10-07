#!/usr/bin/env python3
"""
Assinaturas de email da Orira, automáticas.

Corre em dois passos (o fluxo do GitHub Actions faz isto sozinho, todos os dias):

  1. python sincronizar.py gerar
       Lê os membros ativos do Google Workspace e gera a imagem da assinatura
       de quem ainda não a tem, ou de quem mudou de nome ou de cargo.
       As imagens ficam em docs/ e as pendentes em docs/pendentes.json.

  2. python sincronizar.py aplicar
       Define a assinatura no Gmail de cada pessoa pendente.
       Só corre depois de as imagens estarem publicadas.

Para experimentar sem tocar no Google:
  python sincronizar.py gerar --csv membros.csv      (colunas: email,nome,cargo)
  python sincronizar.py aplicar --dry-run
"""
import argparse
import base64
import csv
import hashlib
import html
import json
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
RECURSOS = RAIZ / "recursos"
SAIDA = RAIZ / "docs"
ESTADO = SAIDA / "estado.json"
PENDENTES = SAIDA / "pendentes.json"

# ---------------------------------------------------------------------------
# Configuração (variáveis de ambiente; no GitHub definem-se em Settings)
# ---------------------------------------------------------------------------
# Conteúdo do ficheiro JSON da conta de serviço (opcional: sem chave usa-se a
# Workload Identity Federation do GitHub Actions e CONTA_SERVICO).
CHAVE_JSON = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
# Email da conta de serviço, quando não há chave JSON.
CONTA_SERVICO = os.environ.get("CONTA_SERVICO", "")
# Email de um superadministrador do Workspace (para ler a lista de membros).
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "")
# Endereço público da pasta docs/, por exemplo https://orira.github.io/assinaturas
URL_BASE_IMAGENS = os.environ.get("URL_BASE_IMAGENS", "").rstrip("/")
# Para onde vai quem clica na assinatura.
URL_SITE = os.environ.get("URL_SITE", "https://orira.app")
# Emails a ignorar (caixas partilhadas, contas técnicas), separados por vírgulas.
EXCLUIR = {e.strip().lower() for e in os.environ.get("EXCLUIR", "").split(",") if e.strip()}

# Identificação da empresa (art. 171.º do CSC), em texto por baixo da imagem.
# A morada fica na página de contactos, para onde aponta "Dados legais".
EMPRESA = "Daniel Romão Leal, Sociedade Unipessoal, Lda."
NIPC = "519502078"
URL_DADOS_LEGAIS = os.environ.get("URL_DADOS_LEGAIS", f"{URL_SITE}/contacto")

LARGURA_NO_EMAIL = 560  # a imagem tem 1120 px, por isso fica nítida em ecrãs retina

AMBITO_DIRETORIO = ["https://www.googleapis.com/auth/admin.directory.user.readonly"]
AMBITO_GMAIL = ["https://www.googleapis.com/auth/gmail.settings.basic"]


# ---------------------------------------------------------------------------
# Membros
# ---------------------------------------------------------------------------
def credenciais(ambito, em_nome_de):
    from google.oauth2 import service_account

    if CHAVE_JSON:
        return service_account.Credentials.from_service_account_info(
            json.loads(CHAVE_JSON), scopes=ambito
        ).with_subject(em_nome_de)

    # Sem chave: o GitHub Actions entra no Google Cloud por Workload Identity
    # Federation e a conta de serviço assina o pedido pela IAM Credentials API.
    import google.auth
    from google.auth import iam
    from google.auth.transport.requests import Request

    if not CONTA_SERVICO:
        sys.exit("Falta a variável GOOGLE_SERVICE_ACCOUNT_JSON ou CONTA_SERVICO.")
    origem, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    return service_account.Credentials(
        signer=iam.Signer(Request(), origem, CONTA_SERVICO),
        service_account_email=CONTA_SERVICO,
        token_uri="https://oauth2.googleapis.com/token",
        scopes=ambito,
        subject=em_nome_de,
    )


def membros_do_workspace():
    """Membros ativos do diretório: (email, nome, cargo)."""
    from googleapiclient.discovery import build

    if not ADMIN_EMAIL:
        sys.exit("Falta a variável ADMIN_EMAIL.")
    diretorio = build(
        "admin", "directory_v1",
        credentials=credenciais(AMBITO_DIRETORIO, ADMIN_EMAIL), cache_discovery=False,
    )
    pedido = diretorio.users().list(
        customer="my_customer", query="isSuspended=false",
        projection="full", maxResults=200, orderBy="email",
    )
    while pedido is not None:
        resposta = pedido.execute()
        for u in resposta.get("users", []):
            if u.get("archived"):
                continue
            orgs = u.get("organizations") or []
            principal = next((o for o in orgs if o.get("primary")), orgs[0] if orgs else {})
            yield (
                u["primaryEmail"].lower(),
                (u.get("name", {}).get("fullName") or "").strip(),
                (principal.get("title") or "").strip(),
            )
        pedido = diretorio.users().list_next(pedido, resposta)


def membros_do_csv(caminho):
    with open(caminho, newline="", encoding="utf-8-sig") as f:
        for linha in csv.DictReader(f):
            linha = {k.strip().lower(): (v or "").strip() for k, v in linha.items()}
            if linha.get("email"):
                yield linha["email"].lower(), linha.get("nome", ""), linha.get("cargo", "")


# ---------------------------------------------------------------------------
# Imagem
# ---------------------------------------------------------------------------
def b64(caminho):
    return base64.b64encode(caminho.read_bytes()).decode()


def modelo_base():
    m = (RECURSOS / "modelo.html").read_text(encoding="utf-8")
    return (
        m.replace("{{LOGO}}", b64(RECURSOS / "logo.png"))
        .replace("{{FONTE_400}}", b64(RECURSOS / "SpaceGrotesk-Regular.ttf"))
        .replace("{{FONTE_500}}", b64(RECURSOS / "SpaceGrotesk-Medium.ttf"))
        .replace("{{FONTE_700}}", b64(RECURSOS / "SpaceGrotesk-Bold.ttf"))
    )


def versao_do_design():
    """Muda quando o modelo, o logótipo, as fontes ou a linha legal mudam: obriga a refazer tudo."""
    h = hashlib.sha256()
    h.update(f"{EMPRESA}|{NIPC}|{URL_DADOS_LEGAIS}".encode())
    for f in sorted(RECURSOS.glob("*")):
        if f.suffix in {".html", ".png", ".ttf"}:
            h.update(f.read_bytes())
    return h.hexdigest()[:12]


def encolher(texto, tamanho, cabem, minimo):
    """Reduz o tamanho da letra quando o texto é mais comprido do que cabe."""
    if len(texto) <= cabem:
        return tamanho
    return max(minimo, round(tamanho * cabem / len(texto)))


def html_da_imagem(base, email, nome, cargo):
    return (
        base.replace("{{NOME}}", html.escape(nome))
        .replace("{{CARGO}}", html.escape(cargo))
        .replace("{{EMAIL}}", html.escape(email))
        .replace("{{TAMANHO_NOME}}", str(encolher(nome, 40, 26, 22)))
        .replace("{{TAMANHO_CARGO}}", str(encolher(cargo, 20, 52, 13)))
        .replace("{{TAMANHO_EMAIL}}", str(encolher(email, 18, 38, 13)))
    )


def nome_do_ficheiro(email):
    return f"assinatura-{email.split('@')[0]}.png"


def impressao(email, nome, cargo, versao):
    return hashlib.sha256(f"{versao}|{email}|{nome}|{cargo}".encode()).hexdigest()[:12]


# ---------------------------------------------------------------------------
# Passo 1: gerar
# ---------------------------------------------------------------------------
def gerar(args):
    from playwright.sync_api import sync_playwright

    SAIDA.mkdir(exist_ok=True)
    estado = json.loads(ESTADO.read_text()) if ESTADO.exists() else {}
    pendentes = json.loads(PENDENTES.read_text()) if PENDENTES.exists() else {}
    versao = versao_do_design()
    base = modelo_base()

    membros = list(membros_do_csv(args.csv) if args.csv else membros_do_workspace())
    por_gerar, sem_cargo = [], []
    for email, nome, cargo in membros:
        if email in EXCLUIR:
            continue
        if not nome or not cargo:
            sem_cargo.append(email)
            continue
        marca = impressao(email, nome, cargo, versao)
        if estado.get(email) != marca or not (SAIDA / nome_do_ficheiro(email)).exists():
            por_gerar.append((email, nome, cargo, marca))

    if por_gerar:
        with sync_playwright() as p:
            navegador = p.chromium.launch()
            pagina = navegador.new_page(viewport={"width": 1120, "height": 300})
            for email, nome, cargo, marca in por_gerar:
                pagina.set_content(html_da_imagem(base, email, nome, cargo))
                pagina.evaluate("document.fonts.ready")
                pagina.screenshot(path=str(SAIDA / nome_do_ficheiro(email)), omit_background=True)
                estado[email] = marca
                pendentes[email] = {"nome": nome, "cargo": cargo, "marca": marca}
                print(f"gerada   {email}  ({nome}, {cargo})")
            navegador.close()

    ESTADO.write_text(json.dumps(estado, indent=2, sort_keys=True) + "\n")
    PENDENTES.write_text(json.dumps(pendentes, indent=2, sort_keys=True, ensure_ascii=False) + "\n")

    for email in sem_cargo:
        print(f"ignorada {email}: falta o nome ou o cargo no diretório do Workspace")
    print(f"\n{len(por_gerar)} imagens geradas, {len(membros)} membros lidos, "
          f"{len(pendentes)} assinaturas por aplicar.")


# ---------------------------------------------------------------------------
# Passo 2: aplicar
# ---------------------------------------------------------------------------
def html_da_assinatura(email, dados):
    alt = html.escape(f"{dados['nome']}, {dados['cargo']} · Orira", quote=True)
    # ?v= muda quando a imagem muda, para o Gmail não mostrar uma cópia antiga.
    src = f"{URL_BASE_IMAGENS}/{nome_do_ficheiro(email)}?v={dados['marca']}"
    return (
        f'<a href="{URL_SITE}" target="_blank">'
        f'<img src="{src}" alt="{alt}" width="{LARGURA_NO_EMAIL}" '
        f'style="display:block;border:0;max-width:100%;height:auto"></a>'
        f'<div style="margin-top:8px;font-family:Arial,Helvetica,sans-serif;font-size:11px;'
        f'line-height:16px;color:#8a8a93">'
        f'{html.escape(EMPRESA)} &middot; NIPC {NIPC} &middot; '
        f'<a href="{URL_DADOS_LEGAIS}" target="_blank" style="color:#8a8a93;text-decoration:underline">'
        f'Dados legais</a></div>'
    )


def imagem_publicada(email):
    """True quando a imagem já responde no endereço público."""
    import urllib.request

    try:
        with urllib.request.urlopen(f"{URL_BASE_IMAGENS}/{nome_do_ficheiro(email)}", timeout=10) as r:
            return r.status == 200
    except Exception:
        return False


def esperar_pelas_imagens(emails, limite=300):
    """Uma assinatura com a imagem em falta mostra-se partida a quem a recebe."""
    import time

    falta = set(emails)
    fim = time.monotonic() + limite
    while falta and time.monotonic() < fim:
        falta = {e for e in falta if not imagem_publicada(e)}
        if falta:
            time.sleep(10)
    return falta


def aplicar(args):
    if not URL_BASE_IMAGENS:
        sys.exit("Falta a variável URL_BASE_IMAGENS.")
    pendentes = json.loads(PENDENTES.read_text()) if PENDENTES.exists() else {}
    if not pendentes:
        print("Nada por aplicar.")
        return

    sem_imagem = set() if args.dry_run else esperar_pelas_imagens(pendentes)
    for email in sorted(sem_imagem):
        print(f"adiada   {email}: a imagem ainda não está publicada")

    falhas = 0
    for email, dados in sorted(pendentes.copy().items()):
        if email in sem_imagem:
            continue
        assinatura = html_da_assinatura(email, dados)
        if args.dry_run:
            print(f"[teste] {email}\n        {assinatura}\n")
            continue
        try:
            from googleapiclient.discovery import build

            gmail = build("gmail", "v1", credentials=credenciais(AMBITO_GMAIL, email),
                          cache_discovery=False)
            gmail.users().settings().sendAs().patch(
                userId="me", sendAsEmail=email, body={"signature": assinatura}
            ).execute()
            del pendentes[email]
            print(f"aplicada {email}")
        except Exception as erro:  # fica pendente e volta a tentar na próxima execução
            falhas += 1
            print(f"FALHOU   {email}: {erro}")

    if not args.dry_run:
        PENDENTES.write_text(
            json.dumps(pendentes, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        )
        print(f"\n{falhas} falhas; {len(pendentes)} continuam pendentes.")


def main():
    p = argparse.ArgumentParser(description="Assinaturas de email da Orira.")
    sub = p.add_subparsers(dest="passo", required=True)
    g = sub.add_parser("gerar", help="gera as imagens em falta ou desatualizadas")
    g.add_argument("--csv", help="lê os membros de um CSV (email,nome,cargo) em vez do Workspace")
    g.set_defaults(func=gerar)
    a = sub.add_parser("aplicar", help="define as assinaturas pendentes no Gmail")
    a.add_argument("--dry-run", action="store_true", help="mostra o que faria, sem alterar nada")
    a.set_defaults(func=aplicar)
    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
