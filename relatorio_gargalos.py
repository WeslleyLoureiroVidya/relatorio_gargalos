import os
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
EMAIL_TO = os.environ.get("EMAIL_TO", "").split(",")

# Stopwords simples para limpar a análise de palavras (palavras que não importam)
STOPWORDS = {"de", "a", "o", "que", "e", "do", "da", "em", "um", "para", "é", "com", "não", "uma", "os", "no", "se", "na", "por", "mais", "as", "dos", "como", "mas", "foi", "ao", "ele", "das", "tem", "seu", "sua", "ou", "ser", "quando", "muito", "nos", "já", "está", "eu"}

# ============================================================
# BUSCAR TICKETS DA ÚLTIMA SEMANA
# ============================================================
hoje = datetime.now()
sete_dias_atras = hoje - timedelta(days=7)
data_filtro = sete_dias_atras.strftime("%Y-%m-%dT00:00:00Z")

url_tickets = "https://api.movidesk.com/public/v1/tickets"
params = {
    "token": MOVIDESK_TOKEN,
    "$filter": f"createdDate ge {data_filtro}",
    "$select": "subject,service,category"
}

response = requests.get(url_tickets, params=params)
tickets = response.json() if response.ok else []

# ============================================================
# PROCESSAMENTO DE DADOS
# ============================================================
categorias = Counter()
servicos = Counter()
palavras = Counter()

def limpar_texto(texto):
    texto = texto.lower()
    # Remove caracteres especiais
    texto = re.sub(r'[^a-z0-9\s]', '', texto)
    return texto.split()

for t in tickets:
    cat = t.get("category") or "Sem Categoria"
    svc = t.get("service") or "Sem Serviço"
    sub = t.get("subject", "")

    categorias[cat] += 1
    servicos[svc] += 1
    
    # Processar palavras do assunto
    for palavra in limpar_texto(sub):
        if palavra not in STOPWORDS and len(palavra) > 3:
            palavras[palavra] += 1

# ============================================================
# MONTAGEM DO HTML
# ============================================================
def criar_tabela(titulo, contador):
    html = f"<h3>{titulo}</h3><table style='width:100%; border-collapse:collapse; margin-bottom:20px;'>"
    html += "<tr><th style='text-align:left; border-bottom:2px solid #ddd;'>Item</th><th style='text-align:right; border-bottom:2px solid #ddd;'>Qtd</th></tr>"
    for item, qtd in contador.most_common(10): # Top 10
        html += f"<tr><td style='padding:5px 0;'>{html.escape(str(item))}</td><td style='text-align:right;'>{qtd}</td></tr>"
    html += "</table>"
    return html

html_body = f"""
<h1>Relatório Semanal de Gargalos ({sete_dias_atras.strftime('%d/%m')} a {hoje.strftime('%d/%m')})</h1>
{criar_tabela("Top Categorias", categorias)}
{criar_tabela("Top Serviços", servicos)}
{criar_tabela("Palavras-Chave Frequentes (Assuntos)", palavras)}
"""

# ============================================================
# ENVIO DO E-MAIL
# ============================================================
msg = MIMEMultipart()
msg["From"] = EMAIL_USER
msg["To"] = ", ".join(EMAIL_TO)
msg["Subject"] = f"📊 Relatório Semanal: Assuntos Frequentes ({hoje.strftime('%d/%m')})"
msg.attach(MIMEText(html_body, "html", "utf-8"))

with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
    server.login(EMAIL_USER, EMAIL_PASSWORD)
    server.sendmail(EMAIL_USER, EMAIL_TO, msg.as_string())