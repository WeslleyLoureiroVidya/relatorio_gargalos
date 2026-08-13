import os
import sys
import requests
import html
import re
from datetime import datetime, timedelta
from collections import Counter
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ============================================================
# CONFIGURAÇÕES
# ============================================================
MOVIDESK_TOKEN = os.environ.get("MOVIDESK_TOKEN")
EMAIL_USER = os.environ.get("EMAIL_USER")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")
EMAIL_TO = [e.strip() for e in os.environ.get("EMAIL_TO", "").split(",") if e.strip()]

# Checagem básica de variáveis obrigatórias (falha rápido e com log claro)
faltando = []
if not MOVIDESK_TOKEN:
    faltando.append("MOVIDESK_TOKEN")
if not EMAIL_USER:
    faltando.append("EMAIL_USER")
if not EMAIL_PASSWORD:
    faltando.append("EMAIL_PASSWORD")
if not EMAIL_TO:
    faltando.append("EMAIL_TO")

if faltando:
    print(f"[ERRO] Variáveis de ambiente ausentes: {', '.join(faltando)}")
    print("[ERRO] Verifique os Secrets do repositório e o mapeamento 'env:' no workflow do GitHub Actions.")
    sys.exit(1)

# ============================================================
# BUSCAR TICKETS
# ============================================================
hoje = datetime.now()
sete_dias_atras = hoje - timedelta(days=7)
data_filtro = sete_dias_atras.strftime("%Y-%m-%dT00:00:00Z")

url_tickets = "https://api.movidesk.com/public/v1/tickets"
params = {
    "token": MOVIDESK_TOKEN,
    "$filter": f"createdDate ge {data_filtro}",
    # IMPORTANTE: todo campo usado no $filter também precisa estar no $select,
    # senão a API do Movidesk costuma devolver uma lista vazia silenciosamente.
    "$select": "subject,service,category,createdDate",
    "$top": "1000"
}

print(f"[DEBUG] Buscando tickets desde: {data_filtro}")
response = requests.get(url_tickets, params=params)

print(f"[DEBUG] Status HTTP: {response.status_code}")
print(f"[DEBUG] URL final: {response.url}")

if not response.ok:
    print(f"[ERRO] Falha na API Movidesk: {response.status_code} - {response.text[:1000]}")
    tickets = []
else:
    try:
        tickets = response.json()
    except ValueError:
        print(f"[ERRO] Resposta não é um JSON válido. Corpo bruto: {response.text[:1000]}")
        tickets = []

    if not isinstance(tickets, list):
        print(f"[ERRO] Resposta inesperada (não é lista). Conteúdo: {str(tickets)[:1000]}")
        tickets = []

    print(f"[DEBUG] Total de tickets encontrados: {len(tickets)}")
    if tickets:
        print(f"[DEBUG] Exemplo de ticket (primeiro item): {tickets[0]}")
    else:
        print("[DEBUG] Lista veio vazia. Possíveis causas: token sem permissão, "
              "filtro sem resultados no período, ou campo do $filter fora do $select.")

# ============================================================
# PROCESSAMENTO
# ============================================================
categorias = Counter()
servicos = Counter()
palavras = Counter()
STOPWORDS = {"de", "a", "o", "que", "e", "do", "da", "em", "um", "para", "é", "com", "não", "uma", "os", "no", "se", "na", "por", "mais", "as", "dos", "como", "mas", "foi", "ao", "ele", "das", "tem", "seu", "sua", "ou", "ser", "quando", "muito", "nos", "já", "está", "eu"}


def extrair_texto(campo):
    """
    Alguns planos do Movidesk retornam category/service como string simples,
    outros como objeto aninhado (ex: {"name": "..."} ou {"description": "..."}).
    Esta função normaliza os dois formatos.
    """
    if campo is None:
        return None
    if isinstance(campo, str):
        return campo
    if isinstance(campo, dict):
        for chave in ("name", "description", "title", "value"):
            if campo.get(chave):
                return str(campo[chave])
        return str(campo)
    return str(campo)


def limpar_texto(texto):
    if not texto:
        return []
    texto = texto.lower()
    texto = re.sub(r'[^a-z0-9\s]', '', texto)
    return texto.split()


for t in tickets:
    cat = extrair_texto(t.get("category")) or "Sem Categoria"
    svc = extrair_texto(t.get("service")) or "Sem Serviço"
    sub = t.get("subject", "") or ""

    categorias[cat] += 1
    servicos[svc] += 1

    for palavra in limpar_texto(sub):
        if palavra not in STOPWORDS and len(palavra) > 3:
            palavras[palavra] += 1

print(f"[DEBUG] Categorias distintas: {len(categorias)}")
print(f"[DEBUG] Serviços distintos: {len(servicos)}")
print(f"[DEBUG] Palavras-chave distintas: {len(palavras)}")

# ============================================================
# MONTAGEM DO HTML
# ============================================================
def criar_tabela(titulo, contador):
    if not contador:
        return f"<h3>{titulo}</h3><p>Nenhum dado encontrado.</p>"
    html_tab = f"<h3>{titulo}</h3><table style='width:100%; border-collapse:collapse; margin-bottom:20px;'>"
    html_tab += "<tr><th style='text-align:left; border-bottom:2px solid #ddd;'>Item</th><th style='text-align:right; border-bottom:2px solid #ddd;'>Qtd</th></tr>"
    for item, qtd in contador.most_common(10):
        html_tab += f"<tr><td style='padding:5px 0;'>{html.escape(str(item))}</td><td style='text-align:right;'>{qtd}</td></tr>"
    html_tab += "</table>"
    return html_tab

html_body = f"""
<h1>Relatório Semanal de Gargalos ({sete_dias_atras.strftime('%d/%m')} a {hoje.strftime('%d/%m')})</h1>
<p>Total de tickets processados: <strong>{len(tickets)}</strong></p>
{criar_tabela("Top Categorias", categorias)}
{criar_tabela("Top Serviços", servicos)}
{criar_tabela("Palavras-Chave Frequentes (Assuntos)", palavras)}
"""

# ============================================================
# ENVIO (Só envia se tiver ticket)
# ============================================================
if not tickets:
    print("[INFO] Nenhum ticket encontrado, abortando envio de e-mail para evitar spam.")
    # Sai com código de erro para o job do GitHub Actions ficar visivelmente "failed"
    # quando o esperado era ter tickets. Comente a linha abaixo se preferir que
    # "sem tickets" seja tratado como sucesso silencioso.
    sys.exit(1)
else:
    msg = MIMEMultipart()
    msg["From"] = EMAIL_USER
    msg["To"] = ", ".join(EMAIL_TO)
    msg["Subject"] = f"📊 Relatório Semanal: Assuntos Frequentes ({hoje.strftime('%d/%m')})"
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_USER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_USER, EMAIL_TO, msg.as_string())
        print("[INFO] E-mail enviado com sucesso!")
    except smtplib.SMTPAuthenticationError as e:
        print(f"[ERRO] Falha de autenticação SMTP: {e}")
        print("[ERRO] Se usa Gmail, confirme que EMAIL_PASSWORD é uma 'senha de app' (App Password), não a senha normal da conta.")
        sys.exit(1)
    except Exception as e:
        print(f"[ERRO] Falha ao enviar e-mail: {e}")
        sys.exit(1)
